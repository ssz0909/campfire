from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_active_user, get_db
from app.models.member import CompanyMembership
from app.models.role import ROLE_PERMISSIONS, Permission, Role
from app.models.user import User


def get_user_permissions(
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    db: Session,
) -> set[Permission]:
    """Return the full permission set for a user within a company."""
    # Platform admins get everything
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if user and user.is_platform_admin:
        return set(Permission)

    membership = (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.status == "active",
        )
        .first()
    )
    if not membership:
        return set()

    # Owner gets full company permissions
    if membership.is_owner:
        return ROLE_PERMISSIONS.get("company_owner", set())

    if not membership.role_id:
        return ROLE_PERMISSIONS.get("readonly", set())

    role = db.query(Role).filter(Role.id == membership.role_id).first()
    if not role:
        return ROLE_PERMISSIONS.get("readonly", set())

    # System roles use the constant mapping; custom roles use stored permissions
    if role.is_system_role:
        return ROLE_PERMISSIONS.get(role.name, set())

    if role.permissions:
        return {
            Permission(p) for p in role.permissions if p in Permission._value2member_map_
        }

    return set()


def is_company_member(
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    db: Session,
) -> bool:
    return (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.status == "active",
        )
        .first()
        is not None
    )


def is_company_owner(
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    db: Session,
) -> bool:
    return (
        db.query(CompanyMembership)
        .filter(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.is_owner == True,
            CompanyMembership.status == "active",
        )
        .first()
        is not None
    )


class PermissionChecker:
    def __init__(self, db: Session) -> None:
        self.db = db

    def check(
        self,
        user: User,
        company_id: uuid.UUID,
        required_permission: Permission,
    ) -> bool:
        perms = get_user_permissions(user.id, company_id, self.db)
        return required_permission in perms

    def require(
        self,
        user: User,
        company_id: uuid.UUID,
        required_permission: Permission,
    ) -> None:
        if not self.check(user, company_id, required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {required_permission.value}",
            )


def require_permission(permission: Permission):
    """
    FastAPI dependency factory that checks a permission against the
    company_id path parameter.
    Usage:
        @router.get("/{company_id}/...")
        def endpoint(
            company_id: uuid.UUID,
            _=Depends(require_permission(Permission.ASSET_VIEW)),
        ):
    """

    def dependency(
        company_id: uuid.UUID,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> User:
        checker = PermissionChecker(db)
        checker.require(current_user, company_id, permission)
        return current_user

    return dependency
