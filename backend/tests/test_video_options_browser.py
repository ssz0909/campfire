import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect
from app.core.security import create_refresh_token
from tests.conftest import create_test_company, create_test_user


def test_ratio_controls_and_workspace_music_choices(client,db):
    user=create_test_user(db);company=create_test_company(db,user)
    root=Path(__file__).resolve().parents[2]/'frontend/dist'
    saved=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1100})
        context.add_init_script('localStorage.setItem("refresh_token",'+json.dumps(create_refresh_token({'sub':str(user.id)}))+');localStorage.setItem("currentCompanyId",'+json.dumps(str(company.id))+')')
        def route(r):
            path=urlparse(r.request.url).path
            if path in ('/video/new','/tasks/new','/settings'):
                r.fulfill(body=(root/'index.html').read_bytes(),content_type='text/html')
            elif path.startswith('/assets/'):
                f=root/path.lstrip('/')
                r.fulfill(status=200 if f.is_file() else 404,body=f.read_bytes() if f.is_file() else b'',content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
            else:
                if path.endswith('/default-video-music') and r.request.method=='PUT':
                    saved.append(json.loads(r.request.post_data))
                response=client.request(r.request.method,r.request.url,content=r.request.post_data_buffer,headers=r.request.headers)
                r.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
        context.route('**/*',route)
        page=context.new_page()
        def select(label,option):
            page.locator('.n-form-item').filter(has=page.locator('.n-form-item-label',has_text=label)).locator('.n-base-selection').click()
            page.locator('.n-base-select-option').filter(has_text=option).click()
        page.goto('https://campfire.dawoai.com/video/new')
        page.locator('.mode-card').first.click()
        page.locator('.step-actions .n-button--primary-type').click()
        select('画面比例','横屏 16:9')
        expect(page.locator('.n-base-selection').filter(has_text='横屏 16:9')).to_be_visible()
        page.goto('https://campfire.dawoai.com/tasks/new')
        select('画面比例（用于本任务及后续视频制作）','方形 1:1')
        expect(page.locator('.n-base-selection').filter(has_text='方形 1:1')).to_be_visible()
        select('本任务的视频配乐','保留模型原声，不替换配乐')
        page.goto('https://campfire.dawoai.com/settings')
        page.locator('.n-tabs-tab').filter(has_text='默认视频配乐').click()
        select('配乐方式','保留模型原声，不替换配乐')
        page.get_by_role('button',name='保存默认视频配乐',exact=True).click()
        expect(page.get_by_text('已保存，后续新视频保留模型原声，不替换配乐。',exact=True)).to_be_visible()
        assert saved[-1]['selection_mode']=='model'
        browser.close()
