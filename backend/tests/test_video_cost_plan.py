import uuid
import pytest
from app.services.video_cost_plan import cost_plan, validate_cost_plan

def assets(n):
    return [{'id': str(uuid.uuid4()), 'name': f'场景{i}', 'description': f'酒店场景{i}'} for i in range(n)]

def test_cost_plan_15_and_30_seconds():
    for duration, count in [(15,3),(30,6)]:
        source=assets(count+2)
        plan=cost_plan(source,duration)
        assert len(plan)==count
        assert all(s['generation_duration_seconds']==5 for s in plan)
        assert all(1 <= len(s['subshots']) <= 2 for s in plan)
        assert sum(s['duration_seconds'] for s in plan)==duration
        assert validate_cost_plan(plan,source,duration)[0]['planning_version']==3

def test_cost_plan_rejects_reused_or_insufficient_assets():
    with pytest.raises(ValueError, match='至少'):
        cost_plan(assets(2),15)
    source=assets(3); plan=cost_plan(source,15)
    plan[-1]['source_asset_id']=plan[0]['source_asset_id']
    with pytest.raises(ValueError, match='重复'):
        validate_cost_plan(plan,source,15)

def test_cost_plan_rejects_bad_subshots():
    source=assets(3); plan=cost_plan(source,15)
    plan[0]['subshots']=[{'duration_seconds':5.1,'description':'x'}]
    with pytest.raises(ValueError): validate_cost_plan(plan,source,15)


def test_non_multiple_of_five_keeps_only_remaining_seconds():
    source=assets(4)
    plan=validate_cost_plan(cost_plan(source,16),source,16)
    assert [s['duration_seconds'] for s in plan]==[5,5,5,1]
    assert len(plan[-1]['subshots'])==1
    assert all(s['generation_duration_seconds']==5 for s in plan)
    for duration in (0,14,61,float('nan')):
        with pytest.raises(ValueError): validate_cost_plan(plan,source,duration)


def test_mode_persists_and_only_draft_can_switch(db):
    from fastapi import HTTPException
    from app.services.video_service import VideoService
    from app.schemas.video_project import VideoProjectCreate, VideoProjectUpdate, StoryboardUpdate
    from tests.conftest import create_test_user, create_test_company
    from tests.test_asset_intelligence import make_asset
    user=create_test_user(db); company=create_test_company(db,user)
    source=[make_asset(db,company,user,f'酒店{i}','landscape',[],f'山景{i}') for i in range(3)]
    service=VideoService(db)
    project=service.create_project(company.id,user.id,VideoProjectCreate(
        title='成本优先',creation_mode='reference_inspired',generation_mode='cost',
        target_duration_seconds=15,selected_asset_ids=[a.id for a in source]))
    assert project.generation_mode=='cost'
    plan=cost_plan([{'id':str(a.id)} for a in source],15)
    service.update_storyboard(company.id,project.id,StoryboardUpdate(storyboard=plan))
    assert len(project.storyboard)==3
    service.update_project(company.id,project.id,VideoProjectUpdate(generation_mode='quality'))
    assert project.storyboard is None
    project.project_status='failed'; db.commit()
    with pytest.raises(HTTPException) as exc:
        service.update_project(company.id,project.id,VideoProjectUpdate(generation_mode='cost'))
    assert exc.value.status_code==409
    assert project.generation_mode=='quality'


def test_cost_generation_submits_three_five_second_clips(db,monkeypatch,tmp_path):
    from unittest.mock import Mock
    from app.models.video_project import VideoProject
    from app.services.video_generation import _compose_selected_images
    from app.config import settings
    from tests.conftest import create_test_user, create_test_company
    from tests.test_asset_intelligence import make_asset
    user=create_test_user(db); company=create_test_company(db,user)
    source=[make_asset(db,company,user,f'场景{i}','landscape',[],f'真实酒店场景{i}') for i in range(3)]
    plan=cost_plan([{'id':str(a.id),'description':a.source_description} for a in source],15)
    project=VideoProject(company_id=company.id,created_by=user.id,title='酒店',
        creation_mode='reference_inspired',generation_mode='cost',selected_asset_ids=[str(a.id) for a in source],
        target_duration_seconds=15,aspect_ratio='9:16',storyboard=plan)
    db.add(project); db.commit()
    monkeypatch.setattr(settings,'STORAGE_BACKEND','local')
    monkeypatch.setattr(settings,'LOCAL_STORAGE_PATH',str(tmp_path))
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    monkeypatch.setattr('app.services.video_generation.reference_url',lambda *a,**k:'https://test.invalid/image')
    generate=Mock(side_effect=lambda db,p,client,request,shot_number:(b'clip',Mock(provider_task_id=f'clip-{shot_number}')))
    monkeypatch.setattr('app.services.video_generation._generate_clip',generate)
    assemble=Mock(return_value=b'final')
    monkeypatch.setattr('app.services.media_processing.assemble_model_clips',assemble)
    monkeypatch.setattr('app.services.media_processing.enrich_video_asset',lambda *a:None)
    monkeypatch.setattr('app.services.video_generation._finalize_content',lambda db,p,c,s:(c,None))
    _compose_selected_images(db,project,[a.id for a in source])
    assert generate.call_count==3
    requests=[call.args[3] for call in generate.call_args_list]
    assert all(r.duration_seconds==5 for r in requests)
    assert all('0至2秒' in r.prompt and '2至5秒' in r.prompt for r in requests)
    assert len({r.prompt for r in requests})==3
    assert assemble.call_args.args[2]==[5,5,5]
    assert project.project_status=='pending_review'
    assert project.generation_mode=='cost'
    assert project.quality_check_result['generation_requests']==3


def test_cost_llm_uses_cost_prompt_and_preserves_director_subshots(db,monkeypatch):
    import json
    from unittest.mock import AsyncMock
    from app.config import settings
    from app.agent.runtime import AgentRuntime
    from app.agent.workflows.llm_draft import enrich
    from tests.test_llm_handoff import setup_parent
    parent=setup_parent(db)
    parent.input_params={'generation_mode':'cost'}
    source=assets(3); plan=cost_plan(source,15)
    plan[0]['subshots'][0]['description']='先沿池边侧移，展示远山倒影'
    for key,value in [('LLM_BASE_URL','https://test.invalid/v1'),('LLM_MODEL','test'),('LLM_API_KEY','test')]:
        monkeypatch.setattr(settings,key,value)
    complete=AsyncMock(return_value={'content':json.dumps({'sections':[{'title':'脚本','content':'酒店体验'}],
        'video_script':'三段酒店体验','video_storyboard':plan}),
        'model':'test','input_tokens':1,'output_tokens':2})
    monkeypatch.setattr('app.agent.workflows.llm_draft.OpenAIProvider.complete',complete)
    result=enrich({'role':'video_producer','video_brief':{'target_duration_seconds':15,'generation_mode':'cost'},
        'data_sources':{'selected_assets':source}},parent,AgentRuntime(db),[])
    assert '当前选择成本优先' in complete.call_args.args[0][0]['content']
    assert '不要按一张图片固定5秒规划' not in complete.call_args.args[0][0]['content']
    assert result['video_storyboard'][0]['subshots'][0]['description']=='先沿池边侧移，展示远山倒影'
    assert len(result['video_storyboard'])==3


def test_cost_mode_propagates_through_children_and_video_handoff(db):
    from tests.test_llm_handoff import setup_parent
    from tests.test_asset_intelligence import make_asset
    from app.models.company import Company
    from app.models.user import User
    from app.services.task_handoff import create_handoffs, create_video_handoff
    from app.services.execution_loop import child_params
    parent=setup_parent(db)
    parent.input_params={'generation_mode':'cost','target_duration_seconds':15}
    assert child_params(parent)['generation_mode']=='cost'
    children=create_handoffs(db,parent)
    assert all(c.input_params['generation_mode']=='cost' for c in children)
    company=db.get(Company,parent.company_id); user=db.get(User,parent.created_by)
    for i in range(3): make_asset(db,company,user,f'环境{i}','landscape',[],'真实山景')
    project=create_video_handoff(db,parent)
    assert project.generation_mode=='cost'
    assert len(project.storyboard)==3
