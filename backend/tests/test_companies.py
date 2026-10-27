from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_test_user, create_test_company, auth_headers


def test_create_company(client: TestClient, db):
    user = create_test_user(db, email="owner@example.com")
    resp = client.post(
        "/api/v1/companies",
        json={"name": "Acme Corp", "slug": "acme-corp"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme-corp"
    assert data["owner_id"] == str(user.id)


def test_create_company_without_slug(client: TestClient, db):
    user = create_test_user(db, email="owner_auto_slug@example.com")
    resp = client.post(
        "/api/v1/companies",
        json={"name": "安吉雲中溪", "industry": "other"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "安吉雲中溪"


def test_generated_company_slugs_are_unique(client: TestClient, db):
    user = create_test_user(db, email="owner_same_name@example.com")
    headers = auth_headers(user)
    slugs = []
    for _ in range(2):
        resp = client.post("/api/v1/companies", json={"name": "Same Name"}, headers=headers)
        assert resp.status_code == 201
        slugs.append(resp.json()["slug"])
    assert slugs[0] != slugs[1]


def test_create_company_duplicate_slug(client: TestClient, db):
    user = create_test_user(db, email="owner2@example.com")
    create_test_company(db, user, slug="existing-slug")
    resp = client.post(
        "/api/v1/companies",
        json={"name": "Another Corp", "slug": "existing-slug"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 409


def test_list_companies(client: TestClient, db):
    user = create_test_user(db, email="list@example.com")
    create_test_company(db, user, name="Company A", slug="company-a")
    create_test_company(db, user, name="Company B", slug="company-b")
    resp = client.get("/api/v1/companies", headers=auth_headers(user))
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Company A" in names
    assert "Company B" in names


def test_get_company(client: TestClient, db):
    user = create_test_user(db, email="getco@example.com")
    company = create_test_company(db, user, name="Get Corp", slug="get-corp")
    resp = client.get(f"/api/v1/companies/{company.id}", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(company.id)


def test_get_company_not_member(client: TestClient, db):
    """User B cannot access User A's company."""
    owner = create_test_user(db, email="owner_a@example.com")
    other = create_test_user(db, email="other_b@example.com")
    company = create_test_company(db, owner, slug="private-co")
    resp = client.get(f"/api/v1/companies/{company.id}", headers=auth_headers(other))
    assert resp.status_code == 403


def test_update_company(client: TestClient, db):
    user = create_test_user(db, email="update@example.com")
    company = create_test_company(db, user, slug="update-co")
    resp = client.put(
        f"/api/v1/companies/{company.id}",
        json={"name": "Updated Name"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


def test_tenant_isolation(client: TestClient, db):
    """User A's company is invisible to User B's list."""
    user_a = create_test_user(db, email="a_isolation@example.com")
    user_b = create_test_user(db, email="b_isolation@example.com")
    create_test_company(db, user_a, name="A Corp", slug="a-corp-iso")
    resp = client.get("/api/v1/companies", headers=auth_headers(user_b))
    assert resp.status_code == 200
    assert all(c["owner_id"] != str(user_a.id) for c in resp.json())
