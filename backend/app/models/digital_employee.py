from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class EmployeeRole(str, enum.Enum):
    OPERATIONS_MANAGER = "operations_manager"
    CONTENT_PLANNER = "content_planner"
    VIDEO_PRODUCER = "video_producer"
    DATA_ANALYST = "data_analyst"
    OPERATIONS_ASSISTANT = "operations_assistant"


class ApprovalPolicy(str, enum.Enum):
    STRICT = "strict"
    MODERATE = "moderate"
    AUTONOMOUS = "autonomous"


class DigitalEmployee(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "digital_employees"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str] = mapped_column(String(100), nullable=False)
    role_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_rules: Mapped[list | None] = mapped_column("business_rules", nullable=True)
    allowed_data_scopes: Mapped[list | None] = mapped_column(
        "allowed_data_scopes", nullable=True
    )
    allowed_tools: Mapped[list | None] = mapped_column("allowed_tools", nullable=True)
    allowed_actions: Mapped[list | None] = mapped_column("allowed_actions", nullable=True)
    forbidden_actions: Mapped[list | None] = mapped_column("forbidden_actions", nullable=True)
    max_task_budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_iterations: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    approval_policy: Mapped[str] = mapped_column(
        String(20), default=ApprovalPolicy.MODERATE.value, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_executed_at: Mapped[datetime | None] = mapped_column(
        "last_executed_at", nullable=True
    )
