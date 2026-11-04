"""Read creator metrics over HTTP; this module never starts a browser.

Only observed, explicitly allowed read endpoints can be replayed. Request
templates and cookies stay encrypted in the selected tenant/account profile.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.config import settings
from app.core.secrets import decrypt_json, encrypt_json
from app.connectors.work_metrics import extract_records, match_records

HOSTS = {'douyin': 'creator.douyin.com', 'wechat_channels': 'channels.weixin.qq.com'}
PATHS = {
    'douyin': {'identity': ('/web/api/media/user/info/',),
               'list': ('/janus/douyin/creator/pc/work_list', '/web/api/creator/item/list/')},
    'wechat_channels': {'identity': ('/cgi-bin/mmfinderassistant-bin/auth/auth_data',),
                        'list': ('/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list',)},
}
# Independent of the interactive browser thread. Keep background HTTP scans
# serial in this deployment, even when several companies request a sync.
_scan_slot = threading.Lock()


def profile_path(company_id, platform, profile_id=None):
    if platform not in HOSTS:
        raise ValueError('unsupported platform')
    root = Path(settings.LOCAL_STORAGE_PATH) / 'platform-sessions' / str(uuid.UUID(str(company_id)))
    return root / (platform + '-accounts') / str(uuid.UUID(str(profile_id))) if profile_id else root / platform


def _kind(platform, url, method):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != HOSTS[platform] or parsed.port not in (None, 443) or parsed.username or parsed.password:
        return None
    if method != ('GET' if platform == 'douyin' else 'POST'):
        return None
    return next((kind for kind, paths in PATHS[platform].items() if parsed.path.rstrip('/') in [p.rstrip('/') for p in paths]), None)


def _ok(payload, platform):
    return isinstance(payload, dict) and payload.get('status_code' if platform == 'douyin' else 'errCode') == 0


def _identity(payload, platform, cookies):
    if not _ok(payload, platform):
        return {}
    if platform == 'douyin':
        from app.connectors.web_platform import _douyin_account_identity, _identity_digest
        result = _douyin_account_identity(payload)
        value = next((c.get('value') for c in cookies if c.get('name') == 'uid_tt'
                      and c.get('domain', '').lstrip('.') in ('douyin.com', HOSTS[platform])), None)
        if result and value:
            result['legacy_account_fingerprint'] = _identity_digest(platform, value, 'websha256:')
        return result
    data = payload.get('data')
    user = data.get('finderUser') if isinstance(data, dict) else None
    value = user.get('finderUsername') if isinstance(user, dict) else None
    if not isinstance(value, str) or not value:
        return {}
    digest = hashlib.sha256((platform + ':' + value).encode()).hexdigest()
    return {'account_fingerprint': 'websha256:' + digest, 'identity_verified': True}


def _headers(headers):
    # Cookie comes from the account's scoped cookie jar, never a stale raw
    # header. No redirects or arbitrary URLs are accepted by the HTTP client.
    return {k: v for k, v in headers.items() if k.lower() in (
        'user-agent', 'referer', 'origin', 'accept', 'accept-language', 'content-type') or k.lower().startswith('x-')}


def observe_request(response, platform, session):
    """Called by login browsers only; capture successful read requests in memory."""
    try:
        kind = _kind(platform, response.url, response.request.method)
        if not kind or not 200 <= response.status < 300:
            return
        payload = response.json()
        if not _ok(payload, platform):
            return
        body = response.request.post_data_json if platform == 'wechat_channels' else None
        if platform == 'wechat_channels' and not isinstance(body, dict):
            return
        if kind == 'list':
            if platform == 'wechat_channels' and body.get('currentPage') not in (0, 1):
                return
            if platform == 'douyin' and dict(parse_qsl(urlparse(response.url).query)).get('max_cursor', '0') != '0':
                return
        session.setdefault('metrics_api_templates', {})[kind] = {
            'url': response.request.url, 'method': response.request.method,
            'headers': _headers(response.request.all_headers()), 'body': body}
    except Exception:
        # An optional data-collection template must never break login.
        return


def save_capture(directory, platform, session):
    """Persist a verified login's read templates, without visiting another page."""
    templates = session.get('metrics_api_templates') or {}
    identity = session.get('account_identity') or {}
    if not identity.get('identity_verified') or not templates:
        return
    cookies = session['context'].cookies()
    signature = hashlib.sha256(json.dumps([templates, identity, cookies], sort_keys=True).encode()).hexdigest()
    if signature == session.get('metrics_api_saved_signature') and time.monotonic() - session.get('metrics_api_saved_at', 0) < 60:
        return
    path = Path(directory) / 'metrics-api.enc'
    previous = decrypt_json(path.read_text()) if path.exists() else {}
    if previous.get('identity', {}).get('account_fingerprint') == identity.get('account_fingerprint'):
        templates = {**previous.get('templates', {}), **templates}
    bundle = {'templates': templates, 'cookies': cookies, 'identity': identity,
              'captured_at': time.time()}
    temporary = path.with_name('metrics-api-' + uuid.uuid4().hex + '.tmp')
    try:
        # Create with restrictive permissions from the first write.
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            stream.write(encrypt_json(bundle))
        temporary.replace(path)
        session['metrics_api_saved_signature'] = signature
        session['metrics_api_saved_at'] = time.monotonic()
    finally:
        temporary.unlink(missing_ok=True)


def _default_douyin(saved):
    # These are the normal first-page parameters observed on creator/manage.
    headers = {'user-agent': 'Mozilla/5.0', 'referer': 'https://creator.douyin.com/creator-micro/content/manage'}
    return {'cookies': saved.get('cookies', []), 'identity': saved.get('account_identity', {}), 'templates': {
        'identity': {'url': 'https://creator.douyin.com/web/api/media/user/info/', 'method': 'GET', 'headers': headers},
        'list': {'url': 'https://creator.douyin.com/janus/douyin/creator/pc/work_list?' + urlencode({
            'status': 0, 'count': 12, 'max_cursor': 0, 'scene': 'star_atlas', 'device_platform': 'android', 'aid': 1128}),
                 'method': 'GET', 'headers': headers}}}


def _cookie_jar(cookies):
    jar = httpx.Cookies()
    for c in cookies:
        domain = c.get('domain', '')
        if domain.lstrip('.') not in ('douyin.com', 'creator.douyin.com', 'weixin.qq.com', 'channels.weixin.qq.com'):
            continue
        expires = c.get('expires', -1)
        jar.jar.set_cookie(Cookie(0, c['name'], c['value'], None, False, domain, True,
            domain.startswith('.'), c.get('path', '/'), True, bool(c.get('secure', True)),
            int(expires) if expires and expires > 0 else None, not expires or expires <= 0,
            None, None, {}, False))
    return jar


class ReadError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def _fetch(client, template, platform, kind, *, body=None, cursor=None):
    if _kind(platform, template.get('url', ''), template.get('method')) != kind:
        raise ReadError('api_setup_required', '未找到有效的只读接口配置，请重新打开对应账号网页登录')
    parsed = urlparse(template['url'])
    # Observed calls work with these ordinary list parameters. Do not replay
    # captured tracking/signature query strings or expose them to HTTP logs.
    query = {k: v for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if platform == 'douyin' and kind == 'list' and k in (
                 'status', 'count', 'max_cursor', 'scene', 'device_platform', 'aid')}
    url = urlunparse(parsed._replace(query=urlencode(query), fragment=''))
    if cursor is not None:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query['max_cursor'] = str(cursor)
        url = urlunparse(parsed._replace(query=urlencode(query)))
    body = body if body is not None else template.get('body')
    if isinstance(body, dict) and 'timestamp' in body:
        body = {**body, 'timestamp': int(time.time() * 1000)}
    kwargs = {'headers': _headers(template.get('headers') or {})}
    if platform == 'wechat_channels':
        kwargs['json'] = body
    with client.stream(template['method'], url, **kwargs) as response:
        if response.status_code == 429:
            raise ReadError('rate_limited', '平台请求频率受限，请稍后再同步；保留上次数据')
        if not 200 <= response.status_code < 300:
            raise ReadError('api_unavailable', '平台接口暂不可用，请稍后重试；保留上次数据')
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > 10 * 1024 * 1024:
                raise ReadError('api_unavailable', '平台接口响应过大，已停止采集')
    try:
        payload = json.loads(content)
    except (ValueError, UnicodeError):
        raise ReadError('api_unavailable', '平台接口未返回有效数据，可能需要重新验证登录')
    if not _ok(payload, platform):
        expired = platform == 'douyin' and isinstance(payload, dict) and payload.get('status_code') == 8
        raise ReadError('login_required' if expired else 'api_unavailable',
            '平台会话已过期，请重新登录对应账号' if expired else '平台未接受数据查询，请重新打开对应账号网页登录检查会话')
    return payload


def collection_result(targets, records, observed_ids, complete):
    items = match_records(targets, records, complete)
    count = len(observed_ids)
    message = None if len(items) == len(targets) else (
        f'已读取 {count} 条平台作品，列表已读完整；未匹配记录请核对账号及发布文案。' if complete else
        f'已读取 {count} 条平台作品，列表尚未读完整；无作品 ID 的记录暂不能安全匹配。')
    statuses, messages = {}, {}
    for target in targets:
        if target['job_id'] not in items and target.get('post_id') in observed_ids:
            statuses[target['job_id']] = 'metrics_unavailable'
            messages[target['job_id']] = '已找到作品，但平台未返回可用指标；保留上次数据'
    status = 'synced' if len(items) == len(targets) else 'partial' if items else 'unmatched'
    if not items and statuses and len(statuses) == len(targets):
        status = 'metrics_unavailable'
    return {'status': status, 'items': items, 'record_count': count, 'list_complete': complete,
            'message': message, 'unmatched_statuses': statuses, 'unmatched_messages': messages,
            'transport': 'web_api'}


def read_work_metrics(company_id, platform, targets, expected_account_id=None, profile_id=None):
    """Read a bounded account scan without using Playwright or its worker queue."""
    try:
        directory = profile_path(company_id, platform, profile_id)
        path = directory / 'metrics-api.enc'
        bundle = decrypt_json(path.read_text()) if path.exists() else {}
        saved_path = directory / 'web-session.enc'
        saved = decrypt_json(saved_path.read_text()) if saved_path.exists() else {}
        if not bundle and platform == 'douyin' and saved:
            bundle = _default_douyin(saved)
        templates = bundle.get('templates') or {}
        if platform == 'douyin' and 'identity' not in templates:
            templates['identity'] = _default_douyin(saved)['templates']['identity']
        if not bundle.get('cookies') or not all(k in templates for k in ('identity', 'list')):
            raise ReadError('api_setup_required', '请打开对应账号网页登录，完成登录并打开作品管理后检查登录状态，以准备接口采集；后台不会自动启动浏览器')
        with _scan_slot, httpx.Client(cookies=_cookie_jar(bundle['cookies']), timeout=httpx.Timeout(15, connect=8), follow_redirects=False) as client:
            started = time.monotonic()
            payload = _fetch(client, templates['identity'], platform, 'identity')
            identity = _identity(payload, platform, bundle['cookies'])
            if not identity.get('identity_verified'):
                raise ReadError('identity_unavailable', '平台接口暂未返回可核对的账号身份，未采集数据')
            from app.connectors.web_platform import _account_matches
            expected = expected_account_id or (bundle.get('identity') or {}).get('account_fingerprint')
            if not expected or not _account_matches(identity, expected):
                raise ReadError('identity_mismatch', '接口返回账号与绑定账号不一致，已停止采集，请检查对应账号登录')
            records, observed, cursor, complete = [], set(), 0, False
            body = dict(templates['list'].get('body') or {})
            current_page = body.get('currentPage', 1)
            if platform == 'wechat_channels' and (isinstance(current_page, bool) or not isinstance(current_page, int) or current_page not in (0, 1)):
                raise ReadError('api_setup_required', '作品接口缺少有效首页参数，请重新打开作品管理并检查登录状态')
            for number in range(20):
                if time.monotonic() - started > 90:
                    break
                if platform == 'wechat_channels':
                    body['currentPage'] = current_page + number
                payload = _fetch(client, templates['list'], platform, 'list', body=body,
                                 cursor=cursor if platform == 'douyin' else None)
                data = payload.get('data') if platform == 'wechat_channels' else (
                    payload if any(isinstance(payload.get(k), list) for k in ('items', 'aweme_list', 'item_list')) else payload.get('data'))
                lists = ('list',) if platform == 'wechat_channels' else ('items', 'aweme_list', 'item_list')
                if not isinstance(data, dict) or not any(isinstance(data.get(k), list) for k in lists):
                    raise ReadError('api_unavailable', '平台作品接口结构已变化，未覆盖已有数据')
                previous = len(observed)
                for key in lists:
                    for item in (data.get(key) or [])[:1000]:
                        if not isinstance(item, dict):
                            continue
                        identifier = item.get('objectId') if platform == 'wechat_channels' else (item.get('aweme_id') or item.get('id'))
                        if isinstance(identifier, (str, int)) and not isinstance(identifier, bool) and str(identifier):
                            observed.add(str(identifier))
                records.extend(extract_records(payload, platform))
                total = data.get('totalCount') if platform == 'wechat_channels' else data.get('total')
                more = data.get('continueFlag') if platform == 'wechat_channels' else data.get('has_more', data.get('hasMore'))
                complete = (isinstance(more, (int, bool)) and more == 0) or (
                    isinstance(total, int) and not isinstance(total, bool) and total >= 0 and len(observed) >= total)
                if complete or len(observed) == previous:
                    break
                if platform == 'douyin':
                    next_cursor = data.get('max_cursor')
                    if isinstance(next_cursor, bool) or not isinstance(next_cursor, (str, int)) or str(next_cursor) == str(cursor):
                        break
                    cursor = next_cursor
                elif 'lastBuff' in body and isinstance(data.get('lastBuff'), str):
                    body['lastBuff'] = data['lastBuff']
            return collection_result(targets, records, observed, complete)
    except ReadError as exc:
        return {'status': exc.status, 'items': {}, 'message': exc.message, 'transport': 'web_api'}
    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
        # Never leak URLs, cookies, raw request bodies or exception text.
        return {'status': 'api_unavailable', 'items': {}, 'message': '平台接口连接失败或会话配置不可用，请稍后重试；保留上次数据', 'transport': 'web_api'}
