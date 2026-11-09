"""Verify image previews, related source clips and regeneration prompt UI."""
import asyncio
import json
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from playwright.async_api import async_playwright


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if not Path(self.translate_path(self.path)).is_file():
            self.path = '/index.html'
        super().do_GET()

    def log_message(self, *_args):
        pass


async def check(browser, base, width):
    page=await browser.new_page(viewport={'width':width,'height':950})
    errors=[]; requests=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    image={'id':'image-1','company_id':'company','uploaded_by':'user','name':'湖景原图',
        'original_filename':'lake.jpg','asset_type':'image','mime_type':'image/jpeg','file_size_bytes':20,
        'file_key':'lake.jpg','file_url':'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=',
        'thumbnail_url':'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=',
        'processing_status':'ready','tags':['湖景'],'category':'landscape','source_description':'真实湖景',
        'metadata':{'vision_analysis':{'status':'completed'}},'is_available':True,
        'created_at':'2026-11-05T00:00:00Z','updated_at':'2026-11-05T00:00:00Z'}
    clip={**image,'id':'clip-1','name':'湖景原图 · 分镜1','original_filename':'clip.mp4',
        'asset_type':'video','mime_type':'video/mp4','file_key':'clip.mp4','file_url':'data:video/mp4;base64,AAAA',
        'thumbnail_url':None,'duration_seconds':5,'source_description':'泳池边自然侧移',
        'metadata':{'production_mode':'raw_model_clip','clip_library':{'review_status':'approved','usage_count':1,
            'contract':{'source_asset_id':'image-1'}}}}
    submitted=[]; deleted=[]
    clips=[clip,{**clip,'id':'clip-2','name':'第二个分镜'}]
    async def api(route):
        path=urlparse(route.request.url).path.split('/api/v1')[-1]
        if path=='/auth/refresh': result={'access_token':'mock'}
        elif path=='/auth/me': result={'id':'user','email':'test@example.invalid','is_active':True}
        elif path=='/companies': result=[{'id':'company','name':'测试工作区'}]
        elif path.endswith('/assets') and route.request.method=='GET': result={'items':[image],'total':1,'page':1,'page_size':20}
        elif path.endswith('/assets/image-1/clips'):
            result={'source':image,'items':clips,'total':len(clips),'jobs':[]}
        elif path.endswith('/assets/clip-2') and route.request.method=='DELETE':
            deleted.append(path); clips.pop(); await route.fulfill(status=204); return
        elif path.endswith('/regenerate-clip'):
            assert path.endswith('/assets/clip-1/regenerate-clip')
            submitted.append(route.request.post_data_json)
            result={'id':'project-1','status':'analyzing','prompt':submitted[-1]['prompt']}
        else: result={}
        await route.fulfill(status=202 if path.endswith('/regenerate-clip') else 200,
            content_type='application/json',body=json.dumps(result))
    await page.route('**/api/v1/**',api)
    await page.add_init_script("localStorage.setItem('refresh_token','mock');localStorage.setItem('currentCompanyId','company')")
    await page.goto(base+'/assets')
    await page.get_by_text('湖景原图',exact=True).first.wait_for()
    await page.get_by_role('button',name='预览湖景原图').click()
    assert await page.locator('.asset-preview-full').evaluate("el=>el.tagName")=='IMG'
    await page.keyboard.press('Escape')
    await page.get_by_role('button',name='查看分镜视频').click()
    await page.locator('.clips-modal__video').wait_for()
    assert await page.get_by_role('button',name='选择分镜 1').get_attribute('aria-pressed') == 'true'
    assert await page.get_by_role('button',name='删除分镜').is_visible()
    await page.get_by_role('button',name='下一个分镜').click()
    assert await page.get_by_role('button',name='选择分镜 2').get_attribute('aria-pressed') == 'true'
    await page.get_by_role('button',name='删除分镜').click()
    await page.get_by_role('button',name='删除',exact=True).last.click()
    await page.get_by_text('分镜已删除').wait_for()
    assert len(deleted)==1
    await page.get_by_role('button',name='重新生成分镜').click()
    await page.get_by_placeholder('描述希望改进的动作、镜头、节奏或画面细节').fill('人物缓慢走向泳池，镜头从全景平稳侧移到水面细节')
    await page.get_by_role('button',name='提交生成').click()
    await page.get_by_text('已提交分镜生成，完成后会显示在原图片下方').wait_for()
    assert submitted[0]['prompt'].startswith('人物缓慢走向泳池')
    assert submitted[0]['request_id'] and submitted[0]['aspect_ratio']=='9:16'
    await page.keyboard.press('Escape')
    await page.get_by_role('button',name=re.compile('List view|列表视图')).click()
    await page.get_by_role('button',name='预览湖景原图').click()
    assert await page.locator('.asset-list-preview').evaluate("el=>el.tagName")=='IMG'
    await page.keyboard.press('Escape')
    assert not errors,errors
    print(f'PASS {width}px: image preview, related clip preview and prompt regeneration',flush=True)
    await page.close()


async def main():
    dist=Path(__file__).resolve().parents[1]/'dist'
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(dist)))
    Thread(target=server.serve_forever,daemon=True).start()
    try:
        async with async_playwright() as playwright:
            browser=await playwright.chromium.launch(headless=True,
                executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args=['--no-sandbox'])
            try:
                base=f'http://127.0.0.1:{server.server_port}'
                for width in (1440,390):await check(browser,base,width)
            finally:await browser.close()
    finally:server.shutdown()


asyncio.run(main())
