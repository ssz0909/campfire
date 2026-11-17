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


def test_unknown_submission_retries_without_id_and_preserves_history(db):
    user, _, p = setup_project(db)
    done = task(db, p, 1, 'completed', 'saved')
    failed = task(db, p, 2, 'failed', 'bad')
    unknown = task(db, p, 3, 'submission_unknown')
    pending = task(db, p, 4, 'pending')
    unknown.error_message = 'original disconnect'
    VideoService(db)._prepare_retry(p, user_id=user.id)
    assert failed.status == unknown.status == pending.status == 'retry_requested'
    assert done.status == 'completed' and done.provider_task_id == 'saved'
    assert unknown.provider_task_id is None and unknown.error_message == 'original disconnect'
    assert unknown.input_params['_submission_recovery']['confirmed_by'] == str(user.id)
    assert unknown.input_params['_submission_recovery']['source'] == 'explicit_retry'


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
    unknown = task(db, p, 1, 'submission_unknown'); db.commit()
    enqueued = []
    monkeypatch.setattr(generation, 'provider', lambda: object())
    monkeypatch.setattr(generation, 'enqueue', enqueued.append)
    monkeypatch.setattr(generation, 'reference_url', lambda *args: None)
    outsider = create_test_user(db, email='other@example.com')
    url = f'/api/v1/companies/{company.id}/video-projects/{p.id}/retry'
    assert client.post(url, headers=auth_headers(outsider)).status_code == 403
    assert client.post(url, headers=auth_headers(user)).status_code == 200
    assert enqueued == [p.id]
    db.refresh(unknown)
    assert unknown.status == 'retry_requested'
    assert unknown.input_params['_submission_recovery']['confirmed_by'] == str(user.id)
    assert client.post(url, headers=auth_headers(user)).status_code == 400
    assert enqueued == [p.id]


def test_submission_recovery_resubmit_requires_confirmation_and_keeps_history(client, db, monkeypatch):
    user, company, p = setup_project(db)
    done = task(db, p, 1, 'completed', 'saved')
    unknown = task(db, p, 2, 'submission_unknown')
    unknown.error_message = 'original disconnect'
    db.commit()
    base=f'/api/v1/companies/{company.id}/video-projects/{p.id}/submission-recovery'
    outsider=create_test_user(db,email='recovery-outsider@example.com')
    assert client.get(base,headers=auth_headers(outsider)).status_code==403
    headers=auth_headers(user)
    rows=client.get(base,headers=headers).json()['items']
    assert len(rows)==1 and rows[0]['attempt_id']==str(unknown.id)
    url=base+'/'+str(unknown.id)
    assert client.post(url,headers=headers,json={'action':'resubmit'}).status_code==422
    assert client.post(url,headers=headers,json={'action':'resubmit','confirmed':True}).status_code==200
    db.refresh(unknown); db.refresh(done)
    assert unknown.status=='retry_requested' and unknown.error_message=='original disconnect'
    assert unknown.input_params['_submission_recovery']['confirmed_by']==str(user.id)
    assert done.status=='completed'
    assert client.post(url,headers=headers,json={'action':'resubmit','confirmed':True}).status_code==409
    assert client.get(base,headers=headers).json()['items']==[]
    VideoService(db)._prepare_retry(p)
    from app.models.audit_log import AuditLog
    assert db.query(AuditLog).filter_by(action='video.submission_recovery').count()==1


def test_submission_recovery_links_existing_task_without_submission(client, db, monkeypatch):
    user, company, p = setup_project(db)
    unknown=task(db,p,2,'submission_unknown');db.commit()
    upstream=AsyncMock()
    upstream.get_task_status.return_value=VideoGenerationResult(provider_task_id='task-existing',status='processing')
    monkeypatch.setattr(generation,'provider',lambda:upstream)
    url=f'/api/v1/companies/{company.id}/video-projects/{p.id}/submission-recovery/{unknown.id}'
    headers=auth_headers(user)
    assert client.post(url,headers=headers,json={'action':'link','confirmed':True}).status_code==422
    assert client.post(url,headers=headers,json={'action':'link','confirmed':True,'provider_task_id':'task-existing'}).status_code==200
    db.refresh(unknown)
    assert unknown.provider_task_id=='task-existing' and unknown.status=='processing'
    upstream.submit_generation.assert_not_called()
    VideoService(db)._prepare_retry(p)
    assert unknown.status=='processing' and '_retry_poll_started_at' in unknown.input_params


def test_submission_recovery_rejects_failed_lookup_and_duplicate_id(client, db, monkeypatch):
    user, company, p = setup_project(db)
    unknown=task(db,p,2,'submission_unknown')
    task(db,p,1,'completed','taken-id');db.commit()
    upstream=AsyncMock();upstream.get_task_status.side_effect=RuntimeError('network')
    monkeypatch.setattr(generation,'provider',lambda:upstream)
    url=f'/api/v1/companies/{company.id}/video-projects/{p.id}/submission-recovery/{unknown.id}'
    headers=auth_headers(user)
    for identifier,code in [('taken-id',409),('missing-id',422)]:
        response=client.post(url,headers=headers,json={'action':'link','confirmed':True,'provider_task_id':identifier})
        assert response.status_code==code
    db.refresh(unknown)
    assert unknown.status=='submission_unknown' and unknown.provider_task_id is None
    p.project_status='generating_shots';db.commit()
    assert client.post(url,headers=headers,json={'action':'resubmit','confirmed':True}).status_code==409


def test_recovery_browser_direct_retry_without_id(db, client, monkeypatch):
    import json,mimetypes
    from pathlib import Path
    from urllib.parse import urlparse
    from playwright.sync_api import sync_playwright,expect
    from app.core.security import create_refresh_token
    user,company,p=setup_project(db)
    unknown=task(db,p,5,'submission_unknown');db.commit()
    enqueued=[]
    monkeypatch.setattr(generation,'provider',lambda:object())
    monkeypatch.setattr(generation,'enqueue',enqueued.append)
    monkeypatch.setattr(generation,'reference_url',lambda *args:None)
    root=Path(__file__).resolve().parents[2]/'frontend/dist'
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_init_script('localStorage.setItem("refresh_token",'+json.dumps(create_refresh_token({'sub':str(user.id)}))+');localStorage.setItem("currentCompanyId",'+json.dumps(str(company.id))+')')
        def route(r):
            path=urlparse(r.request.url).path
            if path.startswith('/assets/'):
                f=root/path.lstrip('/')
                r.fulfill(status=200 if f.exists() else 404,body=f.read_bytes() if f.exists() else b'',content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
            elif path.startswith('/video/') or path=='/login':
                r.fulfill(status=200,body=(root/'index.html').read_bytes(),content_type='text/html')
            else:
                response=client.request(r.request.method,r.request.url,content=r.request.post_data_buffer,headers=r.request.headers)
                r.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
        context.route('**/*',route)
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('https://campfire.dawoai.com/video/'+str(p.id))
        expect(page.get_by_text('没有获取到任务 ID 的分镜直接重新提交生成',exact=False)).to_be_visible()
        expect(page.get_by_placeholder('中转后台任务 ID（关联已有任务时填写）')).to_have_count(0)
        expect(page.get_by_role('button',name='关联上游任务',exact=True)).to_have_count(0)
        retry=page.get_by_role('button',name='重新执行',exact=True)
        expect(retry).to_be_enabled()
        page.screenshot(path='/tmp/campfire-retry-desktop.png',full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path='/tmp/campfire-retry-mobile.png',full_page=True)
        retry.click()
        expect(retry).to_have_count(0)
        assert not errors
        db.refresh(unknown);db.refresh(p)
        assert unknown.status=='retry_requested' and p.project_status=='analyzing'
        assert enqueued==[p.id]
        browser.close()
