from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.approval import Approval
from app.models.task import TaskApprovalRequest


class ApprovalService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_approvals(
        self,
        company_id: uuid.UUID,
        status_filter: str | None = "pending",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Approval], int]:
        query = self.db.query(Approval).filter(Approval.company_id == company_id)
        if status_filter:
            query = query.filter(Approval.status == status_filter)
        query = query.order_by(Approval.created_at.desc())
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_approval(
        self, company_id: uuid.UUID, approval_id: uuid.UUID
    ) -> Approval:
        approval = (
            self.db.query(Approval)
            .filter(
                Approval.id == approval_id,
                Approval.company_id == company_id,
            )
            .with_for_update().first()
        )
        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found"
            )
        return approval

    def approve(
        self,
        company_id: uuid.UUID,
        approval_id: uuid.UUID,
        reviewed_by: uuid.UUID,
        note: str | None = None,
    ) -> Approval:
        approval = self.get_approval(company_id, approval_id)
        if approval.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approval is not in pending status",
            )
        self._validate_review(approval)
        if approval.resource_type == 'publish_job':
            return self._review_publish(approval, reviewed_by, note, True)
        if approval.resource_type == 'operation_task':
            from app.services.execution_loop import enabled, assert_active
            from app.models.task import OperationTask
            target = self.db.query(OperationTask).filter_by(id=uuid.UUID(approval.resource_id), company_id=company_id).first()
            if target and enabled(target):
                assert_active(self.db, target)
            if target and (target.output or {}).get('role') == 'video_producer':
                self._require_permission(reviewed_by, company_id, 'video:create')
        self._update_task(approval, True, note)
        approval.status = "approved"
        approval.reviewed_by = reviewed_by
        approval.reviewed_at = datetime.now(timezone.utc)
        approval.review_note = note
        children, video = [], None
        if approval.resource_type == 'operation_task':
            from app.models.task import OperationTask
            from app.services.task_handoff import create_handoffs, create_video_handoff
            task = self.db.get(OperationTask, uuid.UUID(approval.resource_id))
            children = create_handoffs(self.db, task)
            if (task.output or {}).get('role') == 'video_producer':
                video = create_video_handoff(self.db, task)
        self.db.commit()
        self.db.refresh(approval)
        # Approval and handoff identities are durable before any external call.
        from app.models.user import User
        from app.services.task_dispatch import dispatch_task
        for child in children:
            dispatch_task(self.db, child, self.db.get(User, child.created_by))
        if video:
            from app.services.video_service import VideoService
            try:
                VideoService(self.db).start_generation(company_id, video.id)
            except HTTPException as exc:
                video.quality_check_result = {'status': 'blocked', 'note': str(exc.detail)}
                self.db.commit()
        return approval

    def reject(
        self,
        company_id: uuid.UUID,
        approval_id: uuid.UUID,
        reviewed_by: uuid.UUID,
        note: str | None = None,
    ) -> Approval:
        approval = self.get_approval(company_id, approval_id)
        if approval.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approval is not in pending status",
            )
        self._validate_review(approval)
        if approval.resource_type == 'publish_job':
            return self._review_publish(approval, reviewed_by, note, False)
        self._update_task(approval, False, note)
        approval.status = "rejected"
        approval.reviewed_by = reviewed_by
        approval.reviewed_at = datetime.now(timezone.utc)
        approval.review_note = note
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def _require_permission(self, user_id, company_id, name):
        from app.core.permissions import get_user_permissions
        if not any(p.value == name for p in get_user_permissions(user_id, company_id, self.db)):
            raise HTTPException(403, '当前审批人无执行该操作的权限')

    def _review_publish(self, approval, reviewer_id, note, approved):
        from app.models.publishing import PublishJob
        from app.models.video_project import VideoProject
        from app.models.task import OperationTask
        from app.services.execution_loop import assert_active
        job = self.db.query(PublishJob).filter_by(id=uuid.UUID(approval.resource_id), company_id=approval.company_id).with_for_update().first()
        if not job or job.status != 'waiting_approval':
            raise HTTPException(409, '发布任务状态已改变，请刷新')
        if approved:
            from app.core.permissions import Permission
            self._require_permission(reviewer_id, approval.company_id, Permission.PUBLISH_EXECUTE.value)
            project = self.db.query(VideoProject).filter_by(id=job.video_project_id, company_id=job.company_id, is_deleted=False).first()
            if not project or project.review_status != 'approved' or project.project_status != 'completed' or str(project.output_asset_id) != (approval.details or {}).get('asset_id'):
                raise HTTPException(409, '视频成片已变化，请重新审核')
            if job.title != (approval.details or {}).get('title') or job.description != (approval.details or {}).get('description'):
                raise HTTPException(409, '发布文案已变化，请重新审批')
            task = self.db.query(OperationTask).filter_by(id=job.task_id, company_id=job.company_id).first()
            if not task:
                raise HTTPException(409, '来源任务不存在')
            assert_active(self.db, task)
        approval.status = 'approved' if approved else 'rejected'
        approval.reviewed_by = reviewer_id
        approval.reviewed_at = datetime.now(timezone.utc)
        approval.review_note = note
        job.reviewed_by = reviewer_id
        job.status = 'queued' if approved else 'rejected'
        job.error_message = None if approved else (note or '发布审批被退回，未发布')
        self.db.commit()
        if approved:
            from app.services.publishing_service import web_publish
            try:
                web_publish(self.db, job.company_id, job.id)
            except Exception:
                self.db.rollback(); self.db.refresh(job)
                if job.status != 'published':
                    job.status = 'manual_required'
                    job.error_message = '发布未确认完成，请核对平台、登录状态与执行记录后处理，避免重复发布'
                    self.db.commit()
        self.db.refresh(approval)
        return approval


    def _validate_review(self, approval):
        if approval.expires_at:
            expires = approval.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="审批已过期")

    def _update_task(self, approval, approved, note):
        if approval.resource_type != "operation_task":
            return
        from app.models.task import OperationTask
        from app.agent.runtime import AgentRuntime
        task = self.db.query(OperationTask).filter(
            OperationTask.id == uuid.UUID(approval.resource_id),
            OperationTask.company_id == approval.company_id,
        ).with_for_update().first()
        if not task or task.status != "waiting_approval" or (task.output or {}).get("approval_id") != str(approval.id):
            raise HTTPException(status_code=409, detail="任务已取消或审批状态已改变，请刷新")
        task.status = "completed" if approved else "failed"
        task.progress = 100 if approved else 90
        task.completed_at = datetime.now(timezone.utc)
        task.error_message = None if approved else (note or "草稿被退回，请修改任务目标后重新提交")
        task.output = {**(task.output or {}), "review": {
            "status": "approved" if approved else "rejected", "note": note,
        }}
        AgentRuntime(self.db)._append_log(task, "info", "审批通过，任务完成" if approved else f"草稿被退回：{task.error_message}")
