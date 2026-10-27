from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.task import OperationTask, TaskApprovalRequest
from app.schemas.task import TaskCreate


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(
        self,
        company_id: uuid.UUID,
        created_by: uuid.UUID,
        data: TaskCreate,
    ) -> OperationTask:
        from app.models.digital_employee import DigitalEmployee
        if data.task_type not in {"business_analysis", "marketing_planning", "video_generation", "asset_analysis", "daily_report", "custom"}:
            raise HTTPException(status_code=400, detail="此任务类型尚未实现")
        if not data.title.strip():
            raise HTTPException(status_code=400, detail="请输入任务标题")
        if data.digital_employee_id:
            employee = self.db.query(DigitalEmployee).filter(
                DigitalEmployee.id == data.digital_employee_id,
                DigitalEmployee.company_id == company_id,
                DigitalEmployee.is_deleted == False,
            ).first()
            if not employee:
                raise HTTPException(status_code=404, detail="数字员工不存在")
            if not employee.is_active:
                raise HTTPException(status_code=400, detail="请先启用该数字员工")
            if not (data.input_params or {}).get("goal", "").strip():
                raise HTTPException(status_code=400, detail="请填写任务目标")
        if data.parent_task_id:
            parent = self.get_task(company_id, data.parent_task_id)
            if parent.status != "completed":
                raise HTTPException(status_code=400, detail="只能引用已经审批完成的任务")
        from app.services.execution_loop import configure
        params = configure(data.input_params, (data.input_params or {}).get('goal') or data.title)
        task = OperationTask(
            parent_task_id=data.parent_task_id,
            company_id=company_id,
            created_by=created_by,
            task_type=data.task_type,
            title=data.title,
            description=data.description,
            digital_employee_id=data.digital_employee_id,
            input_params=params,
            status="pending",
            progress=0,
            execution_log=[],
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_task(self, company_id: uuid.UUID, task_id: uuid.UUID) -> OperationTask:
        task = (
            self.db.query(OperationTask)
            .filter(
                OperationTask.id == task_id,
                OperationTask.company_id == company_id,
            )
            .first()
        )
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
            )
        return task

    def list_tasks(
        self,
        company_id: uuid.UUID,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[OperationTask], int]:
        query = self.db.query(OperationTask).filter(
            OperationTask.company_id == company_id
        )
        if status_filter:
            query = query.filter(OperationTask.status == status_filter)
        query = query.order_by(OperationTask.created_at.desc())
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def cancel_task(self, company_id: uuid.UUID, task_id: uuid.UUID) -> OperationTask:
        task = self.get_task(company_id, task_id)
        from app.services.execution_loop import enabled
        if task.status in ("failed", "cancelled") or (task.status == 'completed' and not (enabled(task) and not task.parent_task_id)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel task in status '{task.status}'",
            )
        from app.models.approval import Approval
        self.db.query(Approval).filter(
            Approval.company_id == company_id,
            Approval.resource_type == "operation_task",
            Approval.resource_id == str(task.id), Approval.status == "pending",
        ).update({"status": "expired"}, synchronize_session=False)
        task.status = "cancelled"
        task.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(task)
        return task

    def retry_task(self, company_id: uuid.UUID, task_id: uuid.UUID) -> OperationTask:
        task = self.get_task(company_id, task_id)
        if task.status not in ("failed", "cancelled"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only failed or cancelled tasks can be retried",
            )
        if task.retry_count >= task.max_retries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task has exceeded maximum retry count",
            )
        task.status = "pending"
        task.progress = 0
        task.output = None
        task.celery_task_id = None
        task.retry_count += 1
        task.error_message = None
        task.started_at = None
        task.completed_at = None
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_task_cost(
        self, company_id: uuid.UUID, task_id: uuid.UUID
    ) -> dict:
        task = self.get_task(company_id, task_id)
        from app.models.cost import CostRecord
        records = (
            self.db.query(CostRecord)
            .filter(
                CostRecord.task_id == task_id,
                CostRecord.company_id == company_id,
            )
            .all()
        )
        return {
            "task_id": task.id,
            "estimated_cost_cents": task.estimated_cost_cents,
            "actual_cost_cents": task.actual_cost_cents,
            "cost_records": [
                {
                    "id": str(r.id),
                    "provider": r.provider,
                    "model_name": r.model_name,
                    "record_type": r.record_type,
                    "quantity": float(r.quantity),
                    "unit": r.unit,
                    "total_cost_cents": float(r.total_cost_cents),
                    "is_estimate": r.is_estimate,
                }
                for r in records
            ],
        }
