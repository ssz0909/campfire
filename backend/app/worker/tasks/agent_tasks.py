from __future__ import annotations

import uuid

from app.worker.celery_app import celery_app
from app.database import SessionLocal
from app.models.task import OperationTask
from app.models.user import User


@celery_app.task(bind=True, name="app.worker.tasks.agent_tasks.execute_operation_task")
def execute_operation_task(self, task_id: str) -> dict:
    """
    Run the LangGraph agent workflow for an OperationTask.
    Loads task context, builds a TenantContext, and delegates to AgentRuntime.
    """
    db = SessionLocal()
    try:
        task = (
            db.query(OperationTask)
            .filter(OperationTask.id == uuid.UUID(task_id))
            .first()
        )
        if not task:
            return {"status": "error", "detail": f"Task {task_id} not found"}

        # Build a minimal TenantContext for the task owner
        user = db.query(User).filter(User.id == task.created_by).first()
        if not user:
            return {"status": "error", "detail": "Task owner not found"}

        from app.core.tenant_context import TenantContext
        from app.core.permissions import get_user_permissions

        permissions = get_user_permissions(user.id, task.company_id, db)
        tenant_context = TenantContext(
            current_user=user,
            current_company_id=task.company_id,
            permissions=permissions,
        )

        from app.agent.runtime import AgentRuntime
        runtime = AgentRuntime(db=db)
        result = runtime.execute_task(
            task_id=uuid.UUID(task_id),
            tenant_context=tenant_context,
        )
        return result
    except Exception as exc:
        # Update task status to failed
        db_inner = SessionLocal()
        try:
            t = db_inner.query(OperationTask).filter(
                OperationTask.id == uuid.UUID(task_id)
            ).first()
            if t:
                t.status = "failed"
                t.error_message = str(exc)
                db_inner.commit()
        finally:
            db_inner.close()
        raise self.retry(exc=exc, countdown=60, max_retries=2)
    finally:
        db.close()
