from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.base import Base
from app.models.user import User
from app.models.company import Company
from app.models.member import CompanyMembership
from app.core.security import create_access_token, get_password_hash

# Use SQLite in-memory for tests — no PostgreSQL required
SQLALCHEMY_TEST_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# SQLite doesn't support uuid_generate_v4(); patch server_default to use Python default
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def isolate_model_credentials(monkeypatch):
    # Unit tests must never call paid services using the developer's .env.
    from app.config import settings
    for name in ('LLM_BASE_URL', 'LLM_MODEL', 'LLM_API_KEY', 'VIDEO_BASE_URL', 'VIDEO_MODEL', 'VIDEO_API_KEY'):
        monkeypatch.setattr(settings, name, '')
    monkeypatch.setattr('app.services.video_generation.recover', lambda: None)
    monkeypatch.setattr(settings, 'EXECUTION_AUTOMATION_ENABLED', False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once per test session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """Provide a clean DB session per test, rolling back after each."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db):
    """TestClient with DB override."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def create_test_user(
    db,
    email: str = "test@example.com",
    password: str = "password123",
    full_name: str = "Test User",
    is_platform_admin: bool = False,
) -> User:
    import uuid
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        is_active=True,
        is_platform_admin=is_platform_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_test_company(db, owner: User, name: str = "Test Company", slug: str = "test-company") -> Company:
    import uuid
    from datetime import datetime, timezone
    company = Company(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name=name,
        slug=slug,
        is_active=True,
    )
    db.add(company)
    db.flush()

    membership = CompanyMembership(
        id=uuid.uuid4(),
        user_id=owner.id,
        company_id=company.id,
        is_owner=True,
        status="active",
        joined_at=datetime.now(timezone.utc),
    )
    db.add(membership)
    db.commit()
    db.refresh(company)
    return company


def auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}
