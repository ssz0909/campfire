"""Real Vue checkout rendering against isolated APIs; never reaches payment providers."""
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect
from app.core.security import create_refresh_token
from app.models.billing import PaymentOrder
from app.services import billing, payment_gateway
from tests.conftest import create_test_company, create_test_user


def test_subscription_checkout_admin_settings_and_mobile(client,db,monkeypatch):
    from app.connectors.hotel.models import PlatformKeyValue
    from app.core.secrets import encrypt_json
    from app.services.payment_settings import FIELDS,settings_key
    user=create_test_user(db,is_platform_admin=True)
    company=create_test_company(db,user)
    # Local dummy configuration; provider functions are replaced before checkout.
    db.add(PlatformKeyValue(key=settings_key('wechat'),encrypted_value=encrypt_json(
        {'enabled':True,**{key:'test' for key in FIELDS['wechat']}}),updated_at=billing.now()))
    db.commit()
    monkeypatch.setattr(payment_gateway,'create_checkout',lambda *args:'weixin://wxpay/test')
    root=Path(__file__).resolve().parents[2]/'frontend/dist'
    artifacts=root.parents[1]/'artifacts'/'billing'
    artifacts.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1050})
        context.add_init_script('localStorage.setItem("refresh_token",'+json.dumps(create_refresh_token({'sub':str(user.id)}))+');localStorage.setItem("currentCompanyId",'+json.dumps(str(company.id))+')')
        def route(r):
            path=urlparse(r.request.url).path
            if path in ('/subscription','/costs','/admin','/login'):
                r.fulfill(body=(root/'index.html').read_bytes(),content_type='text/html')
            elif path.startswith('/assets/'):
                f=root/path.lstrip('/')
                r.fulfill(status=200 if f.is_file() else 404,body=f.read_bytes() if f.is_file() else b'',content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
            elif path.startswith('/api/'):
                response=client.request(r.request.method,r.request.url,content=r.request.post_data_buffer,headers=r.request.headers)
                r.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
            else:r.abort()
        context.route('**/*',route)
        page=context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('https://campfire.dawoai.com/costs')
        expect(page).to_have_url('https://campfire.dawoai.com/subscription')
        expect(page.get_by_role('heading',name='轻运营版',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='购买此套餐')).to_have_count(3)
        page.screenshot(path=str(artifacts/'subscription-desktop.png'),full_page=True)
        page.get_by_role('button',name='购买此套餐').first.click()
        page.get_by_role('button',name='确认并获取支付二维码',exact=True).click()
        expect(page.get_by_alt_text('微信支付支付二维码')).to_be_visible()
        expect(page.get_by_role('button',name='我已支付，查询结果')).to_be_visible()
        row=db.query(PaymentOrder).one()
        billing.settle_order(db,row.order_no,row.channel,'browser-verified',row.amount_fen,row.merchant_snapshot)
        page.get_by_role('button',name='我已支付，查询结果').click()
        expect(page.get_by_text('支付成功，订阅已开通。',exact=True)).to_be_visible()
        page.goto('https://campfire.dawoai.com/subscription')
        expect(page.locator('.balance-number strong')).to_have_text('6,000')
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(artifacts/'subscription-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.set_viewport_size({'width':1440,'height':1050})
        page.goto('https://campfire.dawoai.com/admin')
        page.get_by_role('button',name='支付与订阅',exact=True).click()
        expect(page.get_by_role('heading',name='订阅套餐与计量规则')).to_be_visible()
        expect(page.get_by_role('button',name='保存微信支付',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='保存支付宝支付',exact=True)).to_be_visible()
        page.screenshot(path=str(artifacts/'payment-admin.png'),full_page=True)
        assert not errors,errors
        browser.close()
