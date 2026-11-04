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
    monkeypatch.setattr('app.connectors.web_metrics_api.read_work_metrics',collect)
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
    monkeypatch.setattr('app.connectors.web_metrics_api.read_work_metrics',lambda *args,**kwargs:{'status':'login_required','items':{},'message':'请重新登录'})
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
    monkeypatch.setattr('app.connectors.web_metrics_api.read_work_metrics',Mock(side_effect=RuntimeError('transport failed')))
    from sqlalchemy.orm import Session
    request_sync(db,company.id)
    with Session(bind=db.connection(), join_transaction_mode='create_savepoint') as isolated:
        sync_account(isolated,company.id,account.id)
    db.refresh(account)
    assert account.metrics_snapshot['work_sync']['status']=='failed'
    assert job.metrics['work_metrics']['views']==55


def test_creator_scroll_list_collects_until_total_reached(monkeypatch):
    from app.connectors import web_platform as web
    now=datetime.now(timezone.utc)
    page=Mock(url="https://creator.douyin.com/creator-micro/content/manage");page.locator.return_value.count.return_value=0
    page.get_by_text.return_value.count.return_value=0
    context=Mock();context.new_page.return_value=page
    session={'page':Mock(),'context':context}
    monkeypatch.setattr(web,'_ensure_open',lambda *args:None)
    monkeypatch.setattr(web,'_get_session',lambda *args:session)
    monkeypatch.setattr(web,'_metrics_page_status',lambda *args:{'login_required':False})
    monkeypatch.setattr(web,'_page_text',lambda *args,**kwargs:'内容管理')
    observer={}
    page.on.side_effect=lambda event,callback:observer.update(response=callback)
    def deliver(identifier,text):
        response=Mock(url='https://creator.douyin.com/janus/douyin/creator/pc/work_list',status=200)
        response.json.return_value={'status_code':0,'has_more':True,'total':2,
            'items':[{'id':identifier,'description':text,'create_time':now.timestamp(), 'metrics':{'view_count':45}}]}
        observer['response'](response)
    page.goto.side_effect=lambda *args,**kwargs:deliver('1','酒店A')
    page.mouse.wheel.side_effect=lambda *args:deliver('2','酒店B')
    targets=[{'job_id':'a','post_id':None,'title':'酒店A','description':'','created_at':now.isoformat()}]
    result=web.read_work_metrics.__wrapped__(uuid.uuid4(),'douyin',targets)
    assert result['items']['a']['views']==45
    page.mouse.wheel.assert_called_once()
    page.close.assert_called_once()


def test_creator_scan_rejects_wrong_account(monkeypatch):
    from app.connectors import web_platform as web
    session={'page':Mock(),'context':Mock()}
    monkeypatch.setattr(web,'_ensure_open',lambda *args:None)
    monkeypatch.setattr(web,'_get_session',lambda *args:session)
    monkeypatch.setattr(web,'_metrics_page_status',lambda *args:{'login_required':False,'account_fingerprint':'other'})
    result=web.read_work_metrics.__wrapped__(uuid.uuid4(),'douyin',[],expected_account_id='expected')
    assert result['status']=='login_required'
    session['context'].new_page.return_value.close.assert_called_once()
    session['page'].goto.assert_not_called()


def test_channels_201_and_numbered_pages_collect_all_works_without_touching_editor(monkeypatch):
    from app.connectors import web_platform as web
    now=datetime.now(timezone.utc)
    editor=Mock(url='https://channels.weixin.qq.com/platform/post/create')
    page=Mock(url='https://channels.weixin.qq.com/platform')
    context=Mock();context.new_page.return_value=page
    session={'page':editor,'context':context}
    save=Mock(return_value=True)
    monkeypatch.setattr(web,'_save_session',save)
    monkeypatch.setattr(web,'_ensure_open',lambda *args:None)
    monkeypatch.setattr(web,'_get_session',lambda *args:session)
    monkeypatch.setattr(web,'session_status',Mock(side_effect=AssertionError('must not inspect editor')))
    monkeypatch.setattr(web,'_metrics_page_status',lambda platform,probe:{'login_required':False,'identity_verified':True,'account_fingerprint':'bound'})
    monkeypatch.setattr(web,'_page_text',lambda *args,**kwargs:'视频号ID 内容管理')
    observer={}
    page.on.side_effect=lambda event,callback:observer.update(response=callback)
    request=Mock();request.post_data_json={'currentPage':1,'pageSize':1,'rawKeyBuff':'private-test-value','scene':3}
    def payload(identifier,more):
        return {'errCode':0,'data':{'totalCount':2,'continueFlag':more,'list':[
            {'objectId':identifier,'status':1,'createTime':now.timestamp(),
             'desc':{'description':'酒店\n欢迎光临'},'readCount':25,'likeCount':0,'commentCount':2,'forwardCount':1}]}}
    response=Mock(url='https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list',status=201)
    response.request=request;response.json.return_value=payload('old',True)
    page.goto.side_effect=lambda *args,**kwargs:observer['response'](response)
    next_response=Mock(status=201);next_response.json.return_value=payload('wanted',False)
    context.request.fetch.return_value=next_response
    targets=[{'job_id':'a','post_id':'wanted'}]
    result=web.read_work_metrics.__wrapped__('company','wechat_channels',targets,'bound')
    assert result['status']=='synced' and result['list_complete'] and result['record_count']==2
    assert result['items']['a']['views']==25
    assert session['authenticated'] and session['session_saved']
    save.assert_called_once()
    context.request.fetch.assert_called_once_with(request,data={**request.post_data_json,'currentPage':2},timeout=20000)
    assert request.post_data_json['currentPage']==1
    editor.goto.assert_not_called();editor.close.assert_not_called()
    page.close.assert_called_once()


def test_channels_identity_unavailable_is_transient_not_logout(monkeypatch):
    from app.connectors import web_platform as web
    context=Mock();session={'page':Mock(),'context':context}
    monkeypatch.setattr(web,'_ensure_open',lambda *args:None)
    monkeypatch.setattr(web,'_get_session',lambda *args:session)
    monkeypatch.setattr(web,'_wait_for_account_ready',lambda *args,**kwargs:{'status':'login_required','login_required':True,'identity_unavailable':True})
    result=web.read_work_metrics.__wrapped__('company','wechat_channels',[],'bound')
    assert result['status']=='identity_unavailable' and '无需退出账号' in result['message']
    assert '上传' not in result['message']
    context.request.fetch.assert_not_called()
    context.new_page.return_value.close.assert_called_once()


def test_missing_known_work_is_reported_without_overwriting_previous_values(db,monkeypatch):
    user,company,task,account,job=setup(db)
    job.metrics={'work_metrics':{'views':55}};db.commit()
    result={'status':'partial','items':{},'record_count':2,'list_complete':True,
            'message':'读取完整','unmatched_messages':{str(job.id):'当前账号未找到此作品 ID'}}
    monkeypatch.setattr('app.connectors.web_metrics_api.read_work_metrics',lambda *args,**kwargs:result)
    request_sync(db,company.id);sync_account(db,company.id,account.id)
    assert job.metrics['work_metrics']['views']==55
    assert job.metrics['work_sync_status']=='unmatched'
    assert job.metrics['work_sync_message']=='当前账号未找到此作品 ID'
    assert account.metrics_snapshot['work_sync']['record_count']==2
    assert account.metrics_snapshot['work_sync']['list_complete'] is True


def test_channels_page_cap_does_not_claim_complete_or_match_title(monkeypatch):
    from app.connectors import web_platform as web
    now=datetime.now(timezone.utc)
    context=Mock();page=Mock(url='https://channels.weixin.qq.com/platform');context.new_page.return_value=page
    monkeypatch.setattr(web,'_ensure_open',lambda *args:None)
    monkeypatch.setattr(web,'_get_session',lambda *args:{'page':Mock(),'context':context})
    monkeypatch.setattr(web,'_metrics_page_status',lambda *args:{'login_required':False})
    monkeypatch.setattr(web,'_page_text',lambda *args,**kwargs:'视频号ID')
    handler={};page.on.side_effect=lambda event,callback:handler.update(response=callback)
    response=Mock(url='https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list',status=201)
    response.request.post_data_json={'currentPage':1}
    response.json.return_value={'errCode':0,'data':{'totalCount':50,'continueFlag':True,'list':[
        {'objectId':'one','desc':{'description':'酒店'},'createTime':now.timestamp(),'readCount':1}]}}
    page.goto.side_effect=lambda *args,**kwargs:handler['response'](response)
    context.request.fetch.return_value=response  # provider repeats the same page
    result=web.read_work_metrics.__wrapped__('company','wechat_channels',[
        {'job_id':'a','post_id':None,'title':'酒店','description':'','created_at':now.isoformat()}])
    assert result['status']=='unmatched' and not result['list_complete'] and not result['items']
    assert '尚未读完整' in result['message']
    context.request.fetch.assert_called_once()


def test_work_without_metrics_counts_as_read_not_missing(monkeypatch):
    from app.connectors import web_platform as web
    context=Mock();page=Mock(url='https://channels.weixin.qq.com/platform');context.new_page.return_value=page
    monkeypatch.setattr(web,'_ensure_open',lambda *args:None)
    monkeypatch.setattr(web,'_get_session',lambda *args:{'page':Mock(),'context':context})
    monkeypatch.setattr(web,'_metrics_page_status',lambda *args:{'login_required':False})
    monkeypatch.setattr(web,'_page_text',lambda *args,**kwargs:'视频号ID')
    handler={};page.on.side_effect=lambda event,callback:handler.update(response=callback)
    response=Mock(url='https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list',status=201)
    response.json.return_value={'errCode':0,'data':{'totalCount':1,'continueFlag':False,'list':[{'objectId':'known','desc':{'description':'酒店'}}]}}
    page.goto.side_effect=lambda *args,**kwargs:handler['response'](response)
    result=web.read_work_metrics.__wrapped__('company','wechat_channels',[{'job_id':'a','post_id':'known'}])
    assert result['record_count']==1 and result['list_complete']
    assert result['status']=='metrics_unavailable' and not result['items']
    assert '已找到作品' in result['unmatched_messages']['a']
