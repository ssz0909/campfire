"""Real DOM timing regression; no provider requests or publish operations."""
from playwright.sync_api import sync_playwright

from app.connectors import web_platform as web


def test_channels_delayed_app_identity_is_ready_before_publication(monkeypatch):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            page = browser.new_page()
            page.route('**/*', lambda route: route.abort())
            page.set_content('''<body>页面加载中<script>
                setTimeout(() => document.body.insertAdjacentHTML('beforeend','<div>视频号ID · 内容管理</div>'), 200);
                setTimeout(() => window.fixtureIdentity='bound-account', 900);
                </script></body>''')
            checks = []
            def status(*args):
                identity = page.evaluate('() => window.fixtureIdentity || null')
                checks.append(identity)
                return {'status':'authorized', 'login_required':False,
                    **({'account_fingerprint':identity, 'identity_verified':True} if identity else {})}
            monkeypatch.setattr(web, 'session_status', status)
            result = web._wait_for_account_ready('tenant', 'wechat_channels', {'page':page},
                'bound-account', timeout_ms=3000)
            assert not result['login_required'] and result['account_fingerprint'] == 'bound-account'
            assert checks[0] is None and checks[-1] == 'bound-account'
        finally:
            browser.close()
