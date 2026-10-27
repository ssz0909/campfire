"""Regress hidden location controls and identify the failed picker step."""

def test_hidden_location_controls():
    from playwright.sync_api import sync_playwright
    from app.connectors.web_platform import _select_publish_location,_location_step
    from app.schemas.publishing import PublishRequest
    from app.config import settings
    assert settings.DATABASE_URL.startswith('sqlite:')
    name='安吉雲中溪·汤泉度假酒店'
    request=PublishRequest(title='酒店视频',location_name=name,request_key='location-test')
    assert request.location_name==name
    with sync_playwright() as p:
     browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
     page=browser.new_page()
     page.set_content('''<button onclick="document.getElementById('picker').hidden=false">添加位置</button>
     <input placeholder=搜索位置 style="display:none"><span style="display:none">安吉雲中溪·汤泉度假酒店</span><div id=picker hidden><input placeholder="搜索位置"><button onclick="document.getElementById('selected').textContent=this.textContent;document.getElementById('picker').remove()">安吉雲中溪·汤泉度假酒店</button><button>安吉其他酒店</button></div><span id=selected></span>''')
     _select_publish_location(page,name)
     assert page.locator('#selected').inner_text()==name
     page.set_content('<p>没有位置控件的页面</p>')
     try:_select_publish_location(page,name)
     except ValueError:pass
     else:raise AssertionError('Missing location control must prevent submission')
     browser.close()
    print('Location schema, exact POI selection, selected-label verification, missing control stops publishing: PASS')
    
    class TimeoutError(Exception):pass
    def timeout():raise TimeoutError()
    try:_location_step('等待位置搜索框出现',timeout)
    except ValueError as e:assert '等待位置搜索框出现' in str(e)
    else:raise AssertionError('Missing timeout step')
    print('Hidden duplicate input/result skipped; specific timeout step reported: PASS')

if __name__ == "__main__":
    test_hidden_location_controls()
