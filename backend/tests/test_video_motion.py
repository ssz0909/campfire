from tests.test_video_clip_library import library
from types import SimpleNamespace
from app.services.video_motion import people_visible,motion_prompt,MOTION_VERSION
from app.services.video_director import DIRECTOR_PROMPT,fallback_plan
from app.services.video_cost_plan import COST_DIRECTOR_PROMPT,cost_plan


def test_people_metadata_and_legacy_fallback():
    assert people_visible({'people_visible':True,'description':'室外场景'})
    assert not people_visible({'people_visible':False,'description':'有人物'})
    assert people_visible({'description':'一位女士站在庭院'})
    assert not people_visible({'description':'无人泳池景观'})
    assert not people_visible({'description':'人物海报'})
    assert people_visible(SimpleNamespace(asset_metadata={'vision_analysis':{'people_visible':True}},name='photo',source_description=''))


def test_person_action_reaches_both_drafts_and_retained_timing():
    assets=[{'id':str(i),'people_visible':True,'description':'女士在庭院'} for i in range(8)]
    for prompt in (DIRECTOR_PROMPT,COST_DIRECTOR_PROMPT):
        assert '镜头运动不能代替人物动作' in prompt
        assert '前0.3秒' in prompt
    quality=fallback_plan(assets,15)
    assert '人物主动动作优先' in quality[0]['camera_movement']
    assert '前2秒' in quality[0]['generation_prompt']
    cost=cost_plan(assets,15)
    assert all('人物必须主动运动' in s['generation_prompt'] for s in cost)
    assert motion_prompt(assets[0],2,0)!=motion_prompt(assets[0],2,1)
    assert '绝不新增人物' in motion_prompt({'people_visible':False})


def test_motion_contract_blocks_old_static_reuse(library):
    from app.services.video_clip_library import shot_contract,compatible
    _,_,project,_,clips,_=library
    shot=dict(project.storyboard[0])
    assert compatible(project,shot,clips[0])
    shot['human_motion_policy']=MOTION_VERSION
    assert not compatible(project,shot,clips[0])
    assert shot_contract(project,shot)['human_motion_policy']==MOTION_VERSION
