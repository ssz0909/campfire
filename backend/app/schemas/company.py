from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class StoreBase(BaseModel):
    name: str
    address: str | None = None
    contact_info: dict | None = None


class StoreCreate(StoreBase):
    pass


class StoreResponse(StoreBase):
    id: uuid.UUID
    company_id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyProductBase(BaseModel):
    name: str
    description: str | None = None
    price_info: dict | None = None
    features: list | None = None


class CompanyProductCreate(CompanyProductBase):
    pass


class CompanyProductResponse(CompanyProductBase):
    id: uuid.UUID
    company_id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyBase(BaseModel):
    name: str
    description: str | None = None
    industry: str | None = None
    logo_url: str | None = None
    brand_positioning: str | None = None
    target_audience: str | None = None
    brand_voice: str | None = None
    marketing_forbidden_words: list | None = None
    contact_info: dict | None = None
    business_goals: dict | None = None
    faq: list | None = None


class CompanyCreate(CompanyBase):
    slug: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    industry: str | None = None
    logo_url: str | None = None
    brand_positioning: str | None = None
    target_audience: str | None = None
    brand_voice: str | None = None
    marketing_forbidden_words: list | None = None
    contact_info: dict | None = None
    business_goals: dict | None = None
    faq: list | None = None


class CompanyResponse(CompanyBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
