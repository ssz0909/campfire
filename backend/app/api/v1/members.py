from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.member import (
    ChangeMemberRoleRequest,
    InviteMemberRequest,
    MemberWithUserResponse,
)
from app.services.member_service import MemberService

router = APIRouter()


@router.get("/{company_id}/members", response_model=list[MemberWithUserResponse])
def list_members(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.MEMBER_VIEW)),
    db: Session = Depends(get_db),
):
    return MemberService(db).list_members(company_id)


@router.post("/{company_id}/members/invite", status_code=201)
def invite_member(
    company_id: uuid.UUID,
    data: InviteMemberRequest,
    current_user: User = Depends(require_permission(Permission.MEMBER_INVITE)),
    db: Session = Depends(get_db),
):
    membership = MemberService(db).invite_member(
        company_id=company_id,
        invited_by=current_user.id,
        email=data.email,
        role_id=data.role_id,
    )
    return {
        "message": "Invitation sent",
        "invite_token": membership.invite_token,
        "invite_email": membership.invite_email,
    }


@router.put("/{company_id}/members/{user_id}/role")
def change_member_role(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    data: ChangeMemberRoleRequest,
    _: User = Depends(require_permission(Permission.MEMBER_INVITE)),
    db: Session = Depends(get_db),
):
    MemberService(db).change_role(company_id, user_id, data.role_id)
    return {"message": "Role updated"}


@router.delete("/{company_id}/members/{user_id}", status_code=204)
def remove_member(
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.MEMBER_REMOVE)),
    db: Session = Depends(get_db),
):
    MemberService(db).remove_member(company_id, user_id, current_user.id)
    return None


@router.post("/join/{invite_token}")
def join_company(
    invite_token: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    membership = MemberService(db).accept_invitation(invite_token, current_user.id)
    return {"message": "Successfully joined company", "company_id": str(membership.company_id)}
