from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.models.task import OperationTask
from app.schemas.task import TaskCreate, TaskCostResponse, TaskResponse
from app.services.task_service import TaskService
from app.utils.pagination import PaginatedResponse

router = APIRouter()

class ContinueExecution(BaseModel):
    publish_platforms: list[str] = Field(default_factory=list, max_length=2)


class ScheduleState(BaseModel):
    enabled: bool


@router.put('/{company_id}/tasks/{tid}/schedule', response_model=TaskResponse)
def set_schedule_state(company_id: uuid.UUID, tid: uuid.UUID, data: ScheduleState,
    _: User = Depends(require_permission(Permission.TASK_EXECUTE)), db: Session = Depends(get_db)):
    from fastapi import HTTPException
    from app.config import settings
    from app.services.execution_automation import _next_schedule_at
    TaskService(db).get_task(company_id, tid)
    task = db.query(OperationTask).filter_by(id=tid, company_id=company_id).with_for_update().populate_existing().one()
    schedule = dict((task.input_params or {}).get('schedule') or {})
    if not schedule or task.status not in ('scheduled', 'paused', 'cancelled'):
        raise HTTPException(400, '此任务不是定时任务模板')
    if data.enabled and not settings.EXECUTION_AUTOMATION_ENABLED:
        raise HTTPException(400, '服务端定时调度未启用，请联系管理员开启 EXECUTION_AUTOMATION_ENABLED')
    schedule['enabled'] = data.enabled
    schedule.pop('last_error', None)
    if data.enabled: schedule['next_run_at'] = _next_schedule_at(schedule).isoformat()
    task.input_params = {**(task.input_params or {}), 'schedule': schedule}
    task.status = 'scheduled' if data.enabled else 'paused'
    db.commit(); db.refresh(task)
    return task


@router.get('/{company_id}/tasks/{tid}/execution')
def execution_status(company_id: uuid.UUID, tid: uuid.UUID,
    _: User = Depends(require_permission(Permission.TASK_VIEW)), db: Session = Depends(get_db)):
    from app.services.execution_loop import snapshot
    return snapshot(db, TaskService(db).get_task(company_id, tid))


@router.post('/{company_id}/tasks/{tid}/execution/continue')
def continue_execution(company_id: uuid.UUID, tid: uuid.UUID, data: ContinueExecution,
    current_user: User = Depends(require_permission(Permission.TASK_EXECUTE)), db: Session = Depends(get_db)):
    from app.services.execution_loop import continue_loop, snapshot
    TaskService(db).get_task(company_id, tid)
    root = db.query(OperationTask).filter_by(id=tid, company_id=company_id).with_for_update().one()
    created = continue_loop(db, root, data.publish_platforms)
    for task in created:
        dispatch_task(db, task, db.get(User, task.created_by))
    return snapshot(db, root)


@router.post("/{company_id}/tasks", response_model=TaskResponse, status_code=201)
def create_task(
    company_id: uuid.UUID,
    data: TaskCreate,
    current_user: User = Depends(require_permission(Permission.TASK_CREATE)),
    db: Session = Depends(get_db),
):
    if data.schedule:
        from app.config import settings
        from app.core.permissions import PermissionChecker
        from fastapi import HTTPException
        PermissionChecker(db).require(current_user, company_id, Permission.TASK_EXECUTE)
        if not settings.EXECUTION_AUTOMATION_ENABLED:
            raise HTTPException(400, '服务端定时调度未启用，请联系管理员开启 EXECUTION_AUTOMATION_ENABLED')
    task = TaskService(db).create_task(company_id, current_user.id, data)
    dispatch_task(db, task, current_user)
    return task


@router.get("/{company_id}/tasks", response_model=PaginatedResponse[TaskResponse])
def list_tasks(
    company_id: uuid.UUID,
    status: str | None = Query(None),
    schedule_template_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission(Permission.TASK_VIEW)),
    db: Session = Depends(get_db),
):
    items, total = TaskService(db).list_tasks(company_id, status, page, page_size, schedule_template_id)
    return PaginatedResponse.create(items, total, page, page_size)


@router.get("/{company_id}/tasks/{tid}", response_model=TaskResponse)
def get_task(
    company_id: uuid.UUID,
    tid: uuid.UUID,
    _: User = Depends(require_permission(Permission.TASK_VIEW)),
    db: Session = Depends(get_db),
):
    return TaskService(db).get_task(company_id, tid)


@router.post("/{company_id}/tasks/{tid}/cancel", response_model=TaskResponse)
def cancel_task(
    company_id: uuid.UUID,
    tid: uuid.UUID,
    _: User = Depends(require_permission(Permission.TASK_EXECUTE)),
    db: Session = Depends(get_db),
):
    return TaskService(db).cancel_task(company_id, tid)


@router.post("/{company_id}/tasks/{tid}/retry", response_model=TaskResponse)
def retry_task(
    company_id: uuid.UUID,
    tid: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.TASK_EXECUTE)),
    db: Session = Depends(get_db),
):
    task = TaskService(db).retry_task(company_id, tid)
    dispatch_task(db, task, current_user)
    return task


@router.get("/{company_id}/tasks/{tid}/cost", response_model=TaskCostResponse)
def get_task_cost(
    company_id: uuid.UUID,
    tid: uuid.UUID,
    _: User = Depends(require_permission(Permission.COST_VIEW)),
    db: Session = Depends(get_db),
):
    return TaskService(db).get_task_cost(company_id, tid)



from app.services.task_dispatch import dispatch_task
