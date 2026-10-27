from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_test_user, create_test_company, auth_headers


def test_invite_and_list_members(client: TestClient, db):
    owner = create_test_user(db, email="owner_m@example.com")
    company = create_test_company(db, owner, slug="member-co")
    resp = client.post(
        f"/api/v1/companies/{company.id}/members/invite",
        json={"email": "invitee@example.com"},
        headers=auth_headers(owner),
    )
    assert resp.status_code == 201
    assert "invite_token" in resp.json()


def test_list_members_requires_membership(client: TestClient, db):
    owner = create_test_user(db, email="owner_lm@example.com")
    outsider = create_test_user(db, email="outsider_lm@example.com")
    company = create_test_company(db, owner, slug="lm-co")
    resp = client.get(
        f"/api/v1/companies/{company.id}/members",
        headers=auth_headers(outsider),
    )
    assert resp.status_code == 403


def test_accept_invitation(client: TestClient, db):
    owner = create_test_user(db, email="owner_inv@example.com")
    invitee = create_test_user(db, email="invitee_acc@example.com")
    company = create_test_company(db, owner, slug="inv-co")

    invite_resp = client.post(
        f"/api/v1/companies/{company.id}/members/invite",
        json={"email": invitee.email},
        headers=auth_headers(owner),
    )
    token = invite_resp.json()["invite_token"]
    join_resp = client.post(f"/api/v1/companies/join/{token}", headers=auth_headers(invitee))
    assert join_resp.status_code == 200
    assert "company_id" in join_resp.json()


def test_remove_member(client: TestClient, db):
    owner = create_test_user(db, email="owner_rm@example.com")
    member = create_test_user(db, email="member_rm@example.com")
    company = create_test_company(db, owner, slug="rm-co")

    # Invite and accept
    invite = client.post(
        f"/api/v1/companies/{company.id}/members/invite",
        json={"email": member.email},
        headers=auth_headers(owner),
    )
    token = invite.json()["invite_token"]
    client.post(f"/api/v1/companies/join/{token}", headers=auth_headers(member))

    # Remove
    resp = client.delete(
        f"/api/v1/companies/{company.id}/members/{member.id}",
        headers=auth_headers(owner),
    )
    assert resp.status_code == 204
