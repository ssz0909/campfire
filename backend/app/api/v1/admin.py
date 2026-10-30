"""
Platform admin API — accessible only to users with is_platform_admin=True.
Prefix: /admin
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.database import get_db
from app.dependencies import get_current_active_user
from app.models.company import Company
from app.models.member import CompanyMembership
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Guard dependency
# ---------------------------------------------------------------------------

def require_platform_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required",
        )
    return current_user


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_platform_admin: bool
    created_at: datetime
    last_login_at: datetime | None = None
    company_count: int = 0

    model_config = {"from_attributes": True}


class AdminCompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    industry: str | None = None
    is_active: bool
    created_at: datetime
    owner_email: str | None = None
    member_count: int = 0
    plan_name: str = "free"

    model_config = {"from_attributes": True}


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    platform_admins: int
    total_companies: int
    active_companies: int
    new_users_last_30_days: int
    new_companies_last_30_days: int


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    is_platform_admin: bool | None = None
    full_name: str | None = None


class AdminCreateUser(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    is_platform_admin: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=AdminStatsResponse)
def get_platform_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    """Overall platform health metrics."""
    cutoff = datetime.now(timezone.utc).replace(day=1)

    total_users = db.query(func.count(User.id)).filter(User.is_deleted == False).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_deleted == False, User.is_active == True).scalar() or 0
    platform_admins = db.query(func.count(User.id)).filter(User.is_deleted == False, User.is_platform_admin == True).scalar() or 0
    total_companies = db.query(func.count(Company.id)).filter(Company.is_deleted == False).scalar() or 0
    active_companies = db.query(func.count(Company.id)).filter(Company.is_deleted == False, Company.is_active == True).scalar() or 0
    new_users = db.query(func.count(User.id)).filter(User.is_deleted == False, User.created_at >= cutoff).scalar() or 0
    new_companies = db.query(func.count(Company.id)).filter(Company.is_deleted == False, Company.created_at >= cutoff).scalar() or 0

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        platform_admins=platform_admins,
        total_companies=total_companies,
        active_companies=active_companies,
        new_users_last_30_days=new_users,
        new_companies_last_30_days=new_companies,
    )


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    """List all platform users with pagination and optional email/name search."""
    q = db.query(User).filter(User.is_deleted == False)
    if search:
        like = f"%{search}%"
        q = q.filter((User.email.ilike(like)) | (User.full_name.ilike(like)))
    users = q.order_by(User.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for user in users:
        company_count = (
            db.query(func.count(CompanyMembership.id))
            .filter(
                CompanyMembership.user_id == user.id,
                CompanyMembership.status == "active",
            )
            .scalar() or 0
        )
        result.append(AdminUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_platform_admin=user.is_platform_admin,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            company_count=company_count,
        ))
    return result


@router.get("/users/{user_id}", response_model=AdminUserResponse)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    company_count = (
        db.query(func.count(CompanyMembership.id))
        .filter(CompanyMembership.user_id == user.id, CompanyMembership.status == "active")
        .scalar() or 0
    )
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        company_count=company_count,
    )


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> Any:
    """Update user active status, admin flag, or display name."""
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent an admin from revoking their own admin status
    if user.id == admin.id and data.is_platform_admin is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke your own platform admin status",
        )

    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_platform_admin is not None:
        user.is_platform_admin = data.is_platform_admin
    if data.full_name is not None:
        user.full_name = data.full_name

    db.commit()
    db.refresh(user)

    company_count = (
        db.query(func.count(CompanyMembership.id))
        .filter(CompanyMembership.user_id == user.id, CompanyMembership.status == "active")
        .scalar() or 0
    )
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        company_count=company_count,
    )


@router.post("/users", response_model=AdminUserResponse, status_code=201)
def create_user(
    data: AdminCreateUser,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    """Create a new user account (with optional admin flag)."""
    existing = db.query(User).filter(User.email == data.email, User.is_deleted == False).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    if len(data.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    user = User(
        id=uuid.uuid4(),
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        is_active=True,
        is_platform_admin=data.is_platform_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
        created_at=user.created_at,
        last_login_at=None,
        company_count=0,
    )


@router.get("/companies", response_model=list[AdminCompanyResponse])
def list_companies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    """List all companies across all tenants."""
    q = db.query(Company).filter(Company.is_deleted == False)
    if search:
        like = f"%{search}%"
        q = q.filter((Company.name.ilike(like)) | (Company.slug.ilike(like)))
    companies = q.order_by(Company.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for company in companies:
        owner = db.query(User).filter(User.id == company.owner_id, User.is_deleted == False).first()
        member_count = (
            db.query(func.count(CompanyMembership.id))
            .filter(CompanyMembership.company_id == company.id, CompanyMembership.status == "active")
            .scalar() or 0
        )
        subscription = (
            db.query(Subscription)
            .filter(Subscription.company_id == company.id)
            .order_by(Subscription.created_at.desc())
            .first()
        )
        result.append(AdminCompanyResponse(
            id=company.id,
            name=company.name,
            slug=company.slug,
            industry=company.industry,
            is_active=company.is_active,
            created_at=company.created_at,
            owner_email=owner.email if owner else None,
            member_count=member_count,
            plan_name=subscription.plan_name if subscription else "free",
        ))
    return result


@router.patch("/companies/{company_id}/deactivate", response_model=AdminCompanyResponse)
def deactivate_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    company = db.query(Company).filter(Company.id == company_id, Company.is_deleted == False).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.is_active = False
    db.commit()
    db.refresh(company)
    owner = db.query(User).filter(User.id == company.owner_id).first()
    member_count = (
        db.query(func.count(CompanyMembership.id))
        .filter(CompanyMembership.company_id == company.id, CompanyMembership.status == "active")
        .scalar() or 0
    )
    return AdminCompanyResponse(
        id=company.id,
        name=company.name,
        slug=company.slug,
        industry=company.industry,
        is_active=company.is_active,
        created_at=company.created_at,
        owner_email=owner.email if owner else None,
        member_count=member_count,
    )


@router.patch("/companies/{company_id}/activate", response_model=AdminCompanyResponse)
def activate_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    company = db.query(Company).filter(Company.id == company_id, Company.is_deleted == False).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.is_active = True
    db.commit()
    db.refresh(company)
    owner = db.query(User).filter(User.id == company.owner_id).first()
    member_count = (
        db.query(func.count(CompanyMembership.id))
        .filter(CompanyMembership.company_id == company.id, CompanyMembership.status == "active")
        .scalar() or 0
    )
    return AdminCompanyResponse(
        id=company.id,
        name=company.name,
        slug=company.slug,
        industry=company.industry,
        is_active=company.is_active,
        created_at=company.created_at,
        owner_email=owner.email if owner else None,
        member_count=member_count,
    )


class DdllTicketRequest(BaseModel):
    ticket: str


@router.post("/ddll/ticket", status_code=204, response_class=Response)
def set_ddll_ticket(
    data: DdllTicketRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> Response:
    """
    Manually record the current 订单来了 ticket. Normally it arrives by callback
    every ~10 minutes; this is for environments without a public callback URL.
    """
    from app.connectors.hotel.service import store_ticket
    from app.models.audit_log import AuditLog

    ticket = data.ticket.strip()
    if not ticket:
        raise HTTPException(status_code=422, detail="ticket must not be empty")
    store_ticket(db, ticket)
    db.add(AuditLog(user_id=admin.id, action="platform.ddll.ticket.set",
                    resource_type="platform", resource_id="ddll_ticket"))
    db.commit()
    return Response(status_code=204)


class LLMSettingsRequest(BaseModel):
    base_url: str
    model: str
    api_key: str | None = None


@router.get('/model-settings')
def read_model_settings(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    from app.services.model_settings import get_llm_settings, LLM_SETTINGS_KEY
    from app.connectors.hotel.models import PlatformKeyValue
    values = get_llm_settings(db)
    return {'base_url': values['base_url'], 'model': values['model'],
            'api_key_configured': bool(values['api_key']),
            'source': 'database' if db.get(PlatformKeyValue, LLM_SETTINGS_KEY) else 'env'}


@router.put('/model-settings')
def update_model_settings(
    data: LLMSettingsRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> Any:
    from urllib.parse import urlsplit
    from app.services.model_settings import get_llm_settings, save_llm_settings
    from app.models.audit_log import AuditLog
    base_url, model = data.base_url.strip().rstrip('/'), data.model.strip()
    try:
        url = urlsplit(base_url)
        valid_url = url.scheme in ('http', 'https') and url.hostname and not (
            url.username or url.password or url.query or url.fragment)
        url.port
    except ValueError:
        valid_url = False
    if not valid_url:
        raise HTTPException(422, '请输入有效的 HTTP/HTTPS 接口地址，不包含账号、查询参数或片段')
    api_key = (data.api_key or '').strip() or get_llm_settings(db)['api_key']
    if not model or not api_key:
        raise HTTPException(422, '模型名称和 API Key 不能为空')
    save_llm_settings(db, {'base_url': base_url, 'model': model, 'api_key': api_key})
    db.add(AuditLog(user_id=admin.id, action='platform.llm.settings.update',
                    resource_type='platform', resource_id='llm_settings'))
    db.commit()
    return read_model_settings(db, admin)


@router.get('/video-model-settings')
def read_video_model_settings(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> Any:
    from app.services.model_settings import get_video_settings, VIDEO_SETTINGS_KEY
    from app.connectors.hotel.models import PlatformKeyValue
    values = get_video_settings(db)
    return {'base_url': values['base_url'], 'model': values['model'],
            'api_key_configured': bool(values['api_key']),
            'source': 'database' if db.get(PlatformKeyValue, VIDEO_SETTINGS_KEY) else 'env'}


@router.put('/video-model-settings')
def update_video_model_settings(
    data: LLMSettingsRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> Any:
    from urllib.parse import urlsplit
    from app.services.model_settings import get_video_settings, save_video_settings
    from app.models.audit_log import AuditLog
    base_url, model = data.base_url.strip().rstrip('/'), data.model.strip()
    try:
        url = urlsplit(base_url)
        valid_url = url.scheme in ('http', 'https') and url.hostname and not (
            url.username or url.password or url.query or url.fragment)
        url.port
    except ValueError:
        valid_url = False
    if not valid_url:
        raise HTTPException(422, '请输入有效的 HTTP/HTTPS 接口地址，不包含账号、查询参数或片段')
    api_key = (data.api_key or '').strip() or get_video_settings(db)['api_key']
    if not model or not api_key:
        raise HTTPException(422, '模型名称和 API Key 不能为空')
    save_video_settings(db, {'base_url': base_url, 'model': model, 'api_key': api_key})
    db.add(AuditLog(user_id=admin.id, action='platform.video.settings.update',
                    resource_type='platform', resource_id='video_settings'))
    db.commit()
    return read_video_model_settings(db, admin)
