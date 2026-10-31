from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from tests.conftest import create_test_user, create_test_company, auth_headers
from app.config import settings
from app.models.approval import Approval
from app.services.auto_execution import approve_video, require_authority
from app.services.execution_loop import child_params
from tests.test_execution_loop import setup, ready_project


def test_auto_task_and_default_manual(client, db, monkeypatch):
    monkeypatch.setattr(settings, 'TASK_EXECUTION_MODE', 'inline')
    user = create_test_user(db)
    company = create_test_company(db, user)
    employees = client.get(f'/api/v1/companies/{company.id}/employees', headers=auth_headers(user)).json()
    employee = next(e for e in employees if e['role_title'] == 'operations_assistant')
    path = f'/api/v1/companies/{company.id}/tasks'
    payload = {'title':'日报', 'task_type':'daily_report', 'digital_employee_id':employee['id'],
               'input_params':{'goal':'今日运营日报', 'auto_handoff':False, 'execution_loop':False}}
    manual = client.post(path, headers=auth_headers(user), json=payload)
    assert manual.status_code == 201, manual.text
    assert manual.json()['status'] == 'waiting_approval'
    auto = client.post(path, headers=auth_headers(user), json={**payload, 'auto_execute':True})
    assert auto.status_code == 201, auto.text
    assert auto.json()['status'] == 'completed'
    approval = db.get(Approval, __import__('uuid').UUID(auto.json()['output']['approval_id']))
    assert approval.status == 'approved' and '自动' in approval.review_note
    injected = client.post(path, headers=auth_headers(user), json={**payload, 'input_params':{**payload['input_params'],'auto_execute':True}})
    assert injected.json()['status'] == 'waiting_approval'


def test_inherits_with_and_without_loop(db):
    _, _, root = setup(db)
    root.input_params = {**root.input_params, 'auto_execute':True}
    assert child_params(root)['auto_execute'] is True
    root.input_params = {'auto_execute':True}
    assert child_params(root) == {'auto_execute':True}
    root.input_params = {'auto_execute':'false'}
    assert child_params(root)['auto_execute'] is False


def test_final_video_auto_review_queues_and_dispatches_once(db, monkeypatch):
    _, _, root = setup(db)
    project = ready_project(db, root)
    from app.models.task import OperationTask
    task = db.get(OperationTask, project.task_id)
    task.input_params = {**task.input_params, 'auto_execute':True}
    db.commit()
    dispatch = Mock()
    monkeypatch.setattr('app.services.execution_loop.dispatch_queued_publications', dispatch)
    approve_video(db, project)
    assert project.project_status == 'completed' and project.review_status == 'approved'
    assert project.quality_check_result['review_mode'] == 'auto_execute'
    from app.models.publishing import PublishJob
    assert len(db.query(PublishJob).filter_by(video_project_id=project.id).all()) == 2
    approve_video(db, project)
    dispatch.assert_called_once_with(db, project.id)


def test_manual_and_cancelled_video_preserved(db, monkeypatch):
    _, _, root = setup(db)
    project = ready_project(db, root)
    dispatch = Mock()
    monkeypatch.setattr('app.services.execution_loop.dispatch_queued_publications', dispatch)
    approve_video(db, project)
    assert project.project_status == 'pending_review'
    from app.models.task import OperationTask
    task = db.get(OperationTask, project.task_id)
    task.input_params = {**task.input_params,'auto_execute':True}
    root.status = 'cancelled'
    db.commit()
    with pytest.raises(HTTPException): approve_video(db, project)
    dispatch.assert_not_called()


def test_revoked_authority_does_not_auto_review(db):
    user, company, root = setup(db)
    from app.models.member import CompanyMembership
    member = db.query(CompanyMembership).filter_by(user_id=user.id, company_id=company.id).one()
    member.status = 'inactive'; db.commit()
    with pytest.raises(HTTPException) as exc: require_authority(db, company.id, user.id)
    assert exc.value.status_code == 403


def test_schedule_policy_change_only_affects_future_runs(client, db):
    user, company, root = setup(db)
    root.input_params = {'schedule':{'enabled':True}, 'auto_execute':False}
    root.status = 'scheduled'; db.commit()
    path = f'/api/v1/companies/{company.id}/tasks/{root.id}/auto-execute'
    response = client.put(path, headers=auth_headers(user), json={'enabled':True})
    assert response.status_code == 200, response.text
    assert response.json()['input_params']['auto_execute'] is True
    root.status = 'completed'; db.commit()
    assert client.put(path, headers=auth_headers(user), json={'enabled':False}).status_code == 409


def test_all_descendant_drafts_auto_approved(client, db, monkeypatch):
    import uuid
    from app.models.digital_employee import DigitalEmployee
    from app.models.task import OperationTask
    monkeypatch.setattr(settings, 'TASK_EXECUTION_MODE', 'inline')
    user, company, root = setup(db)
    employee = db.query(DigitalEmployee).filter_by(company_id=company.id,role_title='operations_manager').one()
    def workflow(self, task, context, session, runtime):
        role = session.get(DigitalEmployee, task.digital_employee_id).role_title
        return {'role':role, 'employee_name':role, 'next_actions':[],
                'data_sources':{'hotel':{'sync_coverage':{'complete':True}}}}
    monkeypatch.setattr('app.agent.workflows.operations.OperationsWorkflow.run', workflow)
    monkeypatch.setattr('app.agent.workflows.llm_draft.enrich', lambda result, *args: result)
    monkeypatch.setattr('app.services.task_handoff.create_video_handoff', lambda *args: Mock(id=uuid.uuid4()))
    start = Mock()
    monkeypatch.setattr('app.services.video_service.VideoService.start_generation', start)
    response = client.post(f'/api/v1/companies/{company.id}/tasks', headers=auth_headers(user), json={
        'title':'自动运营', 'task_type':'business_analysis', 'digital_employee_id':str(employee.id),
        'auto_execute':True, 'input_params':{'goal':'完成酒店宣传', 'execution_loop':True}})
    assert response.status_code == 201, response.text
    tasks = db.query(OperationTask).filter(OperationTask.id != root.id).all()
    assert len(tasks) == 4
    assert all(t.status == 'completed' and t.input_params['auto_execute'] is True for t in tasks)
    assert db.query(Approval).filter_by(status='pending').count() == 0
    start.assert_called_once()
