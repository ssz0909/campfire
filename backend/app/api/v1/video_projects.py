from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.video_project import (
    VideoProjectCreate,
    VideoProjectResponse,
    VideoProjectUpdate,
    StoryboardUpdate,
    ShotRegenerateRequest,
    MusicSettings,
)
from app.services.video_service import VideoService
from app.utils.pagination import PaginatedResponse

router = APIRouter()

def _with_output_preview(project, db):
    data = VideoProjectResponse.model_validate(project).model_dump()
    from app.services.execution_loop import publication_copy, root_task
    from app.models.task import OperationTask
    copy = (project.quality_check_result or {}).get('approved_publication') or publication_copy(db, project)
    data['publish_title'], data['publish_description'] = copy['title'], copy['description']
    source = db.query(OperationTask).filter_by(id=project.task_id, company_id=project.company_id).first() if project.task_id else None
    if source:
        data['publish_platforms'] = (root_task(db, source).input_params or {}).get('publish_platforms', [])
    if project.output_asset_id:
        from app.models.asset import Asset
        from app.schemas.asset import AssetResponse
        asset = db.query(Asset).filter_by(id=project.output_asset_id, company_id=project.company_id, is_deleted=False).first()
        if asset:
            media = AssetResponse.model_validate(asset).model_dump(mode='json')
            data['output_thumbnail_url'] = media['thumbnail_url']
            data['output_video_url'] = media['file_url']
    return data


@router.post("/{company_id}/video-projects", response_model=VideoProjectResponse, status_code=201)
def create_project(
    company_id: uuid.UUID,
    data: VideoProjectCreate,
    current_user: User = Depends(require_permission(Permission.VIDEO_CREATE)),
    db: Session = Depends(get_db),
):
    return VideoService(db).create_project(company_id, current_user.id, data)


@router.get("/{company_id}/video-projects", response_model=PaginatedResponse[VideoProjectResponse])
def list_projects(
    company_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission(Permission.VIDEO_VIEW)),
    db: Session = Depends(get_db),
):
    items, total = VideoService(db).list_projects(company_id, page, page_size)
    return PaginatedResponse.create([_with_output_preview(item, db) for item in items], total, page, page_size)


@router.get("/{company_id}/video-projects/{pid}", response_model=VideoProjectResponse)
def get_project(
    company_id: uuid.UUID,
    pid: uuid.UUID,
    _: User = Depends(require_permission(Permission.VIDEO_VIEW)),
    db: Session = Depends(get_db),
):
    return _with_output_preview(VideoService(db).get_project(company_id, pid), db)


@router.put("/{company_id}/video-projects/{pid}", response_model=VideoProjectResponse)
def update_project(
    company_id: uuid.UUID,
    pid: uuid.UUID,
    data: VideoProjectUpdate,
    _: User = Depends(require_permission(Permission.VIDEO_CREATE)),
    db: Session = Depends(get_db),
):
    return VideoService(db).update_project(company_id, pid, data)


@router.post("/{company_id}/video-projects/{pid}/start", response_model=VideoProjectResponse)
def start_generation(
    company_id: uuid.UUID,
    pid: uuid.UUID,
    _: User = Depends(require_permission(Permission.VIDEO_CREATE)),
    db: Session = Depends(get_db),
):
    return VideoService(db).start_generation(company_id, pid)


@router.post("/{company_id}/video-projects/{pid}/retry", response_model=VideoProjectResponse)
def retry_generation(
    company_id: uuid.UUID,
    pid: uuid.UUID,
    _: User = Depends(require_permission(Permission.VIDEO_CREATE)),
    db: Session = Depends(get_db),
):
    return VideoService(db).start_generation(company_id, pid, retry=True)


@router.post("/{company_id}/video-projects/{pid}/approve", response_model=VideoProjectResponse)
def approve_project(
    company_id: uuid.UUID,
    pid: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permission(Permission.APPROVAL_APPROVE)),
    db: Session = Depends(get_db),
):
    project = VideoService(db).approve_project(company_id, pid, current_user.id)
    from app.services.execution_loop import publish_approved_project
    background_tasks.add_task(publish_approved_project, project.id)
    return project


@router.post('/{company_id}/video-projects/{pid}/music', response_model=VideoProjectResponse)
def replace_music(company_id: uuid.UUID, pid: uuid.UUID, data: MusicSettings,
    current_user: User = Depends(require_permission(Permission.VIDEO_CREATE)), db: Session = Depends(get_db)):
    project = VideoService(db).replace_music(company_id,pid,current_user.id,data)
    return _with_output_preview(project,db)


@router.get("/{company_id}/video-projects/{pid}/storyboard")
def get_storyboard(
    company_id: uuid.UUID,
    pid: uuid.UUID,
    _: User = Depends(require_permission(Permission.VIDEO_VIEW)),
    db: Session = Depends(get_db),
):
    project = VideoService(db).get_project(company_id, pid)
    return {"storyboard": project.storyboard or []}


@router.put("/{company_id}/video-projects/{pid}/storyboard")
def update_storyboard(
    company_id: uuid.UUID,
    pid: uuid.UUID,
    data: StoryboardUpdate,
    _: User = Depends(require_permission(Permission.VIDEO_CREATE)),
    db: Session = Depends(get_db),
):
    project = VideoService(db).update_storyboard(company_id, pid, data)
    return {"storyboard": project.storyboard or []}


@router.post("/{company_id}/video-projects/{pid}/shots/{shot_num}/regenerate")
def regenerate_shot(
    company_id: uuid.UUID,
    pid: uuid.UUID,
    shot_num: int,
    data: ShotRegenerateRequest,
    _: User = Depends(require_permission(Permission.VIDEO_CREATE)),
    db: Session = Depends(get_db),
):
    project = VideoService(db).regenerate_shot(
        company_id, pid, shot_num, data.reason, data.updated_description
    )
    storyboard = project.storyboard or []
    shot = next((s for s in storyboard if s.get("shot_number") == shot_num), None)
    return {"shot": shot, "project_status": project.project_status}
