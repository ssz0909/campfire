"""Regression for the inspected Douyin Semi Select location tag markup."""
from playwright.sync_api import sync_playwright
from app.connectors.web_platform import _select_publish_location


def test_douyin_location_tag():
    name = '安吉雲中溪·汤泉度假酒店'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        for initial in [name, '请选择位置']:
            page.set_content(f'''<div class="content-obt4oA new-layout-sLYOT6"><span>添加标签</span>
                <div class=anchor-container-hgj7gj><div class=semi-select>位置</div>
                <div class=anchor-component-Shp3mT><div class="semi-select semi-select-filterable">
                <span class=semi-select-selection-text>{initial}</span></div></div></div>
                <div class=recommend-list-Q0Dw6A><span class=recommend-list-item-L8agth
                onclick="document.querySelector('.semi-select-selection-text').textContent=this.textContent">{name}</span></div>
                </div>''')
            _select_publish_location(page, name)
            assert page.locator('.semi-select-selection-text').inner_text() == name
        # A matching recommendation alone cannot count as a selected POI.
        page.set_content(f'''<div class=content-obt4oA><span>添加标签</span>
            <div class=anchor-container-hgj7gj><div class=semi-select>位置</div>
            <div class="semi-select semi-select-filterable"><span class=semi-select-selection-text>请选择位置</span></div></div>
            <span class=recommend-list-item-L8agth>{name}</span></div>''')
        try:
            _select_publish_location(page, name)
        except ValueError as exc:
            assert '核对酒店地点标签的选中值' in str(exc)
        else:
            raise AssertionError('An unselected recommendation was accepted')
        browser.close()


if __name__ == '__main__':
    test_douyin_location_tag()
    print('Actual Semi Select markup: preselected POI, recommendation selection, no-op guard PASS')
