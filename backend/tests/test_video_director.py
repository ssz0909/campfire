import io
import uuid
from unittest.mock import Mock

import pytest
from PIL import Image
from app.services.video_director import fallback_plan, validate_plan, target_duration
from app.services.media_processing import normalize_reference_image
from app.services.video_generation import _compose_selected_images
from app.models.video_project import VideoProject
from app.models.asset import Asset
from app.config import settings
from tests.conftest import create_test_user, create_test_company
from tests.test_asset_intelligence import make_asset


def test_director_timing_and_sources():
    assets=[{'id':str(uuid.uuid4()),'description':f'真实场景{i}'} for i in range(30)]
    for duration in (15,20,30,45,60):
        plan=fallback_plan(assets,duration)
        assert sum(s['duration_seconds'] for s in plan)==pytest.approx(duration)
        assert max(s['duration_seconds'] for s in plan)<=3.5
        assert plan[0]['duration_seconds']<=2
        assert len(set(s['source_asset_id'] for s in plan))>3
        assert all(s['generation_duration_seconds']==5 for s in plan)
        wrong=[dict(s) for s in plan];wrong[0]['source_asset_id']=str(uuid.uuid4())
        with pytest.raises(ValueError,match='候选池'):validate_plan(wrong,assets,duration)
    with pytest.raises(ValueError):target_duration({'target_duration_seconds':90})
    assert target_duration({},'制作1分钟酒店视频')==60
    assert target_duration({},'制作15秒短片')==15
    assert target_duration({},'酒店宣传')==30
    assert target_duration({},'制作1 Min 酒店视频')==60
    with pytest.raises(ValueError,match='补充素材'):
        fallback_plan(assets[:3],30)
    plan=fallback_plan(assets,30)
    repeated=[dict(s) for s in plan]
    repeated[-1]['source_asset_id']=repeated[0]['source_asset_id']
    with pytest.raises(ValueError,match='重复引用'):
        validate_plan(repeated,assets,30)
    assert len({s['source_asset_id'] for s in plan})==len(plan)
    # With only nine sources, use longer permitted edits instead of repeating.
    short_pool=fallback_plan(assets[:9],30)
    assert len(short_pool)==9
    assert sum(s['duration_seconds'] for s in short_pool)==pytest.approx(30)


def test_director_cover_crop_uses_image_not_blurred_padding():
    image=Image.new('RGB',(1200,600),'red')
    for x in range(600,1200):
        for y in range(600):image.putpixel((x,y),(0,0,255))
    buf=io.BytesIO();image.save(buf,'PNG')
    left=Image.open(io.BytesIO(normalize_reference_image(buf.getvalue(),'9:16',framing='detail',focal_x=0.1)))
    right=Image.open(io.BytesIO(normalize_reference_image(buf.getvalue(),'9:16',framing='detail',focal_x=0.9)))
    assert left.size==(720,1280)
    assert left.getpixel((360,640))[0]>200
    assert right.getpixel((360,640))[2]>200


def test_directed_generation_uses_individual_prompts_and_edit_lengths(db,monkeypatch,tmp_path):
    user=create_test_user(db);company=create_test_company(db,user)
    assets=[make_asset(db,company,user,f'场景{i}','landscape',[],f'可见景观{i}') for i in range(6)]
    descriptors=[{'id':str(a.id),'description':a.source_description} for a in assets]
    plan=fallback_plan(descriptors,15)
    plan[0].update(transition_out='fade', transition_duration_seconds=0.3,
                   closing_frame='泳池反光收尾', transition_notes='以水面亮度接汤泉暖光')
    plan[1]['opening_frame']='汤泉水面暖光开场'
    project=VideoProject(company_id=company.id,created_by=user.id,title='酒店短片',
        script='WHOLE_SCRIPT_MUST_NOT_LEAK',creation_mode='prompt_to_video',
        selected_asset_ids=[str(a.id) for a in assets],storyboard=plan,target_duration_seconds=15,aspect_ratio='9:16')
    db.add(project);db.commit()
    from tests.test_video_music import audio_asset
    music=audio_asset(db,company,user)
    project.music_asset_id=music.id
    db.commit()
    soundtrack=Mock(side_effect=lambda db,p,content,storage:content)
    monkeypatch.setattr('app.services.video_music.apply_music',soundtrack)
    monkeypatch.setattr(settings,'STORAGE_BACKEND','local')
    monkeypatch.setattr(settings,'LOCAL_STORAGE_PATH',str(tmp_path))
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    crops=[]
    def reference(db,p,aid,shot=None):
        crops.append(shot);return f'https://test.invalid/{aid}'
    monkeypatch.setattr('app.services.video_generation.reference_url',reference)
    calls=[]
    def generate(db,p,client,request,shot_number):
        calls.append(request)
        assert len(p.storyboard)==len(plan)  # Remaining plan survives every commit/restart.
        return b'clip',Mock(provider_task_id=f'task-{shot_number}')
    monkeypatch.setattr('app.services.video_generation._generate_clip',generate)
    assemble=Mock(return_value=b'final')
    monkeypatch.setattr('app.services.media_processing.assemble_model_clips',assemble)
    monkeypatch.setattr('app.services.media_processing.enrich_video_asset',lambda *args:None)
    _compose_selected_images(db,project,[a.id for a in assets])
    assert len(calls)==len(plan)
    assert all(r.duration_seconds==5 and 'WHOLE_SCRIPT_MUST_NOT_LEAK' not in r.prompt for r in calls)
    assert all(r.audio is False for r in calls)
    assert '完成短淡出' in calls[0].prompt
    assert '本镜从起始即完成短淡入' in calls[1].prompt
    assert soundtrack.call_count==1
    assert len(set(r.prompt for r in calls))>3
    assert all(c['framing'] for c in crops)
    assert sum(assemble.call_args.args[2])==pytest.approx(15)
    assert project.project_status=='pending_review'
    assert all(s['planning_version']==2 and s['generation_status']=='completed' for s in project.storyboard)


def test_more_than_five_assets_keep_duration_independent(db):
    from app.services.video_service import VideoService
    from app.schemas.video_project import VideoProjectCreate
    user=create_test_user(db);company=create_test_company(db,user)
    assets=[make_asset(db,company,user,str(i),'landscape',[],'景观') for i in range(9)]
    project=VideoService(db).create_project(company.id,user.id,VideoProjectCreate(
        title='多场景',creation_mode='reference_inspired',target_duration_seconds=15,selected_asset_ids=[a.id for a in assets]))
    assert len(project.selected_asset_ids)==9 and project.target_duration_seconds==15


def test_transition_plan_reaches_adjacent_generation_prompts():
    from app.services.video_director import shot_generation_prompt
    assets=[{'id':str(uuid.uuid4()),'description':f'真实场景{i}'} for i in range(6)]
    plan=fallback_plan(assets,15)
    plan[0].update(opening_frame='泳池左侧全景',closing_frame='右侧水面反光',transition_out='fade',
                   transition_duration_seconds=0.3,transition_notes='收于反光，接下一镜暖光')
    plan[1].update(opening_frame='汤泉暖光水面',closing_frame='水面细节',transition_out='dissolve',
                   transition_duration_seconds=0.25,transition_notes='相近水面亮度柔和衔接')
    validated=validate_plan(plan,assets,15)
    outgoing=shot_generation_prompt(validated,0)
    incoming=shot_generation_prompt(validated,1)
    assert '0.3秒' in outgoing and '完成短淡出' in outgoing
    assert '右侧水面反光' in incoming and '本镜从起始即完成短淡入' in incoming
    assert '汤泉暖光水面' in incoming and '短叠化' in incoming
    assert '前2.0秒' in outgoing and '不生成下一场景' in outgoing
    assert validated[0]['transition_notes']=='收于反光，接下一镜暖光'
    invalid=[dict(s) for s in validated];invalid[-1].update(transition_out='fade',transition_duration_seconds=0.2)
    with pytest.raises(ValueError,match='最后一镜'):validate_plan(invalid,assets,15)
    invalid=[dict(s) for s in validated];invalid[0]['transition_duration_seconds']=0
    with pytest.raises(ValueError,match='大于0'):validate_plan(invalid,assets,15)
    legacy=[{k:v for k,v in s.items() if k not in ('opening_frame','closing_frame','transition_out','transition_duration_seconds','transition_notes')} for s in plan]
    assert all(s['transition_out']=='cut' for s in validate_plan(legacy,assets,15))
