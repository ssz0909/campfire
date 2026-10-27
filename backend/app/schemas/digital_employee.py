from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class DigitalEmployeeBase(BaseModel):
    name: str
    role_title: str
    role_description: str | None = None
    work_goals: str | None = None
    system_instructions: str | None = None
    business_rules: list | None = None
    allowed_data_scopes: list | None = None
    allowed_tools: list | None = None
    allowed_actions: list | None = None
    forbidden_actions: list | None = None
    max_task_budget_cents: int | None = None
    max_iterations: int = 10
    approval_policy: str = "moderate"
    avatar_url: str | None = None


class DigitalEmployeeCreate(DigitalEmployeeBase):
    pass


class DigitalEmployeeUpdate(BaseModel):
    name: str | None = None
    role_title: str | None = None
    role_description: str | None = None
    work_goals: str | None = None
    system_instructions: str | None = None
    business_rules: list | None = None
    allowed_data_scopes: list | None = None
    allowed_tools: list | None = None
    allowed_actions: list | None = None
    forbidden_actions: list | None = None
    max_task_budget_cents: int | None = None
    max_iterations: int | None = None
    approval_policy: str | None = None
    avatar_url: str | None = None


class DigitalEmployeeResponse(DigitalEmployeeBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_by: uuid.UUID
    is_active: bool
    last_executed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
