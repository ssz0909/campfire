"""Support the inline POI tag row without accepting unbound search text."""
from playwright.sync_api import sync_playwright
from app.connectors.web_platform import _select_publish_location, _inline_location_field


def test_inline_recommendation_selection():
    name = '安吉雲中溪·汤泉度假酒店'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        actions = [
            "field.readOnly=true;recommendations.remove()",
            "recommendations.remove()",
            "field.hidden=true;recommendations.remove();selected.textContent=name",
        ]
        for action in actions:
            page.set_content(f'''<input id=title value="Video title">
                <div id=row><span>添加标签</span><button>位置<input readonly value="位置"></button>
                <input id=tag placeholder="其他标签" value="unchanged"><input id=field placeholder="请输入位置">
                <div id=recommendations><button id=hotel>{name}</button><button>其他酒店</button></div>
                <span id=selected></span></div>
                <script>hotel.onclick=()=>{{let name='{name}';{action}}}</script>''')
            _select_publish_location(page, name)
            assert page.locator('#title').input_value() == 'Video title'
            assert page.locator('#field').input_value() == name
            assert page.locator('#tag').input_value() == 'unchanged'
        page.set_content('''<div id=row><span>添加标签</span>
            <div style="display:flex;align-items:center;gap:20px"><span>位置</span><input id=field></div>
            <input id=other placeholder="其他标签"></div>''')
        assert _inline_location_field(page.locator('#row')).get_attribute('id') == 'field'
        page.set_content('''<div id=row><span>位置</span>
            <input placeholder="搜索位置"><input placeholder="搜索地点"></div>''')
        try:
            _inline_location_field(page.locator('#row'))
        except ValueError:
            pass
        else:
            raise AssertionError('Ambiguous location fields must stop')
        # The platform can render the hotel name in a read-only selector.
        # The old editable-only locator counted zero despite a visible name.
        page.set_content(f'''<div><span>添加标签</span><button>位置<input type=hidden></button>
            <input id=field readonly value="{name}"><div id=recommendations>
            <button onclick="document.getElementById('recommendations').remove()">{name}</button>
            </div></div>''')
        _select_publish_location(page, name)
        assert page.locator('#field').input_value() == name
        # Existing read-only text must not be accepted when the click does nothing.
        page.set_content(f'''<div><span>添加标签</span><button>位置</button>
            <input readonly value="{name}"><button>{name}</button></div>''')
        try:
            _select_publish_location(page, name)
        except ValueError as exc:
            assert '核对内嵌地点已选中' in str(exc)
        else:
            raise AssertionError('Pre-filled readonly text alone was accepted')
        # A click which does nothing must not convert typed query into success.
        page.set_content(f'''<div><span>添加标签</span><button>位置</button><input>
            <button>{name}</button></div>''')
        try:
            _select_publish_location(page, name)
        except ValueError as exc:
            assert '核对内嵌地点已选中' in str(exc)
        else:
            raise AssertionError('Search text without an attached location was accepted')
        browser.close()


if __name__ == '__main__':
    test_inline_recommendation_selection()
    print('Inline recommendation selection, unchanged title, no-op click rejection: PASS')
