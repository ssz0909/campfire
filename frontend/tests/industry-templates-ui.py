"""Built frontend regression: edit/publish an industry and select it in new work."""
import asyncio
import copy
import json
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from playwright.async_api import async_playwright


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file(): self.path = '/index.html'
        super().do_GET()

    def log_message(self, *_args): pass


CONTENT = {'name':'酒旅','description':'住宿、景区及周边体验','positioning':'真实体验',
           'themes':['景观与氛围'],'material_hints':['仅展示真实素材'],'terminology':['打卡'],
           'forbidden_expressions':['无依据的热度'],'selection_keywords':['景观'],
           'publish_tone':'自然','copy_guidance':'围绕成片亮点，关注咨询'}


async def check(browser, base, width):
    page = await browser.new_page(viewport={'width':width,'height':1000})
    errors, writes, tasks = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    rows = [{'code':'travel','enabled':True,'draft':copy.deepcopy(CONTENT),'draft_revision':1,'published_version':1,
             'versions':[{'version':1,'content':copy.deepcopy(CONTENT),'created_at':datetime.now(timezone.utc).isoformat()}],
             'preview':'通用创作底座：任务及事实优先。酒旅体验。'}]

    async def api(route):
        path = urlparse(route.request.url).path.split('/api/v1')[-1]
        method = route.request.method
        result = {}
        if path == '/auth/refresh': result = {'access_token':'mock'}
        elif path == '/auth/me': result = {'id':'u','email':'test@example.invalid','is_active':True,'is_platform_admin':True}
        elif path == '/companies': result = [{'id':'company','name':'测试企业','industry':'travel'}]
        elif path == '/industries':
            result = [{'code':r['code'],'name':r['versions'][-1]['content']['name'],'version':r['published_version'],'description':''}
                      for r in rows if r['published_version'] and r['enabled']]
        elif path == '/admin/industry-templates' and method == 'GET': result = rows
        elif path == '/admin/industry-templates' and method == 'POST':
            body = route.request.post_data_json; writes.append((method,path,copy.deepcopy(body)))
            result = {'code':body['code'],'draft':body['content'],'draft_revision':1,'published_version':0,
                      'enabled':True,'versions':[],'preview':'新行业草稿'}
            rows.append(result)
        elif path.startswith('/admin/industry-templates/'):
            body = route.request.post_data_json; writes.append((method,path,copy.deepcopy(body)))
            result = next(r for r in rows if r['code'] == path.split('/')[3])
            assert body['expected_revision'] == result['draft_revision']
            if path.endswith('/draft'): result['draft'] = body['content']
            elif path.endswith('/publish'):
                result['published_version'] += 1
                result['versions'].append({'version':result['published_version'],'content':copy.deepcopy(result['draft']),
                                          'created_at':datetime.now(timezone.utc).isoformat()})
            elif path.endswith('/status'): result['enabled'] = body['enabled']
            result['draft_revision'] += 1
        elif path.startswith('/admin/'):
            result = [] if path.endswith(('/users','/companies')) else {}
        elif path.endswith('/employees'): result = [{'id':'employee','name':'视频制作员','role_title':'video_producer','is_active':True}]
        elif path.endswith('/publishing/accounts'): result = []
        elif path.endswith('/tasks') and method == 'POST':
            tasks.append(route.request.post_data_json)
            await route.fulfill(status=422,content_type='application/json',body=json.dumps({'detail':'测试提交已记录'})); return
        await route.fulfill(status=200,content_type='application/json',body=json.dumps(result))

    await page.route('**/api/v1/**',api)
    await page.add_init_script("localStorage.setItem('refresh_token','mock');localStorage.setItem('currentCompanyId','company')")
    await page.goto(base+'/admin')
    await page.get_by_role('button',name='行业模板',exact=True).click()
    await page.get_by_role('heading',name='行业与创作模板').wait_for()
    positioning=page.locator('.n-form-item').filter(has_text='创作定位').locator('textarea')
    await positioning.fill('住宿及景区的真实打卡体验')
    assert await page.get_by_role('button',name='发布当前草稿',exact=True).is_disabled()
    await page.get_by_role('button',name='保存草稿',exact=True).click()
    await page.get_by_text('草稿已保存；发布后才对新任务生效。',exact=True).wait_for()
    assert len(writes) == 1 and rows[0]['published_version'] == 1
    await page.get_by_role('button',name='发布当前草稿',exact=True).click()
    await page.get_by_text('模板已发布，新任务可使用此版本。',exact=True).wait_for()
    assert rows[0]['published_version'] == 2
    await page.get_by_role('button',name='新增行业',exact=True).click()
    await page.locator('.n-form-item').filter(has_text='行业标识').locator('input').fill('restaurant')
    await page.locator('.n-form-item').filter(has_text='行业名称').locator('input').fill('餐饮')
    await page.get_by_role('button',name='创建行业草稿',exact=True).click()
    await page.get_by_text('草稿已保存；发布后才对新任务生效。',exact=True).wait_for()
    await page.get_by_role('button',name='发布当前草稿',exact=True).click()
    await page.get_by_text('模板已发布，新任务可使用此版本。',exact=True).wait_for()
    await page.screenshot(path=f'/tmp/campfire-industry-admin-{width}.png',full_page=True)
    await page.goto(base+'/tasks/new?role=video_producer')
    await page.get_by_text('本次模板：酒旅 · v2。',exact=False).wait_for()
    picker=page.locator('.n-form-item').filter(has_text='行业创作模板').locator('.n-base-selection')
    await picker.click();await page.get_by_text('餐饮',exact=True).click()
    await page.get_by_text('本次模板：餐饮 · v1。',exact=False).wait_for()
    await page.get_by_placeholder('例如：本周酒店运营分析').fill('餐饮任务')
    await page.get_by_placeholder('说明你要解决的问题、目标客群和交付要求').fill('根据真实素材展示菜品')
    await page.get_by_role('button',name='提交并执行',exact=True).click()
    await page.get_by_text('测试提交已记录',exact=True).wait_for()
    assert tasks[0]['input_params']['industry_override'] == 'restaurant'
    assert 'publish_account_ids' in tasks[0]['input_params']
    await page.goto(base+'/companies/new')
    await page.locator('.n-select').click();await page.get_by_text('餐饮',exact=True).wait_for()
    assert not errors, errors
    assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'horizontal overflow'
    print(f'PASS {width}px: draft/publish, create industry, dynamic workspace list, task override and matrix payload preserved',flush=True)
    await page.close()


async def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(Path(__file__).resolve().parents[1]/'dist')))
    Thread(target=server.serve_forever,daemon=True).start()
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
            try:
                for width in (1440,390): await check(browser,f'http://127.0.0.1:{server.server_port}',width)
            finally: await browser.close()
    finally: server.shutdown()


asyncio.run(main())
