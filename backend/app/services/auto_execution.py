"""Explicit task-level consent; reuse normal review and publication invariants."""
from fastapi import HTTPException


def enabled(task):
    return (task.input_params or {}).get('auto_execute') is True


def require_authority(db, company_id, user_id):
    from app.core.permissions import get_user_permissions, Permission
    from app.models.user import User
    user = db.get(User, user_id)
    required = {Permission.TASK_EXECUTE, Permission.APPROVAL_APPROVE,
                Permission.VIDEO_CREATE, Permission.PUBLISH_EXECUTE}
    if not user or not user.is_active or user.is_deleted or not required <= get_user_permissions(user_id, company_id, db):
        raise HTTPException(403, '全流程自动执行需要任务执行、审批、视频制作及平台发布权限')


def approve_task(db, task):
    if not enabled(task) or task.status != 'waiting_approval':
        return
    require_authority(db, task.company_id, task.created_by)
    from uuid import UUID
    from app.services.approval_service import ApprovalService
    ApprovalService(db).approve(task.company_id, UUID(task.output['approval_id']),
                               task.created_by, '按任务设置全流程自动通过')


def approve_video(db, project):
    if project.project_status != 'pending_review' or not project.output_asset_id or not project.task_id:
        return
    from app.models.task import OperationTask
    source = db.query(OperationTask).filter_by(id=project.task_id, company_id=project.company_id).first()
    if not source or not enabled(source):
        return
    from app.services.execution_loop import assert_active
    assert_active(db, source)
    require_authority(db, source.company_id, source.created_by)
    from app.services.video_service import VideoService
    project.quality_check_result = {**(project.quality_check_result or {}), 'review_mode': 'auto_execute'}
    VideoService(db).approve_project(project.company_id, project.id, source.created_by)
    from app.services.execution_loop import dispatch_queued_publications
    dispatch_queued_publications(db, project.id)
