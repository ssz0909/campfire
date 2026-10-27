from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.company import Company, CompanyProduct, Store
from app.models.member import CompanyMembership
from app.models.role import ROLE_PERMISSIONS, Role
from app.models.subscription import Subscription
from app.schemas.company import CompanyCreate, CompanyUpdate
from app.services.digital_employee_service import DigitalEmployeeService


class CompanyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_company(self, owner_id: uuid.UUID, data: CompanyCreate) -> Company:
        payload = data.model_dump()
        supplied_slug = payload.get("slug")
        base_slug = self.slugify(supplied_slug or data.name)[:80].strip("-")
        if not base_slug:
            base_slug = f"company-{uuid.uuid4().hex[:8]}"

        slug = base_slug
        existing = (
            self.db.query(Company)
            .filter(Company.slug == slug, Company.is_deleted == False)
            .first()
        )
        if existing and supplied_slug:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Company slug already in use",
            )
        while existing:
            slug = f"{base_slug[:70]}-{uuid.uuid4().hex[:8]}"
            existing = (
                self.db.query(Company)
                .filter(Company.slug == slug, Company.is_deleted == False)
                .first()
            )
        payload["slug"] = slug

        company = Company(
            owner_id=owner_id,
            **payload,
        )
        self.db.add(company)
        self.db.flush()  # get company.id before commit

        # Auto-create free subscription
        subscription = Subscription(
            company_id=company.id,
            plan_name="free",
            status="active",
            member_limit=5,
            employee_limit=5,
            monthly_task_quota=50,
            video_quota=5,
            model_call_quota=1000,
            storage_bytes_quota=1_073_741_824,  # 1 GB
            features_enabled=["basic_analytics", "asset_library"],
        )
        self.db.add(subscription)

        # Create or fetch company_owner system role and add membership
        owner_role = (
            self.db.query(Role)
            .filter(Role.name == "company_owner", Role.is_system_role == True)
            .first()
        )
        membership = CompanyMembership(
            user_id=owner_id,
            company_id=company.id,
            role_id=owner_role.id if owner_role else None,
            is_owner=True,
            status="active",
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        DigitalEmployeeService(self.db).ensure_default_employees(company.id, owner_id, commit=False)
        self.db.commit()
        self.db.refresh(company)
        return company

    def get_user_companies(self, user_id: uuid.UUID) -> list[Company]:
        memberships = (
            self.db.query(CompanyMembership)
            .filter(
                CompanyMembership.user_id == user_id,
                CompanyMembership.status == "active",
            )
            .all()
        )
        company_ids = [m.company_id for m in memberships]
        return (
            self.db.query(Company)
            .filter(Company.id.in_(company_ids), Company.is_deleted == False)
            .all()
        )

    def get_company(self, company_id: uuid.UUID) -> Company:
        company = (
            self.db.query(Company)
            .filter(Company.id == company_id, Company.is_deleted == False)
            .first()
        )
        if not company:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        return company

    def update_company(self, company_id: uuid.UUID, data: CompanyUpdate) -> Company:
        company = self.get_company(company_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(company, field, value)
        self.db.commit()
        self.db.refresh(company)
        return company

    def list_stores(self, company_id: uuid.UUID) -> list[Store]:
        return (
            self.db.query(Store)
            .filter(Store.company_id == company_id, Store.is_active == True)
            .all()
        )

    def create_store(self, company_id: uuid.UUID, data: dict) -> Store:
        store = Store(company_id=company_id, **data)
        self.db.add(store)
        self.db.commit()
        self.db.refresh(store)
        return store

    def list_products(self, company_id: uuid.UUID) -> list[CompanyProduct]:
        return (
            self.db.query(CompanyProduct)
            .filter(CompanyProduct.company_id == company_id, CompanyProduct.is_active == True)
            .all()
        )

    def create_product(self, company_id: uuid.UUID, data: dict) -> CompanyProduct:
        product = CompanyProduct(company_id=company_id, **data)
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    @staticmethod
    def slugify(name: str) -> str:
        slug = name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_-]+", "-", slug)
        slug = slug.strip("-")
        return slug
