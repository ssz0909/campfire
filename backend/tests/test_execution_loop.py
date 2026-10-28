import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from tests.conftest import create_test_user, create_test_company, auth_headers
from app.models.task import OperationTask
from app.models.approval import Approval
from app.models.asset import Asset
from app.models.video_project import VideoProject
from app.models.publishing import PublishJob
from app.models.digital_employee import DigitalEmployee
from app.services.execution_loop import configure, actions_for, continue_loop, snapshot, queue_publications, dispatch_queued_publications
from app.services.approval_service import ApprovalService
from app.services.publishing_service import web_publish, web_metrics, submit_publish
from app.services.video_service import VideoService
from app.config import settings


def setup(db):
    user=create_test_user(db)
    company=create_test_company(db,user)
    from app.services.digital_employee_service import DigitalEmployeeService
    DigitalEmployeeService(db).ensure_default_employees(company.id)
    root=OperationTask(company_id=company.id,created_by=user.id,title='分析酒店本年经营并执行',
        task_type='business_analysis',status='completed',input_params={'goal':'分析本年经营并执行','execution_loop':True,'publish_platforms':['douyin','wechat_channels']},
        output={'role':'operations_manager','next_actions':[]})
    db.add(root);db.commit()
    return user,company,root


def ready_project(db,root):
    task=OperationTask(company_id=root.company_id,created_by=root.created_by,parent_task_id=root.id,
        task_type='video_generation',title='视频脚本',status='completed',
        input_params={'execution_loop':True,'execution_root_id':str(root.id)},
        output={'role':'video_producer','publish_title':'发现酒店周末生活','publish_description':'实拍环境与周边漫步'})
    db.add(task);db.flush()
    asset=Asset(company_id=root.company_id,uploaded_by=root.created_by,name='成片',original_filename='clip.mp4',file_key='clip.mp4',
        asset_type='video',mime_type='video/mp4',file_size_bytes=12,processing_status='ready',is_available=True)
    db.add(asset);db.flush()
    project=VideoProject(company_id=root.company_id,created_by=root.created_by,task_id=task.id,
        title='内部任务标题',creation_mode='prompt_to_video',project_status='pending_review',output_asset_id=asset.id)
    db.add(project);db.commit()
    return project


def test_configuration_and_fixed_transitions():
    assert configure({},'分析并执行')['execution_loop']
    assert not configure({},'仅分析不要执行').get('execution_loop')
    assert configure({'execution_loop':False},'执行')['execution_loop'] is False
    with pytest.raises(HTTPException):configure({'publish_platforms':['other']},'执行')
    task=OperationTask(title='执行',input_params={'execution_loop':True})
    for role,next_role in [('operations_manager','data_analyst'),('data_analyst','content_planner'),('content_planner','video_producer')]:
        result=actions_for(task,{'role':role,'next_actions':[],'data_sources':{'hotel':{'sync_coverage':{'complete':True}}}})
        assert result['next_actions'][0]['role']==next_role
    assert actions_for(task,{'role':'data_analyst'})['execution_blocked']
    task.input_params={**task.input_params,'feedback_publish_job_id':'id'}
    assert actions_for(task,{'role':'data_analyst','next_actions':[]})['next_actions']==[]


def test_continue_old_root_idempotent_and_annual(db):
    _,_,root=setup(db)
    root.input_params={'goal':'分析本年经营并执行'}
    first=continue_loop(db,root,['douyin'])
    assert len(first)==1 and first[0].input_params['date_from'].endswith('-01-01')
    assert first[0].input_params['execution_root_id']==str(root.id)
    # Un-dispatched pending work is returned for recovery, not duplicated.
    again=continue_loop(db,root,['douyin'])
    assert [t.id for t in again]==[first[0].id]
    first[0].status='waiting_approval';db.commit()
    assert continue_loop(db,root,['douyin'])==[]
    first[0].status='completed';first[0].output={'role':'data_analyst','execution_blocked':'gap'};db.commit()
    assert continue_loop(db,root,['douyin'])[0].status=='pending'


def test_approved_video_queues_publications_without_second_approval(db,monkeypatch):
    _,_,root=setup(db);project=ready_project(db,root)
    publish=Mock();monkeypatch.setattr('app.connectors.web_platform.publish',publish)
    VideoService(db).approve_project(root.company_id,project.id,root.created_by)
    jobs=db.query(PublishJob).all()
    assert len(jobs)==2 and all(j.status=='queued' for j in jobs)
    assert all('发现酒店周末生活' in j.title and 'Test Company' in j.description for j in jobs)
    assert not db.query(Approval).filter_by(resource_type='publish_job').all()
    assert len(queue_publications(db,project))==2
    assert db.query(PublishJob).count()==2
    publish.assert_not_called()
    assert snapshot(db,root)['status']=='in_progress'


def test_publication_metrics_and_review_close_loop(db,monkeypatch):
    user,_,root=setup(db);project=ready_project(db,root)
    VideoService(db).approve_project(root.company_id,project.id,user.id)
    publish=Mock(return_value={'status':'published','provider_post_id':'real-observed-id'})
    monkeypatch.setattr('app.connectors.web_platform.publish',publish)
    monkeypatch.setattr('app.connectors.web_platform.read_metrics',lambda *a:{'metrics':{'views':0,'likes':0}})
    dispatch=Mock();monkeypatch.setattr('app.services.task_dispatch.dispatch_task',dispatch)
    dispatch_queued_publications(db)
    dispatch_queued_publications(db)
    assert publish.call_count==2
    assert snapshot(db,root)['status']!='completed'
    for job in db.query(PublishJob).all():
        assert job.metrics['feedback_due_at']
        web_metrics(db,root.company_id,job.id);web_metrics(db,root.company_id,job.id)
        assert job.metrics['scope']=='account'
        task=db.get(OperationTask,uuid.UUID(job.metrics['feedback_task_id']))
        assert task.parent_task_id==project.task_id and task.input_params['auto_handoff'] is False
        task.status='completed';db.commit()
    assert dispatch.call_count==2
    assert snapshot(db,root)['status']=='completed'


def test_mutated_or_cancelled_publish_is_blocked(db,monkeypatch):
    user,_,root=setup(db);project=ready_project(db,root)
    VideoService(db).approve_project(root.company_id,project.id,user.id)
    job=db.query(PublishJob).first()
    job.title='被篡改';db.commit()
    with pytest.raises(HTTPException):web_publish(db,root.company_id,job.id)
    job.title=project.quality_check_result['approved_publication']['title'];root.status='cancelled';db.commit()
    with pytest.raises(HTTPException):web_publish(db,root.company_id,job.id)


def test_scheduler_persists_bounded_retries(db,monkeypatch):
    _,_,root=setup(db);project=ready_project(db,root)
    VideoService(db).approve_project(root.company_id,project.id,root.created_by)
    jobs=db.query(PublishJob).all()
    now=datetime.now(timezone.utc)
    for job in jobs:
        job.status='published';job.metrics={'feedback_due_at':now.isoformat()}
    db.commit()
    read=Mock(return_value={'metrics':{},'message':'登录已过期'})
    monkeypatch.setattr('app.connectors.web_platform.read_metrics',read)
    from app.services.execution_automation import collect_due
    for i in range(3):assert collect_due(db,now+timedelta(hours=i))==2
    assert collect_due(db,now+timedelta(hours=4))==0
    assert read.call_count==6
    assert all(j.metrics['feedback_state']=='manual_required' and j.status=='published' for j in jobs)
    assert snapshot(db,root)['status']=='blocked'


def test_execution_endpoint_tenant_scope(client,db):
    user,company,root=setup(db)
    base=f'/api/v1/companies/{company.id}/tasks/{root.id}/execution'
    response=client.get(base,headers=auth_headers(user))
    assert response.status_code==200 and response.json()['root_id']==str(root.id)
    other=create_test_user(db,email='other@example.com')
    assert client.get(base,headers=auth_headers(other)).status_code in (403,404)
    assert client.post(base+'/continue',headers=auth_headers(user),json={'publish_platforms':['bad']}).status_code==422


def test_full_chain_from_manager_through_feedback_approval(client,db,monkeypatch):
    user,company,_=setup(db)
    from tests.test_asset_intelligence import make_asset
    make_asset(db,company,user,'酒店环境','landscape',[],'酒店真实山景')
    monkeypatch.setattr('app.services.video_generation.reference_url',lambda *a,**k:'https://test.invalid/reference')
    headers=auth_headers(user);base=f'/api/v1/companies/{company.id}'
    monkeypatch.setattr(settings,'TASK_EXECUTION_MODE','inline')
    monkeypatch.setattr('app.agent.tools.hotel_data_scope.ensure_analysis_orders',lambda *a:{'complete':True,'notes':[],'sync_job_ids':[]})
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    enqueue=Mock();monkeypatch.setattr('app.services.video_generation.enqueue',enqueue)
    manager=db.query(DigitalEmployee).filter_by(company_id=company.id,role_title='operations_manager').one()
    response=client.post(base+'/tasks',headers=headers,json={'title':'本年经营分析并执行','task_type':'business_analysis',
        'digital_employee_id':str(manager.id),'input_params':{'goal':'分析本年度并执行','execution_loop':True,'publish_platforms':['douyin','wechat_channels']}})
    assert response.status_code==201,response.text
    current=response.json();root_id=current['id']
    for role in ('operations_manager','data_analyst','content_planner','video_producer'):
        assert current['output']['role']==role
        response=client.post(base+f"/approvals/{current['output']['approval_id']}/approve",headers=headers,json={})
        assert response.status_code==200,response.text
        current=client.get(base+f"/tasks/{current['id']}",headers=headers).json()
        if role!='video_producer':
            current=client.get(base+f"/tasks/{current['output']['handoff_task_ids'][0]}",headers=headers).json()
    assert enqueue.call_count==1
    project=db.get(VideoProject,uuid.UUID(current['output']['video_project_id']))
    fixture=ready_project(db,db.get(OperationTask,uuid.UUID(root_id)))
    project.output_asset_id=fixture.output_asset_id;project.project_status='pending_review';db.delete(fixture);db.commit()
    VideoService(db).approve_project(company.id,project.id,user.id)
    monkeypatch.setattr('app.connectors.web_platform.publish',lambda *a:{'status':'published'})
    monkeypatch.setattr('app.connectors.web_platform.read_metrics',lambda *a:{'metrics':{'views':10}})
    jobs=db.query(PublishJob).filter_by(video_project_id=project.id).all()
    assert len(jobs)==2
    dispatch_queued_publications(db)
    for job in jobs:
        web_metrics(db,company.id,job.id)
        feedback=db.get(OperationTask,uuid.UUID(job.metrics['feedback_task_id']))
        assert feedback.status=='waiting_approval'
        ApprovalService(db).approve(company.id,uuid.UUID(feedback.output['approval_id']),user.id)
        assert not feedback.output.get('handoff_task_ids')
    assert snapshot(db,db.get(OperationTask,uuid.UUID(root_id)))['status']=='completed'
