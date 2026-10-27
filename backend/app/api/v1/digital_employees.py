from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.digital_employee import (
    DigitalEmployeeCreate,
    DigitalEmployeeResponse,
    DigitalEmployeeUpdate,
)
from app.services.digital_employee_service import DigitalEmployeeService

router = APIRouter()


@router.get("/{company_id}/employees", response_model=list[DigitalEmployeeResponse])
def list_employees(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.EMPLOYEE_VIEW)),
    db: Session = Depends(get_db),
):
    return DigitalEmployeeService(db).list_employees(company_id)


@router.post("/{company_id}/employees", response_model=DigitalEmployeeResponse, status_code=201)
def create_employee(
    company_id: uuid.UUID,
    data: DigitalEmployeeCreate,
    current_user: User = Depends(require_permission(Permission.EMPLOYEE_CREATE)),
    db: Session = Depends(get_db),
):
    return DigitalEmployeeService(db).create_employee(company_id, current_user.id, data)


@router.get("/{company_id}/employees/{eid}", response_model=DigitalEmployeeResponse)
def get_employee(
    company_id: uuid.UUID,
    eid: uuid.UUID,
    _: User = Depends(require_permission(Permission.EMPLOYEE_VIEW)),
    db: Session = Depends(get_db),
):
    return DigitalEmployeeService(db).get_employee(company_id, eid)


@router.put("/{company_id}/employees/{eid}", response_model=DigitalEmployeeResponse)
def update_employee(
    company_id: uuid.UUID,
    eid: uuid.UUID,
    data: DigitalEmployeeUpdate,
    _: User = Depends(require_permission(Permission.EMPLOYEE_EDIT)),
    db: Session = Depends(get_db),
):
    return DigitalEmployeeService(db).update_employee(company_id, eid, data)


@router.delete("/{company_id}/employees/{eid}", status_code=204)
def delete_employee(
    company_id: uuid.UUID,
    eid: uuid.UUID,
    _: User = Depends(require_permission(Permission.EMPLOYEE_DELETE)),
    db: Session = Depends(get_db),
):
    DigitalEmployeeService(db).delete_employee(company_id, eid)
    return None


@router.post("/{company_id}/employees/{eid}/activate", response_model=DigitalEmployeeResponse)
def activate_employee(
    company_id: uuid.UUID,
    eid: uuid.UUID,
    _: User = Depends(require_permission(Permission.EMPLOYEE_EDIT)),
    db: Session = Depends(get_db),
):
    return DigitalEmployeeService(db).set_active(company_id, eid, True)


@router.post("/{company_id}/employees/{eid}/deactivate", response_model=DigitalEmployeeResponse)
def deactivate_employee(
    company_id: uuid.UUID,
    eid: uuid.UUID,
    _: User = Depends(require_permission(Permission.EMPLOYEE_EDIT)),
    db: Session = Depends(get_db),
):
    return DigitalEmployeeService(db).set_active(company_id, eid, False)
