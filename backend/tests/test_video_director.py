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
    assets=[{'id':str(uuid.uuid4()),'description':f'真实场景{i}'} for i in range(12)]
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
    single=fallback_plan(assets[:1],15)
    assert all(a['framing']!=b['framing'] for a,b in zip(single,single[1:]))
    wrong=[dict(s) for s in single];wrong[-1]['duration_seconds']=3.5
    with pytest.raises(ValueError,match='时长之和'):validate_plan(wrong,assets[:1],15)


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
    project=VideoProject(company_id=company.id,created_by=user.id,title='酒店短片',
        script='WHOLE_SCRIPT_MUST_NOT_LEAK',creation_mode='prompt_to_video',
        selected_asset_ids=[str(a.id) for a in assets],storyboard=plan,target_duration_seconds=15,aspect_ratio='9:16')
    db.add(project);db.commit()
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
