"""Persisted, bounded metrics collection for explicitly approved publications."""
import logging
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import text
from app.models.publishing import PublishJob

log = logging.getLogger(__name__)


def _next_schedule_at(schedule, now=None):
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(str(schedule.get('timezone') or 'Asia/Shanghai'))
    local_now = now.astimezone(tz)
    hour, minute = [int(x) for x in str(schedule.get('time', '09:00')).split(':', 1)]
    frequency = schedule.get('frequency', 'daily')
    weekdays = set(int(x) for x in (schedule.get('weekdays') or [0, 1, 2, 3, 4, 5, 6]))
    for offset in range(0, 8):
        day = local_now.date() + timedelta(days=offset)
        if frequency == 'weekly' and day.weekday() not in weekdays:
            continue
        candidate = datetime.combine(day, time(hour, minute), tzinfo=tz)
        if candidate > local_now:
            return candidate.astimezone(timezone.utc)
    return (local_now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(timezone.utc)


def _dispatch_scheduled_tasks(db, now=None):
    """Turn due schedule templates into ordinary one-shot tasks."""
    from app.models.task import OperationTask
    from app.models.user import User
    from app.models.company import Company
    from app.models.digital_employee import DigitalEmployee
    from app.core.permissions import Permission, get_user_permissions
    from app.services.task_dispatch import dispatch_task
    now = now or datetime.now(timezone.utc)
    created = 0
    def authorized(task):
        user = db.get(User, task.created_by)
        company = db.get(Company, task.company_id)
        employee = db.get(DigitalEmployee, task.digital_employee_id) if task.digital_employee_id else None
        return bool(user and user.is_active and not user.is_deleted and company and company.is_active and not company.is_deleted
                    and Permission.TASK_EXECUTE in get_user_permissions(user.id, task.company_id, db)
                    and (not task.digital_employee_id or (employee and employee.company_id == task.company_id and employee.is_active and not employee.is_deleted)))
    # Only pending rows can be safely resumed after a crash before dispatch.
    pending = db.query(OperationTask).filter(
        OperationTask.status == 'pending',
        OperationTask.input_params['schedule_template_id'].as_string().isnot(None),
    ).all()
    for run in pending:
        if (run.input_params or {}).get('schedule_template_id'):
            if not authorized(run):
                run.status = 'failed'
                run.error_message = '定时任务发起人权限、企业或员工状态已失效'
                run.completed_at = now
                db.commit()
                continue
            dispatch_task(db, run, db.get(User, run.created_by))
    templates = db.query(OperationTask).filter(OperationTask.status == 'scheduled').all()
    for template in templates:
        schedule = dict((template.input_params or {}).get('schedule') or {})
        if not schedule.get('enabled'):
            continue
        due_text = schedule.get('next_run_at')
        try:
            due = datetime.fromisoformat(str(due_text).replace('Z', '+00:00')) if due_text else _next_schedule_at(schedule, now)
            if due.tzinfo is None: due = due.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, KeyError, ZoneInfoNotFoundError):
            log.error('Invalid schedule configuration for task %s', template.id)
            continue
        if due > now:
            continue
        # Lock and advance before dispatching so a slow inline execution cannot duplicate a run.
        locked = db.query(OperationTask).filter_by(id=template.id).with_for_update().populate_existing().one()
        current = dict((locked.input_params or {}).get('schedule') or {})
        if locked.status != 'scheduled' or current.get('next_run_at') != due_text:
            db.commit()
            continue
        current['last_run_at'] = now.isoformat()
        current['next_run_at'] = _next_schedule_at(current, now).isoformat()
        user = db.get(User, locked.created_by)
        if not authorized(locked):
            current.update(enabled=False, last_error='发起人权限、企业或员工状态已失效，请检查后恢复计划')
            locked.status = 'paused'
            locked.input_params = {**(locked.input_params or {}), 'schedule': current}
            db.commit()
            continue
        overlapping = db.query(OperationTask).filter(
            OperationTask.company_id == locked.company_id,
            OperationTask.status.in_(['pending', 'queued', 'running']),
            OperationTask.input_params['schedule_template_id'].as_string() == str(locked.id),
        ).first()
        if overlapping:
            current['last_error'] = '上一轮仍在执行，本次已跳过，等待下一计划时间'
            locked.input_params = {**(locked.input_params or {}), 'schedule': current}
            db.commit()
            continue
        current.pop('last_error', None)
        locked.input_params = {**(locked.input_params or {}), 'schedule': current}
        run_params = {k: v for k, v in (locked.input_params or {}).items() if k != 'schedule'}
        run = OperationTask(company_id=locked.company_id, created_by=locked.created_by,
            digital_employee_id=locked.digital_employee_id, task_type=locked.task_type,
            title=locked.title,
            description=locked.description, input_params=run_params, status='pending',
            progress=0, execution_log=[], max_retries=locked.max_retries)
        run.input_params = {**run_params, 'schedule_template_id': str(locked.id), 'scheduled_for': due.isoformat()}
        db.add(run); db.flush()
        current['last_task_id'] = str(run.id)
        locked.input_params = {**(locked.input_params or {}), 'schedule': current}
        db.commit(); db.refresh(run)
        try:
            dispatch_task(db, run, user)
            created += 1
        except Exception:
            db.rollback()
            log.exception('Scheduled task dispatch failed for template %s', locked.id)
    return created


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
                _dispatch_scheduled_tasks(db)
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
        try:
            tick()
        except Exception:
            log.exception('Initial execution scheduler tick failed')
        while not stop.wait(60):
            try:tick()
            except Exception:log.exception('Execution metrics scheduler failed')
    thread=Thread(target=run, name='execution-feedback', daemon=True)
    thread.start()
    return stop
