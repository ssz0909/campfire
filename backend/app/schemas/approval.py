from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    requested_by: uuid.UUID
    resource_type: str
    resource_id: str
    action: str
    description: str | None = None
    status: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    expires_at: datetime | None = None
    details: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalActionRequest(BaseModel):
    note: str | None = None


class TaskApprovalResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    company_id: uuid.UUID
    requested_by: uuid.UUID
    operation_type: str
    operation_description: str | None = None
    impact_scope: str | None = None
    estimated_cost_cents: int | None = None
    status: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
