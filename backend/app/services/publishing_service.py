from __future__ import annotations
import secrets, uuid
from datetime import datetime, timezone
from urllib.parse import urlencode
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.config import settings
from app.core.secrets import encrypt_json, decrypt_json
from app.models.publishing import PlatformConnection, PublishJob
from app.models.task import OperationTask
from app.models.video_project import VideoProject

SUPPORTED = {"douyin", "wechat_channels"}
DISPLAY = {"douyin": "抖音", "wechat_channels": "微信视频号"}

def _config(platform):
    if platform == "douyin":
        return settings.DOUYIN_CLIENT_ID, settings.DOUYIN_CLIENT_SECRET, settings.DOUYIN_REDIRECT_URI
    return settings.WECHAT_CHANNELS_CLIENT_ID, settings.WECHAT_CHANNELS_CLIENT_SECRET, settings.WECHAT_CHANNELS_REDIRECT_URI

def get_connection(db, company_id, platform):
    if platform not in SUPPORTED: raise HTTPException(400, "不支持的发布平台")
    return db.query(PlatformConnection).filter_by(company_id=company_id, platform=platform).first()

def authorization_url(db, company_id, platform):
    client_id, _, redirect = _config(platform)
    if not client_id or not redirect:
        raise HTTPException(503, f"{DISPLAY[platform]}发布应用尚未配置，请先配置平台应用凭证")
    row = get_connection(db, company_id, platform)
    if not row:
        row = PlatformConnection(company_id=company_id, platform=platform, status="authorizing")
        db.add(row)
    state = secrets.token_urlsafe(32)
    row.encrypted_credentials = encrypt_json({"oauth_state": state})
    row.status = "authorizing"
    db.commit()
    # Provider-specific scopes and endpoint can be changed without changing tenant data model.
    if platform == "douyin":
        base = "https://open.douyin.com/platform/oauth/connect/"
        scope = "user_info,data.external.item"
    else:
        base = "https://channels.weixin.qq.com/platform/oauth2/authorize"
        scope = "channels.publish,channels.data"
    return {"platform": platform, "authorization_url": base + "?" + urlencode({"client_key": client_id, "redirect_uri": redirect, "response_type": "code", "scope": scope, "state": state}), "state": state}

def complete_authorization(db, company_id, platform, code, state, account_id=None, account_name=None):
    row = get_connection(db, company_id, platform)
    if not row or row.status != "authorizing": raise HTTPException(400, "授权会话不存在或已过期")
    saved = decrypt_json(row.encrypted_credentials or "{}")
    if not secrets.compare_digest(str(saved.get("oauth_state", "")), state): raise HTTPException(400, "授权 state 校验失败")
    client_id, secret, redirect = _config(platform)
    if not client_id or not secret: raise HTTPException(503, "平台应用密钥尚未配置")
    import httpx
    token_url = settings.DOUYIN_TOKEN_URL if platform == "douyin" else settings.WECHAT_CHANNELS_TOKEN_URL
    if not token_url:
        raise HTTPException(503, f"{DISPLAY[platform]} token 接口尚未配置")
    try:
        response = httpx.post(token_url, json={"client_key": client_id, "client_id": client_id, "client_secret": secret, "code": code, "grant_type": "authorization_code", "redirect_uri": redirect}, timeout=15)
        response.raise_for_status(); token_data = response.json()
    except Exception as exc:
        raise HTTPException(502, f"{DISPLAY[platform]}授权换 token 失败：{exc}") from exc
    access_token = token_data.get("data", {}).get("access_token") or token_data.get("access_token")
    if not access_token:
        raise HTTPException(502, f"{DISPLAY[platform]}未返回 access_token")
    row.encrypted_credentials = encrypt_json({"access_token": access_token, "refresh_token": token_data.get("data", {}).get("refresh_token") or token_data.get("refresh_token"), "expires_in": token_data.get("data", {}).get("expires_in") or token_data.get("expires_in")})
    row.status = "authorized"
    row.account_id, row.account_name = account_id, account_name
    row.authorized_at = datetime.now(timezone.utc)
    row.last_error = None
    db.commit(); db.refresh(row)
    return row

def create_publish(db, company_id, user_id, platform, data):
    row = get_connection(db, company_id, platform)
    if not row or row.status not in ('authorized', 'session_saved'): raise HTTPException(400, "请先授权登录发布平台")
    if not data.task_id and not data.video_project_id and not data.asset_ids: raise HTTPException(400, "发布必须关联已审批的任务、视频项目或素材")
    if data.task_id:
        task = db.query(OperationTask).filter_by(id=data.task_id, company_id=company_id).first()
        if not task or task.status != "completed": raise HTTPException(400, "只能发布已审批完成的任务结果")
    if data.video_project_id:
        project = db.query(VideoProject).filter_by(id=data.video_project_id, company_id=company_id).first()
        if not project or project.review_status != "approved" or project.project_status != "completed": raise HTTPException(400, "只能发布已审批完成的视频项目")
    if data.asset_ids:
        from app.models.asset import Asset
        assets = db.query(Asset).filter(Asset.id.in_(data.asset_ids), Asset.company_id == company_id, Asset.is_deleted == False, Asset.is_available == True, Asset.processing_status == "ready").all()
        if len(assets) != len(set(data.asset_ids)): raise HTTPException(400, "只能发布本企业已处理完成的素材")
    existing = db.query(PublishJob).filter_by(company_id=company_id, request_key=data.request_key).first()
    if existing: return existing
    snapshot = {"title": data.title, "description": data.description, "media_type": data.media_type, "asset_ids": [str(x) for x in data.asset_ids]}
    from app.services.execution_loop import publication_location
    snapshot['location_name'] = data.location_name or publication_location(db, company_id)
    if data.task_id:
        task = db.query(OperationTask).filter_by(id=data.task_id, company_id=company_id).first()
        snapshot["task_output"] = (task.output or {}) if task else {}
    job = PublishJob(company_id=company_id, platform_connection_id=row.id, requested_by=user_id, task_id=data.task_id, video_project_id=data.video_project_id, asset_id=(data.asset_ids[0] if data.asset_ids else None), title=data.title, description=data.description, media_url=data.media_url, status="draft", request_key=data.request_key, content_snapshot=snapshot)
    db.add(job); db.commit(); db.refresh(job)
    return job

def submit_publish(db, company_id, job_id):
    job = db.query(PublishJob).filter_by(id=job_id, company_id=company_id).first()
    if not job: raise HTTPException(404, "发布任务不存在")
    if (job.content_snapshot or {}).get('execution_root_id'):
        return web_publish(db, company_id, job_id)
    if job.status not in ("draft", "queued", "failed", "manual_required"): raise HTTPException(400, "当前发布任务不可提交")
    row = db.query(PlatformConnection).filter_by(id=job.platform_connection_id, company_id=company_id).first()
    if not row or row.status != "authorized": raise HTTPException(400, "平台授权已失效，请重新授权")
    if not job.media_url and not job.asset_id and not job.video_project_id:
        raise HTTPException(400, "缺少媒体文件")
    if not job.media_url:
        from app.models.asset import Asset
        asset_id = job.asset_id
        if not asset_id and job.video_project_id:
            asset_id = db.query(VideoProject).filter_by(id=job.video_project_id, company_id=company_id).one().output_asset_id
        asset = db.query(Asset).filter_by(id=asset_id, company_id=company_id).first() if asset_id else None
        if asset:
            job.media_url = str(__import__('pathlib').Path(settings.LOCAL_STORAGE_PATH) / asset.file_key)
    # The provider call is deliberately a separate adapter boundary. Until the
    # operator configures reviewed provider credentials/endpoints, fail closed.
    if not settings.PUBLISHING_MOCK:
        job.status = "blocked"
        job.error_message = f"{DISPLAY[row.platform]}发布接口尚未配置，已保留草稿，未向平台发送内容"
        db.commit(); db.refresh(job)
        return job
    job.status = "published"
    job.provider_post_id = f"mock-{job.id}"
    job.provider_url = f"https://{row.platform}.example.invalid/posts/{job.id}"
    job.metrics = {"source": "mock", "note": "模拟发布，不代表平台真实数据"}
    db.commit(); db.refresh(job)
    return job

def create_republish(db: Session, company_id, user_id, job_id, location_name=None):
    """Create an independent draft from a previously published video."""
    source = db.query(PublishJob).filter_by(id=job_id, company_id=company_id).first()
    if not source: raise HTTPException(404, '原发布记录不存在')
    if source.status != 'published': raise HTTPException(409, '只有已发布作品可以重新发布')
    project = db.query(VideoProject).filter_by(id=source.video_project_id, company_id=company_id, is_deleted=False).first() if source.video_project_id else None
    if not project or project.project_status != 'completed' or project.review_status != 'approved':
        raise HTTPException(409, '原视频项目必须仍处于审核通过状态')
    location = location_name or (source.content_snapshot or {}).get('location_name')
    if not location:
        from app.services.execution_loop import publication_location
        location = publication_location(db, company_id)
    key = f'republish:{source.id}:{uuid.uuid4()}'
    snapshot = {**(source.content_snapshot or {}), 'republished_from_job_id': str(source.id), 'location_name': location, 'title': source.title, 'description': source.description}
    copy = PublishJob(company_id=company_id, platform_connection_id=source.platform_connection_id, requested_by=user_id,
        task_id=source.task_id, video_project_id=source.video_project_id, asset_id=source.asset_id,
        title=source.title, description=source.description, status='draft', request_key=key, content_snapshot=snapshot)
    db.add(copy); db.commit(); db.refresh(copy); return copy


def update_metrics(db, company_id, job_id, metrics):
    job = db.query(PublishJob).filter_by(id=job_id, company_id=company_id).first()
    if not job: raise HTTPException(404, "发布任务不存在")
    if job.status != "published": raise HTTPException(400, "只有已发布内容可以回流数据")
    if any(k.startswith('feedback_') or k in ('execution_root_id','source','scope') for k in metrics):
        raise HTTPException(422, '不可覆盖工作流状态或指标来源')
    job.metrics = {**(job.metrics or {}), **metrics, "source": "platform_api", "updated_at": datetime.now(timezone.utc).isoformat()}
    db.commit(); db.refresh(job); return job


def start_web(db, company_id, platform):
    from app.connectors.web_platform import start_session
    row = get_connection(db, company_id, platform)
    if not row:
        row = PlatformConnection(company_id=company_id, platform=platform, status="authorizing")
        db.add(row); db.commit()
    try:
        from app.services.execution_loop import publication_geolocation
        geolocation = publication_geolocation(db, company_id)
        result = start_session(company_id, platform, geolocation=geolocation) if geolocation else start_session(company_id, platform)
    except RuntimeError as exc:
        row.last_error = str(exc)
        db.commit()
        raise HTTPException(503, str(exc)) from exc
    row.status = "authorizing"
    row.last_error = None
    db.commit()
    return result

def web_status(db, company_id, platform):
    from app.connectors.web_platform import session_status
    row = get_connection(db, company_id, platform)
    result = session_status(company_id, platform)
    if row:
        row.status = {"authorized": "authorized", "session_saved": "session_saved", "login_required": "authorizing"}.get(result.get("status"), "disconnected")
        if row.status == "authorized":
            row.authorized_at = row.authorized_at or datetime.now(timezone.utc)
            row.last_error = None
        db.commit()
    return result

def web_publish(db, company_id, job_id):
    job = db.query(PublishJob).filter_by(id=job_id, company_id=company_id).with_for_update().first()
    if not job: raise HTTPException(404, "发布任务不存在")
    if (job.content_snapshot or {}).get('execution_root_id'):
        from app.services.execution_loop import assert_active
        source = db.query(OperationTask).filter_by(id=job.task_id, company_id=company_id).first()
        if not source: raise HTTPException(409, '来源任务不存在')
        assert_active(db, source)
        if job.status in ('rejected', 'waiting_approval'):
            raise HTTPException(409, '发布任务尚未获准执行')
        project = db.query(VideoProject).filter_by(id=job.video_project_id, company_id=company_id, is_deleted=False).first()
        approved = (project.quality_check_result or {}).get('approved_publication') if project else None
        if approved:
            if any(str(value or '') != str(approved.get(key) or '') for key, value in
                   [('title', job.title), ('description', job.description), ('asset_id', job.asset_id)]):
                raise HTTPException(409, '发布内容发生变化，请重新审核成片与文案')
        else:
            # Existing jobs from the previous release retain their approval.
            from app.models.approval import Approval
            approval = db.query(Approval).filter_by(company_id=company_id, resource_type='publish_job', resource_id=str(job.id), status='approved').first()
            if not approval or any(str(value or '') != str((approval.details or {}).get(key) or '') for key, value in
                                   [('title', job.title), ('description', job.description), ('asset_id', job.asset_id)]):
                raise HTTPException(409, '请审核成片与发布文案')
    if job.status in ('published', 'publishing'):
        raise HTTPException(409, '当前任务已发布或正在发布，请先核对平台结果，避免重复发布')
    row = db.query(PlatformConnection).filter_by(id=job.platform_connection_id, company_id=company_id).first()
    if not row: raise HTTPException(400, "平台未连接")
    if job.video_project_id:
        project = db.query(VideoProject).filter_by(id=job.video_project_id, company_id=company_id, is_deleted=False).first()
        if not project or project.project_status != 'completed' or project.review_status != 'approved':
            raise HTTPException(400, '视频项目必须先审核通过')
        asset_id = project.output_asset_id
        if (job.content_snapshot or {}).get('execution_root_id') and asset_id != job.asset_id:
            raise HTTPException(409, '视频成片已变化，必须重新审批')
    else:
        asset_id = job.asset_id
    if asset_id:
        from app.models.asset import Asset
        from app.services.storage_service import StorageService
        from pathlib import Path
        asset = db.query(Asset).filter_by(id=asset_id, company_id=company_id, is_deleted=False,
            is_available=True, processing_status='ready').first()
        if not asset: raise HTTPException(400, '媒体素材不存在或不可用')
        if settings.STORAGE_BACKEND != 'local':
            raise HTTPException(400, 'Web 发布暂需要本机素材文件，请配置本地存储')
        job.media_url = str(Path(settings.LOCAL_STORAGE_PATH) / asset.file_key)
    from app.connectors.web_platform import publish
    job.status = 'publishing'
    db.commit()
    try:
        location = (job.content_snapshot or {}).get('location_name')
        from app.services.execution_loop import publication_geolocation
        geolocation = publication_geolocation(db, company_id)
        if location or geolocation:
            result = publish(company_id, row.platform, job.title, job.description or "", job.media_url or "", location_name=location, **({'geolocation':geolocation} if geolocation else {}))
        else:
            result = publish(company_id, row.platform, job.title, job.description or "", job.media_url or "")
    except Exception:
        result = {'status':'manual_required','message':'平台执行结果不确定，请核对发布后台后再操作，避免重复发布'}
    job.status = result["status"]; job.provider_url = result.get("provider_url"); job.provider_post_id = result.get("provider_post_id"); job.metrics = result.get("metrics"); job.error_message = result.get("message")
    if job.status == 'published' and (job.content_snapshot or {}).get('execution_root_id'):
        from datetime import timedelta
        job.metrics = {**(job.metrics or {}), 'feedback_due_at': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(), 'feedback_attempts': 0}
    db.commit(); db.refresh(job); return job

def close_web(db, company_id, platform):
    from app.connectors.web_platform import close_session
    result = close_session(company_id, platform, logout=True)
    row = get_connection(db, company_id, platform)
    if row:
        row.status = "disconnected"; row.account_id = None; row.account_name = None; db.commit()
    return result

def web_metrics(db, company_id, job_id):
    job = db.query(PublishJob).filter_by(id=job_id, company_id=company_id).with_for_update().first()
    if not job: raise HTTPException(404, "发布任务不存在")
    if job.status != 'published': raise HTTPException(409, '只有确认发布成功后才可回流数据')
    is_loop = bool((job.content_snapshot or {}).get('execution_root_id'))
    source = None
    if is_loop:
        from app.services.execution_loop import assert_active
        source = db.query(OperationTask).filter_by(id=job.task_id, company_id=company_id).first()
        if not source: raise HTTPException(409, '来源任务不存在')
        assert_active(db, source)
    row = db.query(PlatformConnection).filter_by(id=job.platform_connection_id, company_id=company_id).first()
    if not row: raise HTTPException(400, '平台连接不存在')
    from app.connectors.web_platform import read_metrics
    result = read_metrics(company_id, row.platform)
    feedback_task = None
    if result.get('metrics'):
        numeric = {k:v for k,v in result['metrics'].items() if isinstance(v, (int,float)) and not isinstance(v,bool)}
        previous = {k:v for k,v in (job.metrics or {}).items() if k in numeric}
        job.metrics = {**(job.metrics or {}), **result['metrics'], 'source':'web',
            'scope':'account', 'updated_at':datetime.now(timezone.utc).isoformat()}
        if numeric and (not is_loop and numeric != previous or is_loop and not job.metrics.get('feedback_task_id')):
            from app.models.digital_employee import DigitalEmployee
            analyst = db.query(DigitalEmployee).filter_by(company_id=company_id, role_title='data_analyst',
                is_active=True,is_deleted=False).first()
            if analyst and 'company' in (analyst.allowed_data_scopes or []):
                feedback_task = OperationTask(company_id=company_id,created_by=job.requested_by,
                    parent_task_id=source.id if source else None,
                    digital_employee_id=analyst.id,task_type='business_analysis',title='平台数据复盘与内容优化',
                    input_params={'goal':'根据最新平台数据提出后续内容优化方案，说明账号数据与作品归因的边界',
                                  'feedback_publish_job_id':str(job.id), 'auto_handoff':False,
                                  **({'execution_loop':True, 'execution_root_id':job.content_snapshot['execution_root_id']} if is_loop else {})},status='pending',progress=0,execution_log=[])
                db.add(feedback_task);db.flush()
                job.metrics = {**job.metrics, 'feedback_task_id':str(feedback_task.id)}
        if is_loop and job.metrics.get('feedback_task_id'):
            job.metrics = {**job.metrics, 'feedback_state':'review_pending', 'feedback_error':None}
    job.error_message = result.get('message')
    db.commit()
    if feedback_task:
        from app.models.user import User
        from app.services.task_dispatch import dispatch_task
        dispatch_task(db,feedback_task,db.get(User,job.requested_by))
    db.refresh(job); return job
