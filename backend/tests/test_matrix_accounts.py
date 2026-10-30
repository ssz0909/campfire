import uuid
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import HTTPException
from app.models.publishing import PlatformConnection, PublishJob
from app.models.task import OperationTask
from app.services.publishing_service import get_connection, get_account, resolve_publish_accounts, web_status, web_publish, close_web, web_metrics
from app.services.execution_loop import queue_publications, child_params, continue_loop
from app.services.task_service import TaskService
from app.schemas.task import TaskCreate, TaskSchedule
from tests.conftest import create_test_user, create_test_company, auth_headers
from tests.test_execution_loop import setup, ready_project


def add(db, company, platform, label):
    row=PlatformConnection(company_id=company.id,platform=platform,label=label,session_profile=str(uuid.uuid4()),status='session_saved')
    db.add(row);db.commit()
    return row


def test_four_accounts_routes_and_tenant_isolation(client, db, monkeypatch):
    user=create_test_user(db);company=create_test_company(db,user)
    base=f'/api/v1/companies/{company.id}/publishing'
    rows=[]
    for platform in ['douyin','wechat_channels']:
        for number in [1,2]:
            r=client.post(base+'/accounts',headers=auth_headers(user),json={'platform':platform,'label':f'{platform}{number}'})
            assert r.status_code==201,r.text
            assert 'encrypted_credentials' not in r.json() and 'session_profile' not in r.json()
            rows.append(r.json())
    assert len(client.get(base+'/accounts',headers=auth_headers(user)).json())==4
    assert len({db.get(PlatformConnection,uuid.UUID(row['id'])).session_profile for row in rows})==4
    assert client.post(base+'/douyin/web/start',headers=auth_headers(user)).status_code==409
    calls=[]
    monkeypatch.setattr('app.connectors.web_platform.start_session',lambda c,p,**kw: calls.append((c,p,kw)) or {'status':'browser_open'})
    r=client.post(base+'/douyin/web/start',headers=auth_headers(user),params={'connection_id':rows[1]['id']})
    assert r.status_code==200
    assert calls[0][2]['profile_id']==db.get(PlatformConnection,uuid.UUID(rows[1]['id'])).session_profile
    outsider=create_test_user(db,email='other@example.com');other=create_test_company(db,outsider,slug='other')
    wrong=f'/api/v1/companies/{other.id}/publishing/douyin/web/start'
    assert client.post(wrong,headers=auth_headers(outsider),params={'connection_id':rows[1]['id']}).status_code==404
    assert len(calls)==1
    assert client.get(base+'/accounts',headers=auth_headers(outsider)).status_code==403
    assert client.patch(base+'/accounts/'+rows[1]['id'],headers=auth_headers(user),json={'label':'新备注'}).status_code==200


def test_tasks_pin_exact_account_targets_and_handoff(db):
    user,company,root=setup(db)
    d1=add(db,company,'douyin','抖音1');d2=add(db,company,'douyin','抖音2')
    w1=add(db,company,'wechat_channels','视频号1');w2=add(db,company,'wechat_channels','视频号2')
    for targets in [[d1,w1],[d2],[w2]]:
        task=TaskService(db).create_task(company.id,user.id,TaskCreate(title='矩阵任务',task_type='business_analysis',
            input_params={'goal':'酒店推广','execution_loop':True,'publish_account_ids':[str(a.id) for a in targets]},
            schedule=TaskSchedule() if targets==[d2] else None))
        assert task.input_params['publish_account_ids']==[str(a.id) for a in targets]
        assert child_params(task)['publish_account_ids']==task.input_params['publish_account_ids']
        assert set(task.input_params['publish_platforms'])=={a.platform for a in targets}
    with pytest.raises(HTTPException) as e: resolve_publish_accounts(db,company.id,{'publish_platforms':['douyin']})
    assert e.value.status_code==409
    other_user=create_test_user(db,email='other@example.com');other=create_test_company(db,other_user,slug='other')
    with pytest.raises(HTTPException): resolve_publish_accounts(db,other.id,{'publish_account_ids':[str(d1.id)]})


def test_fanout_unique_per_account_and_no_target_switch_after_queue(db):
    user,company,root=setup(db)
    rows=[add(db,company,'douyin','抖音1'),add(db,company,'douyin','抖音2'),add(db,company,'wechat_channels','视频号1')]
    root.input_params={**root.input_params,'publish_account_ids':[str(row.id) for row in rows]}
    project=ready_project(db,root);project.review_status='approved';project.project_status='completed';db.commit()
    jobs=queue_publications(db,project);db.commit()
    assert len(jobs)==3 and len({j.request_key for j in jobs})==3
    assert {j.platform_connection_id for j in jobs}=={row.id for row in rows}
    assert {j.content_snapshot['account_label'] for j in jobs}=={'抖音1','抖音2','视频号1'}
    assert {j.id for j in queue_publications(db,project)}=={j.id for j in jobs}
    with pytest.raises(HTTPException) as e: continue_loop(db,root,[],[str(rows[0].id)])
    assert e.value.status_code==409


def test_web_publish_and_metrics_route_to_exact_profile(db,monkeypatch,tmp_path):
    user,company,root=setup(db)
    first=add(db,company,'douyin','账号1');second=add(db,company,'douyin','账号2')
    root.input_params={**root.input_params,'publish_account_ids':[str(second.id)]}
    project=ready_project(db,root)
    from app.services.video_service import VideoService
    VideoService(db).approve_project(company.id,project.id,user.id)
    job=db.query(PublishJob).one()
    assert job.platform_connection_id==second.id
    from app.models.asset import Asset
    from app.config import settings
    monkeypatch.setattr(settings,'LOCAL_STORAGE_PATH',str(tmp_path))
    monkeypatch.setattr(settings,'STORAGE_BACKEND','local')
    calls=[]
    def publish(*args,**kwargs):
        calls.append(kwargs);return {'status':'published','provider_post_id':'test-post'}
    monkeypatch.setattr('app.connectors.web_platform.publish',publish)
    assert web_publish(db,company.id,job.id).status=='published'
    assert calls==[{'profile_id':second.session_profile}]
    seen=[]
    monkeypatch.setattr('app.connectors.web_platform.read_metrics',lambda *a,**kw:seen.append(kw) or {'metrics':{'views':12}})
    monkeypatch.setattr('app.services.task_dispatch.dispatch_task',lambda *args:None)
    web_metrics(db,company.id,job.id)
    assert seen==[{'profile_id':second.session_profile}]
    assert job.metrics['platform_connection_id']==str(second.id)
    assert first.status=='session_saved'


def test_logout_only_selected_account_and_identity_cannot_rebind(db,monkeypatch):
    user=create_test_user(db);company=create_test_company(db,user)
    first=add(db,company,'douyin','账号1');second=add(db,company,'douyin','账号2')
    second.account_id='websha256:original';db.commit()
    monkeypatch.setattr('app.connectors.web_platform.session_status',lambda *a,**kw:{'status':'authorized','account_fingerprint':'websha256:other'})
    assert web_status(db,company.id,'douyin',second.id)['status']=='login_required'
    assert second.account_id=='websha256:original'
    calls=[]
    monkeypatch.setattr('app.connectors.web_platform.close_session',lambda *a,**kw:calls.append(kw) or {'status':'disconnected'})
    close_web(db,company.id,'douyin',second.id)
    assert calls==[{'logout':True,'profile_id':second.session_profile}]
    assert first.status=='session_saved' and second.status=='disconnected'
    assert second.account_id=='websha256:original'


def test_browser_account_paths_and_nested_operations_are_isolated(monkeypatch,tmp_path):
    from app.connectors import web_platform as web
    from app.config import settings
    monkeypatch.setattr(settings,'LOCAL_STORAGE_PATH',str(tmp_path))
    first=str(uuid.uuid4());second=str(uuid.uuid4())
    @web.browser_operation
    def inner():return web._session_key('company','douyin'),web._profile_dir('company','douyin')
    @web.browser_operation
    def inspect():
        own=inner();other=inner(profile_id=second);restored=inner()
        return own,other,restored
    own,other,restored=inspect(profile_id=first)
    legacy=inner()
    assert own==restored and own!=other
    assert str(first) in str(own[1]) and str(second) in str(other[1])
    assert not own[1].is_relative_to(legacy[1])
    assert legacy[0]=='company:douyin'
    assert first in own[0] and second in other[0]


def test_wrong_bound_identity_stops_before_upload(monkeypatch):
    from app.connectors import web_platform as web
    monkeypatch.setattr(web,'_ensure_open',lambda *a:None)
    monkeypatch.setattr(web,'_get_session',lambda *a:{'page':object()})
    monkeypatch.setattr(web,'session_status',lambda *a:{'login_required':False,'account_fingerprint':'wrong'})
    result=web.publish.__wrapped__('tenant','douyin','title','copy','file',expected_account_id='expected')
    assert result['status']=='login_required'
    result=web.read_metrics.__wrapped__('tenant','douyin',expected_account_id='expected')
    assert result['status']=='login_required' and not result['metrics']
