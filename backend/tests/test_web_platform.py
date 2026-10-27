from __future__ import annotations

import threading
from types import SimpleNamespace
from pathlib import Path

from app.connectors import web_platform


def test_editor_wait_reports_only_recognized_platform_notices(monkeypatch):
    import pytest
    class Editor:
        @property
        def first(self): return self
        def wait_for(self, **kwargs): raise TimeoutError()
    page = SimpleNamespace(locator=lambda selector: Editor())
    monkeypatch.setattr(web_platform, '_page_text', lambda *args, **kwargs: 'private account text 上传失败 网络异常')
    with pytest.raises(ValueError) as error:
        web_platform._wait_video_editor(page)
    assert '上传失败' in str(error.value) and '网络异常' in str(error.value)
    assert 'private account text' not in str(error.value)


def test_stale_local_singleton_links_are_removed_only_when_process_is_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(web_platform.socket, "gethostname", lambda: "test-host")
    monkeypatch.setattr(web_platform.os, "kill", lambda pid, signal: (_ for _ in ()).throw(ProcessLookupError()))
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        (tmp_path / name).symlink_to("test-host-72381")

    assert web_platform._remove_stale_singleton_links(tmp_path) is True
    assert not list(tmp_path.iterdir())


def test_active_or_foreign_singleton_lock_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(web_platform.socket, "gethostname", lambda: "test-host")
    lock = tmp_path / "SingletonLock"
    lock.symlink_to("other-host-72381")

    assert web_platform._remove_stale_singleton_links(tmp_path) is False
    assert lock.is_symlink()

    lock.unlink()
    lock.symlink_to("test-host-72381")
    monkeypatch.setattr(web_platform.os, "kill", lambda pid, signal: None)
    assert web_platform._remove_stale_singleton_links(tmp_path) is False
    assert lock.is_symlink()


class _Locator:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def nth(self, index):
        return _Locator(self.page)

    def is_visible(self):
        return True

    def inner_text(self, timeout=None):
        self.page.threads.append(threading.get_ident())
        return self.page.body


class _Page:
    def on(self, event, callback):
        pass

    def __init__(self, body="作品管理", url="https://creator.douyin.com/creator-micro/home"):
        self.body = body
        self.url = url
        self.threads = []

    def is_closed(self):
        return False

    def bring_to_front(self):
        self.threads.append(threading.get_ident())

    def goto(self, url, **kwargs):
        self.threads.append(threading.get_ident())
        self.url = url

    def locator(self, selector):
        return _Locator(self)

    @property
    def frames(self):
        return [self]

    def evaluate(self, script):
        return {'origin': 'https://' + web_platform.urlparse(self.url).hostname, 'localStorage': []}


class _Context:
    browser = None

    def on(self, event, callback):
        pass

    def __init__(self, page):
        self.pages = [page]

    def new_page(self):
        raise AssertionError("existing page should be reused")

    def cookies(self):
        return [{'name': 'secret-cookie', 'value': 'secret-value'}]


class _Playwright:
    def stop(self):
        pass


def test_login_window_reuses_existing_session_and_checks_authorization(monkeypatch):
    page = _Page()
    monkeypatch.setitem(web_platform._profiles, "test-company:douyin", {
        "pw": _Playwright(), "context": _Context(page), "page": page,
    })

    opened = web_platform.start_session("test-company", "douyin")
    status = web_platform.session_status("test-company", "douyin")

    assert opened["status"] == "browser_open"
    assert "已存在" in opened["message"]
    assert status["status"] == "authorized"
    assert len(set(page.threads)) == 1
    monkeypatch.delitem(web_platform._profiles, "test-company:douyin")


def test_login_page_remains_unauthorized_until_qr_is_completed(monkeypatch):
    page = _Page(body="扫码登录", url="https://creator.douyin.com/")
    monkeypatch.setitem(web_platform._profiles, "test-company:douyin", {
        "pw": _Playwright(), "context": _Context(page), "page": page,
    })

    status = web_platform.session_status("test-company", "douyin")

    assert status["status"] == "login_required"
    assert status["login_required"] is True
    monkeypatch.delitem(web_platform._profiles, "test-company:douyin")


def test_blank_or_unknown_page_is_not_authorized(monkeypatch):
    page = _Page(body="", url="https://creator.douyin.com/")
    monkeypatch.setitem(web_platform._profiles, "test-company:douyin", {"page": page})
    assert web_platform.session_status("test-company", "douyin")["status"] == "login_required"
    page.body = "网络错误"
    assert web_platform.session_status("test-company", "douyin")["status"] == "login_required"


def test_loading_page_keeps_session_pending(monkeypatch):
    page = _Page()
    def unavailable(selector):
        raise TimeoutError()
    page.locator = unavailable
    monkeypatch.setitem(web_platform._profiles, "test-company:douyin", {"page": page})
    result = web_platform.session_status("test-company", "douyin")
    assert result["status"] == "login_required"
    assert "仍在加载" in result["message"]


def test_status_persists_authorized_and_clears_disconnected(db, monkeypatch):
    from app.models.publishing import PlatformConnection
    from app.services.publishing_service import web_status
    from tests.conftest import create_test_user, create_test_company
    company = create_test_company(db, create_test_user(db))
    row = PlatformConnection(company_id=company.id, platform="douyin", status="authorizing")
    db.add(row)
    db.commit()
    monkeypatch.setattr(web_platform, "session_status", lambda *args: {"status": "authorized"})
    web_status(db, company.id, "douyin")
    assert row.status == "authorized"
    assert row.authorized_at is not None
    monkeypatch.setattr(web_platform, "session_status", lambda *args: {"status": "disconnected"})
    web_status(db, company.id, "douyin")
    assert row.status == "disconnected"


def test_start_failure_returns_readable_http_error(db, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.services.publishing_service import start_web
    from tests.conftest import create_test_user, create_test_company
    company = create_test_company(db, create_test_user(db))
    def fail(*args):
        raise RuntimeError("浏览器运行时未安装，请安装 Chromium 后重试")
    monkeypatch.setattr(web_platform, "start_session", fail)
    with pytest.raises(HTTPException) as error:
        start_web(db, company.id, "douyin")
    assert error.value.status_code == 503
    assert "浏览器运行时未安装" in error.value.detail


def test_two_platforms_share_runtime_but_keep_distinct_profiles(tmp_path, monkeypatch):
    from playwright import sync_api
    launches, starts, contexts = [], [], []
    class Context(_Context):
        def close(self):
            self.closed = True
    def launch(profile, **kwargs):
        launches.append(profile)
        context = Context(_Page())
        contexts.append(context)
        return context
    runtime = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch))
    def start():
        starts.append(True)
        return runtime
    monkeypatch.setattr(sync_api, 'sync_playwright', lambda: SimpleNamespace(start=start))
    monkeypatch.setattr(web_platform, '_playwright', None)
    monkeypatch.setattr(web_platform, '_profiles', {})
    monkeypatch.setattr(web_platform.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    assert web_platform.start_session('company', 'wechat_channels')['status'] == 'browser_open'
    assert web_platform.start_session('company', 'douyin')['status'] == 'browser_open'
    assert len(starts) == 1
    assert len(set(launches)) == 2
    web_platform.close_session('company', 'douyin')
    assert not getattr(contexts[0], 'closed', False)
    assert web_platform.start_session('company', 'wechat_channels')['status'] == 'browser_open'


def test_closed_window_preserves_encrypted_session_and_logout_clears_only_one_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(web_platform.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(web_platform, '_profiles', {})
    page = _Page()
    page.closed = False
    page.is_closed = lambda: page.closed
    context = _Context(page)
    context.storage_state = lambda: {'cookies': [{'name': 'secret-cookie', 'value': 'secret-value'}], 'origins': []}
    context.close = lambda: None
    context.clear_cookies = lambda: None
    web_platform._profiles['company:douyin'] = {'page': page, 'context': context}
    assert web_platform.session_status('company', 'douyin')['status'] == 'authorized'
    saved = web_platform._saved_path('company', 'douyin')
    assert 'secret-value' not in saved.read_text()
    assert saved.stat().st_mode & 0o777 == 0o600
    page.closed = True
    assert web_platform.session_status('company', 'douyin')['status'] == 'session_saved'
    # This also works after a backend restart, with no in-memory profile.
    assert web_platform.session_status('company', 'douyin')['status'] == 'session_saved'
    other = web_platform._profile_dir('company', 'wechat_channels') / 'keep'
    other.write_text('other platform')
    web_platform.close_session('company', 'douyin', logout=True)
    assert web_platform.session_status('company', 'douyin')['status'] == 'disconnected'
    assert other.exists()


def test_expired_login_invalidates_saved_session(tmp_path, monkeypatch):
    monkeypatch.setattr(web_platform.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(web_platform, '_profiles', {})
    path = web_platform._saved_path('company', 'douyin')
    path.write_text('old-session')
    web_platform._profiles['company:douyin'] = {'page': _Page(body='扫码登录')}
    assert web_platform.session_status('company', 'douyin')['login_required'] is True
    assert not path.exists()


def test_saved_session_reopens_and_expired_login_prevents_publish(tmp_path, monkeypatch):
    from app.core.secrets import encrypt_json
    monkeypatch.setattr(web_platform.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(web_platform, '_profiles', {})
    web_platform._saved_path('company', 'douyin').write_text(encrypt_json({'cookies': [], 'origins': []}))
    opened = []
    def reopen(company, platform):
        opened.append(platform)
        web_platform._profiles[f'{company}:{platform}'] = {'page': _Page(body='扫码登录')}
    monkeypatch.setattr(web_platform, 'start_session', reopen)
    result = web_platform.publish('company', 'douyin', 'title', '', '/unused.mp4')
    assert opened == ['douyin']
    assert result['login_required'] is True
    assert result['status'] == 'login_required'


def test_saved_session_has_distinct_database_status(db, monkeypatch):
    from app.models.publishing import PlatformConnection
    from app.services.publishing_service import web_status
    from tests.conftest import create_test_user, create_test_company
    company = create_test_company(db, create_test_user(db))
    row = PlatformConnection(company_id=company.id, platform='douyin', status='authorized')
    db.add(row)
    db.commit()
    monkeypatch.setattr(web_platform, 'session_status', lambda *args: {'status': 'session_saved', 'login_required': False})
    assert web_status(db, company.id, 'douyin')['status'] == 'session_saved'
    assert row.status == 'session_saved'


def test_channels_duplicate_body_detects_login_and_saves_session(tmp_path, monkeypatch):
    monkeypatch.setattr(web_platform.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(web_platform, '_profiles', {})
    page = _Page(body='视频号 · 助手 视频号ID: test 昨日数据', url='https://channels.weixin.qq.com/platform')
    page.evaluate = lambda script: ({'finder_uin': 'test'} if 'Object.fromEntries' in script else {'origin': 'https://channels.weixin.qq.com', 'localStorage': [{'name': 'finder_uin', 'value': 'test'}]})
    class DuplicateBodies(_Locator):
        def inner_text(self, timeout=None):
            raise RuntimeError('strict mode violation: body resolved to 2 elements')
        @property
        def first(self):
            return _Locator(self.page)
        def count(self):
            return 2
        def nth(self, index):
            return _Locator(self.page if index == 0 else _Page(body='最近视频 发表视频'))
    page.locator = lambda selector: DuplicateBodies(page)
    context = _Context(page)
    context.storage_state = lambda: {'cookies': [], 'origins': [{'origin': 'https://channels.weixin.qq.com', 'localStorage': []}]}
    context.close = lambda: None
    web_platform._profiles['company:wechat_channels'] = {'page': page, 'context': context}
    state = web_platform.session_status('company', 'wechat_channels')
    assert state['status'] == 'authorized'
    assert state['session_saved'] is True
    page.is_closed = lambda: True
    assert web_platform.session_status('company', 'wechat_channels')['status'] == 'session_saved'


def test_save_failure_is_reported_without_claiming_session_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(web_platform.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(web_platform, '_profiles', {})
    page = _Page()
    context = _Context(page)
    context.cookies = lambda: (_ for _ in ()).throw(RuntimeError('cookies unavailable'))
    web_platform._profiles['company:douyin'] = {'page': page, 'context': context}
    result = web_platform.session_status('company', 'douyin')
    assert result['status'] == 'authorized'
    assert result['session_saved'] is False
    assert '保存失败' in result['message']


def test_polling_saves_without_storage_state_navigation_and_throttles(tmp_path, monkeypatch):
    monkeypatch.setattr(web_platform.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    monkeypatch.setattr(web_platform, '_profiles', {})
    page = _Page()
    context = _Context(page)
    context.storage_state = lambda: (_ for _ in ()).throw(AssertionError('must not open origin pages'))
    calls = []
    context.cookies = lambda: calls.append(True) or []
    web_platform._profiles['company:douyin'] = {'page': page, 'context': context}
    for _ in range(3):
        assert web_platform.session_status('company', 'douyin')['session_saved']
    assert len(calls) == 1
    assert len(context.pages) == 1


def test_network_failure_keeps_window_and_explicit_retry_reuses_it(monkeypatch):
    page = _Page()
    def offline(*args, **kwargs):
        raise RuntimeError('net::ERR_INTERNET_DISCONNECTED')
    page.goto = offline
    session = {'page': page, 'context': _Context(page)}
    monkeypatch.setattr(web_platform, '_profiles', {'company:douyin': session})
    result = web_platform._navigate_login(session, 'douyin')
    assert result['status'] == 'browser_open' and result['navigation_error']
    assert '网络' in result['message']
    page.goto = lambda url, **kwargs: None
    result = web_platform.start_session('company', 'douyin')
    assert not result['navigation_error']
    assert web_platform._profiles['company:douyin'] is session


def test_channels_anonymous_dashboard_is_not_authorized(tmp_path, monkeypatch):
    monkeypatch.setattr(web_platform.settings, 'LOCAL_STORAGE_PATH', str(tmp_path))
    page = _Page(body='作品管理 数据中心', url='https://channels.weixin.qq.com/platform')
    page.evaluate = lambda script: {'finder_uin': '', 'finder_username': '', 'finder_raw': '', '__ml::aid': 'telemetry'}
    monkeypatch.setattr(web_platform, '_profiles', {'company:wechat_channels': {'page': page, 'context': _Context(page)}})
    assert web_platform.session_status('company', 'wechat_channels')['status'] == 'login_required'
    assert not web_platform._saved_state_has_auth({'cookies': [{'name':'tracking'}], 'origins': []}, 'wechat_channels')
