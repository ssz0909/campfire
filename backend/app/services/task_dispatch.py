def dispatch_task(db, task, user, background_tasks=None):
    """Persist queued before dispatch, never overwrite the worker's result."""
    from app.config import settings
    from app.models.task import OperationTask
    task = db.query(OperationTask).filter_by(id=task.id, company_id=task.company_id).with_for_update().populate_existing().one()
    if task.status != 'pending':
        db.commit()
        return
    if not user or not user.is_active:
        task.status = 'failed'
        task.error_message = '任务发起用户已失效'
        db.commit()
        return
    task.status = "queued"
    db.commit()
    if settings.TASK_EXECUTION_MODE == "inline":
        if background_tasks is not None:
            # Use a fresh session after sending the HTTP response.
            background_tasks.add_task(_execute_inline, task.id)
        else:
            from app.agent.runtime import AgentRuntime
            from app.core.tenant_context import TenantContext
            from app.core.permissions import get_user_permissions
            AgentRuntime(db).execute_task(task.id, TenantContext(
                user, task.company_id, get_user_permissions(user.id, task.company_id, db),
            ))
    else:
        try:
            from app.worker.tasks.agent_tasks import execute_operation_task
            result = execute_operation_task.delay(str(task.id))
            # A worker may already have started; update only the queue identifier.
            db.refresh(task)
            task.celery_task_id = result.id
            db.commit()
        except Exception:
            db.rollback()
            db.refresh(task)
            task.status = "failed"
            task.error_message = "队列提交失败，请确认 Redis 和 Celery 已启动后重试"
            db.commit()
    db.refresh(task)


def _execute_inline(task_id):
    """Execute a persisted task after the response using a fresh session."""
    import logging
    from app.database import SessionLocal
    from app.models.task import OperationTask
    from app.models.user import User
    from app.agent.runtime import AgentRuntime
    from app.core.tenant_context import TenantContext
    from app.core.permissions import get_user_permissions

    with SessionLocal() as db:
        try:
            task = db.get(OperationTask, task_id)
            if not task or task.status != 'queued':
                return
            user = db.get(User, task.created_by)
            if not user or not user.is_active:
                task.status = 'failed'
                task.error_message = '任务发起用户已失效'
                db.commit()
                return
            AgentRuntime(db).execute_task(task.id, TenantContext(
                user, task.company_id, get_user_permissions(user.id, task.company_id, db),
            ))
        except Exception:
            db.rollback()
            logging.getLogger(__name__).exception('Background task execution failed: %s', task_id)
            task = db.get(OperationTask, task_id)
            if task and task.status in ('queued', 'running'):
                task.status = 'failed'
                task.error_message = '后台执行异常，请重新执行或联系管理员查看日志'
                db.commit()
