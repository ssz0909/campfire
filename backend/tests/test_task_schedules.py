from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import uuid

import pytest
from fastapi import HTTPException
from app.config import settings
from app.models.task import OperationTask
from app.schemas.task import TaskCreate, TaskSchedule
from app.services.execution_automation import _next_schedule_at, _dispatch_scheduled_tasks
from app.services.task_service import TaskService
from tests.conftest import create_test_user, create_test_company, auth_headers


def make_schedule(db, schedule=None):
    user = create_test_user(db)
    company = create_test_company(db, user)
    template = TaskService(db).create_task(company.id, user.id, TaskCreate(
        title='每日经营分析', task_type='business_analysis',
        input_params={'goal':'分析最近7天经营，提出计划并执行', 'execution_loop':True, 'publish_platforms':['douyin']},
        schedule=schedule or TaskSchedule(time='09:00')))
    return user, company, template


def test_schedule_music_edits_and_runs_preserve_config_without_selecting_audio(db, monkeypatch):
    user,company,template=make_schedule(db)
    choose=Mock();monkeypatch.setattr('app.services.video_music.random.choice',choose)
    service=TaskService(db)
    choice={'selection_mode':'random','music_volume':0.35}
    edited=service.update_schedule(company.id,template.id,user.id,TaskCreate(
        title='每日配乐视频',task_type='video_generation',schedule=TaskSchedule(time='11:00'),
        input_params={'goal':'制作视频','video_music':choice}))
    assert edited.input_params['video_music']['selection_mode']=='random'
    run=service.run_schedule_now(company.id,template.id,user.id)
    assert run.input_params['video_music']==edited.input_params['video_music']
    run.status='completed';db.commit()
    now=datetime.now(timezone.utc)
    set_due(db,template,now-timedelta(minutes=1))
    monkeypatch.setattr('app.services.task_dispatch.dispatch_task',Mock())
    assert _dispatch_scheduled_tasks(db,now)==1
    runs=db.query(OperationTask).filter(OperationTask.id!=template.id).all()
    assert len(runs)==2
    assert all(r.input_params['video_music']==edited.input_params['video_music'] for r in runs)
    choose.assert_not_called()


def set_due(db, template, due):
    template.input_params = {**template.input_params, 'schedule': {**template.input_params['schedule'], 'next_run_at': due.isoformat()}}
    db.commit()


def test_next_daily_and_weekly_respect_beijing_and_boundary():
    now = datetime(2026,10,30,0,0,tzinfo=timezone.utc)  # Friday 08:00 Beijing
    assert _next_schedule_at({'time':'09:00'}, now) == now + timedelta(hours=1)
    at_nine = now + timedelta(hours=1)
    assert _next_schedule_at({'time':'09:00'}, at_nine) == at_nine + timedelta(days=1)
    assert _next_schedule_at({'time':'09:00','frequency':'weekly','weekdays':[0]}, now) == datetime(2026,11,2,1,0,tzinfo=timezone.utc)
    assert _next_schedule_at({'time':'09:00','frequency':'weekly','weekdays':[4]}, now) == at_nine


@pytest.mark.parametrize('bad', [{'time':'24:00'}, {'time':'9:30'}, {'frequency':'hourly'}, {'weekdays':[]}, {'weekdays':[7]}, {'timezone':'no/such-zone'}])
def test_schedule_validation(bad):
    with pytest.raises(ValueError): TaskSchedule(**bad)


def test_template_is_not_executed_on_creation_and_cannot_retry(client, db, monkeypatch):
    monkeypatch.setattr(settings,'EXECUTION_AUTOMATION_ENABLED', True)
    user = create_test_user(db); company = create_test_company(db,user)
    dispatch = Mock()
    monkeypatch.setattr('app.agent.runtime.AgentRuntime.execute_task', dispatch)
    response = client.post(f'/api/v1/companies/{company.id}/tasks', headers=auth_headers(user),json={
        'title':'每日分析','task_type':'business_analysis','input_params':{'goal':'分析昨天经营'},
        'schedule':{'frequency':'daily','time':'09:00'}})
    assert response.status_code == 201, response.text
    assert response.json()['status'] == 'scheduled'
    assert response.json()['input_params']['schedule']['next_run_at']
    dispatch.assert_not_called()
    tid = response.json()['id']
    url = f'/api/v1/companies/{company.id}/tasks/{tid}'
    response = client.put(url+'/schedule', headers=auth_headers(user),json={'enabled':False})
    assert response.status_code == 200
    assert response.json()['status'] == 'paused'
    assert not response.json()['input_params']['schedule']['enabled']
    response = client.put(url+'/schedule',headers=auth_headers(user),json={'enabled':True})
    assert response.json()['status']=='scheduled'
    assert client.post(url+'/cancel',headers=auth_headers(user)).status_code == 200
    assert client.post(url+'/retry',headers=auth_headers(user)).status_code == 400
    response=client.get(f'/api/v1/companies/{company.id}/tasks',headers=auth_headers(user),params={'status':'schedules'})
    assert response.json()['total']==0


def test_due_schedule_creates_one_distinct_run_and_catches_up_only_once(db, monkeypatch):
    user, company, template = make_schedule(db)
    now=datetime(2026,10,30,2,0,tzinfo=timezone.utc)
    set_due(db,template,now-timedelta(days=4))
    dispatched=[]
    def dispatch(db,task,user):
        dispatched.append(task.id)
        task.status='waiting_approval';db.commit()
    monkeypatch.setattr('app.services.task_dispatch.dispatch_task',dispatch)
    assert _dispatch_scheduled_tasks(db,now)==1
    assert _dispatch_scheduled_tasks(db,now)==0
    runs=db.query(OperationTask).filter(OperationTask.id!=template.id).all()
    assert len(runs)==1
    run=runs[0]
    assert run.parent_task_id is None
    assert run.company_id==company.id and run.created_by==user.id
    assert run.input_params['schedule_template_id']==str(template.id)
    assert 'schedule' not in run.input_params
    assert run.input_params['execution_loop'] is True
    assert run.input_params['publish_platforms']==['douyin']
    assert template.status=='scheduled'
    assert datetime.fromisoformat(template.input_params['schedule']['next_run_at'])>now
    assert dispatched==[run.id]
    listed,total=TaskService(db).list_tasks(company.id,schedule_template_id=template.id)
    assert total==1 and listed[0].id==run.id


def test_paused_and_revoked_owner_dont_execute(db, monkeypatch):
    user, company, template=make_schedule(db)
    now=datetime.now(timezone.utc)
    set_due(db,template,now-timedelta(minutes=2))
    template.status='paused';db.commit()
    dispatch=Mock()
    monkeypatch.setattr('app.services.task_dispatch.dispatch_task',dispatch)
    assert _dispatch_scheduled_tasks(db,now)==0
    template.status='scheduled'; user.is_active=False;db.commit()
    assert _dispatch_scheduled_tasks(db,now)==0
    assert template.status=='paused'
    assert not template.input_params['schedule']['enabled']
    dispatch.assert_not_called()


def test_running_previous_run_skips_new_due_slot(db, monkeypatch):
    user,company,template=make_schedule(db)
    now=datetime.now(timezone.utc)
    set_due(db,template,now-timedelta(minutes=2))
    run=OperationTask(company_id=company.id,created_by=user.id,title='上一轮',task_type='business_analysis',status='running',
        input_params={'schedule_template_id':str(template.id)})
    db.add(run);db.commit()
    dispatch=Mock();monkeypatch.setattr('app.services.task_dispatch.dispatch_task',dispatch)
    assert _dispatch_scheduled_tasks(db,now)==0
    assert '上一轮' in template.input_params['schedule']['last_error']
    assert db.query(OperationTask).count()==2
    dispatch.assert_not_called()


def test_pending_scheduled_run_survives_crash_before_dispatch(db, monkeypatch):
    user,company,template=make_schedule(db)
    now=datetime.now(timezone.utc)
    set_due(db,template,now+timedelta(days=1))
    run=OperationTask(company_id=company.id,created_by=user.id,title='待派发',task_type='business_analysis',status='pending',
        input_params={'schedule_template_id':str(template.id)})
    db.add(run);db.commit()
    seen=[]
    def dispatch(db,task,user):
        seen.append(task.id);task.status='waiting_approval';db.commit()
    monkeypatch.setattr('app.services.task_dispatch.dispatch_task',dispatch)
    assert _dispatch_scheduled_tasks(db,now)==0
    assert seen==[run.id]
    assert db.query(OperationTask).count()==2


def test_edit_schedule_and_run_now_leave_plan_schedule_unchanged(db, monkeypatch):
    user, company, template = make_schedule(db)
    old_next = template.input_params['schedule']['next_run_at']
    template.input_params = {**template.input_params, 'schedule': {**template.input_params['schedule'], 'last_run_at': '2026-11-04T01:00:00+00:00'}}
    db.commit()
    changed = TaskService(db).update_schedule(company.id, template.id, user.id, TaskCreate(
        title='更新后的分析', task_type='business_analysis', auto_execute=False,
        input_params={'goal':'分析本周经营', 'execution_loop':True, 'publish_platforms':['douyin']},
        schedule=TaskSchedule(time='10:30')))
    assert changed.title == '更新后的分析'
    assert changed.input_params['schedule']['time'] == '10:30'
    assert changed.input_params['schedule']['last_run_at'] == '2026-11-04T01:00:00+00:00'
    assert changed.input_params['schedule']['next_run_at'] != old_next
    next_at = changed.input_params['schedule']['next_run_at']
    run = TaskService(db).run_schedule_now(company.id, template.id, user.id)
    assert run.input_params['schedule_template_id'] == str(template.id)
    assert run.input_params['manual_schedule_run'] is True
    assert run.input_params['goal'] == '分析本周经营'
    assert 'schedule' not in run.input_params
    db.refresh(template)
    assert template.input_params['schedule']['next_run_at'] == next_at
    assert template.input_params['schedule']['last_run_at'] == '2026-11-04T01:00:00+00:00'
    with pytest.raises(HTTPException, match='未完成'):
        TaskService(db).run_schedule_now(company.id, template.id, user.id)


def test_manual_pending_run_can_recover_without_double_dispatch(db, monkeypatch):
    user, company, template = make_schedule(db)
    run = OperationTask(company_id=company.id, created_by=user.id, title='手动执行', task_type='business_analysis', status='pending',
        input_params={'schedule_template_id':str(template.id), 'manual_schedule_run':True})
    db.add(run); db.commit()
    from app.services.task_dispatch import dispatch_task
    monkeypatch.setattr(settings, 'TASK_EXECUTION_MODE', 'inline')
    execute = Mock()
    monkeypatch.setattr('app.agent.runtime.AgentRuntime.execute_task', execute)
    assert _dispatch_scheduled_tasks(db) == 0
    dispatch_task(db, run, user)
    execute.assert_called_once()


def test_schedule_edit_api_preserves_pause_and_immediate_run_does_not_resume(client, db, monkeypatch):
    user, company, template = make_schedule(db)
    template.status = 'paused'
    template.input_params = {**template.input_params, 'schedule': {**template.input_params['schedule'], 'enabled': False}}
    db.commit()
    base = f'/api/v1/companies/{company.id}/tasks/{template.id}'
    response = client.put(base+'/schedule-template', headers=auth_headers(user), json={
        'title':'每周分析', 'description':'新的说明', 'task_type':'business_analysis',
        'input_params':{'goal':'每周分析', 'generation_mode':'cost', 'reuse_policy':'fresh'},
        'schedule':{'frequency':'weekly', 'time':'15:45', 'weekdays':[1, 4]},
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'paused'
    assert result['description'] == '新的说明'
    assert result['input_params']['schedule']['enabled'] is False
    assert result['input_params']['schedule']['weekdays'] == [1, 4]
    snapshot = result['input_params']['industry_template_snapshot']
    execute = Mock()
    monkeypatch.setattr('app.api.v1.tasks.dispatch_task', execute)
    response = client.post(base+'/run-now', headers=auth_headers(user))
    assert response.status_code == 201, response.text
    assert response.json()['input_params']['industry_template_snapshot'] == snapshot
    execute.assert_called_once()
    db.refresh(template)
    assert template.status == 'paused'
    assert template.input_params['schedule'] == result['input_params']['schedule']
    assert client.post(base+'/run-now', headers=auth_headers(user)).status_code == 409


def test_schedule_management_rejects_non_templates_and_other_tenants(client, db):
    user, company, template = make_schedule(db)
    outsider = create_test_user(db, email='schedule-other@example.com')
    other = create_test_company(db, outsider, slug='schedule-other')
    payload = {'title':'不可修改', 'task_type':'business_analysis', 'schedule':{'time':'10:00'}}
    for path, expected in [(f'{company.id}/tasks/{template.id}',403), (f'{other.id}/tasks/{template.id}',404)]:
        base = '/api/v1/companies/' + path
        assert client.put(base+'/schedule-template', headers=auth_headers(outsider), json=payload).status_code == expected
        assert client.post(base+'/run-now', headers=auth_headers(outsider)).status_code == expected
    one_shot = TaskService(db).create_task(company.id, user.id, TaskCreate(title='单次任务',task_type='business_analysis'))
    base = f'/api/v1/companies/{company.id}/tasks/{one_shot.id}'
    assert client.put(base+'/schedule-template', headers=auth_headers(user), json=payload).status_code == 409
    assert client.post(base+'/run-now', headers=auth_headers(user)).status_code == 409


def test_cross_tenant_schedule_cannot_be_paused_or_listed(client,db):
    user,company,template=make_schedule(db)
    outsider=create_test_user(db,email='outsider@example.com')
    other=create_test_company(db,outsider,slug='other')
    url=f'/api/v1/companies/{company.id}/tasks/{template.id}/schedule'
    assert client.put(url,headers=auth_headers(outsider),json={'enabled':False}).status_code==403
    assert client.put(f'/api/v1/companies/{other.id}/tasks/{template.id}/schedule',headers=auth_headers(outsider),json={'enabled':False}).status_code==404
    response=client.get(f'/api/v1/companies/{other.id}/tasks',headers=auth_headers(outsider),params={'schedule_template_id':str(template.id)})
    assert response.status_code==200 and response.json()['total']==0
