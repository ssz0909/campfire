"""Payment and AI credit accounting. All monetary amounts are integer CNY fen."""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class PaymentOrder(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'payment_orders'
    __table_args__ = (UniqueConstraint('channel', 'provider_transaction_id', name='uq_payment_provider_transaction'),
                      UniqueConstraint('company_id', 'idempotency_key', name='uq_payment_company_request'))
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('companies.id'), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'))
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))
    plan_code: Mapped[str] = mapped_column(String(30))
    plan_snapshot: Mapped[dict] = mapped_column(nullable=False)
    amount_fen: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default='creating', index=True)
    # creating | pending | paid | failed | expired | unknown
    code_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    merchant_snapshot: Mapped[dict] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)


class SubscriptionPeriod(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'subscription_periods'
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('companies.id'), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('payment_orders.id'), unique=True)
    plan_code: Mapped[str] = mapped_column(String(30))
    plan_name: Mapped[str] = mapped_column(String(60))
    rates: Mapped[dict] = mapped_column(nullable=False, default=dict)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    included_units: Mapped[int] = mapped_column(BigInteger)
    used_units: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_units: Mapped[int] = mapped_column(BigInteger, default=0)


class AIUsage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'ai_usage_ledger'
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('companies.id'), index=True)
    period_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('subscription_periods.id'), nullable=True)
    usage_key: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='reserved')
    reserved_units: Mapped[int] = mapped_column(BigInteger, default=0)
    charged_units: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_micro_yuan: Mapped[int] = mapped_column(BigInteger, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    video_milliseconds: Mapped[int] = mapped_column(BigInteger, default=0)
    rates: Mapped[dict] = mapped_column(nullable=False)
    note: Mapped[str | None] = mapped_column(String(250), nullable=True)
