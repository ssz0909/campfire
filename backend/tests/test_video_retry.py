from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from app.models.video_project import VideoProject, ProviderTask
from app.providers.video.base import VideoGenerationRequest, VideoGenerationResult
from app.providers.video.relay_provider import RelayVideoRequestError
from app.services import video_generation as generation
from app.services.video_service import VideoService
from tests.conftest import create_test_user, create_test_company, auth_headers


def setup_project(db, note=''):
    user = create_test_user(db)
    company = create_test_company(db, user)
    project = VideoProject(company_id=company.id, created_by=user.id, title='Retry', creation_mode='prompt_to_video',
                           project_status='failed', quality_check_result={'note': note})
    db.add(project); db.flush()
    return user, company, project


def task(db, p, shot, status, provider_id=None):
    row = ProviderTask(company_id=p.company_id, video_project_id=p.id, provider_name='relay',
                       task_type='video_generation', shot_number=shot, status=status, provider_task_id=provider_id)
    db.add(row); db.flush()
    return row


def test_retry_reuses_success_and_only_authorizes_failed_shots(db):
    _, _, p = setup_project(db)
    done = task(db, p, 1, 'completed', 'done')
    failed = task(db, p, 2, 'failed', 'bad')
    rejected = task(db, p, 3, 'rejected')
    VideoService(db)._prepare_retry(p)
    assert done.status == 'completed'
    assert failed.status == rejected.status == 'retry_requested'
    assert failed.provider_task_id == 'bad'


def test_unknown_submission_blocks_without_marking_other_shots(db):
    _, _, p = setup_project(db)
    failed = task(db, p, 1, 'failed', 'bad')
    unknown = task(db, p, 2, 'submission_unknown')
    with pytest.raises(HTTPException) as exc:
        VideoService(db)._prepare_retry(p)
    assert exc.value.status_code == 409
    assert failed.status == 'failed'
    assert unknown.status == 'submission_unknown'


def test_legacy_http400_failure_can_retry(db):
    _, _, p = setup_project(db, '视频接口 HTTP 400，请检查接口、模型和密钥配置')
    old = task(db, p, 1, 'pending')
    VideoService(db)._prepare_retry(p)
    assert old.status == 'retry_requested'
    assert '400' in old.error_message


def test_http_rejection_is_persisted_and_explicit_retry_creates_new_attempt(db):
    _, _, p = setup_project(db)
    db.commit()
    request = VideoGenerationRequest(prompt='hotel', duration_seconds=5, aspect_ratio='9:16')
    client = AsyncMock()
    client.submit_generation.side_effect = RelayVideoRequestError('视频接口 HTTP 400：bad duration', 400)
    with pytest.raises(RelayVideoRequestError):
        generation._generate_clip(db, p, client, request, shot_number=1)
    old = db.query(ProviderTask).filter_by(video_project_id=p.id).one()
    assert old.status == 'rejected' and 'bad duration' in old.error_message
    VideoService(db)._prepare_retry(p); db.commit()
    client.submit_generation.side_effect = None
    client.submit_generation.return_value = VideoGenerationResult(provider_task_id='new-id', status='failed')
    with pytest.raises(ValueError):
        generation._generate_clip(db, p, client, request, shot_number=1)
    assert client.submit_generation.await_count == 2
    assert db.query(ProviderTask).filter_by(video_project_id=p.id).count() == 2
    assert old.status == 'retry_requested'


def test_retry_api_prevents_duplicate_execution_and_requires_membership(client, db, monkeypatch):
    user, company, p = setup_project(db)
    task(db, p, 1, 'rejected'); db.commit()
    enqueued = []
    monkeypatch.setattr(generation, 'provider', lambda: object())
    monkeypatch.setattr(generation, 'enqueue', enqueued.append)
    monkeypatch.setattr(generation, 'reference_url', lambda *args: None)
    outsider = create_test_user(db, email='other@example.com')
    url = f'/api/v1/companies/{company.id}/video-projects/{p.id}/retry'
    assert client.post(url, headers=auth_headers(outsider)).status_code == 403
    assert client.post(url, headers=auth_headers(user)).status_code == 200
    assert enqueued == [p.id]
    assert client.post(url, headers=auth_headers(user)).status_code == 400
    assert enqueued == [p.id]
