from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    task_type: str
    parent_task_id: uuid.UUID | None = None
    digital_employee_id: uuid.UUID | None = None
    input_params: dict | None = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    created_by: uuid.UUID
    digital_employee_id: uuid.UUID | None = None
    task_type: str
    title: str
    description: str | None = None
    input_params: dict | None = None
    status: str
    progress: int
    execution_log: list | None = None
    models_used: list | None = None
    tools_used: list | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    estimated_cost_cents: int | None = None
    actual_cost_cents: int | None = None
    output: dict | None = None
    error_message: str | None = None
    celery_task_id: str | None = None
    retry_count: int
    max_retries: int
    parent_task_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskCostResponse(BaseModel):
    task_id: uuid.UUID
    estimated_cost_cents: int | None = None
    actual_cost_cents: int | None = None
    cost_records: list[dict]
