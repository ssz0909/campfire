from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_test_user, create_test_company, auth_headers


def test_owner_has_full_permissions(client: TestClient, db):
    """Company owner can access all company resources."""
    owner = create_test_user(db, email="owner_perm@example.com")
    company = create_test_company(db, owner, slug="perm-co")

    # Owner can view company
    resp = client.get(f"/api/v1/companies/{company.id}", headers=auth_headers(owner))
    assert resp.status_code == 200

    # Owner can list members
    resp = client.get(
        f"/api/v1/companies/{company.id}/members", headers=auth_headers(owner)
    )
    assert resp.status_code == 200


def test_non_member_denied(client: TestClient, db):
    """Non-member cannot access any company resource."""
    owner = create_test_user(db, email="owner_np@example.com")
    stranger = create_test_user(db, email="stranger_np@example.com")
    company = create_test_company(db, owner, slug="np-co")

    for path in [
        f"/api/v1/companies/{company.id}",
        f"/api/v1/companies/{company.id}/members",
        f"/api/v1/companies/{company.id}/assets",
        f"/api/v1/companies/{company.id}/tasks",
    ]:
        resp = client.get(path, headers=auth_headers(stranger))
        assert resp.status_code == 403, f"Expected 403 for {path}, got {resp.status_code}"


def test_cross_tenant_company_access_denied(client: TestClient, db):
    """User from one company cannot read another company's data."""
    owner_a = create_test_user(db, email="a_cross@example.com")
    owner_b = create_test_user(db, email="b_cross@example.com")
    company_a = create_test_company(db, owner_a, slug="cross-a")
    company_b = create_test_company(db, owner_b, slug="cross-b")

    # owner_a tries to access company_b
    resp = client.get(f"/api/v1/companies/{company_b.id}", headers=auth_headers(owner_a))
    assert resp.status_code == 403

    # owner_b tries to access company_a
    resp = client.get(f"/api/v1/companies/{company_a.id}", headers=auth_headers(owner_b))
    assert resp.status_code == 403


def test_unauthenticated_denied(client: TestClient, db):
    """All company endpoints require authentication."""
    owner = create_test_user(db, email="owner_auth@example.com")
    company = create_test_company(db, owner, slug="auth-co")

    resp = client.get(f"/api/v1/companies/{company.id}")
    assert resp.status_code == 401


def test_platform_admin_can_access_any_company(client: TestClient, db):
    """Platform admin has cross-tenant read access."""
    owner = create_test_user(db, email="owner_pa@example.com")
    admin = create_test_user(
        db, email="admin_pa@example.com", is_platform_admin=True
    )
    company = create_test_company(db, owner, slug="pa-co")

    resp = client.get(f"/api/v1/companies/{company.id}", headers=auth_headers(admin))
    # Platform admin has COMPANY_VIEW permission globally
    assert resp.status_code == 200
