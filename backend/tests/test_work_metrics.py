from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import uuid
from tests.conftest import create_test_user, create_test_company, auth_headers
from app.models.task import OperationTask
from app.models.publishing import PublishJob,PlatformConnection
from app.models.video_project import VideoProject
from app.models.approval import Approval
from app.models.cost import CostRecord
from app.connectors.work_metrics import extract_records, match_records
from app.services.work_metrics import summary, request_sync, sync_account


def setup(db):
    user=create_test_user(db);company=create_test_company(db,user)
    task=OperationTask(company_id=company.id,created_by=user.id,title='酒店宣传',task_type='video_generation',status='running')
    account=PlatformConnection(company_id=company.id,platform='douyin',label='酒店账号',status='authorized')
    db.add_all([task,account]);db.flush()
    video=VideoProject(company_id=company.id,created_by=user.id,task_id=task.id,title='酒店视频',creation_mode='prompt_to_video')
    db.add(video);db.flush()
    job=PublishJob(company_id=company.id,requested_by=user.id,task_id=task.id,video_project_id=video.id,platform_connection_id=account.id,title='酒店视频',status='published',provider_post_id='123')
    db.add(job);db.commit()
    return user,company,task,account,job


def test_dashboard_contract_and_company_scope(client,db):
    user,company,task,account,job=setup(db)
    approval=Approval(company_id=company.id,requested_by=user.id,resource_type='operation_task',resource_id=str(task.id),action='审核',status='pending')
    expired=Approval(company_id=company.id,requested_by=user.id,resource_type='operation_task',resource_id=str(task.id),action='已过期',status='pending',expires_at=datetime.now(timezone.utc)-timedelta(days=1))
    cost=CostRecord(company_id=company.id,provider='relay',record_type='video_generation',quantity=1,unit='requests',unit_cost_cents=250,total_cost_cents=250,is_estimate=False)
    old=CostRecord(company_id=company.id,provider='relay',record_type='video_generation',quantity=1,unit='requests',unit_cost_cents=900,total_cost_cents=900,is_estimate=False,created_at=datetime.now(timezone.utc)-timedelta(days=40))
    db.add_all([approval,expired,cost,old]);db.commit()
    res=client.get(f'/api/v1/companies/{company.id}/analytics/overview',headers=auth_headers(user))
    assert res.status_code==200,res.text
    data=res.json();assert data['active_tasks']==1 and data['pending_approvals']==1
    assert data['videos_this_month']==1 and data['total_cost_this_month_usd']==2.5
    assert data['timezone']=='Asia/Shanghai'
    taskstats=client.get(f'/api/v1/companies/{company.id}/analytics/tasks',headers=auth_headers(user)).json()
    assert taskstats['running']==1 and taskstats['completed']==0


def test_parser_preserves_work_metadata_and_precise_metric_source():
    payload={'items':[{'id':'1','description':'酒店','create_time':100, 'metrics':{'view_count':432,'like_count':0}}],
             'aweme_list':[{'aweme_id':'1','desc':'酒店','create_time':100,'statistics':{'aweme_id':'1','play_count':0,'digg_count':1}}]}
    records=extract_records(payload,'douyin')
    targets=[{'job_id':'a','post_id':'1'}]
    item=match_records(targets,records,False)['a']
    assert item['views']==432 and item['description']=='酒店' and item['likes']==0
    assert len(records)==2


def test_title_fallback_requires_complete_unique_and_near_publication():
    now=datetime.now(timezone.utc)
    targets=[{'job_id':'a','post_id':None,'title':'酒店','description':'欢迎光临','created_at':now.isoformat()}]
    records=[{'post_id':'1','description':'酒店\n欢迎光临','created_at':now.timestamp(),'views':15}]
    assert not match_records(targets,records,False)
    assert match_records(targets,records,True)['a']['views']==15
    assert not match_records(targets,records+[dict(records[0],post_id='2')],True)
    assert not match_records(targets+[dict(targets[0],job_id='b')],records,True)
    assert not match_records(targets,[dict(records[0],created_at=now.timestamp()-86400)],True)


def test_account_totals_never_count_as_work_and_duplicates_deduplicated(db):
    user,company,task,account,job=setup(db)
    job.metrics={'scope':'account','views':99999}
    db.commit()
    assert summary(db,company.id)['totals']['views'] is None
    job.metrics={**job.metrics,'work_metrics':{'views':0,'likes':4}}
    duplicate=PublishJob(company_id=company.id,requested_by=user.id,task_id=task.id,video_project_id=job.video_project_id,platform_connection_id=account.id,title='重复记录',status='published',provider_post_id='123',metrics={'work_metrics':{'views':0,'likes':4}})
    db.add(duplicate);db.commit()
    data=summary(db,company.id)
    assert data['totals']['views']==0 and data['totals']['likes']==4
    assert data['published_works']==1 and data['total']==2
    assert sum(row['duplicate'] for row in data['items'])==1
    other=create_test_company(db,user,slug='other')
    assert summary(db,other.id)['total']==0


def test_sync_stores_work_snapshot_separately_and_throttles(db,monkeypatch):
    user,company,task,account,job=setup(db)
    job.metrics={'scope':'account','views':800,'feedback_state':'done'};db.commit()
    collect=Mock(return_value={'status':'synced','items':{str(job.id):{'post_id':'123','views':45,'likes':0}}})
    monkeypatch.setattr('app.connectors.web_platform.read_work_metrics',collect)
    assert request_sync(db,company.id)==[account.id]
    assert not request_sync(db,company.id)
    sync_account(db,company.id,account.id)
    assert job.metrics['views']==800 and job.metrics['feedback_state']=='done'
    assert job.metrics['work_metrics']=={'views':45,'likes':0}
    assert summary(db,company.id)['totals']['views']==45
    collect.assert_called_once()
    assert not request_sync(db,company.id)


def test_failed_sync_preserves_last_known_counts(db,monkeypatch):
    user,company,task,account,job=setup(db)
    job.metrics={'work_metrics':{'views':55},'work_metrics_at':'2026-10-31T10:00:00+00:00'};db.commit()
    monkeypatch.setattr('app.connectors.web_platform.read_work_metrics',lambda *args,**kwargs:{'status':'login_required','items':{},'message':'请重新登录'})
    request_sync(db,company.id);sync_account(db,company.id,account.id)
    assert job.metrics['work_metrics']['views']==55 and job.metrics['work_sync_status']=='login_required'


def test_metrics_endpoint_is_tenant_scoped(client,db):
    user,company,task,account,job=setup(db)
    response=client.get(f'/api/v1/companies/{company.id}/analytics/works',headers=auth_headers(user))
    assert response.status_code==200 and response.json()['total']==1
    assert client.get(f'/api/v1/companies/{company.id}/analytics/works').status_code==401
    other=create_test_user(db,email='unrelated@example.com')
    assert client.get(f'/api/v1/companies/{company.id}/analytics/works',headers=auth_headers(other)).status_code==403


def test_delayed_publication_matches_but_does_not_claim_known_work():
    now=datetime.now(timezone.utc)
    targets=[{'job_id':'a','post_id':None,'title':'酒店','description':'欢迎光临','created_at':now.isoformat()}]
    record={'post_id':'1','description':'酒店\n欢迎光临','created_at':(now+timedelta(hours=9)).timestamp(),'views':5}
    assert match_records(targets,[record],True)['a']['views']==5
    assert not match_records(targets+[{'job_id':'b','post_id':'1'}],[record],True).get('a')


def test_dedup_uses_latest_snapshot_even_when_newest_job_not_synced(db):
    user,company,task,account,job=setup(db)
    job.metrics={'work_metrics':{'views':100},'work_metrics_at':'2026-11-02T00:00:00+00:00'}
    duplicate=PublishJob(company_id=company.id,requested_by=user.id,task_id=task.id,video_project_id=job.video_project_id,platform_connection_id=account.id,title='重复记录',status='published',provider_post_id='123')
    db.add(duplicate);db.commit()
    assert summary(db,company.id)['totals']['views']==100


def test_sync_exception_records_failure_and_preserves_counts(db,monkeypatch):
    user,company,task,account,job=setup(db)
    job.metrics={'work_metrics':{'views':55}};db.commit()
    monkeypatch.setattr('app.connectors.web_platform.read_work_metrics',Mock(side_effect=RuntimeError('transport failed')))
    from sqlalchemy.orm import Session
    request_sync(db,company.id)
    with Session(bind=db.connection(), join_transaction_mode='create_savepoint') as isolated:
        sync_account(isolated,company.id,account.id)
    db.refresh(account)
    assert account.metrics_snapshot['work_sync']['status']=='failed'
    assert job.metrics['work_metrics']['views']==55
