"""Real SPA timing and identity checks; all provider traffic is blocked."""
import json
from playwright.sync_api import sync_playwright
from app.connectors import web_platform as web


def test_fresh_read_tab_verifies_delayed_channels_identity_and_201(monkeypatch):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            context=browser.new_context()
            editor=context.new_page()
            editor.goto('about:blank')
            html='''<meta charset="UTF-8"><body>页面加载中<script>
              setTimeout(()=>{document.body.append('视频号ID · 内容管理');
                  localStorage.setItem('finder_username','bound-hotel');
                  fetch('/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list',{method:'POST',body:'{}'});
              },600);
              </script></body>'''
            def route(request):
                if request.request.url.endswith('/post/post_list'):
                    request.fulfill(status=201,content_type='application/json',body=json.dumps({'errCode':0,'data':{
                        'continueFlag':False,'totalCount':1,'list':[{'objectId':'post-1','readCount':82,'likeCount':0}]}}))
                elif request.request.url=='https://channels.weixin.qq.com/platform':
                    request.fulfill(status=200,content_type='text/html',body=html)
                else:request.abort()
            context.route('**/*',route)
            session={'context':context,'page':editor}
            monkeypatch.setattr(web,'_ensure_open',lambda *args:None)
            monkeypatch.setattr(web,'_save_session',lambda *args:True)
            monkeypatch.setattr(web,'_get_session',lambda *args:session)
            result=web.read_work_metrics.__wrapped__('tenant','wechat_channels',[{'job_id':'job','post_id':'post-1'}],
                expected_account_id=web._identity_digest('wechat_channels','bound-hotel','websha256:'))
            assert result['status']=='synced',result
            assert result['items']['job']['views']==82
            assert result['list_complete'] and result['record_count']==1
            assert editor.url=='about:blank' and len(context.pages)==1
            assert session['authenticated'] and session['session_saved']
        finally:browser.close()


def test_metrics_read_tab_rejects_other_account_without_changing_saved_editor(monkeypatch):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
        try:
            context=browser.new_context();editor=context.new_page()
            context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html',body='''<meta charset="UTF-8"><body>视频号ID 内容管理
                <script>localStorage.setItem('finder_username','other-account')</script></body>'''))
            monkeypatch.setattr(web,'_ensure_open',lambda *args:None)
            monkeypatch.setattr(web,'_save_session',lambda *args:True)
            monkeypatch.setattr(web,'_get_session',lambda *args:{'context':context,'page':editor})
            result=web.read_work_metrics.__wrapped__('tenant','wechat_channels',[],expected_account_id='expected')
            assert result['identity_mismatch'] and not result['items']
            assert editor.url=='about:blank' and len(context.pages)==1
        finally:browser.close()
