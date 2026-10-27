from __future__ import annotations

import uuid
from datetime import datetime, timezone
from secrets import token_urlsafe

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.member import CompanyMembership
from app.models.role import Role
from app.models.user import User


class MemberService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_members(self, company_id: uuid.UUID) -> list[dict]:
        memberships = (
            self.db.query(CompanyMembership)
            .filter(
                CompanyMembership.company_id == company_id,
                CompanyMembership.status.in_(["active", "pending"]),
            )
            .all()
        )
        result = []
        for m in memberships:
            user = self.db.query(User).filter(User.id == m.user_id).first()
            result.append(
                {
                    "user_id": m.user_id,
                    "company_id": m.company_id,
                    "role_id": m.role_id,
                    "is_owner": m.is_owner,
                    "status": m.status,
                    "joined_at": m.joined_at,
                    "invite_email": m.invite_email,
                    "full_name": user.full_name if user else None,
                    "email": user.email if user else m.invite_email,
                    "avatar_url": user.avatar_url if user else None,
                }
            )
        return result

    def invite_member(
        self,
        company_id: uuid.UUID,
        invited_by: uuid.UUID,
        email: str,
        role_id: uuid.UUID | None = None,
    ) -> CompanyMembership:
        # Check if already a member
        existing_user = (
            self.db.query(User).filter(User.email == email, User.is_deleted == False).first()
        )
        if existing_user:
            existing_membership = (
                self.db.query(CompanyMembership)
                .filter(
                    CompanyMembership.user_id == existing_user.id,
                    CompanyMembership.company_id == company_id,
                    CompanyMembership.status == "active",
                )
                .first()
            )
            if existing_membership:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User is already a member",
                )

        invite_token = token_urlsafe(32)
        membership = CompanyMembership(
            user_id=existing_user.id if existing_user else uuid.uuid4(),
            company_id=company_id,
            role_id=role_id,
            invited_by=invited_by,
            status="pending",
            invite_token=invite_token,
            invite_email=email,
        )
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def accept_invitation(self, invite_token: str, user_id: uuid.UUID) -> CompanyMembership:
        membership = (
            self.db.query(CompanyMembership)
            .filter(
                CompanyMembership.invite_token == invite_token,
                CompanyMembership.status == "pending",
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired invitation token",
            )
        membership.user_id = user_id
        membership.status = "active"
        membership.joined_at = datetime.now(timezone.utc)
        membership.invite_token = None
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def change_role(
        self,
        company_id: uuid.UUID,
        target_user_id: uuid.UUID,
        role_id: uuid.UUID,
    ) -> CompanyMembership:
        membership = (
            self.db.query(CompanyMembership)
            .filter(
                CompanyMembership.company_id == company_id,
                CompanyMembership.user_id == target_user_id,
                CompanyMembership.status == "active",
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
            )
        if membership.is_owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change role of company owner",
            )
        role = self.db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        membership.role_id = role_id
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def remove_member(
        self,
        company_id: uuid.UUID,
        target_user_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> None:
        membership = (
            self.db.query(CompanyMembership)
            .filter(
                CompanyMembership.company_id == company_id,
                CompanyMembership.user_id == target_user_id,
                CompanyMembership.status == "active",
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
            )
        if membership.is_owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove company owner",
            )
        membership.status = "removed"
        self.db.commit()
