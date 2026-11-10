"""Built UI against an isolated test DB; all network traffic intercepted locally."""
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
from tests.test_geo import setup
from app.core.security import create_refresh_token
from app.services import geo


def test_owner_publish_search_preview_and_admin(db,client,monkeypatch,tmp_path):
    root=Path(__file__).resolve().parents[2]/'frontend/dist'
    assert (root/'index.html').exists(), 'Run the frontend build before browser validation'
    user,company,headers,api=setup(db)
    user.is_platform_admin=True;db.commit()
    from app.models.asset import Asset
    from app.config import settings
    from PIL import Image
    monkeypatch.setattr(settings,'LOCAL_STORAGE_PATH',str(tmp_path))
    Image.open(Path(__file__).resolve().parents[1]/'app/public_media/hospitality.webp').resize((320,200)).save(tmp_path/'cover.png')
    asset=Asset(company_id=company.id,uploaded_by=user.id,name='图片封面验收',original_filename='cover.png',file_key='cover.png',file_url='/files/cover.png',asset_type='image',mime_type='image/png',file_size_bytes=500,processing_status='ready')
    db.add(asset);db.commit()
    from app.services import geo_writing
    async def suggestions(db,content):
        return {'description':'企业的真实产品和服务介绍，只用于隔离测试。','service_items':[{'name':'AI建议服务','description':'供用户核对的建议。'}],'faq_items':[]}
    monkeypatch.setattr(geo_writing,'generate',suggestions)
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
        page.get_by_role('button',name='＋ 添加产品或服务',exact=True).click()
        page.get_by_label('产品或服务名称',exact=True).fill('真实服务条目')
        page.get_by_label('产品或服务说明',exact=True).fill('根据实际情况提供服务，请提前咨询。')
        page.get_by_role('button',name='＋ 添加问答',exact=True).click()
        page.get_by_label('问题',exact=True).fill('如何咨询？')
        page.get_by_label('回答',exact=True).fill('通过本页公开联系方式咨询。')
        # Verify distinct styling even before any image is configured.
        for code,expected in [('generic','classic'),('travel','scenic'),('gallery','editorial')]:
            page.locator('input[name="template"][value="'+code+'"]').check()
            page.get_by_role('button',name='预览草稿',exact=True).click()
            frame=page.frame_locator('iframe')
            expect(frame.locator('body')).to_have_class('layout-'+expected)
            if expected=='scenic':assert frame.locator('.site-hero').evaluate('(el)=>getComputedStyle(el).textAlign')=='center'
            if expected=='editorial':assert frame.locator('.site-hero').evaluate('(el)=>parseInt(getComputedStyle(el).borderLeftWidth)')==6
            page.get_by_role('button',name='收起预览',exact=True).click()
        page.locator('input[name="template"][value="generic"]').check()
        page.get_by_role('button',name='选择图片',exact=True).click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.get_by_role('button',name='预览图片：图片封面验收',exact=True).click()
        expect(page.get_by_role('dialog').get_by_role('img')).to_have_js_property('naturalWidth',320)
        page.get_by_role('button',name='用作封面',exact=True).click()
        expect(page.get_by_role('dialog')).not_to_be_visible()
        assert page.get_by_label('企业介绍',exact=True).evaluate('(el)=>getComputedStyle(el).resize')=='none'
        assert page.get_by_role('button',name='AI整理文案',exact=True).bounding_box()['y']>page.get_by_label('产品或服务说明',exact=True).bounding_box()['y']
        page.get_by_role('button',name='添加展示图片',exact=True).click()
        page.get_by_role('button',name='添加展示图片',exact=True).last.click()
        page.get_by_role('button',name='AI整理文案',exact=True).click()
        expect(page.get_by_role('dialog')).to_be_visible()
        expect(page.get_by_role('dialog').get_by_text('AI建议服务',exact=True)).to_be_visible()
        page.get_by_role('button',name='暂不采用',exact=True).click()
        expect(page.get_by_label('产品或服务名称',exact=True)).to_have_value('真实服务条目')
        page.get_by_role('button',name='预览此模板',exact=True).nth(1).click()
        frame=page.frame_locator('iframe')
        expect(frame.get_by_role('heading',name='目的地与体验',exact=True)).to_be_visible()
        expect(frame.get_by_role('img',name='浏览器验收企业公开封面')).to_have_js_property('naturalWidth',320)
        expect(frame.get_by_role('link',name='发现企业',exact=True)).to_have_count(0)
        expect(frame.get_by_role('link',name='登录工作台',exact=True)).to_have_count(0)
        page.get_by_role('button',name='收起预览',exact=True).click()
        page.get_by_text('资质、承诺与有效期（选填）',exact=True).click()
        page.get_by_role('button',name='＋ 添加补充信息',exact=True).click()
        remove=page.get_by_role('button',name='移除补充信息',exact=True)
        expect(remove).to_be_visible()
        assert remove.bounding_box()['height']<60
        remove.click()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path='/tmp/campfire-geo-editor-mobile.png',full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        page.get_by_label('我确认以上资料真实').check()
        page.get_by_role('button',name='预览草稿',exact=True).click()
        expect(page.get_by_title('企业主页草稿预览')).to_be_visible()
        expect(page.frame_locator('iframe').get_by_role('heading',name='浏览器验收企业',exact=True)).to_be_visible()
        page.on('dialog',lambda d:d.accept())
        page.get_by_role('button',name='发布主页',exact=True).click()
        expect(page.get_by_role('status')).to_have_text('主页发布成功，已进入站内搜索')
        expect(page.get_by_label('公开网址标识')).to_be_disabled()
        page.screenshot(path='/tmp/campfire-geo-editor.png',full_page=True)
        for style in ['画册展示','品牌海报']:
            page.get_by_label(style,exact=True).check()
            page.get_by_role('button',name='预览草稿',exact=True).click()
            expect(page.frame_locator('iframe').get_by_role('heading',name='浏览器验收企业',exact=True)).to_be_visible()
            html=page.frame_locator('iframe').locator('html').evaluate('(el)=>el.outerHTML')
            standalone=context.new_page()
            standalone.set_content(html.replace('<head>','<head><base href="https://campfire.dawoai.com/">',1))
            expect(standalone.get_by_role('img',name='浏览器验收企业公开封面')).to_have_js_property('naturalWidth',320)
            standalone.screenshot(path='/tmp/geo-style-'+('editorial' if style=='画册展示' else 'poster')+'.png',full_page=True)
            standalone.set_viewport_size({'width':390,'height':844})
            assert standalone.evaluate('document.documentElement.scrollWidth<=innerWidth')
            standalone.screenshot(path='/tmp/geo-style-'+('editorial' if style=='画册展示' else 'poster')+'-mobile.png',full_page=True)
            standalone.close()
            page.get_by_role('button',name='收起预览',exact=True).click()
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
        expect(page.get_by_role('heading',name='让客户一眼看懂你的好。')).to_be_visible()
        for img in page.locator('img').all():
            img.scroll_into_view_if_needed()
            expect(img).to_have_js_property('complete',True)
            assert img.evaluate('(el)=>el.naturalWidth>0')
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
