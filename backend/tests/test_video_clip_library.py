import copy
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models.asset import Asset
from app.models.video_project import VideoProject, ProviderTask
from app.services.video_clip_library import (
    save_raw_clip, load_raw_clip, approve_project_clips, approved_candidates,
    plan_reuse, compatible, record_use,
)
from app.services.video_cost_plan import cost_plan
from app.services.video_service import VideoService
from app.services.storage_service import StorageService
from tests.conftest import create_test_user, create_test_company
from tests.test_asset_intelligence import make_asset


@pytest.fixture
def library(db, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(settings, 'STORAGE_BACKEND', 'local')
    monkeypatch.setattr('app.services.media_processing.enrich_video_asset',
        lambda a,s,c: (setattr(a, 'duration_seconds', 5), setattr(a, 'width', 720), setattr(a, 'height', 1280)))
    user = create_test_user(db)
    company = create_test_company(db,user)
    images = [make_asset(db,company,user,f'酒店场景{i}','landscape',['真实酒店'],f'山景{i}') for i in range(3)]
    plan = cost_plan([{'id':str(a.id),'description':a.source_description} for a in images],15)
    project = VideoProject(company_id=company.id,created_by=user.id,title='原始酒店片',creation_mode='reference_inspired',
        selected_asset_ids=[str(a.id) for a in images],reference_asset_id=images[0].id,storyboard=plan,
        target_duration_seconds=15,aspect_ratio='9:16',generation_mode='cost',reuse_policy='fresh')
    db.add(project); db.commit()
    storage = StorageService('local')
    clips=[]
    for index in range(1,4):
        task=ProviderTask(company_id=company.id,video_project_id=project.id,provider_name='relay',
            task_type='video_generation',shot_number=index,status='completed',provider_task_id=f'upstream-{index}',
            input_params={'prompt':f'酒店场景{index}'})
        db.add(task); db.commit()
        clips.append(save_raw_clip(db,project,task,b'raw-clip',storage))
    project.storyboard = [{**s, 'output_asset_id':str(clips[i].id)} for i,s in enumerate(plan)]
    db.commit()
    return user, company, project, images, clips, storage


def next_project(db, original, policy='prefer_reuse'):
    project=VideoProject(company_id=original.company_id,created_by=original.created_by,title='新主题',
        creation_mode=original.creation_mode,selected_asset_ids=original.selected_asset_ids,
        reference_asset_id=original.reference_asset_id,storyboard=copy.deepcopy(original.storyboard),
        target_duration_seconds=15,aspect_ratio='9:16',generation_mode='cost',reuse_policy=policy)
    db.add(project);db.commit()
    return project


def approve(db, project):
    project.review_status='approved'; project.project_status='completed'
    approve_project_clips(db,project);db.commit()


def test_raw_clips_are_durable_tagged_idempotent_and_unapproved(db,library):
    _,company,project,images,clips,storage=library
    assert len(clips)==3
    assert all(c.category=='landscape' and 'AI分镜' in c.tags for c in clips)
    assert all(c.asset_metadata['clip_library']['review_status']=='pending' for c in clips)
    assert approved_candidates(db,project)==[]
    task=db.query(ProviderTask).filter_by(video_project_id=project.id,shot_number=1).one()
    assert load_raw_clip(db,project,task,storage)==b'raw-clip'
    assert save_raw_clip(db,project,task,b'raw-clip',storage).id==clips[0].id
    assert db.query(Asset).filter_by(company_id=company.id,asset_type='video').count()==3
    approve(db,project)
    assert len(approved_candidates(db,project))==3


def test_reuse_only_preflights_all_and_fresh_clears_pins(db,library):
    *_,original,images,clips,storage=library
    # Tuple has user/company before original.
    approve(db,original)
    project=next_project(db,original,'reuse_only')
    plan=plan_reuse(db,project,storage)
    assert len({s['reused_asset_id'] for s in plan})==3
    project.storyboard=plan
    project.reuse_policy='fresh'
    assert all('reused_asset_id' not in s for s in plan_reuse(db,project,storage))
    project.reuse_policy='reuse_only'
    clips[1].is_available=False;db.commit()
    with pytest.raises(ValueError,match='未调用视频模型'):
        plan_reuse(db,project,storage)
    project.reuse_policy='prefer_reuse'
    assert sum(bool(s.get('reused_asset_id')) for s in plan_reuse(db,project,storage))==2


def test_scope_review_duration_aspect_and_transition_are_enforced(db,library):
    user,company,original,images,clips,storage=library
    approve(db,original);project=next_project(db,original)
    shot=project.storyboard[0]
    assert compatible(project,shot,clips[0])
    clips[0].duration_seconds=1
    assert not compatible(project,shot,clips[0])
    clips[0].duration_seconds=5
    project.aspect_ratio='16:9'
    assert not compatible(project,shot,clips[0])
    project.aspect_ratio='9:16'
    assert not compatible(project,{**shot,'transition_out':'fade'},clips[0])
    assert not compatible(project,{**shot,'visual_description':'不同的拍摄要求'},clips[0])
    other=create_test_company(db,user,name='其他酒店',slug='other')
    project.company_id=other.id;db.commit()
    assert approved_candidates(db,project)==[]
    project.company_id=company.id
    original.is_deleted=True;db.commit()
    assert approved_candidates(db,project)==[]


def test_prior_unknown_submission_never_replaced_by_reused_clip(db,library):
    _,_,original,_,_,storage=library
    approve(db,original);project=next_project(db,original)
    db.add(ProviderTask(company_id=project.company_id,video_project_id=project.id,provider_name='relay',
        task_type='video_generation',shot_number=1,status='submission_unknown'))
    db.commit()
    plan=plan_reuse(db,project,storage)
    assert 'reused_asset_id' not in plan[0]
    assert plan[1].get('reused_asset_id')


def test_usage_is_idempotent_and_missing_files_are_not_selected(db,library):
    _,_,original,_,clips,storage=library
    approve(db,original);project=next_project(db,original)
    record_use(db,project,clips[0]);db.commit()
    record_use(db,project,clips[0]);db.commit()
    assert clips[0].asset_metadata['clip_library']['usage_count']==1
    storage.delete_file(clips[0].file_key)
    assert 'reused_asset_id' not in plan_reuse(db,project,storage)[0]


def test_full_reuse_composes_without_provider_and_uses_new_finishing(db,library,monkeypatch):
    from app.services.video_generation import _compose_selected_images
    _,_,original,images,clips,storage=library
    approve(db,original);project=next_project(db,original,'reuse_only')
    provider=Mock(side_effect=AssertionError('Must not call model'))
    monkeypatch.setattr('app.services.video_generation.provider',provider)
    monkeypatch.setattr('app.services.video_generation.reference_url',Mock(side_effect=AssertionError('No reference upload')))
    assemble=Mock(return_value=b'new-edit')
    finish=Mock(return_value=(b'new-music-brand',{'text':'新品牌'}))
    monkeypatch.setattr('app.services.media_processing.assemble_model_clips',assemble)
    monkeypatch.setattr('app.services.video_generation._finalize_content',finish)
    _compose_selected_images(db,project,[a.id for a in images])
    assert not provider.called
    assert assemble.call_args.args[0]==[b'raw-clip']*3
    assert assemble.call_args.args[2]==[5,5,5]
    assert finish.called
    assert project.project_status=='pending_review'
    assert project.quality_check_result['generation_requests']==0
    assert project.quality_check_result['reused_clips']==3
    assert db.query(ProviderTask).filter_by(video_project_id=project.id).count()==0
    assert all(c.asset_metadata['clip_library']['usage_count']==1 for c in clips)


def test_reuse_only_start_needs_no_model_configuration(db,library,monkeypatch):
    _,company,original,_,_,storage=library
    approve(db,original);project=next_project(db,original,'reuse_only')
    monkeypatch.setattr('app.services.video_generation.provider',Mock(side_effect=AssertionError('model configuration not needed')))
    monkeypatch.setattr('app.services.video_generation.enqueue',lambda *args:None)
    monkeypatch.setattr('app.services.video_generation.reference_url',Mock(side_effect=AssertionError('No image upload')))
    VideoService(db).start_generation(company.id,project.id)
    assert project.project_status=='analyzing'
    assert all(s['reused_asset_id'] for s in project.storyboard)


def test_reuse_only_missing_clips_does_not_submit(db,library,monkeypatch):
    _,company,original,_,_,storage=library
    project=next_project(db,original,'reuse_only')
    provider=Mock(side_effect=AssertionError('Never submit'))
    monkeypatch.setattr('app.services.video_generation.provider',provider)
    with pytest.raises(HTTPException):
        VideoService(db).start_generation(company.id,project.id)
    assert not provider.called
    assert project.project_status=='draft'


def test_approval_excludes_old_unused_attempts(db,library):
    _,_,project,_,clips,_=library
    project.storyboard=[dict(s) for s in project.storyboard if s['output_asset_id']!=str(clips[0].id)]
    approve(db,project)
    assert clips[0].asset_metadata['clip_library']['review_status']=='pending'
    assert len(approved_candidates(db,project))==2


def test_cached_completed_clip_does_not_download_again(db,library,monkeypatch):
    from app.services.video_generation import _generate_clip
    _,_,project,_,_,_=library
    client=Mock()
    monkeypatch.setattr('app.services.video_generation.httpx.Client',
        Mock(side_effect=AssertionError('Must use durable raw file')))
    content,task=_generate_clip(db,project,client,Mock(),shot_number=1)
    assert content==b'raw-clip'
    assert task.raw_asset_id
    assert not client.mock_calls


def test_partial_reuse_generates_only_missing_shot(db,library,monkeypatch):
    from app.services.video_generation import _compose_selected_images
    _,_,original,images,clips,storage=library
    approve(db,original)
    clips[1].is_available=False;db.commit()
    project=next_project(db,original)
    generated=Mock(return_value=(b'new-clip',Mock(provider_task_id='new',raw_asset_id=None)))
    monkeypatch.setattr('app.services.video_generation._generate_clip',generated)
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    monkeypatch.setattr('app.services.video_generation.reference_url',lambda *a,**kw:'https://example.invalid/ref')
    monkeypatch.setattr('app.services.media_processing.assemble_model_clips',lambda *a:b'assembled')
    monkeypatch.setattr('app.services.video_generation._finalize_content',lambda *a:(b'final',{}))
    _compose_selected_images(db,project,[a.id for a in images])
    assert generated.call_count==1
    assert generated.call_args.kwargs['shot_number']==2
    assert project.quality_check_result['reused_clips']==2
    assert project.quality_check_result['generation_requests']==1


def test_incoming_fade_prevents_reuse(db,library):
    _,_,original,_,clips,_=library
    project=next_project(db,original)
    project.storyboard=[{**s,**({'transition_out':'fade'} if i==0 else {})}
                        for i,s in enumerate(project.storyboard)]
    assert not compatible(project,project.storyboard[1],clips[1])
