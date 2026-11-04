"""Per-work analytics; never add account totals once per publication."""
from datetime import datetime, timedelta, timezone
import logging
import math
import uuid
from sqlalchemy import text
from app.models.publishing import PlatformConnection, PublishJob
from app.models.task import OperationTask
from app.core.permissions import Permission, get_user_permissions

log = logging.getLogger(__name__)
KEYS = ('views', 'likes', 'comments', 'shares')


def valid_count(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 and math.isfinite(value)


def work_values(job):
    metrics = job.metrics or {}
    data = metrics.get('work_metrics') or {}
    return {key: int(data[key]) for key in KEYS if valid_count(data.get(key))}


def summary(db, company_id, page=1, page_size=20, platform=None, task_id=None, viewer_id=None):
    query = db.query(PublishJob, PlatformConnection, OperationTask.title).join(
        PlatformConnection, (PublishJob.platform_connection_id == PlatformConnection.id) &
        (PlatformConnection.company_id == company_id)).outerjoin(
        OperationTask, (PublishJob.task_id == OperationTask.id) & (OperationTask.company_id == company_id)).filter(
        PublishJob.company_id == company_id, PublishJob.status == 'published', PublishJob.video_project_id.isnot(None))
    if platform:
        query = query.filter(PlatformConnection.platform == platform)
    if task_id:
        # A root task includes videos created by its downstream employees.
        ids = [row.id for row in db.query(OperationTask).filter(
            OperationTask.company_id == company_id,
            (OperationTask.id == task_id) | (OperationTask.input_params['execution_root_id'].as_string() == str(task_id))).all()]
        query = query.filter(PublishJob.task_id.in_(ids))
    rows = query.order_by(PublishJob.created_at.desc(), PublishJob.id.desc()).all()
    totals = {key: None for key in KEYS}
    platforms, items, seen = {}, [], set()
    preferred = {}
    for job, account, _ in rows:
        identity = (str(account.id), job.provider_post_id or str(job.id))
        previous = preferred.get(identity)
        if work_values(job) and (previous is None or str((job.metrics or {}).get('work_metrics_at', '')) > str((previous.metrics or {}).get('work_metrics_at', ''))):
            preferred[identity] = job
    for job, account, task_title in rows:
        identity = (str(account.id), job.provider_post_id or str(job.id))
        duplicate = identity in seen
        seen.add(identity)
        values = work_values(job)
        group = platforms.setdefault(account.platform, {'platform':account.platform, 'published':0, 'synced':0, **{key:None for key in KEYS}})
        if not duplicate:
            chosen_values = work_values(preferred.get(identity, job))
            group['published'] += 1
            if 'views' in chosen_values: group['synced'] += 1
            for key, value in chosen_values.items():
                totals[key] = (totals[key] or 0) + value
                group[key] = (group[key] or 0) + value
        metrics = job.metrics or {}
        items.append({'job_id':str(job.id), 'task_id':str(job.task_id) if job.task_id else None,
            'task_title':task_title, 'video_project_id':str(job.video_project_id), 'title':job.title,
            'platform':account.platform, 'account_label':account.label or account.account_name or account.platform,
            'provider_post_id':job.provider_post_id, 'published_at':job.created_at,
            **{key:values.get(key) for key in KEYS},
            'captured_at':metrics.get('work_metrics_at'),
            'sync_status':metrics.get('work_sync_status', 'not_synced'),
            'sync_message':metrics.get('work_sync_message'), 'duplicate':duplicate})
    accounts = db.query(PlatformConnection).filter_by(company_id=company_id).all()
    sync_states = []
    for account in accounts:
        account_state = (account.metrics_snapshot or {}).get('work_sync') or {}
        if not account_state and account.status in ('disconnected','authorizing','login_required'):
            account_state = {'status':'login_required','message':'请在发布平台为此账号重新登录后同步作品数据。'}
        sync_states.append({'account_id':str(account.id), 'label':account.label or account.account_name or account.platform, **account_state})
    can_sync = bool(viewer_id and Permission.PUBLISH_CREATE in get_user_permissions(viewer_id, company_id, db))
    return {'items':items[(page-1)*page_size:page*page_size], 'can_sync':can_sync, 'total':len(items),
            'published_works':sum(p['published'] for p in platforms.values()),
            'synced_works':sum(p['synced'] for p in platforms.values()),
            'totals':totals, 'platforms':list(platforms.values()), 'accounts':sync_states,
            'note':'累计作品数据，仅汇总已明确匹配的作品；未采集显示 —，同账号同作品去重。平台展示口径可能不同，不等于独立观看人数。'}


def request_sync(db, company_id):
    accounts = db.query(PlatformConnection).filter_by(company_id=company_id).all()
    now = datetime.now(timezone.utc)
    accepted = []
    for account in accounts:
        if not db.query(PublishJob.id).filter_by(company_id=company_id, platform_connection_id=account.id,
                                               status='published').filter(PublishJob.video_project_id.isnot(None)).first():
            continue
        snapshot = dict(account.metrics_snapshot or {})
        state = snapshot.get('work_sync') or {}
        started = _time(state.get('requested_at'))
        if state.get('status') in ('queued','running') and started and now-started < timedelta(minutes=15):
            continue
        if state.get('status') == 'running' and started and now-started < timedelta(hours=6):
            continue
        if started and now-started < timedelta(minutes=5):
            continue
        snapshot['work_sync'] = {'status':'queued', 'requested_at':now.isoformat()}
        account.metrics_snapshot = snapshot
        accepted.append(account.id)
    db.commit()
    return accepted


def _time(value):
    try:
        result = datetime.fromisoformat(str(value))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError): return None


def sync_account(db, company_id, account_id):
    """Claim one account across processes, then capture a bounded work-list scan."""
    from app.services.publishing_service import session_options, identity_options
    from app.connectors.web_metrics_api import read_work_metrics
    lease = None
    lock_key = uuid.UUID(str(account_id)).int % (2**63-1)
    try:
        if db.get_bind().dialect.name == 'postgresql':
            from sqlalchemy import text
            lease = db.get_bind().connect()
            if not lease.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key':lock_key}).scalar(): return
        account = db.query(PlatformConnection).filter_by(id=account_id, company_id=company_id).populate_existing().first()
        if not account: return
        snapshot = dict(account.metrics_snapshot or {})
        state = snapshot.get('work_sync') or {}
        if state.get('status') not in ('queued','running'): return
        requested = _time(state.get('requested_at'))
        now = datetime.now(timezone.utc)
        if state.get('status') == 'running' and requested and now-requested < timedelta(minutes=15): return
        state = {**state, 'status':'running', 'requested_at':now.isoformat()}
        account.metrics_snapshot = {**snapshot, 'work_sync':state}; db.commit()
        jobs = db.query(PublishJob).filter_by(company_id=company_id, platform_connection_id=account_id,
                                             status='published').filter(PublishJob.video_project_id.isnot(None)).all()
        targets = [{'job_id':str(job.id), 'post_id':job.provider_post_id, 'title':job.title,
                    'description':job.description or '', 'created_at':((job.metrics or {}).get('published_at') or job.created_at.isoformat())} for job in jobs]
        try:
            result = read_work_metrics(company_id, account.platform, targets, **session_options(account), **identity_options(account))
        except Exception as exc:
            log.exception('Platform work scan failed')
            result = {'status':'failed','items':{},'message':'平台作品页读取失败：'+type(exc).__name__}
        matches = result.get('items', {})
        matched = 0
        for job in jobs:
            item = matches.get(str(job.id))
            metrics = dict(job.metrics or {})
            values = {key:int(item[key]) for key in KEYS if item and valid_count(item.get(key))}
            if values:
                metrics.update(work_metrics=values, work_metrics_at=datetime.now(timezone.utc).isoformat(),
                               work_sync_status='synced', work_sync_message=None)
                if item.get('post_id') and not job.provider_post_id: job.provider_post_id = item['post_id']
                if item.get('created_at') is not None:
                    try:
                        timestamp = float(item['created_at'])
                        if timestamp > 10**12: timestamp /= 1000
                        metrics['published_at'] = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
                    except (TypeError, ValueError, OverflowError, OSError): pass
                matched += 1
            else:
                metrics.update(work_sync_status=(result.get('unmatched_statuses') or {}).get(str(job.id)) or (result.get('status') if result.get('status') not in ('synced','partial') else 'unmatched'),
                               work_sync_message=(result.get('unmatched_messages') or {}).get(str(job.id)) or result.get('message') or '未能唯一匹配作品，请在对应账号作品管理检查；保留上次采集值')
            job.metrics = metrics
        state.update(status=result.get('status','failed'), completed_at=datetime.now(timezone.utc).isoformat(),
                     matched=matched, total=len(jobs), message=result.get('message'),
                     record_count=result.get('record_count'), list_complete=result.get('list_complete'),
                     transport=result.get('transport'))
        account.metrics_snapshot = {**(account.metrics_snapshot or {}), 'work_sync':state}
        db.commit()
    except Exception:
        db.rollback()
        account = db.query(PlatformConnection).filter_by(id=account_id, company_id=company_id).first()
        if account:
            previous = (account.metrics_snapshot or {}).get('work_sync') or {}
            account.metrics_snapshot = {**(account.metrics_snapshot or {}), 'work_sync':{**previous,
                'status':'failed', 'completed_at':datetime.now(timezone.utc).isoformat(), 'message':'平台数据采集失败，请检查账号会话后重试'}}
            db.commit()
        log.exception('Work metrics synchronization failed for account %s', account_id)
    finally:
        if lease is not None:
            from sqlalchemy import text
            try:
                lease.rollback()
                lease.execute(text('SELECT pg_advisory_unlock(:key)'), {'key':lock_key})
            finally: lease.close()


def run_sync(company_id):
    from app.database import SessionLocal
    with SessionLocal() as db:
        accounts = db.query(PlatformConnection).filter_by(company_id=company_id).all()
        for account in accounts:
            sync_account(db, company_id, account.id)


def sync_due(db):
    """Six-hour checks, at most one account per scheduler tick."""
    now = datetime.now(timezone.utc)
    from app.models.company import Company
    accounts = db.query(PlatformConnection).join(Company, Company.id == PlatformConnection.company_id).filter(Company.is_active == True, Company.is_deleted == False).all()
    for account in accounts:
        state = (account.metrics_snapshot or {}).get('work_sync') or {}
        requested = _time(state.get('requested_at'))
        if state.get('status') == 'running' and requested and now-requested < timedelta(minutes=15): continue
        if state.get('status') != 'queued':
            if requested and now-requested < timedelta(hours=6): continue
            if not db.query(PublishJob.id).filter_by(company_id=account.company_id, platform_connection_id=account.id,
                    status='published').filter(PublishJob.video_project_id.isnot(None)).first(): continue
            account.metrics_snapshot = {**(account.metrics_snapshot or {}), 'work_sync':{
                'status':'queued','requested_at':now.isoformat()}}
            db.commit()
        sync_account(db, account.company_id, account.id)
        break
