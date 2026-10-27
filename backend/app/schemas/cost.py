from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CostRecordResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    task_id: uuid.UUID | None = None
    video_project_id: uuid.UUID | None = None
    provider: str
    model_name: str | None = None
    record_type: str
    quantity: float
    unit: str
    unit_cost_cents: float
    total_cost_cents: float
    is_estimate: bool
    provider_request_id: str | None = None
    requested_at: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CostSummaryResponse(BaseModel):
    period_start: str
    period_end: str
    total_cost_cents: float
    by_provider: dict[str, float]
    by_type: dict[str, float]


class UsageResponse(BaseModel):
    company_id: uuid.UUID
    plan_name: str
    period_start: datetime | None
    period_end: datetime | None
    tasks_used: int
    tasks_quota: int | None
    videos_used: int
    videos_quota: int | None
    model_calls_used: int
    model_calls_quota: int | None
    storage_bytes_used: int
    storage_bytes_quota: int | None
    total_cost_cents: int
