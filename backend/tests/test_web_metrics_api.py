import json
import uuid
from unittest.mock import Mock

import httpx
import pytest

from app.connectors import web_metrics_api as api
from app.connectors.web_platform import _identity_digest
from app.core.secrets import decrypt_json, encrypt_json

COMPANY = uuid.UUID('11111111-1111-4111-8111-111111111111')
PROFILE = uuid.UUID('22222222-2222-4222-8222-222222222222')
REAL_CLIENT = httpx.Client


@pytest.fixture
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(api.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr('app.connectors.web_platform._runtime', Mock(side_effect=AssertionError('browser must not start')))
    monkeypatch.setattr('app.connectors.web_platform._ensure_open', Mock(side_effect=AssertionError('browser must not open')))
    return tmp_path


def install(monkeypatch, handler):
    monkeypatch.setattr(api.httpx, 'Client', lambda **kwargs: REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs))


def bundle(platform, profile=None):
    identity = _identity_digest(platform, '123' if platform == 'douyin' else 'hotel',
                                'webuidsha256:' if platform == 'douyin' else 'websha256:')
    domain = '.douyin.com' if platform == 'douyin' else 'channels.weixin.qq.com'
    cookies = [{'name': 'session', 'value': 'secret-' + str(profile), 'domain': domain, 'path': '/', 'expires': -1}]
    if platform == 'douyin':
        result = api._default_douyin({'cookies': cookies, 'account_identity': {'account_fingerprint': identity}})
    else:
        common = {'timestamp': 1, 'rawKeyBuff': 'secret', 'pluginSessionId': 'session'}
        result = {'cookies': cookies, 'identity': {'account_fingerprint': identity}, 'templates': {
            'identity': {'url': 'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/auth/auth_data',
                         'method': 'POST', 'body': common},
            'list': {'url': 'https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list',
                     'method': 'POST', 'body': {**common, 'currentPage': 1, 'pageSize': 1}}}}
    path = api.profile_path(COMPANY, platform, profile)
    path.mkdir(parents=True, exist_ok=True)
    (path / 'metrics-api.enc').write_text(encrypt_json(result))
    return result, identity


def test_douyin_http_pagination_and_priority_without_browser(local, monkeypatch):
    _, identity = bundle('douyin')
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.host == 'creator.douyin.com'
        assert request.headers['cookie'] == 'session=secret-None'
        if request.url.path.endswith('/info/'):
            return httpx.Response(200, json={'status_code': 0, 'user': {'uid': '123'}})
        cursor = request.url.params['max_cursor']
        identifier = 1 if cursor == '0' else 2
        return httpx.Response(200, json={'status_code': 0, 'has_more': cursor == '0', 'max_cursor': 99,
            'items': [{'id': identifier, 'metrics': {'view_count': str(identifier * 40)}}],
            'aweme_list': [{'aweme_id': str(identifier), 'statistics': {'play_count': 0}}]})
    install(monkeypatch, handler)
    result = api.read_work_metrics(COMPANY, 'douyin', [{'job_id': 'j', 'post_id': '2'}], identity)
    assert result['status'] == 'synced' and result['transport'] == 'web_api'
    assert result['list_complete'] and result['record_count'] == 2
    assert result['items']['j']['views'] == 80 and len(calls) == 3


def test_channels_201_identity_and_complete_pagination(local, monkeypatch):
    _, identity = bundle('wechat_channels')
    calls = []
    def handler(request):
        body = json.loads(request.content)
        assert body['timestamp'] > 1 and body['rawKeyBuff'] == 'secret'
        calls.append(request.url.path)
        if request.url.path.endswith('/auth_data'):
            return httpx.Response(201, json={'errCode': 0, 'data': {'finderUser': {'finderUsername': 'hotel'}}})
        page = body['currentPage']
        return httpx.Response(201, json={'errCode': 0, 'data': {'totalCount': 3, 'continueFlag': page < 3,
            'list': [{'objectId': str(page), 'readCount': page, 'likeCount': 0}]}})
    install(monkeypatch, handler)
    result = api.read_work_metrics(COMPANY, 'wechat_channels', [{'job_id': 'j', 'post_id': '3'}], identity)
    assert result['status'] == 'synced' and result['record_count'] == 3 and result['list_complete']
    assert result['items']['j']['views'] == 3 and len(calls) == 4


def test_account_mismatch_stops_before_list_and_preserves_cache(local, monkeypatch):
    _, identity = bundle('wechat_channels', PROFILE)
    path = api.profile_path(COMPANY, 'wechat_channels', PROFILE) / 'metrics-api.enc'
    before = path.read_bytes()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(201, json={'errCode': 0, 'data': {'finderUser': {'finderUsername': 'other'}}})
    install(monkeypatch, handler)
    result = api.read_work_metrics(COMPANY, 'wechat_channels', [], identity, PROFILE)
    assert result['status'] == 'identity_mismatch' and not result['items'] and len(calls) == 1
    assert path.read_bytes() == before


def test_missing_tenant_or_profile_does_not_reuse_another_account(local, monkeypatch):
    _, identity = bundle('wechat_channels', PROFILE)
    install(monkeypatch, lambda request: pytest.fail('must not call HTTP for a missing profile'))
    assert api.read_work_metrics(uuid.uuid4(), 'wechat_channels', [], identity, PROFILE)['status'] == 'api_setup_required'
    assert api.read_work_metrics(COMPANY, 'wechat_channels', [], identity)['status'] == 'api_setup_required'


@pytest.mark.parametrize('code,payload,status', [
    (429, {}, 'rate_limited'), (302, {}, 'api_unavailable'),
    (200, {'status_code': 8}, 'login_required'), (200, {'status_code': 99}, 'api_unavailable'),
    (200, [], 'api_unavailable'),
])
def test_http_failures_do_not_start_browser_or_return_counts(local, monkeypatch, code, payload, status):
    _, identity = bundle('douyin')
    install(monkeypatch, lambda request: httpx.Response(code, json=payload, headers={'location': 'https://example.invalid'}))
    result = api.read_work_metrics(COMPANY, 'douyin', [{'job_id': 'j', 'post_id': '1'}], identity)
    assert result['status'] == status and result['items'] == {}


def test_tampered_url_cannot_send_cookies_or_publish(local, monkeypatch):
    value, identity = bundle('wechat_channels')
    value['templates']['identity']['url'] = 'https://example.invalid/cgi-bin/mmfinderassistant-bin/auth/auth_data'
    path = api.profile_path(COMPANY, 'wechat_channels') / 'metrics-api.enc'
    path.write_text(encrypt_json(value))
    install(monkeypatch, lambda request: pytest.fail('unapproved URL must not be requested'))
    assert api.read_work_metrics(COMPANY, 'wechat_channels', [], identity)['status'] == 'api_setup_required'
    assert api._kind('wechat_channels', 'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/post/post_create', 'POST') is None


def test_repeated_page_never_claims_complete_list(local, monkeypatch):
    _, identity = bundle('douyin')
    def handler(request):
        if request.url.path.endswith('/info/'):
            return httpx.Response(200, json={'status_code': 0, 'user': {'uid': '123'}})
        return httpx.Response(200, json={'status_code': 0, 'has_more': True, 'max_cursor': 10,
            'items': [{'id': 1, 'metrics': {'view_count': 5}}]})
    install(monkeypatch, handler)
    result = api.read_work_metrics(COMPANY, 'douyin', [{'job_id': 'j', 'title': 'hotel', 'created_at': '2026-11-03'}], identity)
    assert not result['list_complete'] and not result['items']


def test_cookie_expiration_is_enforced(local, monkeypatch):
    value, identity = bundle('douyin')
    value['cookies'][0]['expires'] = 1
    (api.profile_path(COMPANY, 'douyin') / 'metrics-api.enc').write_text(encrypt_json(value))
    def handler(request):
        assert 'cookie' not in request.headers
        return httpx.Response(200, json={'status_code': 8})
    install(monkeypatch, handler)
    assert api.read_work_metrics(COMPANY, 'douyin', [], identity)['status'] == 'login_required'


def test_capture_only_reads_and_saves_encrypted_verified_account(local):
    path = api.profile_path(COMPANY, 'wechat_channels'); path.mkdir(parents=True)
    request = Mock(method='POST', url='https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list',
                   post_data_json={'currentPage': 1, 'rawKeyBuff': 'private'})
    request.all_headers.return_value = {'cookie': 'private-cookie', 'content-type': 'application/json'}
    response = Mock(url=request.url, status=201, request=request)
    response.json.return_value = {'errCode': 0, 'data': {'list': []}}
    session = {'context': Mock(), 'account_identity': {'identity_verified': True, 'account_fingerprint': 'bound'}}
    session['context'].cookies.return_value = [{'name': 'c', 'value': 'private-cookie'}]
    api.observe_request(response, 'wechat_channels', session)
    api.save_capture(path, 'wechat_channels', session)
    raw = (path / 'metrics-api.enc').read_text()
    assert 'private' not in raw and (path / 'metrics-api.enc').stat().st_mode & 0o777 == 0o600
    result = decrypt_json(raw)
    assert result['templates']['list']['body']['rawKeyBuff'] == 'private'
    assert 'cookie' not in result['templates']['list']['headers']
    request.post_data_json = {'currentPage': 3, 'rawKeyBuff': 'other'}
    api.observe_request(response, 'wechat_channels', session)
    assert session['metrics_api_templates']['list']['body']['currentPage'] == 1
