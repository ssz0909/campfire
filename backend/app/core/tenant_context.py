from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.permissions import get_user_permissions
from app.dependencies import get_current_active_user, get_db
from app.models.role import Permission
from app.models.user import User


@dataclass
class TenantContext:
    current_user: User
    current_company_id: uuid.UUID | None
    permissions: set[Permission] = field(default_factory=set)

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require_permission(self, permission: Permission) -> None:
        from fastapi import HTTPException, status

        if not self.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value}",
            )

    def require_company(self) -> uuid.UUID:
        from fastapi import HTTPException, status

        if self.current_company_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company context required",
            )
        return self.current_company_id


def get_tenant_context(
    company_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Build a TenantContext for the current request."""
    permissions: set[Permission] = set()
    if company_id is not None:
        permissions = get_user_permissions(current_user.id, company_id, db)
    return TenantContext(
        current_user=current_user,
        current_company_id=company_id,
        permissions=permissions,
    )
