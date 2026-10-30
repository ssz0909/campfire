from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class VideoProject(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "video_projects"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    digital_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("digital_employees.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # prompt_to_video | reference_inspired_video
    creation_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    marketing_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    key_selling_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_theme: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 16:9 | 9:16 | 1:1
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="16:9", nullable=False)
    video_style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voiceover_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    subtitle_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cta_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_limit_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True
    )
    music_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('assets.id'), nullable=True
    )
    music_volume: Mapped[float] = mapped_column(Numeric(4, 3), default=0.25, server_default='0.25', nullable=False)
    selected_asset_ids: Mapped[list | None] = mapped_column("selected_asset_ids", nullable=True)
    reference_analysis: Mapped[dict | None] = mapped_column(
        "reference_analysis", nullable=True
    )
    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    storyboard: Mapped[list | None] = mapped_column("storyboard", nullable=True)
    output_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True
    )
    estimated_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pending_review | approved | rejected
    review_status: Mapped[str] = mapped_column(
        String(30), default="pending_review", nullable=False
    )
    # draft|analyzing|generating_script|confirming_storyboard|preparing_assets|
    # generating_shots|compositing|quality_check|pending_review|completed|failed|
    # cancelled|waiting_retry|partial
    project_status: Mapped[str] = mapped_column(
        String(30), default="draft", nullable=False, index=True
    )
    quality_check_result: Mapped[dict | None] = mapped_column(
        "quality_check_result", nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("operation_tasks.id"), nullable=True
    )


class ProviderTask(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "provider_tasks"

    video_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_projects.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # video_generation | image_generation | tts | music_generation
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    shot_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pending | submitted | processing | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    input_params: Mapped[dict | None] = mapped_column("input_params", nullable=True)
    output_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        "submitted_at", nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        "completed_at", nullable=True
    )
