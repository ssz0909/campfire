"""Industry configuration reaches creation, handoffs and prompts without paid calls."""
from copy import deepcopy
import json

import pytest
from fastapi import HTTPException

from tests.conftest import create_test_company, create_test_user, auth_headers
from app.models.industry_template import IndustryTemplate, IndustryTemplateVersion
from app.services.industry_template_defaults import SEEDS
from app.services.industry_templates import resolve_snapshot, ensure_task_snapshot
from app.services.task_service import TaskService
from app.schemas.task import TaskCreate


@pytest.fixture
def seeded(db):
    for code, content in SEEDS.items():
        db.add(IndustryTemplate(code=code, draft=deepcopy(content), enabled=True, draft_revision=1, published_version=1))
    db.flush()
    for code, content in SEEDS.items():
        db.add(IndustryTemplateVersion(industry_code=code, version=1, content=deepcopy(content)))
    owner = create_test_user(db, email='industry-owner@example.com')
    company = create_test_company(db, owner, slug='industry-test')
    company.industry = 'travel'
    db.commit()
    return owner, company


def admin_headers(db):
    return auth_headers(create_test_user(db, email='industry-admin@example.com', is_platform_admin=True))


def test_catalog_and_admin_permissions(client, db, seeded):
    owner, _ = seeded
    assert client.get('/api/v1/industries').status_code == 401
    result = client.get('/api/v1/industries', headers=auth_headers(owner))
    assert result.status_code == 200
    assert any(i['code'] == 'travel' and i['name'] == '酒旅' for i in result.json())
    assert all('draft' not in i for i in result.json())
    assert client.get('/api/v1/admin/industry-templates', headers=auth_headers(owner)).status_code == 403
    assert client.post('/api/v1/admin/industry-templates', headers=auth_headers(owner), json={
        'code':'restaurant','content':SEEDS['generic']}).status_code == 403


def test_publish_draft_versions_and_conflict(client, db, seeded):
    _, company = seeded
    headers = admin_headers(db)
    content = {**SEEDS['generic'], 'name':'餐饮', 'positioning':'展示菜品与真实用餐场景'}
    create = client.post('/api/v1/admin/industry-templates', headers=headers, json={'code':'restaurant','content':content})
    assert create.status_code == 201, create.text
    assert create.json()['published_version'] == 0
    assert 'restaurant' not in [r['code'] for r in client.get('/api/v1/industries',headers=headers).json()]
    with pytest.raises(HTTPException): resolve_snapshot(db, company.id, 'restaurant')
    row = client.post('/api/v1/admin/industry-templates/restaurant/publish',headers=headers,json={'expected_revision':1}).json()
    assert row['published_version'] == 1
    first = resolve_snapshot(db, company.id, 'restaurant')
    content['positioning'] = '新版本菜品细节策略'
    r = client.put('/api/v1/admin/industry-templates/restaurant/draft',headers=headers,json={
        'expected_revision':row['draft_revision'],'content':content})
    assert r.status_code == 200, r.text
    assert resolve_snapshot(db, company.id, 'restaurant')['content'] == first['content']
    assert client.post('/api/v1/admin/industry-templates/restaurant/publish',headers=headers,json={'expected_revision':1}).status_code == 409
    r2 = client.post('/api/v1/admin/industry-templates/restaurant/publish',headers=headers,json={'expected_revision':r.json()['draft_revision']})
    assert r2.json()['published_version'] == 2
    assert len(r2.json()['versions']) == 2
    assert first['content']['positioning'] != resolve_snapshot(db, company.id, 'restaurant')['content']['positioning']
    from app.models.audit_log import AuditLog
    assert db.query(AuditLog).filter(AuditLog.action.like('industry_template.%')).count() == 4


def test_disable_and_generic_fallback(client, db, seeded):
    _, company = seeded
    headers = admin_headers(db)
    assert client.patch('/api/v1/admin/industry-templates/generic/status',headers=headers,json={
        'enabled':False,'expected_revision':1}).status_code == 422
    assert client.patch('/api/v1/admin/industry-templates/travel/status',headers=headers,json={
        'enabled':False,'expected_revision':1}).status_code == 200
    fallback = resolve_snapshot(db, company.id)
    assert fallback['industry_code'] == 'generic' and fallback['resolved_from'] == 'fallback'
    with pytest.raises(HTTPException): resolve_snapshot(db, company.id, 'travel')
    assert 'travel' not in [i['code'] for i in client.get('/api/v1/industries',headers=headers).json()]


def test_resolution_aliases_and_unknown(seeded, db):
    _, company = seeded
    assert resolve_snapshot(db, company.id)['industry_code'] == 'travel'
    assert resolve_snapshot(db, company.id, 'generic')['industry_code'] == 'generic'
    company.industry = 'hotel'
    assert resolve_snapshot(db, company.id)['industry_code'] == 'travel'
    company.industry = 'unknown_old_value'
    assert resolve_snapshot(db, company.id)['industry_code'] == 'generic'
    for value in ('missing', '', [], {}):
        with pytest.raises(HTTPException): resolve_snapshot(db, company.id, value)


def task(db, owner, company, **params):
    return TaskService(db).create_task(company.id, owner.id, TaskCreate(title='创作测试',task_type='marketing_planning',
        input_params={'goal':'展示品牌真实亮点',**params}))


def test_snapshot_cannot_be_spoofed_and_retry_inherits(seeded, db):
    owner, company = seeded
    root = task(db, owner, company, industry_template_snapshot={'content':{'positioning':'恶意覆盖'}})
    snapshot = deepcopy(root.input_params['industry_template_snapshot'])
    assert snapshot['industry_code'] == 'travel'
    row = db.get(IndustryTemplate, 'travel')
    row.published_version = 2
    db.add(IndustryTemplateVersion(industry_code='travel',version=2,content={**SEEDS['travel'],'positioning':'新版'}))
    company.industry = 'generic'
    root.status = 'failed'; db.commit()
    TaskService(db).retry_task(company.id, root.id)
    assert root.input_params['industry_template_snapshot'] == snapshot
    assert ensure_task_snapshot(db, root) == snapshot
    from app.services.execution_loop import child_params
    assert child_params(root)['industry_template_snapshot'] == snapshot
    root.status = 'completed'; db.commit()
    child = TaskService(db).create_task(company.id,owner.id,TaskCreate(title='下游测试', task_type='marketing_planning',
        parent_task_id=root.id,input_params={'goal':'继续制作'}))
    assert child.input_params['industry_template_snapshot'] == snapshot
    assert task(db, owner, company).input_params['industry_template_snapshot']['industry_code'] == 'generic'


def test_project_snapshot_and_create_override(client, db, seeded):
    owner, company = seeded
    from app.services.video_service import VideoService
    from app.schemas.video_project import VideoProjectCreate
    project = VideoService(db).create_project(company.id,owner.id,VideoProjectCreate(title='酒旅视频',creation_mode='ai_creative'))
    assert project.industry_template_snapshot['industry_code'] == 'travel'
    original = deepcopy(project.industry_template_snapshot)
    company.industry = None; db.commit()
    from app.services.industry_templates import project_snapshot
    assert project_snapshot(db, project) == original
    other = VideoService(db).create_project(company.id,owner.id,VideoProjectCreate(
        title='通用视频',creation_mode='ai_creative',industry_override='generic'))
    assert other.industry_template_snapshot['industry_code'] == 'generic'


def test_handoff_copies_project_snapshot(db, seeded):
    owner, company = seeded
    from app.models.asset import Asset
    from app.services.task_handoff import create_video_handoff
    root = task(db,owner,company,generation_mode='cost',target_duration_seconds=15)
    assets = []
    for i in range(3):
        a = Asset(company_id=company.id,uploaded_by=owner.id,name=f'真实景观{i}',original_filename='a.jpg',
            file_key=f'{company.id}/{i}.jpg',asset_type='image',mime_type='image/jpeg',file_size_bytes=100,
            processing_status='ready',is_available=True)
        db.add(a);db.flush();assets.append(a)
    root.output={'selected_asset_ids':[str(a.id) for a in assets]}
    project=create_video_handoff(db,root)
    assert project.industry_template_snapshot == root.input_params['industry_template_snapshot']
    assert project.generation_mode == 'cost' and len(project.storyboard) == 3


def test_template_reaches_llm_and_local_draft(db, seeded, monkeypatch):
    owner, company = seeded
    from app.agent.workflows.operations import OperationsWorkflow
    from app.agent.runtime import AgentRuntime
    from app.core.tenant_context import TenantContext
    root=task(db,owner,company)
    result=OperationsWorkflow().run(root,TenantContext(current_user=owner,current_company_id=company.id),db,AgentRuntime(db))
    assert result['industry_template_snapshot']['industry_code'] == 'travel'
    assert any(s['title']=='行业创作配置' for s in result['sections'])
    from app.agent.workflows import llm_draft
    monkeypatch.setattr(llm_draft,'get_llm_settings',lambda:{'base_url':'https://example.invalid/v1','model':'fake','api_key':'fake'})
    calls=[]
    class Fake:
        def __init__(self, **kw): pass
        async def complete(self,messages,**kw):
            calls.append(messages)
            return {'content':json.dumps({'sections':[{'title':'测试','content':'已根据真实素材拟定方案'}]}),
                    'model':'fake','input_tokens':1,'output_tokens':1}
    monkeypatch.setattr(llm_draft,'OpenAIProvider',Fake)
    output=llm_draft.enrich(result,root,AgentRuntime(db),[])
    assert '住宿与景区不强制拆分' in calls[0][0]['content']
    assert output['industry_template_snapshot'] == root.input_params['industry_template_snapshot']
    assert '关注' in calls[0][0]['content']
    assert '任务明确要求' in calls[0][0]['content']


def test_template_selection_never_crosses_tenants(db, seeded):
    owner, company = seeded
    from app.models.asset import Asset
    from app.services.asset_selection import select_assets_for_video
    other=create_test_company(db,owner,slug='industry-other')
    for c,name in [(company,'产品细节'),(company,'景观风景'),(other,'景观风景')]:
        db.add(Asset(company_id=c.id,uploaded_by=owner.id,name=name,original_filename='a.jpg',file_key=name,
            asset_type='image',mime_type='image/jpeg',file_size_bytes=100,processing_status='ready',is_available=True,
            tags=[name],asset_metadata={'manual_classification':True}))
    db.commit()
    result=select_assets_for_video(db,company.id,'产品细节',template=resolve_snapshot(db,company.id))
    assert len(result)==1 and result[0].name=='产品细节'
    assert all(a.company_id==company.id for a in result)


def test_validation_rejects_workflow_controls(client, db, seeded):
    content={**SEEDS['generic'],'auto_execute':True}
    response=client.post('/api/v1/admin/industry-templates',headers=admin_headers(db),json={'code':'bad_template','content':content})
    assert response.status_code == 422


def test_visual_prompt_has_no_copy_instructions(db, seeded):
    _, company=seeded
    from app.services.industry_templates import visual_guidance
    snapshot=resolve_snapshot(db,company.id)
    snapshot['content']['copy_guidance']='只在发布文案使用的独特标记'
    prompt=visual_guidance(snapshot)
    assert '独特标记' not in prompt
    assert '不生成字幕' in prompt and '当前任务' in prompt


def test_restore_is_draft_only_and_preserves_history(client, db, seeded):
    _, company=seeded
    headers=admin_headers(db)
    changed={**SEEDS['travel'],'positioning':'第二版视觉方向'}
    saved=client.put('/api/v1/admin/industry-templates/travel/draft',headers=headers,
        json={'expected_revision':1,'content':changed}).json()
    current=client.post('/api/v1/admin/industry-templates/travel/publish',headers=headers,
        json={'expected_revision':saved['draft_revision']}).json()
    restored=client.post('/api/v1/admin/industry-templates/travel/versions/1/restore',headers=headers,
        json={'expected_revision':current['draft_revision']})
    assert restored.status_code==200,restored.text
    assert restored.json()['draft']==SEEDS['travel']
    assert resolve_snapshot(db,company.id)['content']==changed
    assert len(restored.json()['versions'])==2


@pytest.mark.parametrize('mode,count', [('quality',5),('cost',3)])
def test_actual_generation_requests_receive_template(db,seeded,monkeypatch,mode,count):
    from types import SimpleNamespace
    from app.models.asset import Asset
    from app.schemas.video_project import VideoProjectCreate
    from app.services.video_service import VideoService
    from app.services import video_generation as gen
    from app.services.video_director import fallback_plan
    from app.services.video_cost_plan import cost_plan
    owner,company=seeded
    images=[]
    for i in range(count):
        a=Asset(company_id=company.id,uploaded_by=owner.id,name=f'景观{i}',original_filename='a.jpg',file_key=f'a{i}',
            asset_type='image',mime_type='image/jpeg',file_size_bytes=100,processing_status='ready',is_available=True)
        db.add(a);db.flush();images.append(a)
    project=VideoService(db).create_project(company.id,owner.id,VideoProjectCreate(title='体验视频',creation_mode='reference_inspired',
        selected_asset_ids=[a.id for a in images],generation_mode=mode,reuse_policy='fresh',target_duration_seconds=15))
    assets=[{'id':str(a.id),'name':a.name} for a in images]
    project.storyboard=(cost_plan if mode=='cost' else fallback_plan)(assets,15)
    requests=[]
    def generate(db,project,client,request,shot_number=None):
        requests.append(request)
        return b'clip',SimpleNamespace(provider_task_id='fake',raw_asset_id=None)
    monkeypatch.setattr(gen,'_generate_clip',generate)
    monkeypatch.setattr(gen,'provider',lambda:object())
    monkeypatch.setattr(gen,'reference_url',lambda *a,**kw:'https://example.invalid/reference.jpg')
    monkeypatch.setattr(gen,'StorageService',lambda *a:SimpleNamespace(upload_file=lambda *a:'/files/fake.mp4'))
    monkeypatch.setattr('app.services.media_processing.assemble_model_clips',lambda *a:b'assembled')
    monkeypatch.setattr('app.services.media_processing.enrich_video_asset',lambda *a:None)
    monkeypatch.setattr(gen,'_finalize_content',lambda *a:(b'final',{}))
    gen._compose_selected_images(db,project,[a.id for a in images])
    assert len(requests)==count
    assert all(r.duration_seconds==5 for r in requests)
    assert all('住宿与景区不强制拆分' in r.prompt and '只生成当前镜头画面' in r.prompt for r in requests)
    assert project.project_status=='pending_review'


def test_generic_industry_does_not_require_hotel_connector(db,seeded):
    from app.agent.workflows.operations import OperationsWorkflow
    from app.agent.runtime import AgentRuntime
    from app.core.tenant_context import TenantContext
    from app.services.execution_loop import actions_for
    owner,company=seeded
    company.industry='generic'
    root=task(db,owner,company,execution_loop=True)
    # A generic analyst can plan from available facts without fabricating order data.
    from app.models.digital_employee import DigitalEmployee
    employee=DigitalEmployee(company_id=company.id,created_by=owner.id,name='分析员',role_title='data_analyst',
        is_active=True,allowed_data_scopes=['company'])
    db.add(employee);db.flush();root.digital_employee_id=employee.id
    result=OperationsWorkflow().run(root,TenantContext(owner,company.id),db,AgentRuntime(db))
    result=actions_for(root,result)
    assert not result['execution_blocked']
    assert result['next_actions'][0]['role']=='content_planner'
    assert result['data_sources']['hotel']['metrics'] is None
