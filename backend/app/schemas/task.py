from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


class TaskSchedule(BaseModel):
    frequency: Literal['daily', 'weekly'] = 'daily'
    time: str = Field(default='09:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    timezone: str = 'Asia/Shanghai'
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6], min_length=1, max_length=7)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try: ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError): raise ValueError('无效时区')
        return value

    @field_validator('weekdays')
    @classmethod
    def valid_weekdays(cls, value):
        if any(day < 0 or day > 6 for day in value): raise ValueError('星期必须为 0 到 6')
        return sorted(set(value))


class TaskCreate(BaseModel):
    auto_execute: bool = False
    schedule: TaskSchedule | None = None
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
