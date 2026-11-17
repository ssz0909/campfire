import copy

import pytest

from app.services.video_requirements import (
    requires_people_opening, task_visual_text, mark_opening_candidates,
)
from app.services.video_director import fallback_plan, validate_plan
from app.services.video_cost_plan import cost_plan, validate_cost_plan
from app.services.asset_selection import select_assets_for_video
from app.models.video_project import VideoProject
from tests.conftest import create_test_user, create_test_company
from tests.test_asset_intelligence import make_asset


@pytest.mark.parametrize('text', ['视频以人物入境开头', '开场先用真人出镜', '第一镜头要模特', '人物出镜开头，不要字幕'])
def test_explicit_opening_request(text):
    assert requires_people_opening(text)


@pytest.mark.parametrize('text', ['不需要人物出镜开头', '不要人物开场', '开头展示泳池，后半段展示人物', '人物要动起来'])
def test_no_invented_opening_requirement(text):
    assert not requires_people_opening(text)


def test_people_metadata_survives_zero_keyword_match_and_rotates(db):
    user = create_test_user(db); company = create_test_company(db, user)
    people = [make_asset(db, company, user, f'照片{i}', 'other', [], '蓝色背景') for i in range(3)]
    for asset in people:
        asset.asset_metadata = {'vision_analysis': {'status': 'completed', 'people_visible': True, 'visual_description': '蓝色背景'}}
    rooms = [make_asset(db, company, user, f'房间{i}', 'guest_room', ['客房'], '客房') for i in range(5)]
    db.add(VideoProject(company_id=company.id, created_by=user.id, title='昨天',
        creation_mode='reference_inspired', project_status='completed',
        storyboard=[{'source_asset_id':str(people[0].id)}]))
    db.commit()
    selected = select_assets_for_video(db, company.id, '人物入镜开头，突出客房', limit=3, rotation_key='today')
    assert selected[0].id in {a.id for a in people[1:]}
    assert any(a.id in {r.id for r in rooms} for a in selected)
    # Hard requirement survives even a single available human's repeat penalty.
    for a in people[1:]: a.is_available = False
    db.commit()
    selected = select_assets_for_video(db, company.id, '人物入镜开头，突出客房', limit=1)
    assert selected[0].id == people[0].id


def test_missing_people_fails_before_generation(db):
    user=create_test_user(db); company=create_test_company(db,user)
    make_asset(db,company,user,'客房','guest_room',['客房'],'无人客房')
    db.commit()
    with pytest.raises(ValueError, match='真人图片'):
        select_assets_for_video(db,company.id,'人物出镜开头，展示客房')


@pytest.mark.parametrize('mode', ['quality', 'cost'])
def test_both_modes_require_real_people_first_and_local_plan_complies(mode):
    assets = [{'id':str(i), 'description':'泳池', 'people_visible':False} for i in range(6)]
    assets[-1] = {'id':'5', 'description':'一位游客站立', 'people_visible':True}
    assets = mark_opening_candidates(assets, True)
    factory, validate = (fallback_plan, validate_plan) if mode == 'quality' else (cost_plan, validate_cost_plan)
    plan = factory(assets, 15)
    assert plan[0]['source_asset_id']=='5'
    invalid = copy.deepcopy(plan)
    invalid[0]['source_asset_id'],invalid[1]['source_asset_id'] = invalid[1]['source_asset_id'],invalid[0]['source_asset_id']
    with pytest.raises(ValueError,match='首镜'):
        validate(invalid,assets,15)


def test_only_this_task_prompt_controls_people_opening():
    from types import SimpleNamespace
    task=SimpleNamespace(input_params={'execution_goal':'人物出镜开头'},title='制作短片',description='展示环境')
    assert requires_people_opening(task_visual_text(task))
    task.input_params={}
    task.title='制作短片'; task.description='展示环境'
    assert not requires_people_opening(task_visual_text(task))
    with pytest.raises(ValueError,match='真人图片'):
        mark_opening_candidates([{'id':'x','people_visible':False,'description':'人物海报'}],True)


@pytest.mark.parametrize('mode', ['quality', 'cost'])
def test_llm_wrong_opening_is_rejected_before_handoff(db, monkeypatch, mode):
    import json
    from unittest.mock import AsyncMock
    from app.agent.workflows import llm_draft
    from app.agent.runtime import AgentRuntime
    from tests.test_llm_handoff import setup_parent
    task=setup_parent(db)
    task.input_params={'generation_mode':mode}
    candidates=[{'id':str(i),'people_visible':i==5,'description':'游客' if i==5 else '泳池'} for i in range(6)]
    # Build a valid unconstrained script that omits the required human opener.
    plan=(fallback_plan if mode=='quality' else cost_plan)(candidates,15)
    monkeypatch.setattr(llm_draft,'get_llm_settings',lambda:{'base_url':'https://example.invalid','model':'test','api_key':'test'})
    complete=AsyncMock(return_value={'content':json.dumps({'sections':[{'title':'脚本','content':'环境开场'}], 'video_script':'环境开场', 'video_storyboard':plan}),
        'model':'test','input_tokens':1,'output_tokens':1})
    monkeypatch.setattr(llm_draft.OpenAIProvider,'complete',complete)
    with pytest.raises(ValueError,match='首镜'):
        llm_draft.enrich({'role':'video_producer','video_brief':{'target_duration_seconds':15},
            'data_sources':{'selected_assets':mark_opening_candidates(candidates,True),
                'visual_requirements':{'people_opening':True}}},task,AgentRuntime(db),[])
    assert '首镜必须引用' in complete.call_args.args[0][0]['content']
