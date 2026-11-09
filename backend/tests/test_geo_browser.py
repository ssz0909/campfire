"""Built UI against an isolated test DB; all network traffic intercepted locally."""
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
from tests.test_geo import setup
from app.core.security import create_refresh_token
from app.services import geo


def test_owner_publish_search_preview_and_admin(db,client,monkeypatch):
    root=Path(__file__).resolve().parents[2]/'frontend/dist'
    assert (root/'index.html').exists(), 'Run the frontend build before browser validation'
    user,company,headers,api=setup(db)
    user.is_platform_admin=True;db.commit()
    monkeypatch.setattr(geo,'index_site',lambda *args:None)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_init_script('if(window.top===window){localStorage.setItem("refresh_token",'+json.dumps(create_refresh_token({'sub':str(user.id)}))+');localStorage.setItem("currentCompanyId",'+json.dumps(str(company.id))+')}')
        errors=[]
        def route(r):
            path=urlparse(r.request.url).path
            if path.startswith('/assets/'):
                f=root/path.lstrip('/')
                r.fulfill(status=200 if f.exists() else 404,body=f.read_bytes() if f.exists() else b'',content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
            elif path in ('/geo','/admin','/login'):
                r.fulfill(status=200,body=(root/'index.html').read_bytes(),content_type='text/html')
            else:
                response=client.request(r.request.method,r.request.url,content=r.request.post_data_buffer,headers=r.request.headers)
                r.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
        context.route('**/*',route)
        page=context.new_page();page.on('pageerror',lambda ex:errors.append(str(ex)))
        page.goto('https://campfire.dawoai.com/geo')
        expect(page.get_by_role('heading',name='GEO · 企业公开主页')).to_be_visible()
        page.get_by_label('公开网址标识').fill('browser-example')
        page.get_by_label('公开名称',exact=True).fill('浏览器验收企业')
        page.get_by_label('企业介绍',exact=True).fill('企业的真实产品和服务介绍，只用于隔离测试。')
        page.get_by_label('公开联系信息',exact=True).fill('测试联系渠道')
        page.get_by_label('我确认以上资料真实').check()
        page.get_by_role('button',name='预览草稿',exact=True).click()
        expect(page.get_by_title('企业主页草稿预览')).to_be_visible()
        page.on('dialog',lambda d:d.accept())
        page.get_by_role('button',name='发布主页',exact=True).click()
        expect(page.get_by_role('status')).to_have_text('主页发布成功，已进入站内搜索')
        expect(page.get_by_label('公开网址标识')).to_be_disabled()
        page.screenshot(path='/tmp/campfire-geo-editor.png',full_page=True)
        page.reload()
        expect(page.get_by_label('公开网址标识')).to_be_disabled()
        page.goto('https://campfire.dawoai.com/search?q=浏览器验收企业')
        expect(page.get_by_role('link',name='浏览器验收企业')).to_be_visible()
        page.get_by_role('link',name='浏览器验收企业').click()
        expect(page.get_by_role('heading',name='浏览器验收企业',exact=True)).to_be_visible()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path='/tmp/campfire-geo-mobile.png',full_page=True)
        page.goto('https://campfire.dawoai.com/')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path='/tmp/campfire-geo-home.png',full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto('https://campfire.dawoai.com/admin')
        page.get_by_role('button',name='GEO运营数据',exact=True).click()
        expect(page.get_by_role('heading',name='GEO运营数据')).to_be_visible()
        expect(page.get_by_text('browser-example',exact=False)).to_be_visible()
        page.screenshot(path='/tmp/campfire-geo-admin.png',full_page=True)
        assert not errors,errors
        browser.close()
