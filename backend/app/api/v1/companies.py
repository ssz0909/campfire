from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.company import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    CompanyProductCreate,
    CompanyProductResponse,
    StoreCreate,
    StoreResponse,
)
from app.services.company_service import CompanyService

router = APIRouter()

from app.services.publish_location import PublishLocationSettings, resolve_location

@router.put('/{company_id}/publish-location', response_model=CompanyResponse)
def set_publish_location(company_id: uuid.UUID, data: PublishLocationSettings,
    _: User = Depends(require_permission(Permission.COMPANY_EDIT)), db: Session = Depends(get_db)):
    company = CompanyService(db).get_company(company_id)
    location = resolve_location(data)
    company.business_goals = {**(company.business_goals or {}),
        'publish_location_name':data.location_name.strip(), 'publish_geolocation':location,
        'publish_location_input':data.model_dump()}
    db.commit(); db.refresh(company)
    return company


@router.post("", response_model=CompanyResponse, status_code=201)
def create_company(
    data: CompanyCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return CompanyService(db).create_company(current_user.id, data)


@router.get("", response_model=list[CompanyResponse])
def list_companies(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return CompanyService(db).get_user_companies(current_user.id)


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.COMPANY_VIEW)),
    db: Session = Depends(get_db),
):
    return CompanyService(db).get_company(company_id)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: uuid.UUID,
    data: CompanyUpdate,
    _: User = Depends(require_permission(Permission.COMPANY_EDIT)),
    db: Session = Depends(get_db),
):
    return CompanyService(db).update_company(company_id, data)


@router.get("/{company_id}/stores", response_model=list[StoreResponse])
def list_stores(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.COMPANY_VIEW)),
    db: Session = Depends(get_db),
):
    return CompanyService(db).list_stores(company_id)


@router.post("/{company_id}/stores", response_model=StoreResponse, status_code=201)
def create_store(
    company_id: uuid.UUID,
    data: StoreCreate,
    _: User = Depends(require_permission(Permission.COMPANY_EDIT)),
    db: Session = Depends(get_db),
):
    return CompanyService(db).create_store(company_id, data.model_dump())


@router.get("/{company_id}/products", response_model=list[CompanyProductResponse])
def list_products(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.COMPANY_VIEW)),
    db: Session = Depends(get_db),
):
    return CompanyService(db).list_products(company_id)


@router.post(
    "/{company_id}/products", response_model=CompanyProductResponse, status_code=201
)
def create_product(
    company_id: uuid.UUID,
    data: CompanyProductCreate,
    _: User = Depends(require_permission(Permission.COMPANY_EDIT)),
    db: Session = Depends(get_db),
):
    return CompanyService(db).create_product(company_id, data.model_dump())
