from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class CostRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cost_records"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("operation_tasks.id"), nullable=True
    )
    video_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_projects.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # llm_input|llm_output|video_generation|image_generation|tts|storage|other
    record_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    # tokens|seconds|images|bytes|requests
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_cost_cents: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    total_cost_cents: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
