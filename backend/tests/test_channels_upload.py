"""Exercise the Channels dashboard boot and editor against browser DOM fixtures."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
from app.connectors import web_platform as web

EDITOR = '''
<input type="file" accept="image/*" id="cover">
<input type="file" accept="video/mp4,video/x-m4v,video/*" id="video" hidden>
<div class="input-editor" contenteditable></div>
<input placeholder="填写短标题有机会获得更多流量">
<input placeholder="有趣的合集标题更容易吸引粉丝" hidden>
<textarea hidden id="product">original product links</textarea>
<button onclick="window.submitted=true">发表</button>
'''


def test_channels_dashboard_boot_and_copy():
    with sync_playwright() as p, TemporaryDirectory() as directory:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            page = browser.new_page()
            def dashboard(route):
                assert route.request.url == 'https://channels.weixin.qq.com/platform'
                route.fulfill(content_type='text/html; charset=utf-8', body='<button id="entry">发表视频</button>')
            page.route('**/*', dashboard)
            # Only the dashboard button initializes the editor, like the live app.
            page.add_init_script('document.addEventListener("click", e => {if (e.target.id === "entry") document.body.innerHTML = ' + json.dumps(EDITOR) + ';})')
            upload = web._open_channels_upload(page)
            path = Path(directory) / 'video.mp4'
            path.write_bytes(b'test fixture, never sent to a platform')
            upload.set_input_files(str(path))
            assert page.locator('#video').evaluate('(e)=>e.files[0].name') == 'video.mp4'
            assert page.locator('#cover').evaluate('(e)=>e.files.length') == 0
            web._wait_video_editor(page)
            title = '雲中溪｜山景、泳池与池畔暖光 🏨 放慢节奏'
            web._fill_channels_copy(page, title, 'Come stay at our hotel')
            assert page.locator('.input-editor').inner_text() == title + '\nCome stay at our hotel'
            short = page.locator('input[placeholder*="短标题"]').input_value()
            assert '｜' not in short and '🏨' not in short and '、' not in short
            assert len(short.encode('utf-16-le')) <= 32
            assert page.locator('#product').input_value() == 'original product links'
            assert not page.evaluate('Boolean(window.submitted)')
            page.locator('body').evaluate('(e)=>e.insertAdjacentHTML("beforeend", "<div contenteditable></div>")')
            try:
                web._fill_channels_copy(page, title, 'description')
            except ValueError:
                pass
            else:
                raise AssertionError('Ambiguous editors must stop before publishing')
        finally:
            browser.close()


def test_channels_upload_failure_never_submits(monkeypatch, tmp_path):
    monkeypatch.setattr(web, '_ensure_open', lambda *args: None)
    monkeypatch.setattr(web, '_get_session', lambda *args: {'page': object()})
    monkeypatch.setattr(web, 'session_status', lambda *args: {'login_required': False})
    def fail(*args):
        raise ValueError('视频号编辑器未加载')
    def forbidden(*args):
        raise AssertionError('Must not submit after uploader failure')
    monkeypatch.setattr(web, '_open_channels_upload', fail)
    monkeypatch.setattr(web, '_publish_button', forbidden)
    result = web.publish.__wrapped__('test', 'wechat_channels', 'title', 'description', str(tmp_path/'file.mp4'))
    assert result['status'] == 'manual_required'
    assert result['metrics']['submission_uncertain'] is False
    assert result['metrics']['publish_stage'] == '打开视频号发表入口'


def test_channels_exact_hotel_location():
    hotel = '安吉雲中溪·汤泉度假酒店'
    provider_hotel = '安吉云中溪·汤泉度假酒店'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            page = browser.new_page()
            page.set_content('''<div class="post-position-wrap">
              <div class="position-display" onclick="document.querySelector('.location-filter-wrap').style.display='block'">
                <div class="place">上海市</div>
              </div>
              <div class="location-filter-wrap" style="display:none">
                <input placeholder="搜索附近位置">
                <button class="weui-desktop-search__btn">搜索</button>
              </div>
            </div><input placeholder="搜索附近位置" hidden>
            <button onclick="window.submitted=true">发表</button>''')
            page.evaluate('''(hotel) => {
              document.querySelector('.weui-desktop-search__btn').onclick = () => {
                const wrap = document.querySelector('.location-filter-wrap');
                for (const name of [hotel+'地上停车场', hotel+'停车场-出入口', hotel]) {
                  const option = document.createElement('div'); option.className='option-item';
                  const label = document.createElement('div'); label.className='name'; label.textContent=name;
                  option.append(label); wrap.append(option);
                  option.onclick = () => { document.querySelector('.place').textContent=name; wrap.style.display='none'; };
                }
              };
            }''', provider_hotel)
            page.locator('.position-display').click()
            web._select_channels_publish_location(page, hotel)
            assert page.locator('.position-display .place').inner_text() == provider_hotel
            assert not page.locator('.location-filter-wrap').is_visible()
            assert not page.evaluate('Boolean(window.submitted)')
            # Already selected is idempotent and does not reopen the picker.
            web._select_channels_publish_location(page, hotel)
            assert not page.locator('.location-filter-wrap').is_visible()
        finally:
            browser.close()


def test_channels_location_failure_never_submits(monkeypatch, tmp_path):
    from types import SimpleNamespace
    path = tmp_path/'file.mp4'
    path.write_bytes(b'offline')
    monkeypatch.setattr(web, '_ensure_open', lambda *args: None)
    monkeypatch.setattr(web, '_get_session', lambda *args: {'page': object()})
    monkeypatch.setattr(web, 'session_status', lambda *args: {'login_required': False})
    monkeypatch.setattr(web, '_open_channels_upload', lambda *args: SimpleNamespace(set_input_files=lambda *a, **kw: None))
    monkeypatch.setattr(web, '_wait_video_editor', lambda *args: None)
    monkeypatch.setattr(web, '_fill_channels_copy', lambda *args: None)
    monkeypatch.setattr(web, '_upload_channels_video', lambda *args: None)
    def fail(*args):
        raise ValueError('酒店地点无唯一全名匹配')
    def forbidden(*args):
        raise AssertionError('Must not submit with unconfirmed location')
    monkeypatch.setattr(web, '_select_channels_publish_location', fail)
    monkeypatch.setattr(web, '_publish_button', forbidden)
    result = web.publish.__wrapped__('test', 'wechat_channels', 'title', 'description', str(path), location_name='hotel')
    assert result['metrics'] == {'publish_stage': '选择地理位置', 'submission_uncertain': False}
    assert result['status'] == 'manual_required'


def test_channels_validation_and_success_are_distinct():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            page = browser.new_page()
            page.set_content('<div>短标题包含特殊字符，符号仅支持书名号</div><span hidden>发表成功</span>')
            try:
                web._wait_channels_publish_result(page)
            except ValueError as exc:
                assert '特殊字符' in str(exc)
            else:
                raise AssertionError('Hidden success must not override visible validation')
            page.set_content('<div hidden>短标题包含特殊字符</div><span>发表成功</span>')
            web._wait_channels_publish_result(page)
        finally:
            browser.close()


def test_channels_form_error_stops_before_submit(monkeypatch, tmp_path):
    from types import SimpleNamespace
    path = tmp_path/'file.mp4'
    path.write_bytes(b'offline')
    monkeypatch.setattr(web, '_ensure_open', lambda *args: None)
    monkeypatch.setattr(web, '_get_session', lambda *args: {'page': object()})
    monkeypatch.setattr(web, 'session_status', lambda *args: {'login_required': False})
    monkeypatch.setattr(web, '_open_channels_upload', lambda *args: SimpleNamespace(set_input_files=lambda *a, **kw: None))
    monkeypatch.setattr(web, '_wait_video_editor', lambda *args: None)
    monkeypatch.setattr(web, '_fill_channels_copy', lambda *args: None)
    monkeypatch.setattr(web, '_upload_channels_video', lambda *args: None)
    monkeypatch.setattr(web, '_channels_validation_messages', lambda *args: ['短标题包含特殊字符'])
    def forbidden(*args):
        raise AssertionError('Must not click publish with invalid Channels form')
    monkeypatch.setattr(web, '_publish_button', forbidden)
    result = web.publish.__wrapped__('test', 'wechat_channels', 'title', 'description', str(path))
    assert result['metrics']['submission_uncertain'] is False
    assert '短标题包含特殊字符' in result['message']


def test_channels_upload_waits_for_server_clip_not_form(monkeypatch):
    from types import SimpleNamespace
    events = []
    class Page:
        handler = None
        def on(self, event, handler): self.handler = handler
        def remove_listener(self, event, handler):
            assert handler == self.handler
            self.handler = None
        def get_by_text(self, *a, **kw):
            return SimpleNamespace(filter=lambda **kw: SimpleNamespace(count=lambda: 0))
        def wait_for_timeout(self, timeout):
            if events:
                body, endpoint = events.pop(0)
                self.handler(SimpleNamespace(url='https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/'+endpoint,
                                             status=201, json=lambda: body))
    page = Page()
    ready = []
    monkeypatch.setattr(web, '_wait_video_editor', lambda p: ready.append(True))
    def select(*args, **kw):
        events.extend([
            ({'errCode':0,'data':{'clipKey':'this-upload'}}, 'post_clip_video'),
            ({'errCode':0,'data':{'flag':2}}, 'post_clip_video_result'),
            ({'errCode':0,'data':{'flag':1,'url':'https://example.test/video','duration':30,'fileSize':'123'}}, 'post_clip_video_result')])
        assert not ready  # The editor exists but no server upload has finished.
    web._upload_channels_video(page, SimpleNamespace(set_input_files=select), 'file.mp4')
    assert ready == [True]
    assert not events and page.handler is None


def test_channels_upload_timeout_stops_before_post(monkeypatch):
    from types import SimpleNamespace
    calls = []
    page = SimpleNamespace(on=lambda *a: calls.append('listen'),remove_listener=lambda *a: calls.append('remove'))
    upload = SimpleNamespace(set_input_files=lambda *a, **kw: calls.append('file'))
    try:
        web._upload_channels_video(page, upload, 'file.mp4', timeout_seconds=0)
    except ValueError as exc:
        assert '未确认上传及转码完成' in str(exc)
    else:
        raise AssertionError('No successful clip result must block submission')
    assert calls == ['listen','file','remove']


def test_channels_success_captured_during_click_without_toast(monkeypatch):
    from types import SimpleNamespace
    class Page:
        handler = None
        def on(self, event, callback): self.handler = callback
        def remove_listener(self, event, callback):
            assert callback == self.handler
            self.handler = None
    page = Page()
    def click(**kwargs):
        # The success response arrives during click(), before a toast waiter
        # could be attached. Upload and draft endpoints must not be counted.
        prefix = 'https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/'
        page.handler(SimpleNamespace(url=prefix+'post_clip_video',status=201,json=lambda:{'errCode':0}))
        page.handler(SimpleNamespace(url=prefix+'post_create',status=201,
            request=SimpleNamespace(method='POST'),json=lambda:{'errCode':0,'data':{'objectId':'published-123'}}))
    result = web._submit_channels_video(page, SimpleNamespace(click=click), 'Hotel', 'Description')
    assert result == {'source':'web_create_response_verified','provider_post_id':'published-123'}
    assert page.handler is None


def test_channels_published_list_matches_current_content_and_time(monkeypatch):
    from types import SimpleNamespace
    class Page:
        handler = None
        def on(self, event, callback): self.handler = callback
        def remove_listener(self, *args): self.handler = None
    page=Page()
    def click(**kwargs):
        items=[{'objectId':'old','createTime':web.time.time()-3600,'status':1,'desc':{'description':'Hotel\nDescription'}},
               {'objectId':'draft','createTime':web.time.time(),'status':0,'desc':{'description':'Hotel\nDescription'}},
               {'objectId':'new','createTime':web.time.time(),'status':1,'desc':{'description':'Hotel\nDescription'}}]
        page.handler(SimpleNamespace(url='https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_list',status=201,json=lambda:{'errCode':0,'data':{'list':items}}))
    result=web._submit_channels_video(page,SimpleNamespace(click=click),'Hotel','Description')
    assert result['provider_post_id']=='new'
    assert result['source']=='web_post_list_verified'


def test_channels_rejected_create_is_not_success(monkeypatch):
    from types import SimpleNamespace
    class Page:
        handler=None
        def on(self,event,callback):self.handler=callback
        def remove_listener(self,*args):self.handler=None
    page=Page()
    def click(**kwargs):
        page.handler(SimpleNamespace(url='https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/post_create',status=201,request=SimpleNamespace(method='POST'),json=lambda:{'errCode':1001,'data':{}}))
    try:web._submit_channels_video(page,SimpleNamespace(click=click),'Hotel','Description')
    except ValueError as exc:assert '接口返回失败' in str(exc)
    else:raise AssertionError('Rejected create cannot be published')
    assert page.handler is None
