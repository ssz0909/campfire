"""Persisted, bounded metrics collection for explicitly approved publications."""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.models.publishing import PublishJob

log = logging.getLogger(__name__)


def collect_due(db, now=None):
    from app.services.publishing_service import web_metrics
    from app.services.execution_loop import assert_active
    from app.models.task import OperationTask
    now = now or datetime.now(timezone.utc)
    ids = [j.id for j in db.query(PublishJob).filter_by(status='published').all()
           if (j.content_snapshot or {}).get('execution_root_id')
           and not (j.metrics or {}).get('feedback_task_id')
           and (j.metrics or {}).get('feedback_attempts',0)<3
           and (j.metrics or {}).get('feedback_due_at')
           and str(j.metrics['feedback_due_at'])<=now.isoformat()]
    processed = 0
    for job_id in ids[:100]:
        job = db.query(PublishJob).filter_by(id=job_id).with_for_update().first()
        if not job:
            db.commit(); continue
        metrics = dict(job.metrics or {})
        if metrics.get('feedback_task_id') or metrics.get('feedback_attempts', 0) >= 3 or not metrics.get('feedback_due_at'):
            db.commit(); continue
        try:
            due = datetime.fromisoformat(metrics['feedback_due_at']).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            db.commit(); continue
        if due > now:
            db.commit(); continue
        source = db.query(OperationTask).filter_by(id=job.task_id, company_id=job.company_id).first()
        try:
            if not source: raise ValueError('来源任务不存在')
            assert_active(db, source)
        except Exception:
            db.commit(); continue
        # Persist the attempt before touching a browser. A crash cannot hot-loop.
        metrics.update(feedback_attempts=metrics.get('feedback_attempts', 0)+1,
                       feedback_due_at=(now+timedelta(hours=1)).isoformat(),
                       feedback_state='collecting')
        job.metrics=metrics; db.commit()
        error=None
        try:
            web_metrics(db, job.company_id, job.id)
        except Exception:
            db.rollback(); error='自动数据回流失败，请检查平台登录后手动刷新数据'
            log.exception('Metrics collection failed for publish job %s', job_id)
        db.refresh(job)
        metrics=dict(job.metrics or {})
        complete=bool(metrics.get('feedback_task_id'))
        exhausted=metrics.get('feedback_attempts',0)>=3
        metrics.update(feedback_state='review_pending' if complete else 'manual_required' if exhausted else 'retry_scheduled',
                       feedback_error=None if complete else error or job.error_message or '未读取到可用指标或分析员未启用，请检查后手动刷新数据')
        job.metrics=metrics;db.commit();processed+=1
    return processed


def tick():
    from app.database import engine, SessionLocal
    # A session-level lock remains held across service commits and dispatches.
    with engine.connect() as connection:
        postgres=connection.dialect.name=='postgresql'
        locked=False
        try:
            if postgres:
                locked=bool(connection.execute(text('SELECT pg_try_advisory_lock(727431921)')).scalar())
                connection.commit()
                if not locked:return
            with SessionLocal() as db:
                from app.services.execution_loop import dispatch_queued_publications
                dispatch_queued_publications(db)
                collect_due(db)
        finally:
            if locked:
                connection.execute(text('SELECT pg_advisory_unlock(727431921)'))
                connection.commit()


def start():
    from threading import Event, Thread
    stop=Event()
    def run():
        while not stop.wait(60):
            try:tick()
            except Exception:log.exception('Execution metrics scheduler failed')
    thread=Thread(target=run, name='execution-feedback', daemon=True)
    thread.start()
    return stop
