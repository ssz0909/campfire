from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.video_project import VideoProject, ProviderTask
from app.schemas.video_project import (
    VideoProjectCreate,
    VideoProjectUpdate,
    StoryboardUpdate,
)


class VideoService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_project(
        self,
        company_id: uuid.UUID,
        created_by: uuid.UUID,
        data: VideoProjectCreate,
    ) -> VideoProject:
        values=data.model_dump()
        if values.get('reference_asset_id') and not values.get('selected_asset_ids'):
            values['selected_asset_ids']=[values['reference_asset_id']]
        values['selected_asset_ids']=[str(v) for v in self._validate_selected_assets(company_id,values.get('selected_asset_ids') or [])]
        values['target_duration_seconds'] = values.get('target_duration_seconds') or 30
        if values.get('reference_asset_id') and values['reference_asset_id'] not in [uuid.UUID(v) for v in values['selected_asset_ids']]:
            raise HTTPException(422,'首帧图片必须包含在本项目已选素材中')
        if not values.get('reference_asset_id') and values['selected_asset_ids']:
            values['reference_asset_id']=uuid.UUID(values['selected_asset_ids'][0])
        project = VideoProject(
            company_id=company_id,
            created_by=created_by,
            **values,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def list_projects(
        self,
        company_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[VideoProject], int]:
        query = (
            self.db.query(VideoProject)
            .filter(
                VideoProject.company_id == company_id,
                VideoProject.is_deleted == False,
            )
            .order_by(VideoProject.created_at.desc())
        )
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_project(
        self, company_id: uuid.UUID, project_id: uuid.UUID
    ) -> VideoProject:
        project = (
            self.db.query(VideoProject)
            .filter(
                VideoProject.id == project_id,
                VideoProject.company_id == company_id,
                VideoProject.is_deleted == False,
            )
            .first()
        )
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video project not found",
            )
        return project

    def update_project(
        self,
        company_id: uuid.UUID,
        project_id: uuid.UUID,
        data: VideoProjectUpdate,
    ) -> VideoProject:
        project = self.get_project(company_id, project_id)
        updates=data.model_dump(exclude_unset=True)
        if any(key in updates for key in ('selected_asset_ids','target_duration_seconds','aspect_ratio')):
            if project.project_status!='draft':raise HTTPException(409,'只能在生成前调整分镜、时长和素材')
            project.storyboard=None
        if 'selected_asset_ids' in updates:
            if project.project_status!='draft':raise HTTPException(409,'只能在生成前调整素材；已提交或完成的视频需另建项目')
            updates['selected_asset_ids']=[str(v) for v in self._validate_selected_assets(company_id,updates['selected_asset_ids'] or [])]
            project.reference_asset_id=uuid.UUID(updates['selected_asset_ids'][0]) if updates['selected_asset_ids'] else None
            updates['target_duration_seconds'] = updates.get('target_duration_seconds') or project.target_duration_seconds or 30
        for field, value in updates.items():
            setattr(project, field, value)
        self.db.commit()
        self.db.refresh(project)
        return project

    def _validate_selected_assets(self,company_id,asset_ids):
        from app.models.asset import Asset
        ids=list(dict.fromkeys(uuid.UUID(str(v)) for v in asset_ids))
        if len(ids)>40:raise HTTPException(422,'15至60秒视频最多选择40张候选图片')
        if not ids:return []
        assets=self.db.query(Asset).filter(Asset.company_id==company_id,Asset.id.in_(ids),
            Asset.asset_type=='image',Asset.is_deleted==False,Asset.is_available==True,
            Asset.processing_status=='ready').all()
        if len(assets)!=len(ids):raise HTTPException(422,'只能选择本企业已处理完成且可用的图片素材')
        return ids

    def start_generation(
        self, company_id: uuid.UUID, project_id: uuid.UUID, *, retry: bool = False
    ) -> VideoProject:
        project = self.db.query(VideoProject).filter(
            VideoProject.id == project_id, VideoProject.company_id == company_id,
            VideoProject.is_deleted == False,
        ).with_for_update().first()
        if not project:
            raise HTTPException(status_code=404, detail="Video project not found")
        if project.project_status not in ("draft", "failed", "cancelled"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot start project in status '{project.project_status}'",
            )
        if retry and project.project_status != 'failed':
            raise HTTPException(409, '只有失败的视频项目可以重新执行')
        if project.project_status == 'failed' and not retry:
            raise HTTPException(409, '请使用重新执行入口重试失败项目')
        if retry:
            from app.services.video_generation import _active, _active_lock
            with _active_lock:
                if str(project.id) in _active:
                    raise HTTPException(409, '上次执行尚在结束，请稍后重新执行')
        from app.services.video_generation import provider, enqueue
        if project.task_id:
            from app.models.task import OperationTask
            from app.services.execution_loop import enabled, assert_active
            source=self.db.query(OperationTask).filter_by(id=project.task_id, company_id=company_id).first()
            if source and enabled(source): assert_active(self.db,source)
        try:
            provider()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if project.creation_mode not in ("prompt_to_video", "ai_creative", "reference_inspired", "reference_inspired_video"):
            raise HTTPException(status_code=400, detail="不支持的视频创建模式")
        from app.services.video_generation import reference_url
        try:
            self._validate_selected_assets(company_id,project.selected_asset_ids or [])
            if project.selected_asset_ids and not project.reference_asset_id:
                project.reference_asset_id=uuid.UUID(str(project.selected_asset_ids[0]))
            if project.selected_asset_ids:
                for asset_id in project.selected_asset_ids:
                    reference_url(self.db, project, uuid.UUID(str(asset_id)))
            else:
                reference_url(self.db, project)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if retry:
            self._prepare_retry(project)
        if not retry and project.selected_asset_ids and not project.storyboard:
            from app.services.video_director import fallback_plan
            from app.models.asset import Asset
            ids=[uuid.UUID(str(v)) for v in project.selected_asset_ids]
            assets=self.db.query(Asset).filter(Asset.company_id==company_id,Asset.id.in_(ids)).all()
            by_id={str(a.id):a for a in assets}
            descriptors=[{'id':str(v),'name':by_id[str(v)].name,'description':((by_id[str(v)].asset_metadata or {}).get('vision_analysis') or {}).get('visual_description') or by_id[str(v)].source_description} for v in ids]
            project.target_duration_seconds=max(15,min(60,project.target_duration_seconds or 30))
            project.storyboard=fallback_plan(descriptors,project.target_duration_seconds)
        project.quality_check_result = None
        project.review_status = 'pending_review'
        project.project_status = "analyzing"
        self.db.commit()
        self.db.refresh(project)
        enqueue(project_id)
        return project

    def _prepare_retry(self, project):
        """Authorize a fresh attempt only after a definitive failure/rejection."""
        import re
        tasks = self.db.query(ProviderTask).filter_by(video_project_id=project.id,
            company_id=project.company_id).order_by(ProviderTask.created_at.desc(), ProviderTask.id.desc()).all()
        latest = {}
        for task in tasks:
            latest.setdefault(task.shot_number, task)
        note = str((project.quality_check_result or {}).get('note') or '')
        legacy_rejection = bool(re.match(r'^视频接口 HTTP (400|401|403|404|405|413|415|422|429)\b', note))
        unknown_count = sum(not task.provider_task_id and task.status not in ('rejected', 'retry_requested') for task in latest.values())
        fresh = []
        for task in latest.values():
            if task.status in ('completed', 'retry_requested'):
                continue
            if task.status == 'rejected' or (task.status == 'failed' and task.provider_task_id):
                fresh.append(task)
            elif not task.provider_task_id:
                # Old versions persisted the task before submit, losing HTTP
                # rejection status. Migrate only the one unambiguous legacy case.
                if legacy_rejection and unknown_count == 1 and task.status == 'pending':
                    task.error_message = note
                    fresh.append(task)
                else:
                    raise HTTPException(409, '上次提交结果不确定，无法安全重新执行；请先核对中转后台任务，避免重复计费')
            # A known active provider ID will be polled, never submitted again.
        for task in fresh:
            task.status = 'retry_requested'
        for task in latest.values():
            if task.provider_task_id and task.status not in ('completed', 'retry_requested'):
                task.input_params = {**(task.input_params or {}), '_retry_poll_started_at': datetime.now(timezone.utc).isoformat()}

    def approve_project(
        self,
        company_id: uuid.UUID,
        project_id: uuid.UUID,
        reviewer_id: uuid.UUID,
    ) -> VideoProject:
        project = self.db.query(VideoProject).filter_by(id=project_id, company_id=company_id, is_deleted=False).with_for_update().first()
        if not project:
            raise HTTPException(404, 'Video project not found')
        if project.project_status != "pending_review" or not project.output_asset_id:
            raise HTTPException(status_code=400, detail="视频尚未生成完成，不能批准")
        if project.task_id:
            from app.models.task import OperationTask
            from app.services.execution_loop import enabled, assert_active
            source = self.db.query(OperationTask).filter_by(id=project.task_id, company_id=company_id).first()
            if source and enabled(source):
                root = assert_active(self.db, source)
                if (root.input_params or {}).get('publish_platforms'):
                    from app.core.permissions import get_user_permissions, Permission
                    if Permission.PUBLISH_EXECUTE not in get_user_permissions(reviewer_id, company_id, self.db):
                        raise HTTPException(403, '审核后将自动发布，请由具有平台发布权限的成员审核')
        project.review_status = "approved"
        if project.project_status == "pending_review":
            project.project_status = "completed"
        from app.services.execution_loop import queue_publications, publication_copy
        project.quality_check_result = {**(project.quality_check_result or {}),
            'approved_publication':publication_copy(self.db, project), 'reviewed_by':str(reviewer_id)}
        queue_publications(self.db, project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def update_storyboard(
        self,
        company_id: uuid.UUID,
        project_id: uuid.UUID,
        data: StoryboardUpdate,
    ) -> VideoProject:
        project = self.get_project(company_id, project_id)
        if project.project_status != 'draft':
            raise HTTPException(409,'分镜提交生成后不能修改，请另建项目以免复用错误的生成任务')
        from app.services.video_director import validate_plan
        try:
            project.storyboard = validate_plan(data.storyboard,[{'id':str(v)} for v in project.selected_asset_ids or []],project.target_duration_seconds or 30)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        self.db.commit()
        self.db.refresh(project)
        return project

    def regenerate_shot(
        self,
        company_id: uuid.UUID,
        project_id: uuid.UUID,
        shot_number: int,
        reason: str | None = None,
        updated_description: str | None = None,
    ) -> VideoProject:
        project = self.get_project(company_id, project_id)
        storyboard = project.storyboard or []
        shot = next(
            (s for s in storyboard if s.get("shot_number") == shot_number), None
        )
        if not shot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shot {shot_number} not found in storyboard",
            )
        if updated_description:
            shot["description"] = updated_description
            shot["visual_description"] = updated_description
        shot["generation_status"] = "pending"
        shot["generation_task_id"] = None
        shot["output_asset_id"] = None
        shot["error"] = None
        project.storyboard = storyboard
        self.db.commit()
        self.db.refresh(project)
        return project
