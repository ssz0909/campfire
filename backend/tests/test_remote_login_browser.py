"""Local DOM fixtures only: never submit an actual provider verification."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from app.connectors import web_platform


@pytest.fixture
def login_page(monkeypatch):
    with sync_playwright() as pw:
        chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        options = {'headless':True, 'args':['--no-sandbox']}
        if Path(chrome).exists():
            options['executable_path'] = chrome
        browser = pw.chromium.launch(**options)
        page = browser.new_page(viewport={'width':1440,'height':960})
        session = {'page':page,'context':page.context}
        monkeypatch.setattr(web_platform,'_get_session',lambda *args:session)
        yield page, session
        browser.close()


def test_user_click_reaches_nested_frame_and_paints_result(login_page):
    page, _ = login_page
    page.set_content('<iframe style="position:absolute;left:300px;top:100px;width:600px;height:400px;border:0"></iframe>')
    frame = page.frames[1]
    frame.set_content('''<button style="position:absolute;left:50px;top:50px;width:300px;height:80px"
      onmousedown="window.downAt=performance.now()"
      onclick="if(performance.now()-window.downAt>=50)setTimeout(()=>document.body.dataset.clicked='yes',100)">选择验证方式（测试）</button>''')
    result = web_platform.login_view.__wrapped__('test','douyin',{'kind':'click','x':450,'y':190})
    assert frame.locator('body').get_attribute('data-clicked') == 'yes'
    assert result['width'] == 1440


def test_focused_input_behind_modal_does_not_cover_verification_controls(login_page):
    page, _ = login_page
    page.set_content('''<input style="position:absolute;left:300px;top:200px;width:400px;height:100px">
      <div style="position:fixed;inset:0;background:white;z-index:2">身份验证（测试）</div>''')
    page.locator('input').focus()
    result = web_platform.login_view.__wrapped__('test','douyin')
    assert result['input_field'] is None
    page.locator('div').evaluate('(el)=>el.remove()')
    result = web_platform.login_view.__wrapped__('test','douyin')
    assert result['input_field']['width'] > 0


def test_login_diagnostics_omit_form_values_text_and_urls(login_page):
    import json
    page, _ = login_page
    page.set_content('<p>DO_NOT_RETURN_ACCOUNT</p><input value="DO_NOT_RETURN_PASSWORD"><button>身份验证</button>')
    result = web_platform.login_diagnostics.__wrapped__('test','douyin')
    assert result['frames'][0]['verification'] is True
    assert result['frames'][0]['controls'][0]['tag'] == 'BUTTON'
    assert 'DO_NOT_RETURN' not in json.dumps(result)


def test_top_verification_layer_activates_only_the_user_point_once(login_page):
    page, session = login_page
    page.set_content('''<div class="second_verify_panel-test" style="position:fixed;left:300px;top:200px;width:500px;height:400px;background:white">
      <div id="first" style="height:100px" onclick="document.body.dataset.first=(+document.body.dataset.first||0)+1"><span>第一种验证方式</span></div>
      <div id="second" style="height:100px" onclick="document.body.dataset.second=(+document.body.dataset.second||0)+1"><span>第二种验证方式</span></div>
      </div>''')
    page.locator('#first,#second').evaluate_all("els=>els.forEach(el=>el.__reactProps$fixture={onClick:()=>{}})")
    web_platform.login_view.__wrapped__('test','douyin',{'kind':'click','x':450,'y':350})
    assert session['last_login_click']['delivery'] == 'element'
    assert page.locator('body').get_attribute('data-second') == '1'
    assert page.locator('body').get_attribute('data-first') is None


def test_blank_verification_panel_keeps_native_input(login_page):
    page, _ = login_page
    page.set_content('<div class="second_verify_panel-test" style="position:fixed;inset:0"></div>')
    assert web_platform._click_login_point(page,720,490) == 'pointer'


def test_verification_icon_uses_clickable_ancestor(login_page):
    page, _ = login_page
    page.set_content('''<div class="second_verify_panel-test" style="position:fixed;inset:0">
      <div role="button" style="position:absolute;left:400px;top:200px;width:60px;height:60px" onclick="document.body.dataset.closed='yes'">
      <svg width="60" height="60"><rect width="60" height="60" /></svg></div></div>''')
    assert web_platform._click_login_point(page,430,230) == 'element'
    assert page.locator('body').get_attribute('data-closed') == 'yes'


def test_disabled_verification_control_does_not_receive_activation(login_page):
    page, _ = login_page
    page.set_content('''<div class="second_verify_panel-test" style="position:fixed;inset:0">
      <div role="button" aria-disabled="true" style="position:absolute;left:400px;top:200px;width:300px;height:60px" onclick="document.body.dataset.clicked='yes'">等待平台</div></div>''')
    with pytest.raises(RuntimeError,match='暂不可用'):
        web_platform._click_login_point(page,430,230)
    assert page.locator('body').get_attribute('data-clicked') is None
