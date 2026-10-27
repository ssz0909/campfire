from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Permission(str, enum.Enum):
    # Company
    COMPANY_VIEW = "company:view"
    COMPANY_EDIT = "company:edit"
    COMPANY_DELETE = "company:delete"
    # Members
    MEMBER_INVITE = "member:invite"
    MEMBER_REMOVE = "member:remove"
    MEMBER_VIEW = "member:view"
    # Assets
    ASSET_VIEW = "asset:view"
    ASSET_UPLOAD = "asset:upload"
    ASSET_DELETE = "asset:delete"
    # Digital Employees
    EMPLOYEE_VIEW = "employee:view"
    EMPLOYEE_CREATE = "employee:create"
    EMPLOYEE_EDIT = "employee:edit"
    EMPLOYEE_DELETE = "employee:delete"
    # Tasks
    TASK_VIEW = "task:view"
    TASK_CREATE = "task:create"
    TASK_EXECUTE = "task:execute"
    TASK_DELETE = "task:delete"
    # Approvals
    APPROVAL_VIEW = "approval:view"
    APPROVAL_APPROVE = "approval:approve"
    APPROVAL_REJECT = "approval:reject"
    # Video
    VIDEO_VIEW = "video:view"
    VIDEO_CREATE = "video:create"
    VIDEO_DELETE = "video:delete"
    # Cost
    COST_VIEW = "cost:view"
    # Analytics
    ANALYTICS_VIEW = "analytics:view"
    # Connectors
    CONNECTOR_VIEW = "connector:view"
    CONNECTOR_CONFIG = "connector:config"
    # Publishing: authoring and external execution are separate permissions.
    PUBLISH_VIEW = "publish:view"
    PUBLISH_CREATE = "publish:create"
    PUBLISH_EXECUTE = "publish:execute"
    # Subscription
    SUBSCRIPTION_VIEW = "subscription:view"
    SUBSCRIPTION_MANAGE = "subscription:manage"


# Permissions by system role name
ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "platform_admin": set(Permission),
    "company_owner": {
        Permission.COMPANY_VIEW,
        Permission.COMPANY_EDIT,
        Permission.COMPANY_DELETE,
        Permission.MEMBER_INVITE,
        Permission.MEMBER_REMOVE,
        Permission.MEMBER_VIEW,
        Permission.ASSET_VIEW,
        Permission.ASSET_UPLOAD,
        Permission.ASSET_DELETE,
        Permission.EMPLOYEE_VIEW,
        Permission.EMPLOYEE_CREATE,
        Permission.EMPLOYEE_EDIT,
        Permission.EMPLOYEE_DELETE,
        Permission.TASK_VIEW,
        Permission.TASK_CREATE,
        Permission.TASK_EXECUTE,
        Permission.TASK_DELETE,
        Permission.APPROVAL_VIEW,
        Permission.APPROVAL_APPROVE,
        Permission.APPROVAL_REJECT,
        Permission.VIDEO_VIEW,
        Permission.VIDEO_CREATE,
        Permission.VIDEO_DELETE,
        Permission.COST_VIEW,
        Permission.ANALYTICS_VIEW,
        Permission.CONNECTOR_VIEW,
        Permission.CONNECTOR_CONFIG,
        Permission.SUBSCRIPTION_VIEW,
        Permission.SUBSCRIPTION_MANAGE,
        Permission.PUBLISH_VIEW, Permission.PUBLISH_CREATE, Permission.PUBLISH_EXECUTE,
    },
    "company_admin": {
        Permission.PUBLISH_VIEW, Permission.PUBLISH_CREATE, Permission.PUBLISH_EXECUTE,
        Permission.COMPANY_VIEW,
        Permission.COMPANY_EDIT,
        Permission.MEMBER_INVITE,
        Permission.MEMBER_REMOVE,
        Permission.MEMBER_VIEW,
        Permission.ASSET_VIEW,
        Permission.ASSET_UPLOAD,
        Permission.ASSET_DELETE,
        Permission.EMPLOYEE_VIEW,
        Permission.EMPLOYEE_CREATE,
        Permission.EMPLOYEE_EDIT,
        Permission.EMPLOYEE_DELETE,
        Permission.TASK_VIEW,
        Permission.TASK_CREATE,
        Permission.TASK_EXECUTE,
        Permission.TASK_DELETE,
        Permission.APPROVAL_VIEW,
        Permission.APPROVAL_APPROVE,
        Permission.APPROVAL_REJECT,
        Permission.VIDEO_VIEW,
        Permission.VIDEO_CREATE,
        Permission.VIDEO_DELETE,
        Permission.COST_VIEW,
        Permission.ANALYTICS_VIEW,
        Permission.CONNECTOR_VIEW,
        Permission.CONNECTOR_CONFIG,
        Permission.SUBSCRIPTION_VIEW,
    },
    "operator": {
        Permission.PUBLISH_VIEW, Permission.PUBLISH_CREATE,
        Permission.COMPANY_VIEW,
        Permission.MEMBER_VIEW,
        Permission.ASSET_VIEW,
        Permission.ASSET_UPLOAD,
        Permission.EMPLOYEE_VIEW,
        Permission.TASK_VIEW,
        Permission.TASK_CREATE,
        Permission.TASK_EXECUTE,
        Permission.APPROVAL_VIEW,
        Permission.VIDEO_VIEW,
        Permission.VIDEO_CREATE,
        Permission.ANALYTICS_VIEW,
        Permission.CONNECTOR_VIEW,
    },
    "reviewer": {
        Permission.PUBLISH_VIEW,
        Permission.COMPANY_VIEW,
        Permission.MEMBER_VIEW,
        Permission.ASSET_VIEW,
        Permission.EMPLOYEE_VIEW,
        Permission.TASK_VIEW,
        Permission.APPROVAL_VIEW,
        Permission.APPROVAL_APPROVE,
        Permission.APPROVAL_REJECT,
        Permission.VIDEO_VIEW,
        Permission.ANALYTICS_VIEW,
    },
    "readonly": {
        Permission.PUBLISH_VIEW,
        Permission.COMPANY_VIEW,
        Permission.MEMBER_VIEW,
        Permission.ASSET_VIEW,
        Permission.EMPLOYEE_VIEW,
        Permission.TASK_VIEW,
        Permission.APPROVAL_VIEW,
        Permission.VIDEO_VIEW,
        Permission.ANALYTICS_VIEW,
    },
}


class Role(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    # null company_id means platform-level role
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions: Mapped[list | None] = mapped_column("permissions", nullable=True)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
