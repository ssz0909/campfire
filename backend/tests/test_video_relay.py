import asyncio
import json
import httpx
import pytest
from app.providers.video.relay_provider import RelayVideoProvider
from app.providers.video.base import VideoGenerationRequest
from app.config import settings
from app.services.video_generation import recover as recover_video_jobs

def test_relay_submit_and_poll(monkeypatch):
    monkeypatch.setattr(settings, 'VIDEO_BASE_URL', 'https://relay.test/v1/')
    monkeypatch.setattr(settings, 'VIDEO_MODEL', 'test-video')
    monkeypatch.setattr(settings, 'VIDEO_API_KEY', 'test-key')
    monkeypatch.setattr(settings, 'VIDEO_STATUS_URL', '')
    seen=[]
    def handle(request):
        seen.append(str(request.url))
        assert request.headers['Authorization'] == 'Bearer test-key'
        if request.method == 'POST':
            body = json.loads(request.content)
            assert body['model'] == 'test-video'
            assert body['metadata']['parameters'] == {'resolution':'720P','duration':5,'audio':True}
            assert 'duration_seconds' not in body
            return httpx.Response(200,json={'id':'job1','status':'queued'})
        return httpx.Response(200,json={'data':{'id':'job1','status':'succeeded','video_url':'https://cdn.test/a.mp4'}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handle),**kw))
    provider=RelayVideoProvider()
    result=asyncio.run(provider.submit_generation(VideoGenerationRequest(prompt='hotel',duration_seconds=5,aspect_ratio='9:16')))
    assert result.status == 'processing'
    result=asyncio.run(provider.get_task_status(result.provider_task_id))
    assert result.status == 'completed'
    assert seen == ['https://relay.test/v1/video/generations','https://relay.test/v1/video/generations/job1']

@pytest.mark.parametrize('response',[{}, {'id':'a','status':'completed'}, {'id':'a','status':'unknown'}])
def test_invalid_response_is_not_reported_as_success(response):
    with pytest.raises(ValueError): RelayVideoProvider.parse(response)

def test_first_frame_payload(monkeypatch):
    from unittest.mock import AsyncMock
    for key,value in [('VIDEO_BASE_URL','https://relay.test/v1/video/generations'),('VIDEO_MODEL','wan3.0-video'),('VIDEO_API_KEY','test')]:
        monkeypatch.setattr(settings,key,value)
    provider=RelayVideoProvider()
    send=AsyncMock(return_value={'id':'job1','status':'processing'})
    monkeypatch.setattr(provider,'request',send)
    asyncio.run(provider.submit_generation(VideoGenerationRequest(prompt='酒店',duration_seconds=5,
        aspect_ratio='9:16',reference_image_url='https://cdn.test/a.png')))
    body=send.call_args.kwargs['json']
    assert body['metadata']['input']['media']==[{'type':'first_frame','url':'https://cdn.test/a.png'}]
    assert body['metadata']['parameters']['audio'] is True
    assert body['model']=='wan3.0-video'

def test_recovery_uses_existing_provider_id(db, monkeypatch, tmp_path):
    from app.models.video_project import VideoProject,ProviderTask
    from app.models.asset import Asset
    from app.providers.video.base import VideoGenerationResult
    from app.services import video_generation as generation
    from tests.conftest import create_test_user,create_test_company
    from unittest.mock import AsyncMock,Mock
    from contextlib import contextmanager
    user=create_test_user(db);company=create_test_company(db,user)
    project=VideoProject(company_id=company.id,created_by=user.id,title='恢复生成',creation_mode='prompt_to_video',
        project_status='generating_shots',target_duration_seconds=5,aspect_ratio='9:16')
    db.add(project);db.flush()
    task=ProviderTask(company_id=company.id,video_project_id=project.id,provider_name='relay',
        task_type='video_generation',provider_task_id='existing',status='processing')
    db.add(task);db.commit()
    provider=Mock()
    provider.get_task_status=AsyncMock(return_value=VideoGenerationResult(provider_task_id='existing',
        status='completed',output_url='https://cdn.test/v.mp4'))
    provider.submit_generation=AsyncMock()
    class Session:
        def __getattr__(self,key): return getattr(db,key)
        def close(self): pass
    class Response:
        headers={'content-type':'video/mp4'}
        def raise_for_status(self): pass
        def iter_bytes(self): return iter([b'video'])
    class Client:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        @contextmanager
        def stream(self,*args): yield Response()
    monkeypatch.setattr(generation,'SessionLocal',Session)
    monkeypatch.setattr(generation,'provider',lambda:provider)
    monkeypatch.setattr(generation.httpx,'Client',Client)
    monkeypatch.setattr(settings,'LOCAL_STORAGE_PATH',str(tmp_path))
    monkeypatch.setattr(settings,'STORAGE_BACKEND','local')
    monkeypatch.setattr('app.services.media_processing.enrich_video_asset',lambda *args:None)
    monkeypatch.setattr('app.services.media_processing.inspect_video',lambda *args:({}, b''))
    monkeypatch.setattr('app.services.media_processing.assemble_model_clips',lambda clips,*args:clips[0])
    generation.run(str(project.id))
    assert provider.submit_generation.call_count==0
    assert provider.get_task_status.call_args.args==('existing',)
    db.refresh(project)
    assert project.project_status=='pending_review'
    assert db.get(Asset,project.output_asset_id).file_size_bytes==5
    assert (tmp_path/db.get(Asset,project.output_asset_id).file_key).read_bytes()==b'video'

def test_restart_never_submits_unconfirmed_job(db,monkeypatch):
    from app.models.video_project import VideoProject
    from app.services import video_generation as generation
    from tests.conftest import create_test_user,create_test_company
    from unittest.mock import Mock
    user=create_test_user(db);company=create_test_company(db,user)
    project=VideoProject(company_id=company.id,created_by=user.id,title='未确认提交',
        creation_mode='prompt_to_video',project_status='analyzing')
    db.add(project);db.commit()
    class Session:
        def __enter__(self):return db
        def __exit__(self,*args):pass
    monkeypatch.setattr(generation,'SessionLocal',Session)
    enqueue=Mock();monkeypatch.setattr(generation,'enqueue',enqueue)
    recover_video_jobs()
    assert enqueue.call_count==0
    assert project.project_status=='failed'

def test_multiple_shots_resume_without_resubmitting_or_double_counting_cost(db, monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import AsyncMock, Mock
    from tests.conftest import create_test_user, create_test_company
    from app.models.video_project import VideoProject, ProviderTask
    from app.models.cost import CostRecord
    from app.services import video_generation as generation
    user = create_test_user(db); company = create_test_company(db, user)
    project = VideoProject(company_id=company.id, created_by=user.id, title='多镜头恢复',
        creation_mode='reference_inspired', project_status='generating_shots')
    db.add(project); db.flush()
    first = ProviderTask(company_id=company.id, video_project_id=project.id, provider_name='relay',
        task_type='video_generation', shot_number=1, provider_task_id='existing-shot',
        status='completed', output_url='https://cdn.test/first.mp4')
    db.add(first); db.commit()
    client = Mock()
    from app.providers.video.base import VideoGenerationResult
    client.submit_generation = AsyncMock(return_value=VideoGenerationResult(provider_task_id='new-shot',
        status='completed', output_url='https://cdn.test/second.mp4', cost_cents=10))
    class Response:
        headers = {'content-type':'video/mp4'}
        def raise_for_status(self): pass
        def iter_bytes(self): return iter([b'dynamic-video'])
    class Downloader:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        @contextmanager
        def stream(self, *args): yield Response()
    monkeypatch.setattr(generation.httpx, 'Client', Downloader)
    monkeypatch.setattr('app.services.media_processing.inspect_video', lambda *args: ({}, b''))
    request = VideoGenerationRequest(prompt='动态酒店镜头', duration_seconds=5, aspect_ratio='9:16')
    for _ in range(2):
        for shot in (1,2):
            content, task = generation._generate_clip(db, project, client, request, shot)
            assert content == b'dynamic-video'
            assert task.shot_number == shot
    assert client.submit_generation.await_count == 1
    assert db.query(ProviderTask).filter_by(video_project_id=project.id).count() == 2
    assert db.query(CostRecord).filter_by(video_project_id=project.id).count() == 1


def test_relay_error_details_are_preserved_and_secrets_redacted(monkeypatch):
    monkeypatch.setattr(settings, 'VIDEO_BASE_URL', 'https://relay.test/v1')
    monkeypatch.setattr(settings, 'VIDEO_MODEL', 'test-video')
    monkeypatch.setattr(settings, 'VIDEO_API_KEY', 'secret-test-key')
    original = httpx.AsyncClient
    def handle(request):
        body = json.loads(request.content)
        assert type(body['metadata']['parameters']['duration']) is int
        return httpx.Response(400, json={'error': {'message': 'duration invalid secret-test-key https://cdn.test/a?token=secret'}})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    with pytest.raises(ValueError) as exc:
        asyncio.run(RelayVideoProvider().submit_generation(VideoGenerationRequest(prompt='hotel', duration_seconds=5.0, aspect_ratio='9:16')))
    message = str(exc.value)
    assert 'duration invalid' in message
    assert 'HTTP 400' in message
    assert 'secret-test-key' not in message and 'token=secret' not in message


@pytest.mark.parametrize('state', ['NOT_START', 'SUBMITTED', 'IN_PROGRESS'])
def test_tokenspace_waiting_states_preserve_relay_task_id(state):
    result = RelayVideoProvider.parse({'code': 'success', 'data': {'id': 36, 'task_id': 'task_relay', 'status': state}}, 'task_relay')
    assert result.status == 'processing'
    assert result.provider_task_id == 'task_relay'


def test_tokenspace_success_result_and_ids():
    result = RelayVideoProvider.parse({'code': 'success', 'data': {
        'id': 36, 'task_id': 'task_relay', 'status': 'SUCCESS', 'result_url': 'https://cdn.test/video.mp4',
        'data': {'output': {'task_id': 'upstream-id', 'task_status': 'SUCCEEDED', 'video_url': 'https://cdn.test/video.mp4'}}}}, 'task_relay')
    assert result.status == 'completed'
    assert result.provider_task_id == 'task_relay'
    assert result.output_url == 'https://cdn.test/video.mp4'
    assert RelayVideoProvider.parse({'data': {'id': 36, 'status': 'IN_PROGRESS'}}, 'task_relay').provider_task_id == 'task_relay'


def test_tokenspace_failure_reason():
    result = RelayVideoProvider.parse({'data': {'task_id': 'task_relay', 'status': 'FAILURE', 'fail_reason': 'unsupported size'}})
    assert result.status == 'failed'
    assert result.error == 'unsupported size'
