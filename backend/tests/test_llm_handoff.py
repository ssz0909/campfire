import json
from unittest.mock import AsyncMock
import pytest
from app.config import settings
from app.agent.workflows.llm_draft import enrich
from app.agent.runtime import AgentRuntime
from app.models.task import OperationTask
from app.services.task_handoff import create_handoffs, create_video_handoff
from tests.conftest import create_test_user, create_test_company

@pytest.mark.parametrize('script', [
    '酒店开场\n泳池体验',
    {'title':'酒店短片','scenes':[{'duration':2,'description':'泳池体验'}]},
    [{'description':'酒店开场'}, {'description':'泳池体验'}],
])
def test_script_string_and_structured_relay_outputs(script):
    from app.agent.workflows.llm_draft import Draft
    draft=Draft.model_validate({'sections':[{'title':'交付','content':'脚本'}],'video_script':script})
    assert isinstance(draft.video_script,str)
    assert '泳池体验' in draft.video_script

def test_structured_script_does_not_bypass_length_or_storyboard_validation():
    from app.agent.workflows.llm_draft import Draft
    with pytest.raises(ValueError):
        Draft.model_validate({'sections':[{'title':'交付','content':'脚本'}],'video_script':{'body':'x'*12001}})
    with pytest.raises(ValueError):
        Draft.model_validate({'sections':[{'title':'交付','content':'脚本'}],
            'video_script':{'body':'泳池'}, 'video_storyboard':[{'source_asset_id':'invalid'}]})

def test_nested_section_deliverables_are_extracted_and_validated():
    from app.agent.workflows.llm_draft import Draft
    from app.services.video_director import fallback_plan
    plan=fallback_plan([{'id':f'hotel-{i}','name':'酒店'} for i in range(6)],15)
    draft=Draft.model_validate({'sections':[
        {'title':'脚本','content':{'video_script':'真实酒店体验'}},
        {'title':'分镜','content':{'video_storyboard':plan}},
        {'title':'文案','content':{'publish_title':'酒店','publish_description':'咨询入住'}},
    ]})
    assert len(draft.video_storyboard)==6
    assert draft.video_script=='真实酒店体验'
    assert isinstance(draft.sections[1].content,str)
    with pytest.raises(ValueError,match='冲突'):
        Draft.model_validate({'video_script':'另一个版本','sections':[{'title':'脚本','content':{'video_script':'原版本'}}]})

def setup_parent(db):
    user = create_test_user(db)
    company = create_test_company(db, user)
    # Provision using the same method as production.
    from app.models.digital_employee import DigitalEmployee
    for role in ('content_planner','data_analyst','video_producer'):
        db.add(DigitalEmployee(company_id=company.id,name=role,role_title=role,
            created_by=user.id,allowed_data_scopes=['company'],is_active=True))
    parent = OperationTask(company_id=company.id,created_by=user.id, title='提升曝光',task_type='business_analysis',
        status='completed',output={'role':'operations_manager','next_actions':[
            {'role':'content_planner','title':'计划','goal':'三日主题'},
            {'role':'data_analyst','title':'分析','goal':'真实数据'},
            {'role':'operations_manager','title':'循环','goal':'不允许'}]})
    db.add(parent);db.commit()
    return parent

def test_automatic_handoff_is_scoped_acyclic_and_idempotent(db):
    parent=setup_parent(db)
    children=create_handoffs(db,parent); db.commit()
    assert len(children)==2
    assert all(c.company_id==parent.company_id and c.parent_task_id==parent.id for c in children)
    assert create_handoffs(db,parent)==[]
    assert len(parent.output['handoff_task_ids'])==2

def test_video_handoff_reuses_project(db):
    parent=setup_parent(db)
    from tests.test_asset_intelligence import make_asset
    from app.models.company import Company
    from app.models.user import User
    for image_index in range(12):
        make_asset(db,db.get(Company,parent.company_id),db.get(User,parent.created_by),f'酒店环境{image_index}','landscape',[],'山景')
    a=create_video_handoff(db,parent);db.commit()
    b=create_video_handoff(db,parent)
    assert a.id==b.id

def test_legacy_llm_script_cannot_silently_loop_assets(db):
    from fastapi import HTTPException
    parent=setup_parent(db)
    parent.output={'mode':'llm','video_script':'旧版三图脚本'}
    with pytest.raises(HTTPException,match='') as exc:
        create_video_handoff(db,parent)
    assert exc.value.status_code==422
    assert '缺少结构化分镜' in exc.value.detail

def test_llm_generates_validated_draft_and_filters_cyclic_actions(db,monkeypatch):
    parent=setup_parent(db)
    for k,v in [('LLM_BASE_URL','https://relay.test/v1'),('LLM_MODEL','model'),('LLM_API_KEY','test')]:
        monkeypatch.setattr(settings,k,v)
    response={'content':json.dumps({'sections':[{'title':'主题','content':'禁词'}],
        'next_actions':[{'role':'operations_manager','title':'循环','goal':'循环'}]}),
        'model':'model','input_tokens':10,'output_tokens':20}
    monkeypatch.setattr('app.agent.workflows.llm_draft.OpenAIProvider.complete',AsyncMock(return_value=response))
    result=enrich(parent.output,parent,AgentRuntime(db),['禁词'])
    assert result['mode']=='llm'
    assert result['next_actions']==[]
    assert '禁词' not in result['report_markdown']
    assert parent.models_used==['model']

def test_approval_dispatches_children_and_rejects_duplicate(db, monkeypatch):
    from app.services.approval_service import ApprovalService
    from app.models.approval import Approval
    from fastapi import HTTPException
    from unittest.mock import Mock
    parent = setup_parent(db)
    approval=Approval(company_id=parent.company_id,requested_by=parent.created_by,
        resource_type='operation_task',resource_id=str(parent.id),action='review',status='pending')
    db.add(approval);db.flush()
    parent.status='waiting_approval'
    parent.output={**parent.output,'approval_id':str(approval.id)}
    db.commit()
    dispatch=Mock()
    monkeypatch.setattr('app.services.task_dispatch.dispatch_task', dispatch)
    ApprovalService(db).approve(parent.company_id,approval.id,parent.created_by)
    assert dispatch.call_count==2
    assert parent.status=='completed'
    with pytest.raises(HTTPException):
        ApprovalService(db).approve(parent.company_id,approval.id,parent.created_by)
    assert dispatch.call_count==2

def test_visible_metrics_rejects_ambiguous_values():
    from app.connectors.web_platform import parse_visible_metrics
    assert parse_visible_metrics('播放量\n1.2万\n点赞量\n25') == {'views':12000,'likes':25}
    assert parse_visible_metrics('播放量\n100\n播放量\n200') == {}

def test_full_approved_chain_creates_video_without_live_calls(client, db, monkeypatch):
    from tests.conftest import auth_headers
    from unittest.mock import AsyncMock, Mock
    from app.models.digital_employee import DigitalEmployee
    from app.models.video_project import VideoProject
    user=create_test_user(db,email='chain@example.com')
    company=create_test_company(db,user,slug='chain')
    from tests.test_asset_intelligence import make_asset
    for image_index in range(12):
        make_asset(db,company,user,f'酒店环境{image_index}','landscape',[],'酒店真实山景')
    monkeypatch.setattr('app.services.video_generation.reference_url',lambda *a,**k:'https://test.invalid/reference')
    monkeypatch.setattr(settings,'TASK_EXECUTION_MODE','inline')
    for k,v in [('LLM_BASE_URL','https://relay.test/v1'),('LLM_MODEL','test-model'),('LLM_API_KEY','test')]:
        monkeypatch.setattr(settings,k,v)
    async def complete(self,messages,**kwargs):
        context=json.loads(messages[-1]['content'])
        role=context['role']
        next_role={'operations_manager':'content_planner','content_planner':'video_producer'}.get(role)
        actions=[{'role':next_role,'title':'后续工作','goal':'酒店曝光目标'}] if next_role else []
        from app.services.video_director import fallback_plan
        plan=fallback_plan(context['data_sources']['selected_assets'],context['video_brief']['target_duration_seconds']) if role=='video_producer' else []
        return {'model':'test-model','input_tokens':20,'output_tokens':30,
            'content':json.dumps({'video_storyboard':plan,'video_script':'0–5秒，酒店环境连续动态镜头，缓慢推进，保留酒店真实特征。','sections':[{'title':'交付','content':'真实酒店环境镜头脚本'}],'next_actions':actions})}
    monkeypatch.setattr('app.providers.llm.openai_provider.OpenAIProvider.complete',complete)
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    enqueue=Mock();monkeypatch.setattr('app.services.video_generation.enqueue',enqueue)
    headers=auth_headers(user)
    response=client.get(f'/api/v1/companies/{company.id}/employees',headers=headers)
    manager=next(e for e in response.json() if e['role_title']=='operations_manager')
    response=client.post(f'/api/v1/companies/{company.id}/tasks',headers=headers,json={
        'title':'酒店曝光','task_type':'business_analysis','digital_employee_id':manager['id'],
        'input_params':{'goal':'提升抖音酒店曝光'}})
    assert response.status_code==201,response.text
    current=response.json()
    for expected_role in ('operations_manager','content_planner','video_producer'):
        assert current['output']['role']==expected_role
        assert current['output']['mode']=='llm'
        approval=current['output']['approval_id']
        response=client.post(f'/api/v1/companies/{company.id}/approvals/{approval}/approve',headers=headers,json={})
        assert response.status_code==200,response.text
        current=client.get(f"/api/v1/companies/{company.id}/tasks/{current['id']}",headers=headers).json()
        if expected_role!='video_producer':
            child=current['output']['handoff_task_ids'][0]
            current=client.get(f'/api/v1/companies/{company.id}/tasks/{child}',headers=headers).json()
    import uuid
    project=db.get(VideoProject,uuid.UUID(current['output']['video_project_id']))
    assert project.task_id is not None and project.project_status=='analyzing'
    assert '连续动态镜头' in project.script
    assert enqueue.call_count==1
