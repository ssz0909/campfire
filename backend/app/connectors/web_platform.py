"""Browser-session adapters for platforms without an approved open-platform app.

The browser is intentionally user-visible: the user scans/logs in themselves.
No passwords or cookies are accepted by the API. Playwright keeps a local,
company-scoped browser profile and publishing stops when the page layout or
login state is not recognised.
"""
from __future__ import annotations
import asyncio, errno, logging, os, re, socket, threading, uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from urllib.parse import urlparse
from app.config import settings

logger = logging.getLogger(__name__)

PLATFORM_URLS = {"douyin": "https://creator.douyin.com/", "wechat_channels": "https://channels.weixin.qq.com/"}
_profiles: dict[str, Any] = {}
_lock = threading.Lock()
_browser_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="platform-browser")
_worker_state = threading.local()
_playwright = None

def _runtime():
    # One sync runtime owns the event loop on the dedicated browser thread.
    # Starting a second runtime on that thread raises the nested-loop error.
    global _playwright
    if _playwright is None:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
    return _playwright

def _saved_path(company_id, platform):
    return _profile_dir(company_id, platform) / 'web-session.enc'

def _save_session(company_id, platform, session):
    from app.core.secrets import encrypt_json
    try:
        # storage_state() visits every previously seen origin in a temporary
        # page. Never use it while polling a visible login browser.
        if session.get('session_saved') and time.monotonic() - session.get('saved_at', 0) < 60:
            return True
        origins = {}
        expected_host = urlparse(PLATFORM_URLS[platform]).hostname
        for page in session['context'].pages:
            if page.is_closed():
                continue
            for frame in page.frames:
                if urlparse(frame.url).hostname != expected_host:
                    continue
                snapshot = frame.evaluate('() => ({origin: location.origin, localStorage: Object.entries(localStorage).map(([name, value]) => ({name, value}))})')
                origins[snapshot['origin']] = snapshot
        state = {'cookies': session['context'].cookies(), 'origins': list(origins.values())}
        path = _saved_path(company_id, platform)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(encrypt_json(state))
        temporary.chmod(0o600)
        temporary.replace(path)
        session['saved_at'] = time.monotonic()
        return True
    except Exception as exc:
        logger.warning('Could not save %s browser session (%s)', platform, type(exc).__name__)
        return False

def _page_text(page, *, timeout=5000):
    # Channels renders duplicate body nodes. A bare locator is strict and
    # raises instead of returning the already-authenticated dashboard.
    bodies = page.locator('body')
    return '\n'.join(bodies.nth(i).inner_text(timeout=timeout)
                     for i in range(bodies.count()) if bodies.nth(i).is_visible())

def _saved_status(company_id, platform):
    from app.core.secrets import decrypt_json
    path = _saved_path(company_id, platform)
    try:
        saved = decrypt_json(path.read_text()) if path.exists() else {}
    except OSError:
        saved = {}
    if saved and (platform != 'wechat_channels' or _saved_state_has_auth(saved, platform)):
        return {'status': 'session_saved', 'login_required': False, 'browser_open': False,
                'message': '登录会话已保存，窗口已关闭；重新打开或发布时将校验平台登录是否过期'}
    if saved and platform == 'wechat_channels':
        path.unlink(missing_ok=True)
    return {'status': 'disconnected', 'login_required': True, 'browser_open': False}


def _saved_state_has_auth(saved, platform):
    """Reject a profile containing only anonymous provider telemetry."""
    if platform == 'wechat_channels':
        names = {'finder_uin', 'finder_username', 'finder_raw'}
        return any(item.get('name') in names and item.get('value') for origin in saved.get('origins', [])
                   for item in origin.get('localStorage', []))
    if saved.get('cookies'):
        return True
    return False

def browser_operation(function):
    """Playwright's sync objects must stay on their owning thread."""
    @wraps(function)
    def wrapper(*args, **kwargs):
        if getattr(_worker_state, "active", False):
            return function(*args, **kwargs)
        def run():
            _worker_state.active = True
            return function(*args, **kwargs)
        return _browser_worker.submit(run).result()
    return wrapper

def _profile_dir(company_id, platform):
    if platform not in PLATFORM_URLS:
        raise ValueError('unsupported platform')
    root = Path(settings.LOCAL_STORAGE_PATH) / "platform-sessions" / str(company_id) / platform
    root.mkdir(parents=True, exist_ok=True)
    return root

def _remove_stale_singleton_links(profile_dir):
    lock = profile_dir / "SingletonLock"
    if not lock.is_symlink():
        return False
    try:
        host, pid_text = os.readlink(lock).rsplit("-", 1)
        pid = int(pid_text)
    except (OSError, ValueError):
        return False
    if host != socket.gethostname():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    except PermissionError:
        return False
    except OSError as exc:
        if exc.errno != errno.ESRCH:
            return False
    else:
        return False

    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        link = profile_dir / name
        if link.is_symlink():
            try:
                link.unlink()
            except OSError:
                logger.warning("Could not remove stale browser profile link: %s", link)
    return True

def _get_session(company_id, platform):
    key = f"{company_id}:{platform}"
    with _lock:
        return _profiles.get(key)

def _watch_browser_session(context, page, platform, session):
    """Log lifecycle only; never log provider account content or session data."""
    context.on('close', lambda *_: logger.warning('Platform browser context closed: platform=%s', platform))
    if context.browser is not None:
        context.browser.on('disconnected', lambda *_: logger.warning('Platform browser disconnected: platform=%s', platform))
    page.on('close', lambda *_: logger.warning('Platform browser page closed: platform=%s', platform))
    def crashed(*_):
        session['page_crashed'] = True
        logger.warning('Platform browser page crashed: platform=%s', platform)
    page.on('crash', crashed)

def _browser_launch_options():
    executable = getattr(settings, 'WEB_BROWSER_EXECUTABLE', '')
    if not executable:
        candidate = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        executable = candidate if Path(candidate).exists() else ''
    options = {'headless': settings.WEB_BROWSER_HEADLESS,
               'viewport': {'width': 1440, 'height': 960},
               'args': ['--disable-crash-reporter', '--disable-breakpad']}
    if executable and Path(executable).exists():
        options['executable_path'] = executable
    elif settings.WEB_BROWSER_HEADLESS:
        # Use the full browser's new headless mode for rich creator editors,
        # rather than the separate reduced headless-shell executable.
        options['channel'] = 'chromium'
    return options

def _browser_environment(profile_dir):
    # System service accounts may have a root-owned home. Full Chromium uses
    # XDG directories for Crashpad even with its reporting switches disabled.
    # Keep these writable and scoped to the same tenant/platform as the profile.
    runtime = profile_dir / '.runtime'
    config = runtime / 'config'
    cache = runtime / 'cache'
    for directory in (runtime, config, cache):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
    return dict(os.environ, XDG_CONFIG_HOME=str(config), XDG_CACHE_HOME=str(cache))

def _closed_browser_error(exc):
    detail = str(exc).lower()
    return type(exc).__name__ == 'TargetClosedError' or any(
        text in detail for text in ('target page, context or browser has been closed', 'page crashed'))

@browser_operation
def start_session(company_id, platform, geolocation=None):
    if platform not in PLATFORM_URLS: raise ValueError("unsupported platform")
    existing = _get_session(company_id, platform)
    if existing:
        try:
            if existing.get('page_crashed') or existing["page"].is_closed():
                raise RuntimeError("page closed")
            if geolocation:
                _apply_geolocation(existing['context'], platform, geolocation)
            existing["page"].bring_to_front()
            if existing.get('navigation_error'):
                return _navigate_login(existing, platform)
            return {"status": "browser_open", "url": existing["page"].url, "login_required": True,
                    "message": "登录窗口已存在，请在浏览器中完成登录"}
        except Exception:
            close_session(company_id, platform)
    pw = None
    context = None
    try:
        pw = _runtime()
        kwargs = _browser_launch_options()
        profile_dir = _profile_dir(company_id, platform)
        kwargs['env'] = _browser_environment(profile_dir)
        _remove_stale_singleton_links(profile_dir)
        context = pw.chromium.launch_persistent_context(str(profile_dir), **kwargs)
        if geolocation:
            _apply_geolocation(context, platform, geolocation)
        from app.core.secrets import decrypt_json
        saved_file = _saved_path(company_id, platform)
        saved = decrypt_json(saved_file.read_text()) if saved_file.exists() else {}
        if saved.get('cookies'):
            context.add_cookies(saved['cookies'])
        if saved.get('origins'):
            import json
            context.add_init_script('(() => { const savedOrigins = ' + json.dumps(saved['origins']) + '; for (const origin of savedOrigins) { if (location.origin === origin.origin) { for (const item of origin.localStorage || []) { if (localStorage.getItem(item.name) === null) localStorage.setItem(item.name, item.value); } } } })();')
        page = context.pages[0] if context.pages else context.new_page()
        session = {"pw": pw, "context": context, "page": page}
        _watch_browser_session(context, page, platform, session)
        with _lock: _profiles[f"{company_id}:{platform}"] = session
        return _navigate_login(_get_session(company_id, platform), platform)
    except Exception as exc:
        logger.exception("Could not start %s browser session for company %s", platform, company_id)
        if context:
            try: context.close()
            except Exception: pass
        with _lock: _profiles.pop(f"{company_id}:{platform}", None)
        message = str(exc).lower()
        if isinstance(exc, ImportError) or "executable doesn't exist" in message or "browser" in message and "install" in message:
            detail = "浏览器运行时未安装，请安装 Chromium 后重试"
        elif any(x in message for x in ("processsingleton", "singletonlock", "profile appears to be in use", "user data directory is already in use")):
            detail = "登录窗口已被其他浏览器进程占用，请关闭已有窗口后重试"
        else:
            detail = "无法启动平台登录窗口，请重试；若持续失败，请联系管理员检查后端日志"
        raise RuntimeError(detail) from exc

def _navigate_login(session, platform):
    page = session['page']
    try:
        page.goto(PLATFORM_URLS[platform], wait_until='domcontentloaded', timeout=30000)
        session.pop('navigation_error', None)
        message = '浏览器窗口已打开，请完成扫码登录'
    except Exception as exc:
        if page.is_closed():
            raise
        # Chrome launched successfully. Preserve its profile/window on network
        # failure; only an explicit Open click retries navigation.
        session['navigation_error'] = True
        logger.warning('%s login navigation failed (%s)', platform, type(exc).__name__)
        message = '浏览器已打开，但平台页面加载失败，请检查本机网络或代理；恢复后在该窗口刷新，或点击重新打开。无需关闭其他平台窗口。'
    return {'status': 'browser_open', 'url': page.url, 'login_required': True,
            'navigation_error': bool(session.get('navigation_error')), 'message': message}

@browser_operation
def session_status(company_id, platform):
    if platform not in PLATFORM_URLS: raise ValueError('unsupported platform')
    session = _get_session(company_id, platform)
    if not session: return _saved_status(company_id, platform)
    page = session["page"]
    try:
        if session.get('page_crashed'):
            return _saved_status(company_id, platform) | {'message': '平台页面已崩溃，请重新打开网页登录；已保存的会话将重新校验'}
        if page.is_closed():
            close_session(company_id, platform)
            return _saved_status(company_id, platform)
        text = _page_text(page)[:8000]
        # These strings are present on the login screen.  Once the account is
        # logged in they disappear, even though the exact dashboard text varies.
        login = any(x in text for x in ("扫码登录", "验证码登录", "登录后使用", "登录/注册", "扫码进入", "立即登录"))
        parsed = urlparse(page.url)
        expected_host = urlparse(PLATFORM_URLS[platform]).hostname
        recognised = any(x in text for x in ("作品管理", "内容管理", "发布视频", "发布作品", "数据中心", "创作者中心"))
        if platform == 'wechat_channels':
            recognised = recognised or (
                '视频号ID' in text and any(x in text for x in ('发表视频', '昨日数据', '最近视频'))
            )
        authorized = parsed.hostname == expected_host and not login and recognised
        if authorized and platform == 'wechat_channels':
            # A dashboard shell can be rendered for anonymous visitors. Require
            # actual provider auth state before marking it publishable.
            cookies = session['context'].cookies()
            local_storage = page.evaluate('() => Object.fromEntries(Object.entries(localStorage))')
            state = {'cookies': cookies, 'origins': [{'localStorage': [{'name': k, 'value': v} for k, v in local_storage.items()]}]}
            authorized = _saved_state_has_auth(state, platform)
        if authorized:
            session.pop('navigation_error', None)
            session['authenticated'] = True
            session['session_saved'] = _save_session(company_id, platform, session)
        elif login:
            session['authenticated'] = False
            _saved_path(company_id, platform).unlink(missing_ok=True)
        return {"status": "authorized" if authorized else "login_required", "login_required": not authorized, "url": page.url,
                'session_saved': bool(authorized and session.get('session_saved')), 'browser_open': True,
                'message': ('平台网页登录成功，登录会话已保存' if session.get('session_saved') else '平台网页登录成功，但会话保存失败，请暂勿关闭窗口') if authorized else ('平台页面加载失败，请检查本机网络或代理，恢复后刷新已打开的窗口' if session.get('navigation_error') else '请在平台窗口完成扫码登录')}
    except Exception as exc:
        # A slow provider page is still an open login session. Do not downgrade
        # the connection to disconnected while the QR page is loading.
        return {"status": "login_required", "login_required": True, "url": page.url,
                "message": f"平台页面仍在加载，请稍后重试：{type(exc).__name__}"}

@browser_operation
def publish(company_id, platform, title, description, media_url, location_name=None, geolocation=None):
    _ensure_open(company_id, platform)
    session = _get_session(company_id, platform)
    if not session: return {"status": "login_required", "message": "请先打开平台 Web 登录窗口并完成扫码登录"}
    page = session["page"]
    state = session_status(company_id, platform)
    if state["login_required"]: return state | {"message": "请在打开的浏览器窗口完成扫码登录"}
    stage = '打开上传页'
    submit_attempted = False
    try:
        if geolocation:
            stage = '设置酒店浏览器定位'
            _apply_geolocation(session['context'], platform, geolocation)
        if platform == "douyin":
            page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until="domcontentloaded", timeout=30000)
            file_input = page.locator('input[type="file"]').first
            if not media_url or not Path(media_url).exists():
                return {"status": "manual_required", "message": "Web 发布需要本机媒体文件路径，当前仅创建发布草稿"}
            stage = '选择并上传视频文件'
            file_input.set_input_files(media_url, timeout=30000)
            stage = '等待上传后的编辑器'
            _wait_video_editor(page)
            stage = '填写发布文案'
            _fill_douyin_copy(page, title, description)
        else:
            page.goto("https://channels.weixin.qq.com/platform/post/create", wait_until="domcontentloaded", timeout=30000)
            if not media_url or not Path(media_url).exists():
                return {"status": "manual_required", "message": "Web 发布需要本机媒体文件路径，当前仅创建发布草稿"}
            stage = '选择并上传视频文件'
            page.locator('input[type="file"]').first.set_input_files(media_url, timeout=30000)
            stage = '等待上传后的编辑器'
            _wait_video_editor(page)
            stage = '填写发布文案'
            _fill_channels_copy(page, title, description)
        if location_name:
            stage = '选择地理位置'
            _select_publish_location(page, location_name)
        stage = '等待发布按钮可用'
        button = _publish_button(page, platform)
        button.wait_for(state='visible', timeout=30000)
        # Mark uncertain before clicking: even a click timeout can mean the
        # platform received it. Never automatically retry that operation.
        stage = '提交发布'
        submit_attempted = True
        button.click(timeout=60000)
        stage = '核对平台发布结果'
        try:
            page.get_by_text(re.compile(r'^(发布成功|发表成功|提交成功)[！!。]?$')).first.wait_for(timeout=30000)
        except Exception:
            return {'status':'manual_required', 'metrics':{'publish_stage':stage, 'submission_uncertain':True},
                    'message':'已尝试点击发布，但未取得平台成功凭据；请在云端画面的作品管理中核对审核中、已发布及草稿，核对前勿重复提交。'}
        return {"status": "published", "provider_post_id": None, "metrics": {"source": "web_pending_sync", 'publish_stage':'平台确认成功'}}
    except Exception as exc:
        logger.warning('Platform publish failed: platform=%s stage=%s error=%s submit_attempted=%s',
                       platform, stage, type(exc).__name__, submit_attempted)
        reason = ('平台页面或浏览器已关闭或崩溃，请重新打开网页登录并检查会话；这不是酒店搜索无结果' if _closed_browser_error(exc)
                  else str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        return {"status": "manual_required", 'metrics':{'publish_stage':stage, 'submission_uncertain':submit_attempted},
                "message": f"发布停在「{stage}」：{reason}。" +
                    ('提交结果不确定，请先在云端作品管理核对，勿重复提交。' if submit_attempted else
                     '尚未进入提交发布步骤，请打开对应平台的云端画面检查上传、文案、封面及平台提示。')}

def _publish_button(page, platform):
    # Match an actual submit button, not navigation such as “作品发布”,
    # a checkbox containing “发布”, or the last matching text on the page.
    labels = r'^(发布|立即发布)$' if platform == 'douyin' else r'^(发表|发布|立即发表|立即发布)$'
    return page.get_by_role('button', name=re.compile(labels))

def _apply_geolocation(context, platform, geolocation):
    """Use verified hotel WGS84 coordinates; never infer a county centre."""
    import math
    try:
        if any(isinstance(geolocation.get(key), bool) for key in ('latitude', 'longitude')):
            raise ValueError()
        latitude = float(geolocation['latitude'])
        longitude = float(geolocation['longitude'])
        accuracy = float(geolocation.get('accuracy', 100))
        if not (math.isfinite(latitude) and math.isfinite(longitude) and math.isfinite(accuracy)
                and -90 <= latitude <= 90 and -180 <= longitude <= 180 and accuracy > 0):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ValueError('酒店定位配置无效，需要准确的WGS84经纬度') from None
    context.set_geolocation({'latitude': latitude, 'longitude': longitude, 'accuracy': accuracy})
    parsed = urlparse(PLATFORM_URLS[platform])
    context.grant_permissions(['geolocation'], origin=f'{parsed.scheme}://{parsed.netloc}')

def _wait_video_editor(page):
    """Accept the separate-title and shared rich-text editor layouts."""
    editor = page.locator('input[placeholder*="标题"]:visible, textarea:visible, [contenteditable="true"]:visible')
    try:
        editor.first.wait_for(state='visible', timeout=120000)
    except Exception as exc:
        if _closed_browser_error(exc):
            # Preserve the exception type so publishing can report browser
            # failure separately from a missing/ambiguous hotel search result.
            logger.warning('Video editor interrupted by closed browser: error=%s', type(exc).__name__)
            raise
        # Only expose known platform notices, never a dump of account content.
        text = _page_text(page, timeout=3000)
        notices = [label for label in ('上传失败', '上传出错', '视频格式不支持', '格式不支持',
                   '网络异常', '网络错误', '重新上传', '扫码登录', '验证码登录', '安全验证') if label in text]
        if notices:
            raise ValueError('平台提示：' + '、'.join(notices) + '；编辑器未就绪') from exc
        raise ValueError('视频已交给浏览器，但120秒内未发现可用编辑器；请核对云端画面的上传进度、网络和平台提示') from exc

def _fill_douyin_copy(page, title, description):
    title_boxes = page.locator('input[placeholder*="标题"]:visible, textarea[placeholder*="标题"]:visible, [contenteditable="true"][data-placeholder*="标题"]:visible')
    body_boxes = page.locator('textarea:not([placeholder*="标题"]):visible, [contenteditable="true"]:not([data-placeholder*="标题"]):visible')
    if title_boxes.count() > 1 or body_boxes.count() > 1:
        raise ValueError('发布页存在多个文案编辑框，无法唯一确认标题和正文，已停止提交')
    if title_boxes.count() == 1:
        title_boxes.first.fill(title, timeout=15000)
        if description:
            if body_boxes.count() != 1:
                raise ValueError('标题可填写，但未找到正文编辑框，已停止提交')
            body_boxes.first.fill(description, timeout=15000)
    elif body_boxes.count() == 1:
        body_boxes.first.fill(title + ('\n' + description if description else ''), timeout=15000)
    else:
        raise ValueError('未找到可用的标题或图文描述编辑框，已停止提交')

def _select_publish_location(page, location_name):
    try:
        return _select_publish_location_impl(page, location_name)
    except ValueError:
        raise
    except Exception as exc:
        if _closed_browser_error(exc):
            logger.warning('Location selection interrupted by closed browser: error=%s', type(exc).__name__)
            raise
        # Locator errors previously collapsed to “Error”, hiding whether a
        # duplicate locator, detached node, or timeout stopped location picking.
        detail = str(exc).lower()
        reason = ('页面存在多个匹配控件' if 'strict mode violation' in detail else
                  '控件在页面更新时失效' if 'detach' in detail else
                  '平台页面等待超时' if 'timeout' in detail else
                  '平台位置控件未能完成操作')
        logger.warning('Location selection failed: error=%s reason=%s', type(exc).__name__, reason)
        raise ValueError(f'{reason}，未确认酒店地点，已停止提交') from exc

def _location_step(label, operation):
    try:
        return operation()
    except Exception as exc:
        if _closed_browser_error(exc):
            raise
        if type(exc).__name__ == 'TimeoutError':
            logger.warning('Location selection timed out: step=%s', label)
            raise ValueError(f'地点选择超时：{label}；未确认酒店地点，已停止提交') from exc
        raise

def _location_name_pattern(location_name):
    import unicodedata
    parts = [re.escape(c) for c in unicodedata.normalize('NFKC', location_name) if not c.isspace()]
    return re.compile(r'^\s*' + r'\s*'.join(parts) + r'\s*$')

def _inline_location_field(row, location_name=None):
    if location_name:
        existing = []
        controls = row.locator('input:not([type="hidden"]):not([type="file"]):visible')
        for index in range(controls.count()):
            control = controls.nth(index)
            if _location_name_pattern(location_name).fullmatch(control.input_value()):
                existing.append(control)
        if len(existing) == 1:
            return existing[0]
    editable = 'input:not([type="hidden"]):not([type="file"]):not([readonly]):not([disabled]):visible'
    fields = row.locator(editable)
    # Prefer explicit location semantics; select widgets often contain a second
    # focus/search input next to the actual POI query field.
    semantic = fields.and_(row.locator(
        'input[placeholder*="位置"]:visible, input[placeholder*="地点"]:visible, input[placeholder*="地址"]:visible, '
        'input[placeholder*="商家"]:visible, input[placeholder*="门店"]:visible, '
        'input[aria-label*="位置"]:visible, input[aria-label*="地点"]:visible'))
    if semantic.count() == 1:
        return semantic.first
    if semantic.count() > 1:
        raise ValueError('位置区域存在多个地点搜索框，已停止发布')
    anchor_locator = row.get_by_text('位置', exact=True)
    anchors = []
    for index in range(anchor_locator.count()):
        item = anchor_locator.nth(index)
        try:
            if item.is_visible():
                anchors.append(item)
        except Exception:
            continue
    # The screenshot layout has a type dropdown on the left and the POI input
    # on its right. Restrict to that horizontal row, excluding title/tag inputs.
    if len(anchors) == 1:
        anchor = anchors[0].bounding_box()
        nearby = []
        if anchor:
            for index in range(fields.count()):
                item = fields.nth(index)
                rect = item.bounding_box()
                if rect and rect['width'] >= 80 and rect['x'] >= anchor['x'] + anchor['width'] and abs(
                    rect['y'] + rect['height']/2 - anchor['y'] - anchor['height']/2
                ) <= max(rect['height'], anchor['height'])/2:
                    nearby.append((rect['x'] - (anchor['x'] + anchor['width']), item))
        if nearby:
            # The nearest same-row input is the POI query. Other tag inputs are
            # farther away or on a different row; keep the deterministic choice.
            nearby.sort(key=lambda pair: pair[0])
            return nearby[0][1]
    if fields.count() == 1:
        return fields.first
    logger.warning('Inline location field ambiguous: visible_editable_inputs=%s semantic_inputs=%s',
                   fields.count(), semantic.count())
    raise ValueError('未能唯一识别位置右侧的酒店搜索框，请核对云端画面，已停止发布')

def _select_inline_publish_location(page, location_name):
    """Douyin's 添加标签/位置 row has an inline field and recommended POIs.

    The 位置 dropdown selects the tag type; it is not a modal-picker trigger.
    Restrict generic input matching to this labelled row, never the title/body.
    """
    labels = page.get_by_text('添加标签', exact=True).and_(page.locator(':visible'))
    if labels.count() != 1:
        return False
    if _select_douyin_location_tag(page, labels, location_name):
        return True
    row = labels.locator('xpath=ancestor::*[.//input[not(@type="hidden")] and .//*[normalize-space(.)="位置"]][1]')
    if row.count() != 1:
        return False
    try:
        field = _inline_location_field(row, location_name)
    except ValueError:
        # Diagnose actual ancestry and widget types instead of expanding a
        # selector blindly. Never capture values, account text or outerHTML.
        try:
            structure = labels.evaluate('''label => {
                const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
                const layers = [];
                for (let el=label.parentElement; el && layers.length<6; el=el.parentElement) {
                    const controls = [...el.querySelectorAll('input,textarea,[contenteditable], [role="combobox"], [role="textbox"]')];
                    layers.push({tag:el.tagName, classes:String(el.className || '').slice(0,160),
                        controls:controls.slice(0,20).map(c=>({tag:c.tagName, type:c.getAttribute('type'),
                            role:c.getAttribute('role'), editable:c.getAttribute('contenteditable'),
                            readonly:c.hasAttribute('readonly'), disabled:c.hasAttribute('disabled'),
                            visible:visible(c), classes:String(c.className || '').slice(0,120)}))});
                }
                return layers;
            }''')
            logger.warning('Inline location DOM structure (no input values): %s', structure)
        except Exception as exc:
            logger.warning('Inline location structural diagnostics unavailable: %s', type(exc).__name__)
        raise
    before = field.evaluate('(el) => ({value: el.value, readOnly: el.readOnly, disabled: el.disabled})')
    if not _location_name_pattern(location_name).fullmatch(before['value']):
        _location_step('填写内嵌位置搜索框', lambda: field.fill(location_name, timeout=10000))
    candidates = row.get_by_text(_location_name_pattern(location_name)).and_(page.locator(':visible'))
    _location_step('等待内嵌位置推荐或搜索结果中的酒店全名',
                   lambda: candidates.first.wait_for(state='visible', timeout=20000))
    if candidates.count() != 1:
        raise ValueError('推荐地点中酒店全名匹配不唯一，已停止发布')
    option = candidates.first
    handles = {'field': field.element_handle(), 'option': option.element_handle(),
               'row': row.element_handle(), 'name': location_name, 'before': before}
    _location_step('点击酒店地点推荐卡片', lambda: option.click(timeout=10000))
    # Editable query text alone is not proof of an attached POI. Require the
    # clicked suggestion to disappear with an exact field value, the control
    # to become read-only, or a selected token replacing the search field.
    try:
        _location_step('核对内嵌地点已选中', lambda: page.wait_for_function('''({field, option, row, name, before}) => {
            const norm = v => (v || '').normalize('NFKC').replace(/\\s+/g, '');
            const visible = el => !!el && el.isConnected && el.getClientRects().length > 0 &&
                getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
            if (visible(field) && norm(field.value) === norm(name) &&
                ((!before.readOnly && field.readOnly) || (!before.disabled && field.disabled) ||
                 !visible(option) || option.getAttribute('aria-selected') === 'true' ||
                 option.closest('[aria-selected="true"]'))) return true;
            if (!visible(field) && row && row.isConnected) {
                return [...row.querySelectorAll('*')].some(el => visible(el) && el !== option &&
                    !el.contains(option) && !option.contains(el) && norm(el.textContent) === norm(name));
            }
            return false;
        }''', arg=handles, timeout=10000))
    finally:
        for key in ('field', 'option', 'row'):
            if handles[key] is not None:
                handles[key].dispose()
    logger.warning('Location selection confirmed: layout=inline-recommendation')
    return True

def _select_douyin_location_tag(page, label, location_name):
    """Handle the real creator page's Semi Select (no input until opened).

    Confirm its selected-label slot, never a query input or recommended card.
    Class prefixes identify the inspected component without depending on the
    build-specific suffix of its CSS modules.
    """
    row = label.locator('xpath=ancestor::div[contains(@class,"content-obt")][1]')
    if row.count() != 1:
        return False
    picker = row.locator('.semi-select-filterable:visible')
    if picker.count() != 1:
        raise ValueError('地点标签选择器不唯一，已停止提交')
    type_selector = row.locator('[class*="anchor-container-"] > .semi-select').filter(has_text=re.compile(r'^位置$'))
    if type_selector.count() != 1:
        raise ValueError('添加标签类型不是唯一的位置选项，已停止提交')
    selected = picker.locator('.semi-select-selection-text')
    pattern = _location_name_pattern(location_name)
    if selected.count() == 1 and pattern.fullmatch(selected.inner_text()):
        logger.warning('Location selection confirmed: layout=semi-select already-selected=True')
        return True
    recommendations = row.locator('[class*="recommend-list-item-"]:visible').filter(has_text=pattern)
    if recommendations.count() == 1:
        _location_step('点击地点标签中的酒店推荐卡片', lambda: recommendations.click(timeout=10000))
    elif recommendations.count() > 1:
        raise ValueError('酒店推荐卡片匹配不唯一，已停止提交')
    else:
        _location_step('打开酒店地点下拉选择器', lambda: picker.click(timeout=10000))
        query = picker.locator('input:visible')
        _location_step('等待地点下拉搜索输入框', lambda: query.wait_for(state='visible', timeout=10000))
        _location_step('搜索酒店地点标签', lambda: query.fill(location_name, timeout=10000))
        options = page.locator('.semi-select-option:visible').filter(has_text=pattern)
        _location_step('等待酒店全名地点选项', lambda: options.first.wait_for(state='visible', timeout=20000))
        if options.count() != 1:
            raise ValueError('酒店地点下拉结果匹配不唯一，已停止提交')
        _location_step('选择酒店地点标签', lambda: options.click(timeout=10000))
    _location_step('核对酒店地点标签的选中值', lambda: selected.filter(has_text=pattern).wait_for(state='visible', timeout=10000))
    if not pattern.fullmatch(selected.inner_text()):
        raise ValueError('酒店地点标签选中值与目标酒店不符，已停止提交')
    logger.warning('Location selection confirmed: layout=semi-select already-selected=False')
    return True

def _select_publish_location_impl(page, location_name):
    """Require an exact POI result and a visible selected label before submit."""
    import unicodedata
    def normalized(value):
        return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value))
    expected = normalized(location_name)
    if _select_inline_publish_location(page, location_name):
        return
    # Enter the location picker through its actual visible label. Ambiguous or
    # unsupported layouts stop before submission rather than omit the POI.
    trigger = page.get_by_text(re.compile(r'^(添加位置|添加地点|选择位置|选择地点|你在哪里|位置|地点)$'))
    visible = []
    for i in range(trigger.count()):
        try:
            item = trigger.nth(i)
            if item.is_visible(): visible.append(item)
        except Exception:
            continue
    if len(visible) != 1:
        raise ValueError('未找到唯一的位置选择入口，已停止发布以免遗漏酒店位置')
    logger.info('Location selection step: opening picker')
    _location_step('点击位置选择入口', lambda: visible[0].click(timeout=10000))
    search = page.locator(', '.join(f'input[placeholder*="{word}"]:visible' for word in
        ('搜索位置', '搜索地点', '搜索地址', '搜索商家', '搜索门店', '搜索你想', '搜索相关')))
    logger.info('Location selection step: waiting for search input')
    _location_step('等待位置搜索框出现', lambda: search.first.wait_for(state='visible', timeout=10000))
    boxes = []
    for i in range(search.count()):
        try:
            item = search.nth(i)
            if item.is_visible(): boxes.append(item)
        except Exception:
            continue
    if len(boxes) != 1:
        raise ValueError('位置搜索框不明确，已停止发布')
    logger.info('Location selection step: entering hotel query')
    _location_step('填写酒店名称', lambda: boxes[0].fill(location_name, timeout=10000))
    # Match the full name; never silently choose the first fuzzy search result.
    parts = [re.escape(c) for c in unicodedata.normalize('NFKC', location_name) if not c.isspace()]
    candidates = page.get_by_text(re.compile(r'^\s*' + r'\s*'.join(parts) + r'\s*$')).and_(page.locator(':visible'))
    logger.info('Location selection step: waiting for exact hotel result')
    _location_step('等待酒店全名匹配结果，请核对搜索城市及平台显示的酒店名称',
                   lambda: candidates.first.wait_for(state='visible', timeout=20000))
    matches = []
    for i in range(candidates.count()):
        try:
            item = candidates.nth(i)
            if item.is_visible() and normalized(item.inner_text()) == expected: matches.append(item)
        except Exception:
            continue
    if len(matches) != 1:
        raise ValueError('酒店地点无唯一精确匹配，请在云端画面核对，已停止发布')
    logger.info('Location selection step: selecting exact hotel result')
    _location_step('点击酒店搜索结果', lambda: matches[0].click(timeout=10000))
    # The result node disappears after selection. Confirm the panel closed and
    # the exact POI label is now visible in the editor before submitting.
    _location_step('等待地点面板关闭并确认选中', lambda: boxes[0].wait_for(state='hidden', timeout=10000))
    selected = page.get_by_text(re.compile(r'^\s*' + r'\s*'.join(parts) + r'\s*$'))
    selected_matches = []
    for i in range(selected.count()):
        try:
            item = selected.nth(i)
            if item.is_visible() and normalized(item.inner_text()) == expected: selected_matches.append(item)
        except Exception:
            continue
    if not selected_matches:
        raise ValueError('地点搜索面板已关闭，但页面未显示已选酒店地点')

def _fill_channels_copy(page, title, description):
    title_box = page.locator('input[placeholder*="标题"], input[placeholder*="短标题"]')
    body_box = page.locator('textarea, [contenteditable="true"]')
    if title_box.count():
        title_box.first.fill(title)
        body_box.last.fill(description or title)
    else:
        # Some video-account pages expose one shared title/description editor.
        body_box.last.fill(title + ('\n' + description if description else ''))

@browser_operation
def read_metrics(company_id, platform):
    _ensure_open(company_id, platform)
    session = _get_session(company_id, platform)
    if not session: return {"status": "login_required", "metrics": {}}
    state = session_status(company_id, platform)
    if state["login_required"]: return {"status": "login_required", "metrics": {}}
    page = session['page']
    try:
        # Only follow a link actually present in the authenticated provider UI.
        for label in ('数据中心', '数据概览'):
            link = page.get_by_text(label, exact=True)
            if link.count() == 1:
                link.click(timeout=5000)
                break
        body = _page_text(page, timeout=10000)
        metrics = parse_visible_metrics(body)
        if not metrics:
            return {'status':'manual_refresh_required','metrics':{},
                    'message':'未识别到明确指标，请在平台数据中心打开数据概览后再同步'}
        return {'status':'synced','metrics':{**metrics, 'scope':'account', 'page_url':page.url,
            'captured_at':datetime.now(timezone.utc).isoformat(),
            'period_note':'平台当前页面所选统计周期；不代表单条作品数据'}}
    except Exception:
        return {'status':'manual_refresh_required','metrics':{},'message':'平台数据页面需要人工确认，请打开数据中心后重试'}

def parse_visible_metrics(body):
    """Only accept a unique label/value pair; never infer counts from unrelated numbers."""
    values = {}
    labels = {'播放量':'views','曝光量':'impressions','点赞量':'likes',
              '评论量':'comments','分享量':'shares','粉丝总数':'followers'}
    for label, key in labels.items():
        found = re.findall(r'(?:^|\n)\s*' + re.escape(label) + r'\s*[:：]?\s*\n?\s*([\d,]+(?:\.\d+)?)([万亿]?)\s*(?=\n|$)', body)
        if len(found) == 1:
            number, unit = found[0]
            values[key] = int(float(number.replace(',', '')) * {'':1,'万':10000,'亿':100000000}[unit])
    return values


@browser_operation
def close_session(company_id, platform, *, logout=False):
    if platform not in PLATFORM_URLS: raise ValueError('unsupported platform')
    key = f"{company_id}:{platform}"
    with _lock: session = _profiles.pop(key, None)
    if session:
        if logout:
            try: session["context"].clear_cookies()
            except Exception: pass
            for page in session["context"].pages:
                try: page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
                except Exception: pass
        elif session.get('authenticated') and not session.get('page_crashed') and not session['page'].is_closed():
            _save_session(company_id, platform, session)
        try: session["context"].close()
        except Exception: pass
    if logout:
        # Remove only this tenant/platform's managed profile, even if its window
        # was already closed. Other platforms and the user's Chrome are untouched.
        import shutil
        shutil.rmtree(_profile_dir(company_id, platform))
    return {"status": "disconnected"}

def _ensure_open(company_id, platform):
    session = _get_session(company_id, platform)
    if not session or session.get('page_crashed') or session['page'].is_closed():
        if _saved_status(company_id, platform)['status'] == 'session_saved':
            start_session(company_id, platform)

@browser_operation
def shutdown_sessions():
    global _playwright
    for key in list(_profiles):
        company_id, platform = key.rsplit(':', 1)
        close_session(company_id, platform)
    if _playwright is not None:
        _playwright.stop()
        _playwright = None


@browser_operation
def login_view(company_id, platform, action=None):
    """Company-scoped remote login view; never expose cookies or arbitrary URLs."""
    if platform not in PLATFORM_URLS:
        raise ValueError('unsupported platform')
    session = _get_session(company_id, platform)
    if not session or session.get('page_crashed') or session['page'].is_closed():
        raise RuntimeError('登录窗口已关闭，请重新打开网页登录')
    page = session['page']
    if action:
        kind = action['kind']
        if kind == 'click':
            page.mouse.click(action['x'], action['y'])
        elif kind == 'drag':
            page.mouse.move(action['x'], action['y'])
            page.mouse.down()
            try:
                page.mouse.move(action['end_x'], action['end_y'], steps=30)
            finally:
                page.mouse.up()
        elif kind == 'fill':
            target = session.get('login_input')
            if not target or target['id'] != action.get('field_id'):
                raise RuntimeError('输入框已变化，请重新点击目标输入框')
            target['locator'].fill(action['text'], timeout=5000)
        elif kind == 'text':
            if not any(frame.evaluate("() => {const el=document.activeElement; return !!el && (el.tagName==='INPUT' || el.tagName==='TEXTAREA' || el.isContentEditable)}") for frame in page.frames):
                raise RuntimeError('请先点击云端画面中的手机号或验证码输入框')
            page.keyboard.insert_text(action['text'])
        elif kind == 'key':
            page.keyboard.press(action['key'])
        elif kind == 'scroll':
            page.mouse.wheel(0, action['delta'])
        elif kind == 'refresh':
            page.reload(wait_until='domcontentloaded', timeout=30000)
    import base64
    input_focused = False
    for frame in page.frames:
        try:
            if frame.evaluate("() => {const el=document.activeElement; return !!el && (el.tagName==='INPUT' || el.tagName==='TEXTAREA' || el.isContentEditable)}"):
                input_focused = True
                break
        except Exception:
            pass
    input_field = None
    for frame in page.frames:
        try:
            field = frame.evaluate('''(candidate) => {
                const el = document.activeElement;
                if (!el || !['INPUT','TEXTAREA'].includes(el.tagName) || el.disabled || el.readOnly ||
                    (el.tagName==='INPUT' && !['text','tel','password','number','email','search','url'].includes(el.type))) return null;
                if (!el.dataset.campfireLoginId) el.dataset.campfireLoginId = candidate;
                return {id: el.dataset.campfireLoginId, type: el.type, placeholder: el.placeholder || '在此输入'};
            }''', uuid.uuid4().hex)
            if not isinstance(field, dict) or not field.get('id'):
                continue
            locator = frame.locator('[data-campfire-login-id="' + field['id'] + '"]')
            rect = locator.bounding_box(timeout=1000)
            if rect and rect['width'] > 0 and rect['height'] > 0:
                input_field = {**field, **rect}
                session['login_input'] = {'id': field['id'], 'locator': locator}
                break
        except Exception:
            continue
    screenshot = page.screenshot(type='jpeg', quality=75, timeout=10000)
    viewport = page.viewport_size or {'width': 1440, 'height': 960}
    return {'image': 'data:image/jpeg;base64,' + base64.b64encode(screenshot).decode(),
            'width': viewport['width'], 'height': viewport['height'], 'input_focused': input_focused, 'input_field': input_field}
