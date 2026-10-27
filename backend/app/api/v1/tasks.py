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
    task = TaskService(db).create_task(company_id, current_user.id, data)
    dispatch_task(db, task, current_user)
    return task


@router.get("/{company_id}/tasks", response_model=PaginatedResponse[TaskResponse])
def list_tasks(
    company_id: uuid.UUID,
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission(Permission.TASK_VIEW)),
    db: Session = Depends(get_db),
):
    items, total = TaskService(db).list_tasks(company_id, status, page, page_size)
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
