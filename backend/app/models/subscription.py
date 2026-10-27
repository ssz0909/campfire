from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Subscription(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    # free | basic | professional | enterprise
    plan_name: Mapped[str] = mapped_column(String(30), default="free", nullable=False)
    # active | suspended | cancelled | trial
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    member_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_task_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_call_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_bytes_quota: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    features_enabled: Mapped[list | None] = mapped_column("features_enabled", nullable=True)


class UsageRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "usage_records"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    tasks_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    videos_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_calls_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_bytes_used: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
