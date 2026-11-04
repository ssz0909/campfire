"""Account eviction/status-recovery regression using built UI and mock APIs only."""
import asyncio
import base64
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse
from playwright.async_api import async_playwright


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file():
            self.path = '/index.html'
        super().do_GET()

    def log_message(self, *args):
        pass


async def check(browser, base, width):
    page = await browser.new_page(viewport={'width': width, 'height': 1100})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    accounts = [{'id': f'account-{i}', 'platform': 'douyin', 'label': name, 'status': 'disconnected'}
                for i, name in enumerate(['龙兜兜', '灵感来了', '官号'])]
    states = {row['id']: {'status': 'disconnected'} for row in accounts}
    opened = []
    calls = {row['id']: 0 for row in accounts}
    screen = {'image': 'data:image/svg+xml;base64,' + base64.b64encode(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="960"><rect width="1440" height="960" fill="#eee"/></svg>'
    ).decode(), 'width': 1440, 'height': 960, 'input_field': None}

    async def api(route):
        url = urlparse(route.request.url)
        path = url.path.split('/api/v1')[-1]
        payload = {}
        if path == '/auth/refresh':
            payload = {'access_token': 'mock'}
        elif path == '/auth/me':
            payload = {'id': 'test-user', 'full_name': 'Test', 'email': 'test@example.invalid', 'is_active': True}
        elif path == '/companies':
            payload = [{'id': 'test-company', 'name': '测试酒店', 'business_goals': {}}]
        elif path.endswith('/publishing/accounts'):
            payload = accounts
        elif path.endswith('/web/start'):
            identifier = parse_qs(url.query)['connection_id'][0]
            if identifier not in opened:
                opened.append(identifier)
            if len(opened) > 2:
                evicted = opened.pop(0)
                states[evicted] = {'status': 'session_saved', 'session_saved': True,
                                   'publish_ready': True, 'browser_open': False}
            states[identifier] = {'status': 'authorized', 'session_saved': True,
                                  'publish_ready': True, 'browser_open': True}
        elif path.endswith('/web/status'):
            identifier = parse_qs(url.query)['connection_id'][0]
            calls[identifier] += 1
            payload = dict(states[identifier])
        elif path.endswith('/web/view'):
            payload = screen
        elif path.endswith('/publishing/jobs') or path.endswith('/approvals'):
            payload = {'items': [], 'total': 0}
        await route.fulfill(status=200, content_type='application/json', body=json.dumps(payload))

    await page.route('**/api/v1/**', api)
    await page.add_init_script("localStorage.setItem('refresh_token','mock');localStorage.setItem('currentCompanyId','test-company')")
    await page.goto(base + '/publishing')
    rows = page.get_by_role('list', name='发布账号', exact=True).get_by_role('listitem')
    await rows.nth(2).wait_for()
    for i in range(3):
        await rows.nth(i).get_by_role('button', name='打开网页登录', exact=True).click()
        await rows.nth(i).get_by_text('可发布', exact=True).wait_for()
    assert await page.get_by_text('可发布', exact=True).count() == 3
    # Wait until the first row has observed its evicted, saved state.
    await rows.nth(0).get_by_text('已授权，会话已保存（发布前自动校验）', exact=True).wait_for()
    # A transient incomplete saved status must be checked again after recovery.
    states['account-0']['publish_ready'] = False
    await rows.nth(0).get_by_text('登录会话已保存（使用前校验）', exact=True).wait_for(timeout=12000)
    states['account-0']['publish_ready'] = True
    await rows.nth(0).get_by_text('可发布', exact=True).wait_for(timeout=12000)
    assert await page.get_by_text('可发布', exact=True).count() == 3
    assert not errors, errors
    await page.screenshot(path=f'/tmp/campfire-matrix-eviction-{width}.png', full_page=True)
    print(f'PASS {width}px: third account evicts first; all stay publishable; saved status recovers without reload', flush=True)
    await page.close()


async def main():
    root = Path(__file__).resolve().parents[1] / 'dist'
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True,
                executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', args=['--no-sandbox'])
            try:
                for width in (1440, 390):
                    await check(browser, f'http://127.0.0.1:{server.server_port}', width)
            finally:
                await browser.close()
    finally:
        server.shutdown()


asyncio.run(main())
