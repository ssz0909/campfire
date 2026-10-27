from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from tests.conftest import create_test_user, create_test_company, auth_headers


@pytest.fixture(autouse=True)
def celery_dispatch(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "TASK_EXECUTION_MODE", "celery")



def test_create_task(client: TestClient, db):
    owner = create_test_user(db, email="owner_task@example.com")
    company = create_test_company(db, owner, slug="task-co")

    with patch("app.worker.tasks.agent_tasks.execute_operation_task") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "mock-celery-id"
        mock_task.delay.return_value = mock_result

        resp = client.post(
            f"/api/v1/companies/{company.id}/tasks",
            json={
                "title": "Test Analysis",
                "task_type": "business_analysis",
                "description": "Run a business analysis",
            },
            headers=auth_headers(owner),
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test Analysis"
    assert data["task_type"] == "business_analysis"
    assert data["company_id"] == str(company.id)


def test_get_task(client: TestClient, db):
    owner = create_test_user(db, email="owner_gettask@example.com")
    company = create_test_company(db, owner, slug="gettask-co")

    with patch("app.worker.tasks.agent_tasks.execute_operation_task") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "mock-celery-id-2"
        mock_task.delay.return_value = mock_result

        create_resp = client.post(
            f"/api/v1/companies/{company.id}/tasks",
            json={"title": "Get Me", "task_type": "custom"},
            headers=auth_headers(owner),
        )

    task_id = create_resp.json()["id"]
    resp = client.get(
        f"/api/v1/companies/{company.id}/tasks/{task_id}",
        headers=auth_headers(owner),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == task_id


def test_list_tasks(client: TestClient, db):
    owner = create_test_user(db, email="owner_listtask@example.com")
    company = create_test_company(db, owner, slug="listtask-co")

    with patch("app.worker.tasks.agent_tasks.execute_operation_task") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "mock-id"
        mock_task.delay.return_value = mock_result

        for i in range(3):
            client.post(
                f"/api/v1/companies/{company.id}/tasks",
                json={"title": f"Task {i}", "task_type": "custom"},
                headers=auth_headers(owner),
            )

    resp = client.get(
        f"/api/v1/companies/{company.id}/tasks", headers=auth_headers(owner)
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 3


def test_cancel_task(client: TestClient, db):
    owner = create_test_user(db, email="owner_cancel@example.com")
    company = create_test_company(db, owner, slug="cancel-co")

    with patch("app.worker.tasks.agent_tasks.execute_operation_task") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "mock-cancel-id"
        mock_task.delay.return_value = mock_result

        create_resp = client.post(
            f"/api/v1/companies/{company.id}/tasks",
            json={"title": "Cancel Me", "task_type": "custom"},
            headers=auth_headers(owner),
        )

    task_id = create_resp.json()["id"]

    # Force status to 'running' so cancel is allowed
    from app.models.task import OperationTask
    import uuid
    task = db.query(OperationTask).filter(OperationTask.id == uuid.UUID(task_id)).first()
    task.status = "running"
    db.commit()

    resp = client.post(
        f"/api/v1/companies/{company.id}/tasks/{task_id}/cancel",
        headers=auth_headers(owner),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_task_status_transitions(client: TestClient, db):
    """Verify that cancelled tasks cannot be cancelled again."""
    owner = create_test_user(db, email="owner_transitions@example.com")
    company = create_test_company(db, owner, slug="transitions-co")

    with patch("app.worker.tasks.agent_tasks.execute_operation_task") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "mock-trans-id"
        mock_task.delay.return_value = mock_result

        create_resp = client.post(
            f"/api/v1/companies/{company.id}/tasks",
            json={"title": "Transition Test", "task_type": "custom"},
            headers=auth_headers(owner),
        )

    task_id = create_resp.json()["id"]
    from app.models.task import OperationTask
    import uuid
    task = db.query(OperationTask).filter(OperationTask.id == uuid.UUID(task_id)).first()
    task.status = "cancelled"
    db.commit()

    # Cancel again should fail
    resp = client.post(
        f"/api/v1/companies/{company.id}/tasks/{task_id}/cancel",
        headers=auth_headers(owner),
    )
    assert resp.status_code == 400


def test_task_tenant_isolation(client: TestClient, db):
    """User cannot access tasks belonging to another company."""
    owner_a = create_test_user(db, email="a_tasktenant@example.com")
    owner_b = create_test_user(db, email="b_tasktenant@example.com")
    company_a = create_test_company(db, owner_a, slug="a-task-iso")
    company_b = create_test_company(db, owner_b, slug="b-task-iso")

    with patch("app.worker.tasks.agent_tasks.execute_operation_task") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "iso-mock-id"
        mock_task.delay.return_value = mock_result

        create_resp = client.post(
            f"/api/v1/companies/{company_a.id}/tasks",
            json={"title": "A's Task", "task_type": "custom"},
            headers=auth_headers(owner_a),
        )

    task_id = create_resp.json()["id"]
    # owner_b tries to access company_a's task via company_b's path
    resp = client.get(
        f"/api/v1/companies/{company_b.id}/tasks/{task_id}",
        headers=auth_headers(owner_b),
    )
    assert resp.status_code == 404
