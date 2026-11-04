from unittest.mock import Mock

import pytest

from app.connectors import web_platform as web


@pytest.mark.parametrize('platform', ['wechat_channels', 'douyin'])
def test_publish_waits_for_restored_page_and_identity_before_upload(tmp_path, monkeypatch, platform):
    source = tmp_path / 'video.mp4'
    source.write_bytes(b'test')
    page = Mock()
    page.is_closed.return_value = False
    session = {'page': page}
    states = iter([
        {'status': 'login_required', 'login_required': True},
        {'status': 'authorized', 'login_required': False},
        {'status': 'authorized', 'login_required': False, 'identity_verified': True,
         'account_fingerprint': 'websha256:bound'},
    ])
    status = Mock(side_effect=lambda *args: next(states))
    monkeypatch.setattr(web, '_ensure_open', lambda *args: None)
    monkeypatch.setattr(web, '_get_session', lambda *args: session)
    monkeypatch.setattr(web, 'session_status', status)
    monkeypatch.setattr(web, '_page_text', lambda *args, **kwargs: '页面加载中')
    upload = Mock(side_effect=ValueError('TEST_STOP_BEFORE_SUBMIT'))
    if platform == 'douyin':
        page.locator.return_value.first.set_input_files = upload
    else:
        monkeypatch.setattr(web, '_open_channels_upload', lambda *args: object())
        monkeypatch.setattr(web, '_upload_channels_video', upload)
    result = web.publish.__wrapped__('company', platform, 'title', 'copy', str(source),
        expected_account_id='websha256:bound')
    assert upload.call_count == 1, result
    assert status.call_count == 3
    assert result['status'] == 'manual_required'  # Deliberately stop before any platform submit.


@pytest.mark.parametrize('platform', ['wechat_channels', 'douyin'])
def test_true_wrong_identity_stops_without_upload_or_retry(monkeypatch, platform):
    page = Mock()
    state = {'status':'authorized', 'login_required':False, 'identity_verified':True,
             'account_fingerprint':'websha256:other'}
    status = Mock(return_value=state)
    monkeypatch.setattr(web, 'session_status', status)
    result = web._wait_for_account_ready('company', platform, {'page':page}, 'websha256:bound')
    assert result['identity_mismatch'] and result['login_required']
    assert not result['publish_ready']
    assert status.call_count == 1
    page.wait_for_timeout.assert_not_called()
    page.goto.assert_not_called()


def test_missing_identity_timeout_does_not_claim_wrong_account(monkeypatch):
    page = Mock()
    monkeypatch.setattr(web, 'session_status', lambda *args: {
        'status':'authorized', 'login_required':False})
    monkeypatch.setattr(web, '_page_text', lambda *args: '视频号助手 · 内容管理')
    result = web._wait_for_account_ready('company', 'wechat_channels', {'page':page},
        'websha256:bound', timeout_ms=0)
    assert result['identity_unavailable'] and result['login_required']
    assert not result.get('identity_mismatch')
    assert '无需退出账号' in result['message']
    assert '账号不一致' not in result['message']


def test_explicit_login_screen_requests_login_instead_of_identity_mismatch(monkeypatch):
    page = Mock()
    monkeypatch.setattr(web, 'session_status', lambda *args: {
        'status':'login_required', 'login_required':True})
    monkeypatch.setattr(web, '_page_text', lambda *args: '扫码登录 · 验证码登录')
    result = web._wait_for_account_ready('company', 'wechat_channels', {'page':page}, 'websha256:bound')
    assert result['login_required'] and '登录已失效' in result['message']
    assert not result.get('identity_mismatch') and not result.get('identity_unavailable')
    page.wait_for_timeout.assert_not_called()


def test_missing_identity_stops_publish_and_metrics_before_any_platform_action(monkeypatch):
    page = Mock()
    session = {'page':page, 'context':Mock()}
    monkeypatch.setattr(web, '_ensure_open', lambda *args: None)
    monkeypatch.setattr(web, '_get_session', lambda *args: session)
    wait = Mock(return_value={'status':'login_required', 'login_required':True,
        'identity_unavailable':True, 'publish_ready':False})
    monkeypatch.setattr(web, '_wait_for_account_ready', wait)
    result = web.publish.__wrapped__('company', 'wechat_channels', 'title', 'copy', '/unused',
        expected_account_id='websha256:bound')
    assert result['identity_unavailable'] and result['status'] == 'manual_required'
    assert web.read_metrics.__wrapped__('company', 'wechat_channels', 'websha256:bound')['metrics'] == {}
    assert web.read_work_metrics.__wrapped__('company', 'wechat_channels', [], 'websha256:bound')['items'] == {}
    session['context'].new_page.return_value.close.assert_called_once()
    page.goto.assert_not_called()
    page.locator.assert_not_called()
