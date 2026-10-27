from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    company_id: uuid.UUID
    role_id: uuid.UUID | None = None
    is_owner: bool
    status: str
    joined_at: datetime | None = None
    invite_email: str | None = None

    model_config = {"from_attributes": True}


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role_id: uuid.UUID | None = None


class ChangeMemberRoleRequest(BaseModel):
    role_id: uuid.UUID


class MemberWithUserResponse(MemberResponse):
    full_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
