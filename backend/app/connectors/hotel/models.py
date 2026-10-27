"""Persistence models for the hotel connector."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, TimestampMixin, UUIDMixin


class HotelConnectorConfig(UUIDMixin, TimestampMixin, Base):
    """
    Per-company connection to a 订单来了 store.

    ``encrypted_credentials`` holds ``{"auth_access_token": ...}`` encrypted with
    Fernet (see ``app.core.secrets``). The token is never returned by the API.
    """

    __tablename__ = "hotel_connector_configs"

    company_id: Any = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, unique=True, index=True
    )
    # unconfigured | configured | connected | error
    status: Any = Column(String(30), default="unconfigured", nullable=False)
    # Store (门店) number at 订单来了. Unique so a callback maps to exactly one tenant.
    hotel_num: Any = Column(BigInteger, nullable=True, unique=True, index=True)
    encrypted_credentials: Any = Column(Text, nullable=True)
    hotel_name: Any = Column(String(255), nullable=True)
    # Snapshot of the hotel profile / room inventory from the last successful fetch.
    hotel_info: Any = Column(JSON, nullable=True)
    room_count: Any = Column(Integer, nullable=True)
    room_types: Any = Column(JSON, nullable=True)
    last_connect_at: Any = Column(DateTime(timezone=True), nullable=True)
    last_sync_at: Any = Column(DateTime(timezone=True), nullable=True)
    # running | success | failed | partial
    last_sync_status: Any = Column(String(30), nullable=True)
    last_sync_error: Any = Column(Text, nullable=True)
    last_sync_stats: Any = Column(JSON, nullable=True)
    notes: Any = Column(Text, nullable=True)


class HotelOrder(UUIDMixin, TimestampMixin, Base):
    """
    A PMS order synchronised from 订单来了 (tenant-scoped).

    Only fields needed for operations analytics are kept as columns. The stored
    ``detail`` is the platform response with personal identifiers removed.
    """

    __tablename__ = "hotel_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "hotel_num", "order_num", name="uq_hotel_order"),
        Index("ix_hotel_orders_company_created", "company_id", "order_created_at"),
    )

    company_id: Any = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    hotel_num: Any = Column(BigInteger, nullable=False)
    order_num: Any = Column(String(64), nullable=False)
    # 2 已预订 / 3 进行中 / 4 已取消 / 7 已完成; None when the order is no longer valid
    status: Any = Column(Integer, nullable=True)
    # Set when the platform reports the order no longer exists (e.g. merged into another)
    is_invalid: Any = Column(Boolean, default=False, nullable=False)
    channel_type: Any = Column(Integer, nullable=True)
    channel_name: Any = Column(String(255), nullable=True)
    pay_type: Any = Column(Integer, nullable=True)
    currency: Any = Column(String(8), nullable=True)
    actual_amount: Any = Column(Numeric(14, 2), nullable=True)
    paid_amount: Any = Column(Numeric(14, 2), nullable=True)
    order_created_at: Any = Column(DateTime, nullable=True)
    check_in_at: Any = Column(DateTime, nullable=True)
    check_out_at: Any = Column(DateTime, nullable=True)
    room_count: Any = Column(Integer, nullable=True)
    room_nights: Any = Column(Integer, nullable=True)
    # [{"date": "2026-10-01", "room_code": 1, "room_type": "...", "amount": 388.0}]
    nights: Any = Column(JSON, nullable=True)
    detail: Any = Column(JSON, nullable=True)
    synced_at: Any = Column(DateTime(timezone=True), nullable=True)
    last_event_type: Any = Column(Integer, nullable=True)


class HotelSyncJob(UUIDMixin, TimestampMixin, Base):
    """One execution of an order synchronisation (state lives in the DB, not Redis)."""

    __tablename__ = "hotel_sync_jobs"

    company_id: Any = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    # manual | callback | scheduled
    trigger: Any = Column(String(20), nullable=False, default="manual")
    # queued | running | success | partial | failed
    status: Any = Column(String(20), nullable=False, default="queued", index=True)
    requested_by: Any = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    begin_date: Any = Column(String(10), nullable=True)
    end_date: Any = Column(String(10), nullable=True)
    orders_found: Any = Column(Integer, nullable=False, default=0)
    orders_synced: Any = Column(Integer, nullable=False, default=0)
    orders_failed: Any = Column(Integer, nullable=False, default=0)
    error: Any = Column(Text, nullable=True)
    started_at: Any = Column(DateTime(timezone=True), nullable=True)
    finished_at: Any = Column(DateTime(timezone=True), nullable=True)


class PlatformKeyValue(Base):
    """Small encrypted key/value store for platform-level (non-tenant) state."""

    __tablename__ = "platform_key_values"

    key: Any = Column(String(100), primary_key=True)
    encrypted_value: Any = Column(Text, nullable=False)
    updated_at: Any = Column(DateTime(timezone=True), nullable=False)
