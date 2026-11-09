"""Public, versioned business sites. Private company data is never a search source."""
import uuid
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDMixin, TimestampMixin

class GeoSite(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'geo_sites'
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('companies.id'), unique=True, index=True)
    slug: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24), default='draft', index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    draft: Mapped[dict] = mapped_column(default=dict)
    live: Mapped[dict] = mapped_column(default=dict)
    published_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_result: Mapped[dict] = mapped_column(default=dict)
    vector: Mapped[list | None] = mapped_column(nullable=True)
    vector_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    index_status: Mapped[str] = mapped_column(String(40), default='keyword_only')

class GeoSlug(Base):
    __tablename__ = 'geo_slugs'
    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('geo_sites.id'), index=True)

class GeoVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'geo_versions'
    __table_args__ = (UniqueConstraint('site_id', 'revision'),)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('geo_sites.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column()

class GeoTemplate(TimestampMixin, Base):
    __tablename__ = 'geo_templates'
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(default=dict)

class GeoEvent(UUIDMixin, Base):
    __tablename__ = 'geo_events'
    __table_args__ = (Index('ix_geo_event_site_day', 'site_id', 'day'), UniqueConstraint('event_key'))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('geo_sites.id'), nullable=True)
    event_key: Mapped[str] = mapped_column(String(100))
    day: Mapped[str] = mapped_column(String(10), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(80), default='unknown')
    visitor: Mapped[str] = mapped_column(String(64), default='')
    audience: Mapped[str] = mapped_column(String(20), default='unknown')
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True))

class GeoDaily(Base):
    __tablename__ = 'geo_daily'
    site_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True, index=True)
    kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), primary_key=True)
    audience: Mapped[str] = mapped_column(String(20), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)

class GeoVisitor(Base):
    __tablename__ = 'geo_visitors'
    site_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True, index=True)
    visitor: Mapped[str] = mapped_column(String(64), primary_key=True)

class GeoFeedback(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'geo_feedback'
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('geo_sites.id'), index=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default='open', index=True)
    resolution: Mapped[str] = mapped_column(Text, default='')
