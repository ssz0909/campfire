"""HTTP submission returns persisted state before executing agent work."""
from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_test_company, create_test_user


def test_create_sends_response_before_inline_execution(client, db, monkeypatch):
    from app.config import settings
    from app.main import app
    from app.models.task import OperationTask

    monkeypatch.setattr(settings, 'TASK_EXECUTION_MODE', 'inline')
    user = create_test_user(db, email='background-submit@example.com')
    company = create_test_company(db, user, slug='background-submit')
    events = []

    async def observe_response(scope, receive, send):
        async def observed_send(message):
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                events.append('response_sent')
            await send(message)
        await app(scope, receive, observed_send)

    def execute(task_id):
        assert events == ['response_sent']
        task = db.get(OperationTask, task_id)
        assert task.status == 'queued'
        events.append('execution_started')
        task.status = 'completed'
        db.commit()

    monkeypatch.setattr('app.services.task_dispatch._execute_inline', execute)
    response = TestClient(observe_response).post(
        f'/api/v1/companies/{company.id}/tasks',
        json={'title': '后台执行', 'task_type': 'custom'},
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    assert response.json()['status'] == 'queued'
    assert events == ['response_sent', 'execution_started']
    result = client.get(
        f"/api/v1/companies/{company.id}/tasks/{response.json()['id']}",
        headers=auth_headers(user),
    )
    assert result.json()['status'] == 'completed'


def test_background_runner_uses_own_session_and_skips_cancelled(db, monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import Mock
    from app.models.task import OperationTask
    from app.services.task_dispatch import _execute_inline

    user = create_test_user(db, email='background-cancel@example.com')
    company = create_test_company(db, user, slug='background-cancel')
    task = OperationTask(company_id=company.id, created_by=user.id,
                         title='已取消', task_type='custom', status='cancelled')
    db.add(task)
    db.commit()
    sessions = []

    @contextmanager
    def session():
        sessions.append(True)
        yield db

    monkeypatch.setattr('app.database.SessionLocal', session)
    execute = Mock()
    monkeypatch.setattr('app.agent.runtime.AgentRuntime.execute_task', execute)
    _execute_inline(task.id)
    assert sessions == [True]
    execute.assert_not_called()


def test_background_runner_updates_status_and_handles_failure(db, monkeypatch):
    from contextlib import contextmanager
    from app.models.task import OperationTask
    from app.services.task_dispatch import _execute_inline

    user = create_test_user(db, email='background-run@example.com')
    company = create_test_company(db, user, slug='background-run')
    task = OperationTask(company_id=company.id, created_by=user.id,
                         title='后台执行', task_type='custom', status='queued')
    db.add(task)
    db.commit()

    @contextmanager
    def session():
        yield db

    monkeypatch.setattr('app.database.SessionLocal', session)

    def complete(self, task_id, context):
        assert context.current_user.id == user.id
        assert context.require_company() == company.id
        db.get(OperationTask, task_id).status = 'completed'
        db.commit()

    monkeypatch.setattr('app.agent.runtime.AgentRuntime.execute_task', complete)
    _execute_inline(task.id)
    db.refresh(task)
    assert task.status == 'completed'



def test_background_runner_records_unexpected_failure(monkeypatch):
    from unittest.mock import MagicMock
    from uuid import uuid4
    from app.services.task_dispatch import _execute_inline

    db = MagicMock()
    task = MagicMock(status='queued')
    user = MagicMock(is_active=True)
    db.get.side_effect = [task, user, task]
    session = MagicMock()
    session.__enter__.return_value = db
    monkeypatch.setattr('app.database.SessionLocal', lambda: session)
    monkeypatch.setattr('app.core.permissions.get_user_permissions', lambda *args: [])

    def fail(*args):
        raise RuntimeError('simulated worker failure')

    monkeypatch.setattr('app.agent.runtime.AgentRuntime.execute_task', fail)
    _execute_inline(uuid4())
    db.rollback.assert_called_once()
    assert task.status == 'failed'
    assert task.error_message == '后台执行异常，请重新执行或联系管理员查看日志'
    db.commit.assert_called_once()
