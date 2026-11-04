"""Public industry catalog and platform-admin template publishing."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.admin import require_platform_admin
from app.database import get_db
from app.dependencies import get_current_active_user
from app.models.audit_log import AuditLog
from app.models.industry_template import IndustryTemplate, IndustryTemplateVersion
from app.models.user import User
from app.schemas.industry_template import IndustryCreate, DraftUpdate, PublishTemplate, TemplateStatus, TemplateContent
from app.services.industry_templates import published_options, render_guidance, BASE_GUIDANCE, ALIASES

router = APIRouter()


def get_row(db, code):
    row = db.query(IndustryTemplate).filter_by(code=code).with_for_update().first()
    if not row:
        raise HTTPException(404, '行业模板不存在')
    return row


def describe(db, row):
    versions = db.query(IndustryTemplateVersion).filter_by(industry_code=row.code).order_by(
        IndustryTemplateVersion.version.desc()).all()
    return {'code': row.code, 'enabled': row.enabled, 'draft': row.draft,
            'draft_revision': row.draft_revision, 'published_version': row.published_version,
            'versions': [{'version': v.version, 'content': v.content, 'created_at': v.created_at} for v in versions],
            'preview': render_guidance({'content': row.draft, 'base_guidance': BASE_GUIDANCE})}


def audit(db, user, row, action):
    db.add(AuditLog(user_id=user.id, action=f'industry_template.{action}', resource_type='industry_template',
        resource_id=row.code, details={'draft_revision': row.draft_revision,
                                     'published_version': row.published_version, 'enabled': row.enabled}))


def check_revision(row, expected):
    if row.draft_revision != expected:
        raise HTTPException(409, '模板已被修改，请重新加载后再保存或发布')


@router.get('/industries')
def industries(_: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return published_options(db)


@router.get('/admin/industry-templates')
def list_templates(_: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    return [describe(db, row) for row in db.query(IndustryTemplate).order_by(IndustryTemplate.code).all()]


@router.post('/admin/industry-templates', status_code=201)
def create_template(data: IndustryCreate, user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    # The primary key is the final guard against duplicate industry codes.
    if db.get(IndustryTemplate, data.code):
        raise HTTPException(409, '该行业标识已存在')
    if data.code in ALIASES:
        raise HTTPException(422, '该标识已作为历史行业别名保留，请使用其他标识')
    row = IndustryTemplate(code=data.code, enabled=True, draft=data.content.model_dump(),
                           draft_revision=1, published_version=0)
    db.add(row)
    audit(db, user, row, 'create')
    try:
        db.commit()
    except Exception as exc:
        from sqlalchemy.exc import IntegrityError
        db.rollback()
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, '该行业标识已存在') from exc
        raise
    return describe(db, row)


@router.put('/admin/industry-templates/{code}/draft')
def save_draft(code: str, data: DraftUpdate, user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    row = get_row(db, code)
    check_revision(row, data.expected_revision)
    row.draft = data.content.model_dump()
    row.draft_revision += 1
    audit(db, user, row, 'save_draft')
    db.commit()
    return describe(db, row)


@router.post('/admin/industry-templates/{code}/publish')
def publish(code: str, data: PublishTemplate, user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    row = get_row(db, code)
    check_revision(row, data.expected_revision)
    content = TemplateContent.model_validate(row.draft).model_dump()
    current = db.query(IndustryTemplateVersion).filter_by(industry_code=code, version=row.published_version).first()
    if current and current.content == content:
        return describe(db, row)
    row.published_version += 1
    row.draft_revision += 1
    db.add(IndustryTemplateVersion(industry_code=code, version=row.published_version, content=content))
    audit(db, user, row, 'publish')
    db.commit()
    return describe(db, row)


@router.patch('/admin/industry-templates/{code}/status')
def set_status(code: str, data: TemplateStatus, user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    row = get_row(db, code)
    check_revision(row, data.expected_revision)
    if code == 'generic' and not data.enabled:
        raise HTTPException(422, '通用兜底模板不能停用')
    row.enabled = data.enabled
    row.draft_revision += 1
    audit(db, user, row, 'enable' if data.enabled else 'disable')
    db.commit()
    return describe(db, row)


@router.post('/admin/industry-templates/{code}/versions/{version}/restore')
def restore_version(code: str, version: int, data: PublishTemplate,
                    user: User = Depends(require_platform_admin), db: Session = Depends(get_db)):
    row = get_row(db, code)
    check_revision(row, data.expected_revision)
    previous = db.query(IndustryTemplateVersion).filter_by(industry_code=code, version=version).first()
    if not previous:
        raise HTTPException(404, '历史模板版本不存在')
    row.draft = TemplateContent.model_validate(previous.content).model_dump()
    row.draft_revision += 1
    audit(db, user, row, 'restore_draft')
    db.commit()
    return describe(db, row)
