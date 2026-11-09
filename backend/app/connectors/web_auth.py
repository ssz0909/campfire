"""Read-only provider identity probes. Never infer authentication from DOM text."""
from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy

import httpx

from app.connectors import web_metrics_api as api


def pending(message='平台身份接口暂不可用，请稍后检查状态，无需退出账号'):
    return {'status': 'login_required', 'login_required': True, 'publish_ready': False,
            'identity_unavailable': True, 'auth_state': 'unverified',
            'auth_source': 'web_api', 'message': message}


def check(platform, cookies, template, cache, *, force=False):
    """Cache a bounded proof for one credential set, never just a saved account ID.

    Callers own the cache and scope it to a tenant/account profile. Transient
    failures retain encrypted credentials but cannot authorize a publication.
    """
    if platform not in api.HOSTS:
        raise ValueError('unsupported platform')
    if not template or api._kind(platform, template.get('url', ''), template.get('method')) != 'identity':
        return pending('尚未取得平台身份接口配置，请重新打开该账号网页登录，无需退出账号')
    signature = hashlib.sha256(json.dumps([platform, cookies, template], sort_keys=True).encode()).hexdigest()
    previous = cache.get('auth_probe') or {}
    ttl = 60 if previous.get('result', {}).get('auth_state') == 'verified' else 3
    if not force and previous.get('signature') == signature and time.monotonic() - previous.get('at', 0) < ttl:
        return deepcopy(previous['result'])
    result = pending()
    try:
        with httpx.Client(cookies=api._cookie_jar(cookies), timeout=httpx.Timeout(8, connect=4), follow_redirects=False) as client:
            payload = api._fetch(client, template, platform, 'identity')
        code = payload.get('status_code' if platform == 'douyin' else 'errCode')
        identity = api._identity(payload, platform, cookies) if type(code) is int and code == 0 else {}
        if identity.get('identity_verified') and identity.get('account_fingerprint'):
            result = {**identity, 'status': 'authorized', 'login_required': False,
                      'publish_ready': True, 'auth_state': 'verified', 'auth_source': 'web_api',
                      'auth_checked_at': time.time(), 'message': '平台身份接口校验成功'}
    except api.ReadError as exc:
        if exc.status == 'login_required':
            result = {'status': 'login_required', 'login_required': True, 'publish_ready': False,
                      'auth_state': 'expired', 'auth_source': 'web_api',
                      'message': '平台接口确认会话已过期，请重新登录对应账号'}
        elif exc.status == 'rate_limited':
            result = pending('平台身份接口请求受限，请稍后重试，无需退出账号')
    except (httpx.HTTPError, OSError, ValueError, TypeError):
        pass
    cache['auth_probe'] = {'signature': signature, 'at': time.monotonic(), 'result': deepcopy(result)}
    return result


def template_for(directory, platform, session=None):
    """Only the allowlisted identity request is replayed; never use DOM fields."""
    template = ((session or {}).get('metrics_api_templates') or {}).get('identity')
    if template:
        return template
    if platform == 'douyin':
        return api._default_douyin({})['templates']['identity']
    if directory:
        from app.core.secrets import decrypt_json
        path = directory / 'metrics-api.enc'
        try:
            bundle = decrypt_json(path.read_text()) if path.exists() else {}
            return (bundle.get('templates') or {}).get('identity')
        except (OSError, ValueError, TypeError):
            pass
    return None
