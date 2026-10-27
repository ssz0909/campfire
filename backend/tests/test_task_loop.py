from unittest.mock import patch, MagicMock
from tests.conftest import create_test_user, create_test_company, auth_headers
from app.config import settings

def test_inline_employee_report_and_approval(client, db, monkeypatch):
    monkeypatch.setattr(settings, 'TASK_EXECUTION_MODE', 'inline')
    owner = create_test_user(db, email='loop@example.com')
    company = create_test_company(db, owner, slug='loop-company')
    # Provision defaults through employee list endpoint
    r = client.get(f'/api/v1/companies/{company.id}/employees', headers=auth_headers(owner))
    assert r.status_code == 200 and len(r.json()) == 5
    employee = r.json()[0]
    r = client.post(f'/api/v1/companies/{company.id}/tasks', headers=auth_headers(owner), json={
        'title': '运营分析', 'task_type': 'business_analysis', 'digital_employee_id': employee['id'],
        'input_params': {'goal': '找出本周最重要的运营问题'},
    })
    assert r.status_code == 201, r.text
    task = r.json()
    assert task['status'] == 'waiting_approval'
    assert task['output']['sections']
    approval_id = task['output']['approval_id']
    r = client.post(f'/api/v1/companies/{company.id}/approvals/{approval_id}/approve', headers=auth_headers(owner), json={})
    assert r.status_code == 200, r.text
    r = client.get(f"/api/v1/companies/{company.id}/tasks/{task['id']}", headers=auth_headers(owner))
    assert r.json()['status'] == 'completed'
