from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Asset(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "assets"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # image | video | document | audio | other
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # image / video dimensions
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # video / audio
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fps: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column("tags", nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    copyright_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending | processing | ready | failed
    processing_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_metadata: Mapped[dict | None] = mapped_column("metadata", nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
