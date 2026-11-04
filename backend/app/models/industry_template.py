"""Platform-owned industry drafts and immutable published template revisions."""
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class IndustryTemplate(TimestampMixin, Base):
    __tablename__ = 'industry_templates'

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    draft: Mapped[dict] = mapped_column(nullable=False)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class IndustryTemplateVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = 'industry_template_versions'
    __table_args__ = (UniqueConstraint('industry_code', 'version'),)

    industry_code: Mapped[str] = mapped_column(String(64), ForeignKey('industry_templates.code'), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(nullable=False)
