import copy
import uuid
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


def test_asset_list_hides_task_final_and_raw_clips_from_top_level(db,library):
    from app.services.asset_service import AssetService
    from app.models.asset import Asset
    from app.models.video_project import VideoProject
    from app.models.task import OperationTask
    user,company,project,images,clips,storage=library
    task=OperationTask(company_id=company.id,created_by=user.id,title='来源任务',task_type='video_generation',status='completed')
    db.add(task);db.flush();project.task_id=task.id
    final=Asset(company_id=company.id,uploaded_by=user.id,name='最终成片',original_filename='final.mp4',
        file_key='final.mp4',asset_type='video',mime_type='video/mp4',file_size_bytes=1,processing_status='ready')
    db.add(final);db.flush();project.output_asset_id=final.id;db.commit()
    items,total=AssetService(db,storage).list_assets(company.id,asset_type='video')
    assert final not in items
    assert total==0 and items==[]


def test_library_clip_regeneration_creates_isolated_billable_project(db,library,monkeypatch):
    from app.services.asset_clip_regeneration import create,related,MODE
    from app.models.video_project import VideoProject
    user,company,project,images,clips,storage=library
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    monkeypatch.setattr('app.services.video_generation.reference_url',lambda *args,**kwargs:'https://example.test/reference')
    queued=Mock();monkeypatch.setattr('app.services.video_generation.enqueue',queued)
    request_id=uuid.uuid4()
    variant=create(db,images[0],user.id,'镜头先展现泳池整体，再缓慢侧移展示瀑布水流',request_id,'9:16')
    assert variant.creation_mode==MODE and variant.task_id is None
    assert variant.music_disabled is True and variant.review_status=='pending_review'
    assert variant.script=='镜头先展现泳池整体，再缓慢侧移展示瀑布水流'
    assert variant.reference_asset_id==images[0].id and variant.storyboard[0]['source_asset_id']==str(images[0].id)
    queued.assert_called_once_with(variant.id)
    same=create(db,images[0],user.id,variant.script,request_id,'9:16')
    assert same.id==variant.id and queued.call_count==1
    with pytest.raises(HTTPException):
        create(db,images[0],user.id,'不允许并发重复生成',uuid.uuid4(),'9:16')
    source,related_clips,total,jobs=related(db,images[0])
    assert source.id==images[0].id and total==1 and len(related_clips)==1
    assert any(job['id']==str(variant.id) for job in jobs)


def test_task_final_and_raw_clips_are_hidden_from_top_level_asset_list(db,library):
    from app.services.asset_service import AssetService
    from app.models.task import OperationTask
    user,company,project,images,clips,storage=library
    task=OperationTask(company_id=company.id,created_by=user.id,title='视频任务',task_type='video_generation',status='completed')
    db.add(task);db.flush();project.task_id=task.id
    final=Asset(company_id=company.id,uploaded_by=user.id,name='最终成片',original_filename='final.mp4',
        file_key='final.mp4',asset_type='video',mime_type='video/mp4',file_size_bytes=1,processing_status='ready')
    db.add(final);db.flush();project.output_asset_id=final.id;db.commit()
    items,total=AssetService(db,storage).list_assets(company.id,asset_type='video')
    assert total==0 and items==[]


def test_hand_regenerated_variant_requires_explicit_approval(db,library,monkeypatch):
    from fastapi import HTTPException
    from app.services.asset_clip_regeneration import create,approve as approve_variant
    user,company,project,images,clips,storage=library
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    monkeypatch.setattr('app.services.video_generation.reference_url',lambda *args,**kwargs:'https://example.test/reference')
    monkeypatch.setattr('app.services.video_generation.enqueue',lambda *args:None)
    variant=create(db,clips[0],user.id,'人物自然入镜并向泳池边走去',uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        approve_variant(db,clips[0])
    assert error.value.status_code==409
    from app.models.video_project import ProviderTask
    generated=Asset(company_id=company.id,uploaded_by=user.id,name='手动分镜',original_filename='variant.mp4',
        file_key='variant.mp4',asset_type='video',mime_type='video/mp4',file_size_bytes=1,
        processing_status='ready',duration_seconds=5,asset_metadata={'production_mode':'raw_model_clip','clip_library':{
            'source_project_id':str(variant.id),'provider_task_id':str(uuid.uuid4()),
            'contract':{'source_asset_id':str(images[0].id),'aspect_ratio':variant.aspect_ratio,
                'generation_mode':variant.generation_mode,'framing':'wide','focal_x':0.5,'focal_y':0.5,
                'camera_movement':'自然运镜','transition_in':'cut','transition_out':'cut','video_style':'',
                'visual_description':'泳池','generation_prompt':'人工提示','retained_duration':3,
                'subshots':[]},'review_status':'pending','usage_count':0,'music_applied':False,'branding_applied':False}})
    db.add(generated);db.flush()
    provider_task=ProviderTask(company_id=company.id,video_project_id=variant.id,provider_name='relay',
        task_type='video_generation',shot_number=1,status='completed',raw_asset_id=generated.id)
    db.add(provider_task);db.flush()
    generated.asset_metadata['clip_library']['provider_task_id']=str(provider_task.id)
    variant.storyboard=[{**variant.storyboard[0],'output_asset_id':str(generated.id)}]
    variant.output_asset_id=generated.id;variant.project_status='pending_review';db.commit()
    approve_variant(db,generated)
    assert generated.asset_metadata['clip_library']['review_status']=='approved'


def test_regeneration_api_returns_durable_project_and_related_preview(client,db,library,monkeypatch):
    from tests.conftest import auth_headers
    user,company,project,images,clips,storage=library
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    monkeypatch.setattr('app.services.video_generation.reference_url',lambda *args,**kwargs:'https://example.test/reference')
    enqueue=Mock();monkeypatch.setattr('app.services.video_generation.enqueue',enqueue)
    path=f'/api/v1/companies/{company.id}/assets/{images[0].id}'
    response=client.post(path+'/regenerate-clip',headers=auth_headers(user),json={
        'prompt':'人物缓慢走向泳池','request_id':str(uuid.uuid4()),'aspect_ratio':'9:16'})
    assert response.status_code==202,response.text
    assert response.json()['status']=='analyzing'
    enqueue.assert_called_once()
    response=client.get(path+'/clips',headers=auth_headers(user))
    assert response.status_code==200,response.text
    assert response.json()['source']['id']==str(images[0].id)
    assert response.json()['total']==1 and len(response.json()['items'])==1
    assert response.json()['jobs'][0]['status']=='analyzing'


def test_manual_clip_generation_preserves_original_film(db,library,monkeypatch):
    from app.services.asset_clip_regeneration import create,generate,approve as approve_variant
    user,company,original,images,clips,storage=library
    before=copy.deepcopy(original.storyboard)
    original_output=original.output_asset_id
    original_status=original.project_status
    monkeypatch.setattr('app.services.video_generation.provider',lambda:Mock())
    monkeypatch.setattr('app.services.video_generation.reference_url',lambda *a,**kw:'https://example.test/reference')
    monkeypatch.setattr('app.services.video_generation.enqueue',lambda *a:None)
    variant=create(db,clips[0],user.id,'镜头缓慢靠近水面，保持真实建筑结构',uuid.uuid4())
    def fake_generate(db,project,provider,request,shot_number):
        assert project.id==variant.id and shot_number==1
        assert request.duration_seconds==5 and request.audio is False
        assert '镜头缓慢靠近水面' in request.prompt
        assert request.reference_image_url=='https://example.test/reference'
        task=ProviderTask(company_id=company.id,video_project_id=variant.id,provider_name='mock',
            task_type='video_generation',shot_number=1,status='completed',input_params={'prompt':request.prompt})
        db.add(task);db.flush()
        save_raw_clip(db,project,task,b'new-clip',storage)
        return b'new-clip',task
    monkeypatch.setattr('app.services.video_generation._generate_clip',fake_generate)
    generate(db,variant)
    assert variant.project_status=='pending_review' and variant.task_id is None
    new=db.get(Asset,variant.output_asset_id)
    assert new.asset_metadata['clip_library']['manual_variant'] is True
    assert new.asset_metadata['clip_library']['review_status']=='pending'
    assert new not in approved_candidates(db,variant)
    approve_variant(db,new)
    assert new in approved_candidates(db,variant)
    db.refresh(original)
    assert original.storyboard==before and original.output_asset_id==original_output
    assert original.project_status==original_status


def test_delete_clip_blocks_incomplete_project_and_preserves_completed_film(db,library):
    from app.services.asset_service import AssetService
    user,company,project,images,clips,storage=library
    project.project_status='generating_shots'
    db.commit()
    with pytest.raises(HTTPException) as error:
        AssetService(db,storage).delete_asset(company.id,clips[0].id)
    assert error.value.status_code==409 and not clips[0].is_deleted
    project.project_status='completed'
    db.commit()
    original=copy.deepcopy(project.storyboard)
    AssetService(db,storage).delete_asset(company.id,clips[0].id)
    assert clips[0].is_deleted and not clips[0].is_available
    assert not images[0].is_deleted and project.storyboard==original
