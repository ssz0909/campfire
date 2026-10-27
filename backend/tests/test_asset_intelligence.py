import base64
import io
import json
import uuid
from unittest.mock import AsyncMock, Mock
from PIL import Image
import pytest
from fastapi import HTTPException
from tests.conftest import create_test_user,create_test_company
from app.config import settings
from app.models.asset import Asset
from app.models.video_project import VideoProject
from app.services.asset_selection import select_assets_for_video
from app.services.asset_vision import analyze_image
from app.services.video_service import VideoService


def image_bytes(color):
    image=Image.new('RGB',(320,240),color)
    buf=io.BytesIO();image.save(buf,'PNG');return buf.getvalue()


def test_vision_request_sends_image_and_normalizes_tags(monkeypatch):
    for key,value in [('LLM_BASE_URL','https://relay.test/v1'),('LLM_MODEL','vision-model'),('LLM_API_KEY','test-key')]:
        monkeypatch.setattr(settings,key,value)
    response={'content':'```json\n'+json.dumps({'category':'guest_room','tags':['客房','落地窗','城市景观'],
        'caption':'带落地窗的客房','visual_description':'一间整洁客房，窗外可见城市建筑。','people_visible':False})+'\n```',
        'model':'vision-model','input_tokens':30,'output_tokens':20}
    mock=AsyncMock(return_value=response)
    monkeypatch.setattr('app.services.asset_vision.OpenAIProvider.complete',mock)
    result=analyze_image(image_bytes('blue'),'image/png')
    assert result['category']=='guest_room' and result['tags'][0]=='客房'
    content=mock.await_args.args[0][1]['content']
    image=next(part for part in content if part['type']=='image_url')
    assert base64.b64decode(image['image_url']['url'].split(',',1)[1])


def test_vision_missing_config_is_nonfatal(monkeypatch):
    for key in ('LLM_BASE_URL','LLM_MODEL','LLM_API_KEY'):monkeypatch.setattr(settings,key,'')
    assert analyze_image(image_bytes('red'),'image/png')['status']=='skipped'


def make_asset(db,company,user,name,category,tags,description):
    asset=Asset(company_id=company.id,uploaded_by=user.id,name=name,original_filename=name+'.jpg',
        file_key=f'{uuid.uuid4()}.jpg',asset_type='image',mime_type='image/jpeg',file_size_bytes=10,
        processing_status='ready',is_available=True,category=category,tags=tags,source_description=description,
        asset_metadata={'vision_analysis':{'status':'completed','caption':description,'visual_description':description}})
    db.add(asset);db.flush();return asset


def test_topic_selection_prefers_recognized_images_and_is_tenant_scoped(db):
    user,company=create_test_user(db),None
    company=create_test_company(db,user)
    other=create_test_company(db,create_test_user(db,email='other-assets@example.com'),slug='other-assets')
    room=make_asset(db,company,user,'房间窗景','guest_room',['客房','落地窗'],'大床房窗外城市景观')
    lobby=make_asset(db,company,user,'酒店大堂','lobby',['前台'],'酒店接待前厅')
    stale=make_asset(db,company,user,'未识别照片','other',['客房'],'客房')
    stale.asset_metadata={'vision_analysis':{'status':'failed'}}
    make_asset(db,other,user,'越权房间','guest_room',['客房'],'客房')
    db.commit()
    selected=select_assets_for_video(db,company.id,'突出客房落地窗與城市景观',limit=2)
    assert selected[0].id==room.id
    assert all(item.company_id==company.id for item in selected)
    assert stale.id not in [item.id for item in selected]


def test_video_project_rejects_foreign_or_unready_images(db):
    user=create_test_user(db)
    company=create_test_company(db,user)
    other=create_test_company(db,create_test_user(db,email='foreign-image@example.com'),slug='foreign-image')
    foreign=make_asset(db,other,user,'foreign','guest_room',[],'')
    db.commit()
    from app.schemas.video_project import VideoProjectCreate
    with pytest.raises(HTTPException):
        VideoService(db).create_project(company.id,user.id,VideoProjectCreate(title='x',creation_mode='reference_inspired',selected_asset_ids=[foreign.id]))


def test_asset_search_filters_by_category_and_recognized_topic(client,db):
    user=create_test_user(db)
    company=create_test_company(db,user)
    room=make_asset(db,company,user,'窗景','guest_room',['客房','落地窗'],'明亮客房')
    make_asset(db,company,user,'早餐','breakfast',['早餐'],'餐台')
    db.commit()
    from tests.conftest import auth_headers
    response=client.get(f'/api/v1/companies/{company.id}/assets?asset_type=image&category=guest_room&q=落地窗',headers=auth_headers(user))
    assert response.status_code==200,response.text
    assert response.json()['total']==1 and response.json()['items'][0]['id']==str(room.id)


def test_multiple_selected_images_generate_model_clips_and_bind_sources(db, monkeypatch, tmp_path):
    user = create_test_user(db)
    company = create_test_company(db, user)
    images = [make_asset(db, company, user, name, 'guest_room', ['客房'], name)
              for name in ('落地窗', '床头')]
    project = VideoProject(company_id=company.id, created_by=user.id, title='酒店宣传片',
        creation_mode='reference_inspired', selected_asset_ids=[str(a.id) for a in images],
        target_duration_seconds=10, aspect_ratio='9:16', project_status='analyzing')
    db.add(project); db.commit()
    monkeypatch.setattr(settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(settings, 'STORAGE_BACKEND', 'local')
    monkeypatch.setattr('app.services.video_generation.provider', lambda: Mock())
    monkeypatch.setattr('app.services.video_generation.reference_url', lambda db, p, aid: f'https://cdn.test/{aid}.jpg')
    calls = []
    def generate(db, project, provider, request, shot_number):
        calls.append((request, shot_number))
        return f'dynamic-clip-{shot_number}'.encode(), Mock(provider_task_id=f'job-{shot_number}')
    monkeypatch.setattr('app.services.video_generation._generate_clip', generate)
    assembled = Mock(return_value=b'composed-video')
    monkeypatch.setattr('app.services.media_processing.assemble_model_clips', assembled)
    monkeypatch.setattr('app.services.media_processing.enrich_video_asset', lambda *a: None)
    from app.services.video_generation import _compose_selected_images
    _compose_selected_images(db, project, [a.id for a in images])
    assert len(calls) == 2
    assert [request.reference_image_url for request, _ in calls] == [f'https://cdn.test/{a.id}.jpg' for a in images]
    assert all(request.duration_seconds == 5 and request.aspect_ratio == '9:16' for request, _ in calls)
    assert '落地窗' in calls[0][0].prompt and '床头' in calls[1][0].prompt
    assembled.assert_called_once_with([b'dynamic-clip-1', b'dynamic-clip-2'], '9:16', 5)
    assert project.project_status == 'pending_review'
    assert len(project.storyboard) == 2
    output = db.get(Asset, project.output_asset_id)
    assert output.asset_metadata['production_mode'] == 'video_model_multi_shot'
    assert output.asset_metadata['source_asset_ids'] == [str(a.id) for a in images]


def test_multi_image_requires_model_and_public_reference_url(db, monkeypatch):
    user = create_test_user(db); company = create_test_company(db, user)
    images = [make_asset(db, company, user, str(i), 'guest_room', ['客房'], '客房') for i in range(2)]
    from app.schemas.video_project import VideoProjectCreate
    project = VideoService(db).create_project(company.id, user.id, VideoProjectCreate(
        title='test', creation_mode='reference_inspired', selected_asset_ids=[a.id for a in images]))
    assert project.target_duration_seconds == 10
    monkeypatch.setattr(settings, 'PUBLIC_BASE_URL', '')
    with pytest.raises(HTTPException, match='VIDEO_BASE_URL'):
        VideoService(db).start_generation(company.id, project.id)
    monkeypatch.setattr('app.services.video_generation.provider', lambda: Mock())
    with pytest.raises(HTTPException, match='PUBLIC_BASE_URL'):
        VideoService(db).start_generation(company.id, project.id)
    assert project.project_status == 'draft'
