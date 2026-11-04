"""Verify branded opening settings persist and fit desktop/mobile using mock APIs."""
import asyncio
import base64
import io
import sys
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from playwright.async_api import async_playwright
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.services.video_branding import VideoBrandingSettings, wordmark_image


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file():
            self.path = '/index.html'
        super().do_GET()

    def log_message(self, *args):
        pass


async def check(browser, base, width):
    page = await browser.new_page(viewport={'width': width, 'height': 1050})
    errors, saves = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    company = {'id': 'test-company', 'name': '安吉雲中溪', 'business_goals': {}}

    async def api(route):
        path = urlparse(route.request.url).path.split('/api/v1')[-1]
        result = {}
        if path == '/auth/refresh':
            result = {'access_token': 'mock'}
        elif path == '/auth/me':
            result = {'id': 'test-user', 'email': 'test@example.invalid', 'is_active': True}
        elif path == '/companies':
            result = [company]
        elif path.endswith('/video-branding/fonts'):
            result = [{'value': 'default', 'label': '默认中文字体'}, {'value': 'sans', 'label': '黑体（简洁现代）'}, {'value': 'serif', 'label': '宋体（典雅人文）'}]
        elif path.endswith('/video-branding/preview'):
            from urllib.parse import parse_qs
            aspect = parse_qs(urlparse(route.request.url).query).get('aspect', ['9:16'])[0]
            size = {'9:16':(720,1280), '16:9':(1280,720), '1:1':(960,960)}[aspect]
            data = route.request.post_data_json
            img = wordmark_image(data['text'], *size, VideoBrandingSettings(**data))
            img.thumbnail((480,480)); out=io.BytesIO(); img.save(out,format='PNG')
            result = {'image_base64':base64.b64encode(out.getvalue()).decode()}
        elif path.endswith('/video-branding'):
            settings = route.request.post_data_json
            saves.append(settings)
            company['business_goals']['video_branding'] = settings
            result = company
        elif path.endswith('/products'):
            result = []
        elif path == '/companies/test-company':
            result = company
        await route.fulfill(status=200, content_type='application/json', body=json.dumps(result))

    await page.route('**/api/v1/**', api)
    await page.add_init_script("localStorage.setItem('refresh_token','mock');localStorage.setItem('currentCompanyId','test-company')")
    await page.goto(base + '/settings')
    await page.get_by_text('视频品牌片头', exact=True).click()
    await page.get_by_text('自动在视频开头展示品牌名称', exact=True).click()
    await page.get_by_label('品牌字体', exact=True).click()
    await page.get_by_text('宋体（典雅人文）',exact=True).click()
    await page.get_by_label('品牌位置', exact=True).click()
    await page.get_by_text('右下',exact=True).click()
    for label in ['品牌字号','品牌左右边距','品牌上下边距']:
        slider=page.locator(f'[aria-label="{label}"]')
        await slider.click(position={'x':100,'y':10})
    await page.get_by_role('button', name='保存视频品牌片头', exact=True).click()
    await page.get_by_text('已保存，后续成片将自动添加品牌片头。', exact=True).wait_for()
    assert len(saves)==1 and saves[0]['enabled'] and saves[0]['font']=='serif' and saves[0]['position']=='bottom_right', saves
    assert saves[0]['font_size_percent']!=6.2 and saves[0]['margin_x_percent']!=8 and saves[0]['margin_y_percent']!=14,saves
    saved=saves[0].copy()
    await page.reload()
    await page.get_by_text('视频品牌片头', exact=True).click()
    await page.get_by_label('品牌片头样式示意').wait_for()
    assert await page.get_by_placeholder('例如：安吉雲中溪').input_value() == '安吉雲中溪'
    await page.get_by_alt_text('服务器真实字体和排版预览').wait_for()
    assert await page.get_by_label('品牌字体',exact=True).inner_text() == '宋体（典雅人文）'
    assert await page.get_by_label('品牌位置',exact=True).inner_text() == '右下'
    await page.get_by_role('button',name='保存视频品牌片头',exact=True).click()
    await page.wait_for_timeout(400)
    assert saves[-1]==saved
    for aspect in ['横屏 16:9','方形 1:1','竖屏 9:16']:
        await page.get_by_label('预览画幅',exact=True).click()
        await page.get_by_text(aspect,exact=True).last.click()
        await page.get_by_alt_text('服务器真实字体和排版预览').wait_for()
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal page overflow'
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal page overflow' 
    assert not errors, errors
    await page.screenshot(path=f'/tmp/campfire-video-branding-ui-{width}.png', full_page=True)
    print(f'PASS {width}px: opening branding saved/restored, no overflow or browser errors', flush=True)
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
