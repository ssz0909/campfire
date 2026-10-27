from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_test_user, auth_headers


def test_register_success(client: TestClient):
    resp = client.post("/api/v1/auth/register", json={
        "email": "newuser@example.com",
        "password": "password123",
        "full_name": "New User",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "newuser@example.com"


def test_register_duplicate_email(client: TestClient, db):
    create_test_user(db, email="dup@example.com")
    resp = client.post("/api/v1/auth/register", json={
        "email": "dup@example.com",
        "password": "password123",
        "full_name": "Dup User",
    })
    assert resp.status_code == 409


def test_login_success(client: TestClient, db):
    create_test_user(db, email="login@example.com", password="mypassword")
    resp = client.post("/api/v1/auth/login", json={
        "email": "login@example.com",
        "password": "mypassword",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password(client: TestClient, db):
    create_test_user(db, email="wrongpw@example.com", password="correct")
    resp = client.post("/api/v1/auth/login", json={
        "email": "wrongpw@example.com",
        "password": "wrong",
    })
    assert resp.status_code == 401


def test_login_unknown_email(client: TestClient):
    resp = client.post("/api/v1/auth/login", json={
        "email": "nobody@example.com",
        "password": "password",
    })
    assert resp.status_code == 401


def test_refresh_token(client: TestClient, db):
    create_test_user(db, email="refresh@example.com", password="pw123")
    login = client.post("/api/v1/auth/login", json={
        "email": "refresh@example.com",
        "password": "pw123",
    })
    refresh_token = login.json()["refresh_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_invalid_token(client: TestClient):
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


def test_me_authenticated(client: TestClient, db):
    user = create_test_user(db, email="me@example.com")
    resp = client.get("/api/v1/auth/me", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


def test_me_unauthenticated(client: TestClient):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
