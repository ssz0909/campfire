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
        session = {'page':page}
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
