from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.cost import CostRecordResponse, CostSummaryResponse, UsageResponse
from app.services.cost_service import CostService
from app.utils.pagination import PaginatedResponse

router = APIRouter()


@router.get("/{company_id}/costs", response_model=PaginatedResponse[CostRecordResponse])
def list_costs(
    company_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(require_permission(Permission.COST_VIEW)),
    db: Session = Depends(get_db),
):
    items, total = CostService(db).list_cost_records(company_id, page, page_size)
    return PaginatedResponse.create(items, total, page, page_size)


@router.get("/{company_id}/costs/summary", response_model=CostSummaryResponse)
def cost_summary(
    company_id: uuid.UUID,
    period_start: str | None = Query(None),
    period_end: str | None = Query(None),
    _: User = Depends(require_permission(Permission.COST_VIEW)),
    db: Session = Depends(get_db),
):
    return CostService(db).get_cost_summary(company_id, period_start, period_end)


@router.get("/{company_id}/usage", response_model=UsageResponse)
def get_usage(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.SUBSCRIPTION_VIEW)),
    db: Session = Depends(get_db),
):
    return CostService(db).get_usage(company_id)
