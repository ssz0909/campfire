from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.approval import ApprovalActionRequest, ApprovalResponse
from app.services.approval_service import ApprovalService
from app.utils.pagination import PaginatedResponse

router = APIRouter()


@router.get("/{company_id}/approvals", response_model=PaginatedResponse[ApprovalResponse])
def list_approvals(
    company_id: uuid.UUID,
    status: str | None = Query("pending"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission(Permission.APPROVAL_VIEW)),
    db: Session = Depends(get_db),
):
    items, total = ApprovalService(db).list_approvals(company_id, status, page, page_size)
    return PaginatedResponse.create(items, total, page, page_size)


@router.get("/{company_id}/approvals/{aid}", response_model=ApprovalResponse)
def get_approval(
    company_id: uuid.UUID,
    aid: uuid.UUID,
    _: User = Depends(require_permission(Permission.APPROVAL_VIEW)),
    db: Session = Depends(get_db),
):
    return ApprovalService(db).get_approval(company_id, aid)


@router.post("/{company_id}/approvals/{aid}/approve", response_model=ApprovalResponse)
def approve(
    company_id: uuid.UUID,
    aid: uuid.UUID,
    data: ApprovalActionRequest,
    current_user: User = Depends(require_permission(Permission.APPROVAL_APPROVE)),
    db: Session = Depends(get_db),
):
    return ApprovalService(db).approve(company_id, aid, current_user.id, data.note)


@router.post("/{company_id}/approvals/{aid}/reject", response_model=ApprovalResponse)
def reject(
    company_id: uuid.UUID,
    aid: uuid.UUID,
    data: ApprovalActionRequest,
    current_user: User = Depends(require_permission(Permission.APPROVAL_REJECT)),
    db: Session = Depends(get_db),
):
    return ApprovalService(db).reject(company_id, aid, current_user.id, data.note)
