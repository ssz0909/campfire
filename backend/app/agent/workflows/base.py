from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant_context import TenantContext
from app.models.task import OperationTask


class BaseWorkflow:
    """
    Default fallback workflow. Logs the task parameters and marks it complete.
    Subclass and override `run` for domain-specific workflows.
    """

    def run(
        self,
        task: OperationTask,
        tenant_context: TenantContext,
        db: Session,
        runtime: Any,
    ) -> dict[str, Any]:
        runtime._append_log(task, "info", f"Running base workflow for task type: {task.task_type}")
        params = task.input_params or {}
        task.progress = 100
        db.commit()
        return {
            "task_type": task.task_type,
            "input_params": params,
            "status": "completed",
            "note": f"No specialised workflow registered for task type '{task.task_type}'.",
        }
