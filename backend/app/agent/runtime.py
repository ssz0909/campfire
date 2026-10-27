from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agent.tool_registry import tool_registry
from app.core.tenant_context import TenantContext
from app.models.cost import CostRecord
from app.models.task import OperationTask


class AgentRuntime:
    """
    Executes an OperationTask by running the appropriate LangGraph workflow.
    Handles budget checks, approval pauses, cost recording, and status updates.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def execute_task(
        self,
        task_id: uuid.UUID,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        task = self._load_task(task_id, tenant_context.require_company())
        if task.status not in ("pending", "queued"):
            return {"status": task.status}
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        self._append_log(task, "info", "开始执行任务")
        self.db.commit()
        try:
            from app.services.execution_loop import enabled, assert_active
            if enabled(task):
                assert_active(self.db, task)
            self._validate_budget(task)
            from app.agent.workflows.operations import OperationsWorkflow
            result = OperationsWorkflow().run(task, tenant_context, self.db, self)
            from app.agent.workflows.llm_draft import enrich
            from app.models.company import Company
            company = self.db.get(Company, task.company_id)
            result = enrich(result, task, self, company.marketing_forbidden_words)
            from app.services.execution_loop import actions_for, enabled, assert_active
            if enabled(task):
                assert_active(self.db, task)
            result = actions_for(task, result)
            # Refresh to respect cancellation by another request/worker.
            self.db.refresh(task, ["status"])
            if task.status == "cancelled":
                return {"status": "cancelled"}
            task.output = result
            from app.models.approval import Approval
            approval = Approval(
                company_id=task.company_id, requested_by=task.created_by,
                resource_type="operation_task", resource_id=str(task.id),
                action=("审核视频脚本并启动模型生成（产生费用）" if result['role'] == 'video_producer' else "审核任务草稿并派发后续任务"), description=task.title,
                details={"task_type": task.task_type, "employee_name": result["employee_name"]},
                status="pending",
            )
            self.db.add(approval)
            self.db.flush()
            task.output = {**result, "approval_id": str(approval.id)}
            task.status = "waiting_approval"
            task.progress = 90
            self._append_log(task, "info", "草稿已生成，等待人工审批；未执行外部发布")
        except Exception as exc:
            self.db.rollback()
            self.db.refresh(task)
            if task.status == 'cancelled':
                return {'status':'cancelled'}
            task.status = "failed"
            task.error_message = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            self._append_log(task, "error", f"任务失败：{exc}")
        self.db.commit()
        return {"status": task.status, "output": task.output}

    def _load_task(
        self, task_id: uuid.UUID, company_id: uuid.UUID
    ) -> OperationTask:
        from fastapi import HTTPException, status as http_status

        task = (
            self.db.query(OperationTask)
            .filter(
                OperationTask.id == task_id,
                OperationTask.company_id == company_id,
            )
            .with_for_update().first()
        )
        if not task:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="Task not found"
            )
        return task

    def _validate_budget(self, task: OperationTask) -> None:
        if task.digital_employee_id:
            from app.models.digital_employee import DigitalEmployee

            employee = (
                self.db.query(DigitalEmployee)
                .filter(DigitalEmployee.id == task.digital_employee_id, DigitalEmployee.company_id == task.company_id)
                .first()
            )
            if (
                employee
                and employee.max_task_budget_cents is not None
                and task.estimated_cost_cents is not None
                and task.estimated_cost_cents > employee.max_task_budget_cents
            ):
                raise ValueError(
                    f"Estimated cost {task.estimated_cost_cents} cents exceeds "
                    f"budget limit {employee.max_task_budget_cents} cents"
                )

    def _resolve_workflow(self, task_type: str):
        from app.agent.workflows.marketing_analysis import MarketingAnalysisWorkflow
        from app.agent.workflows.video_creation import VideoCreationWorkflow
        from app.agent.workflows.base import BaseWorkflow

        workflow_map = {
            "marketing_planning": MarketingAnalysisWorkflow,
            "business_analysis": MarketingAnalysisWorkflow,
            "video_generation": VideoCreationWorkflow,
        }
        cls = workflow_map.get(task_type, BaseWorkflow)
        return cls()

    def append_log(
        self,
        task: OperationTask,
        level: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        self._append_log(task, level, message, data)
        self.db.commit()

    def _append_log(
        self,
        task: OperationTask,
        level: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        if data:
            entry["data"] = data
        if task.execution_log is None:
            task.execution_log = []
        task.execution_log = task.execution_log + [entry]

    def record_cost(
        self,
        company_id: uuid.UUID,
        task_id: uuid.UUID,
        provider: str,
        model_name: str,
        record_type: str,
        quantity: float,
        unit: str,
        unit_cost_cents: float,
        is_estimate: bool = False,
    ) -> CostRecord:
        total = quantity * unit_cost_cents
        record = CostRecord(
            company_id=company_id,
            task_id=task_id,
            provider=provider,
            model_name=model_name,
            record_type=record_type,
            quantity=quantity,
            unit=unit,
            unit_cost_cents=unit_cost_cents,
            total_cost_cents=total,
            is_estimate=is_estimate,
            requested_at=datetime.now(timezone.utc).isoformat(),
        )
        self.db.add(record)
        self.db.flush()
        return record


class ApprovalRequiredError(Exception):
    def __init__(self, operation_type: str, approval_id: uuid.UUID) -> None:
        self.operation_type = operation_type
        self.approval_id = approval_id
        super().__init__(f"Approval required for {operation_type}")
