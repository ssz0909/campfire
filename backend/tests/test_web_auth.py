import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.connectors import web_auth as auth, web_platform as web
from app.core.secrets import encrypt_json

REAL_CLIENT = httpx.Client


def template(platform):
    if platform == 'douyin':
        return auth.api._default_douyin({})['templates']['identity']
    return {'url': 'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/auth/auth_data',
            'method': 'POST', 'body': {'timestamp': 1, 'rawKeyBuff': 'token', 'pluginSessionId': 'session'}}


def cookies(platform, value='credential'):
    return [{'name': 'sessionid', 'value': value, 'domain': auth.api.HOSTS[platform], 'path': '/', 'expires': -1}]


def payload(platform, uid='123'):
    return {'status_code': 0, 'user': {'uid': uid}} if platform == 'douyin' else {
        'errCode': 0, 'data': {'finderUser': {'finderUsername': uid}}}


def transport(monkeypatch, handler):
    monkeypatch.setattr(auth.httpx, 'Client', lambda **kwargs: REAL_CLIENT(
        transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.parametrize('platform', ['douyin', 'wechat_channels'])
def test_actual_api_identity_replaces_all_page_text_and_storage(monkeypatch, tmp_path, platform):
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url.host == auth.api.HOSTS[platform]
        assert request.headers['cookie'] == 'sessionid=credential'
        if platform == 'wechat_channels':
            assert json.loads(request.content)['timestamp'] > 1
        return httpx.Response(201, json=payload(platform))
    transport(monkeypatch, handle)
    monkeypatch.setattr(web.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    # A hostile/changed page is deliberately unreadable; neither DOM nor its
    # storage may be consulted to determine authorization.
    page = Mock(url='https://' + auth.api.HOSTS[platform] + '/changed-layout')
    page.is_closed.return_value = False
    page.evaluate.side_effect = AssertionError('DOM is not authentication')
    page.locator.side_effect = AssertionError('text is not authentication')
    context = SimpleNamespace(cookies=lambda: cookies(platform))
    session = {'page': page, 'context': context, 'metrics_api_templates': {'identity': template(platform)}}
    monkeypatch.setattr(web, '_profiles', {'company:' + platform: session})
    monkeypatch.setattr(web, '_save_session', lambda *args: True)
    state = web.session_status('company', platform)
    assert state['publish_ready'] and state['identity_verified'] and state['session_saved']
    assert state['auth_source'] == 'web_api' and state['auth_state'] == 'verified'
    assert web._metrics_page_status(platform, session)['publish_ready']
    assert len(calls) == 1  # Polls reuse a short-lived proof for this exact credential set.


@pytest.mark.parametrize('platform', ['douyin', 'wechat_channels'])
def test_cache_invalidates_on_credentials_change_or_forced_submission(monkeypatch, platform):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=payload(platform, '123' if len(calls) < 2 else '456'))
    transport(monkeypatch, handle)
    cache = {}
    first = auth.check(platform, cookies(platform), template(platform), cache)
    assert auth.check(platform, cookies(platform), template(platform), cache) == first
    second = auth.check(platform, cookies(platform, 'rotated'), template(platform), cache)
    assert first['account_fingerprint'] != second['account_fingerprint']
    assert not web._account_matches(second, first['account_fingerprint'])
    auth.check(platform, cookies(platform, 'rotated'), template(platform), cache, force=True)
    assert len(calls) == 3


@pytest.mark.parametrize('status,body,state', [
    (401, {}, 'expired'), (403, {}, 'unverified'), (429, {}, 'unverified'),
    (302, {}, 'unverified'), (200, {}, 'unverified'),
    (200, {'errCode': 0, 'data': {}}, 'unverified'),
    (200, {'errCode': False, 'data': {'finderUser': {'finderUsername': 'spoof'}}}, 'unverified'),
])
def test_failed_or_ambiguous_interfaces_never_authorize(monkeypatch, status, body, state):
    transport(monkeypatch, lambda request: httpx.Response(status, json=body))
    result = auth.check('wechat_channels', cookies('wechat_channels'), template('wechat_channels'), {})
    assert not result['publish_ready'] and result['login_required'] and result['auth_state'] == state
    assert 'account_fingerprint' not in result


def test_timeout_does_not_delete_encrypted_session_or_trust_saved_identity(monkeypatch, tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout('private-url?token=private', request=request)
    transport(monkeypatch, timeout)
    monkeypatch.setattr(web.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(web, '_profiles', {})
    monkeypatch.setattr(web, '_closed_auth_caches', {})
    directory = tmp_path / 'platform-sessions/company/wechat_channels'
    directory.mkdir(parents=True)
    saved = directory / 'web-session.enc'
    saved.write_text(encrypt_json({'cookies': cookies('wechat_channels'), 'account_identity': {
        'account_fingerprint': 'old-id', 'identity_verified': True}}))
    (directory / 'metrics-api.enc').write_text(encrypt_json({'templates': {'identity': template('wechat_channels')}}))
    before = saved.read_bytes()
    result = web.session_status('company', 'wechat_channels')
    assert result['auth_state'] == 'unverified' and not result['publish_ready']
    assert result['session_saved'] and not result['browser_open']
    assert saved.read_bytes() == before and 'private' not in str(result)


def test_closed_session_is_freshly_verified_without_starting_browser(monkeypatch, tmp_path):
    transport(monkeypatch, lambda request: httpx.Response(200, json=payload('douyin')))
    monkeypatch.setattr(web.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(web, '_profiles', {})
    monkeypatch.setattr(web, '_closed_auth_caches', {})
    monkeypatch.setattr(web, '_runtime', Mock(side_effect=AssertionError('must not start browser')))
    directory = tmp_path / 'platform-sessions/company/douyin'
    directory.mkdir(parents=True)
    (directory / 'web-session.enc').write_text(encrypt_json({'cookies': cookies('douyin'),
        'account_identity': {'account_fingerprint': 'stale-id', 'identity_verified': True}}))
    result = web.session_status('company', 'douyin')
    assert result['status'] == 'session_saved' and result['publish_ready']
    assert result['account_fingerprint'] == web._identity_digest('douyin', '123')
    assert not result['browser_open']


def test_non_allowlisted_endpoint_and_missing_template_never_make_request(monkeypatch):
    transport(monkeypatch, lambda request: pytest.fail('untrusted endpoint'))
    for endpoint in (None, {'url': 'https://evil.example/auth', 'method': 'POST'},
                     {'url': 'https://channels.weixin.qq.com/publish', 'method': 'POST'}):
        assert not auth.check('wechat_channels', cookies('wechat_channels'), endpoint, {})['publish_ready']


def test_publish_forces_proof_refresh_before_using_identity(monkeypatch):
    session = {'page': Mock(), 'auth_probe': {'result': {'auth_state': 'verified'}}}
    def read(*args):
        assert 'auth_probe' not in session
        return {'status': 'login_required', 'login_required': True, 'publish_ready': False, 'auth_state': 'expired'}
    monkeypatch.setattr(web, 'session_status', read)
    result = web._wait_for_account_ready('company', 'douyin', session, 'expected')
    assert result['auth_state'] == 'expired'
    session['page'].locator.assert_not_called()
    session['page'].wait_for_function.assert_not_called()
