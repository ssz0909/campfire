"""Closed browser errors must stop before submit and retain a useful cause."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.connectors import web_platform as web


def test_browser_closed_before_submit():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        page.close()
        try:
            web._select_publish_location(page, 'Test hotel')
        except Exception as exc:
            assert web._closed_browser_error(exc), type(exc).__name__
            closed = exc
        else:
            raise AssertionError('Closed page was accepted')
        page = browser.new_page()
        page.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<input type=file><input placeholder=标题><textarea></textarea>'))
        media = Path('/tmp/campfire-publish-fix/test-only-closed.mp4')
        media.write_bytes(b'test-only')
        originals = {key: getattr(web, key) for key in ['_ensure_open', '_get_session', 'session_status', '_select_publish_location_impl', '_publish_button']}
        try:
            web._ensure_open = lambda *args: None
            web._get_session = lambda *args: {'page': page}
            web.session_status = lambda *args: {'login_required': False}
            def select(*args):
                raise closed
            def forbidden(*args):
                raise AssertionError('Must not attempt submit after browser closed')
            web._select_publish_location_impl = select
            web._publish_button = forbidden
            result = web.publish.__wrapped__('test', 'douyin', 'Test', 'Test', str(media), location_name='Test hotel')
            assert result['status'] == 'manual_required'
            assert result['metrics']['submission_uncertain'] is False
            assert result['metrics']['publish_stage'] == '选择地理位置'
            assert '浏览器已关闭或崩溃' in result['message']
        finally:
            for key, value in originals.items():
                setattr(web, key, value)
            media.unlink(missing_ok=True)
            browser.close()


if __name__ == '__main__':
    test_browser_closed_before_submit()
    print('Closed page diagnosis and no-submit guard: PASS')
