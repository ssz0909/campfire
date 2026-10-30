from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.permissions import Permission, require_permission
from app.dependencies import get_db
from app.models.user import User
from app.schemas.publishing import PlatformConnectionResponse, PublishJobResponse, PublishRequest, RepublishRequest, MetricsUpdate, PublishingAccountCreate, PublishingAccountUpdate
from app.services.publishing_service import SUPPORTED, DISPLAY, get_connection, authorization_url, complete_authorization, create_publish, submit_publish, update_metrics, start_web, web_status, web_publish, web_metrics, close_web
from app.utils.pagination import PaginatedResponse

router = APIRouter()

@router.get('/{company_id}/publishing/accounts', response_model=list[PlatformConnectionResponse])
def list_accounts(company_id: uuid.UUID, _: User = Depends(require_permission(Permission.PUBLISH_VIEW)), db: Session = Depends(get_db)):
    from app.models.publishing import PlatformConnection
    return db.query(PlatformConnection).filter_by(company_id=company_id).order_by(PlatformConnection.platform, PlatformConnection.created_at).all()


@router.post('/{company_id}/publishing/accounts', response_model=PlatformConnectionResponse, status_code=201)
def add_account(company_id: uuid.UUID, data: PublishingAccountCreate, _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    from app.models.publishing import PlatformConnection
    from fastapi import HTTPException
    if not data.label.strip(): raise HTTPException(422, '请输入账号备注名称')
    row = PlatformConnection(company_id=company_id, platform=data.platform, label=data.label.strip(), session_profile=str(uuid.uuid4()), status='disconnected')
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.patch('/{company_id}/publishing/accounts/{account_id}', response_model=PlatformConnectionResponse)
def rename_account(company_id: uuid.UUID, account_id: uuid.UUID, data: PublishingAccountUpdate, _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    from app.services.publishing_service import get_account
    from fastapi import HTTPException
    if not data.label.strip(): raise HTTPException(422, '请输入账号备注名称')
    row = get_account(db, company_id, account_id)
    row.label = data.label.strip(); db.commit(); db.refresh(row)
    return row


@router.get("/{company_id}/publishing/platforms")
def list_platforms(company_id: uuid.UUID, _: User = Depends(require_permission(Permission.PUBLISH_VIEW)), db: Session = Depends(get_db)):
    from app.models.publishing import PlatformConnection
    rows = db.query(PlatformConnection).filter_by(company_id=company_id).all()
    items = []
    for platform in sorted(SUPPORTED):
        accounts = [row for row in rows if row.platform == platform]
        single = accounts[0] if len(accounts) == 1 else None
        items.append({'platform':platform, 'name':DISPLAY[platform],
                      'status':single.status if single else 'multiple_accounts' if accounts else 'disconnected',
                      'account_name':single.account_name if single else None, 'account_count':len(accounts),
                      'configured':bool(__import__('app.services.publishing_service', fromlist=['_config'])._config(platform)[0])})
    return {'items':items}

@router.post("/{company_id}/publishing/{platform}/authorize")
def authorize_platform(company_id: uuid.UUID, platform: str, _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    return authorization_url(db, company_id, platform)

@router.get("/{company_id}/publishing/{platform}/callback", response_model=PlatformConnectionResponse)
def platform_callback_redirect(company_id: uuid.UUID, platform: str, code: str, state: str, account_id: str | None = None, account_name: str | None = None, db: Session = Depends(get_db)):
    return complete_authorization(db, company_id, platform, code, state, account_id, account_name)

@router.post("/{company_id}/publishing/{platform}/callback", response_model=PlatformConnectionResponse)
def platform_callback(company_id: uuid.UUID, platform: str, code: str, state: str, account_id: str | None = None, account_name: str | None = None, _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    return complete_authorization(db, company_id, platform, code, state, account_id, account_name)

@router.post("/{company_id}/publishing/{platform}/jobs", response_model=PublishJobResponse, status_code=201)
def create_job(company_id: uuid.UUID, platform: str, data: PublishRequest, current_user: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    return create_publish(db, company_id, current_user.id, platform, data)

@router.post("/{company_id}/publishing/jobs/{job_id}/submit", response_model=PublishJobResponse)
def submit_job(company_id: uuid.UUID, job_id: uuid.UUID, _: User = Depends(require_permission(Permission.PUBLISH_EXECUTE)), db: Session = Depends(get_db)):
    return submit_publish(db, company_id, job_id)

@router.get("/{company_id}/publishing/jobs", response_model=PaginatedResponse[PublishJobResponse])
def list_jobs(company_id: uuid.UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), _: User = Depends(require_permission(Permission.PUBLISH_VIEW)), db: Session = Depends(get_db)):
    q = __import__('app.models.publishing', fromlist=['PublishJob']).PublishJob
    query = db.query(q).filter_by(company_id=company_id).order_by(q.created_at.desc())
    total = query.count(); items = query.offset((page-1)*page_size).limit(page_size).all()
    return PaginatedResponse.create(items, total, page, page_size)


@router.post("/{company_id}/publishing/jobs/{job_id}/metrics", response_model=PublishJobResponse)
def ingest_metrics(company_id: uuid.UUID, job_id: uuid.UUID, data: MetricsUpdate, _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    return update_metrics(db, company_id, job_id, data.metrics)


@router.post("/{company_id}/publishing/{platform}/web/start")
def web_start(company_id: uuid.UUID, platform: str, connection_id: uuid.UUID | None = Query(None), _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    return start_web(db, company_id, platform, connection_id)

@router.get("/{company_id}/publishing/{platform}/web/status")
def web_session_status(company_id: uuid.UUID, platform: str, connection_id: uuid.UUID | None = Query(None), _: User = Depends(require_permission(Permission.PUBLISH_VIEW)), db: Session = Depends(get_db)):
    return web_status(db, company_id, platform, connection_id)

@router.post("/{company_id}/publishing/jobs/{job_id}/web-submit", response_model=PublishJobResponse)
def web_submit(company_id: uuid.UUID, job_id: uuid.UUID, _: User = Depends(require_permission(Permission.PUBLISH_EXECUTE)), db: Session = Depends(get_db)):
    return web_publish(db, company_id, job_id)

@router.post("/{company_id}/publishing/jobs/{job_id}/republish", response_model=PublishJobResponse, status_code=201)
def republish_job(company_id: uuid.UUID, job_id: uuid.UUID, data: RepublishRequest, current_user: User = Depends(require_permission(Permission.PUBLISH_EXECUTE)), db: Session = Depends(get_db)):
    from app.services.publishing_service import create_republish
    return create_republish(db, company_id, current_user.id, job_id, data.location_name)

@router.post("/{company_id}/publishing/jobs/{job_id}/web-metrics", response_model=PublishJobResponse)
def web_sync_metrics(company_id: uuid.UUID, job_id: uuid.UUID, _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    return web_metrics(db, company_id, job_id)


@router.post("/{company_id}/publishing/{platform}/web/logout")
def web_logout(company_id: uuid.UUID, platform: str, connection_id: uuid.UUID | None = Query(None), _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    return close_web(db, company_id, platform, connection_id)


from typing import Literal
from pydantic import BaseModel, Field
from fastapi import HTTPException, Response


class LoginViewAction(BaseModel):
    kind: Literal['click', 'drag', 'fill', 'text', 'key', 'scroll', 'refresh']
    x: int = Field(default=0, ge=0, lt=1440)
    y: int = Field(default=0, ge=0, lt=960)
    end_x: int = Field(default=0, ge=0, lt=1440)
    end_y: int = Field(default=0, ge=0, lt=960)
    text: str = Field(default='', max_length=256)
    field_id: str = Field(default='', pattern=r'^[a-f0-9]{0,32}$')
    key: Literal['Enter', 'Tab', 'Backspace', 'Escape'] = 'Enter'
    delta: int = Field(default=0, ge=-960, le=960)


def _login_view(company_id, platform, response, action=None, row=None):
    from app.connectors.web_platform import login_view
    response.headers['Cache-Control'] = 'no-store'
    try:
        from app.services.publishing_service import session_options
        return login_view(company_id, platform, action, **session_options(row))
    except ValueError as exc:
        raise HTTPException(400, '不支持的发布平台') from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, '无法读取登录画面，请重新打开网页登录或稍后重试') from exc


@router.get('/{company_id}/publishing/{platform}/web/view')
def web_login_view(company_id: uuid.UUID, platform: str, response: Response, connection_id: uuid.UUID | None = Query(None),
                   db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.PUBLISH_CREATE))):
    row = get_connection(db, company_id, platform, connection_id)
    return _login_view(company_id, platform, response, row=row)


@router.post('/{company_id}/publishing/{platform}/web/action')
def web_login_action(company_id: uuid.UUID, platform: str, data: LoginViewAction, response: Response, connection_id: uuid.UUID | None = Query(None),
                     db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.PUBLISH_CREATE))):
    row = get_connection(db, company_id, platform, connection_id)
    return _login_view(company_id, platform, response, data.model_dump(), row=row)
