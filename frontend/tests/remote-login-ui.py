"""Built-app regression with mock APIs; does not contact any publishing platform.

Run after npm run build: backend/.venv311/bin/python frontend/tests/remote-login-ui.py
"""
import asyncio
import base64
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.async_api import async_playwright


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file():
            self.path = '/index.html'
        super().do_GET()

    def log_message(self, *args):
        pass


async def check(browser, base_url, width):
    page = await browser.new_page(viewport={'width':width,'height':1100})
    errors, actions = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    company, account = 'test-company', 'test-account'
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="960"><rect width="1440" height="960" fill="#eee"/><rect x="500" y="400" width="400" height="100" fill="white"/><text x="520" y="450">Verification fixture</text></svg>'
    image = 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()
    screen = {'image':image,'width':1440,'height':960,'input_field':None}
    poll_started, release_poll = asyncio.Event(), asyncio.Event()
    view_count = 0

    async def api(route):
        nonlocal view_count
        path = route.request.url.split('/api/v1')[-1].split('?')[0]
        payload = {}
        if path == '/auth/refresh':
            payload = {'access_token':'mock-token'}
        elif path == '/auth/me':
            payload = {'id':'test-user','full_name':'Test','email':'test@example.invalid','is_active':True}
        elif path == '/companies':
            payload = [{'id':company,'name':'Test Hotel','business_goals':{}}]
        elif path.endswith('/publishing/accounts'):
            payload = [{'id':account,'platform':'douyin','label':'Test','status':'disconnected'}]
        elif path.endswith('/web/status'):
            payload = {'status':'login_required'}
        elif path.endswith('/web/view'):
            view_count += 1
            if view_count == 2:
                poll_started.set()
                await release_poll.wait()
            payload = screen
        elif path.endswith('/web/action'):
            action = route.request.post_data_json
            actions.append(action)
            payload = dict(screen)
            if action['kind'] in ('click','fill'):
                payload['input_field'] = {'id':'a'*32,'type':'text','placeholder':'测试输入框','x':400,'y':300,'width':300,'height':60}
        elif path.endswith('/publishing/jobs') or path.endswith('/approvals'):
            payload = {'items':[],'total':0}
        await route.fulfill(status=200,content_type='application/json',body=json.dumps(payload))

    await page.route('**/api/v1/**',api)
    await page.add_init_script("localStorage.setItem('refresh_token','mock');localStorage.setItem('currentCompanyId','test-company')")
    await page.goto(base_url+'/publishing')
    await page.get_by_role('button',name='打开网页登录',exact=True).click()
    screen_element = page.locator('.login-screen')
    await screen_element.wait_for()
    await screen_element.scroll_into_view_if_needed()
    await asyncio.wait_for(poll_started.wait(),10)
    box = await screen_element.bounding_box()
    x, y = box['x']+box['width']*.45, box['y']+box['height']*.45
    # Poll is in flight while the user clicks with a small natural hand movement.
    await page.mouse.move(x,y)
    await page.mouse.down()
    await page.mouse.move(x+5,y+2)
    await page.mouse.up()
    release_poll.set()
    await page.locator('.login-direct-input').wait_for()
    assert actions[0]['kind'] == 'click', actions
    assert abs(actions[0]['x']-648) <= 1, actions
    # Clicking elsewhere must flush the current field before forwarding the click.
    await page.locator('.login-direct-input').fill('123456')
    await page.mouse.click(x,y)
    await page.wait_for_function("!document.body.innerText.includes('正在同步操作，请稍候')")
    assert [a['kind'] for a in actions] == ['click','fill','click'], actions
    assert actions[1]['text'] == '123456'
    assert not errors, errors
    print(f'PASS viewport={width}: click during poll, jitter, coordinates, text/click order')
    await page.close()


async def main():
    root = Path(__file__).resolve().parents[1]/'dist'
    server = ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root)))
    Thread(target=server.serve_forever,daemon=True).start()
    try:
        async with async_playwright() as pw:
            options = {'headless':True,'args':['--no-sandbox']}
            chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
            if Path(chrome).exists():
                options['executable_path'] = chrome
            browser = await pw.chromium.launch(**options)
            try:
                for width in (1440,390):
                    await check(browser,f'http://127.0.0.1:{server.server_port}',width)
            finally:
                await browser.close()
    finally:
        server.shutdown()


asyncio.run(main())
