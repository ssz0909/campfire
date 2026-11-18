"""User-facing notices and clip retry status, exercised with real Vue rendering."""
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect
from app.core.security import create_refresh_token
from tests.conftest import create_test_company, create_test_user


def test_notices_remain_admin_only_and_clip_failure_clears(client, db):
    user = create_test_user(db)
    company = create_test_company(db, user)
    user.is_platform_admin = True
    db.commit()
    root = Path(__file__).resolve().parents[2] / 'frontend/dist'
    source = {'id': '11111111-1111-4111-8111-111111111111', 'name': '状态验收图片',
              'asset_type': 'image', 'processing_status': 'ready', 'file_size_bytes': 10,
              'tags': [], 'metadata': {'vision_analysis': {'status': 'skipped',
                  'detail': '未配置完整的视觉模型参数，已保留原素材'}},
              'created_at': '2026-11-18T00:00:00Z'}
    jobs = [{'id': 'old', 'status': 'failed', 'error': '旧的生成错误'}]
    notices = ['暂无外部搜索数据；管理员可在站长工具中配置Google或Bing自动同步，或导入渠道报表。',
               '未配置联网检索监测渠道，暂无引用样本',
               '联系点击不等于实际咨询；尚未接入客服或咨询表单']
    metrics = {'counts': {}, 'sources': {}, 'trend': [], 'definition': '统计口径',
               'timezone': 'Asia/Shanghai', 'updated_at': '2026-11-18T00:00:00Z',
               **{key: {'message': value, 'items': []} for key, value in
                  zip(['external_search', 'model_citations', 'consultations'], notices)}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        context.add_init_script('localStorage.setItem("refresh_token",' + json.dumps(create_refresh_token({'sub': str(user.id)})) + ');localStorage.setItem("currentCompanyId",' + json.dumps(str(company.id)) + ')')

        def route(r):
            path = urlparse(r.request.url).path
            if path in ('/dashboard', '/assets', '/assets/', '/admin', '/login'):
                r.fulfill(body=(root / 'index.html').read_bytes(), content_type='text/html')
            elif path.startswith('/assets/'):
                f = root / path.lstrip('/')
                r.fulfill(status=200 if f.is_file() else 404, body=f.read_bytes() if f.is_file() else b'', content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
            elif path.endswith('/geo/metrics'):
                r.fulfill(json={'site': {'status': 'draft'}, 'metrics': metrics})
            elif path == f'/api/v1/companies/{company.id}/assets':
                r.fulfill(json={'items': [source], 'total': 1})
            elif path.endswith('/clips'):
                r.fulfill(json={'source': source, 'items': [], 'total': 0, 'jobs': jobs})
            else:
                response = client.request(r.request.method, r.request.url, content=r.request.post_data_buffer, headers=r.request.headers)
                r.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))

        context.route('**/*', route)
        page = context.new_page()
        page.goto('https://campfire.dawoai.com/dashboard')
        expect(page.locator('.geo-metrics .numbers')).to_be_visible()
        for notice in notices:
            expect(page.get_by_text(notice, exact=True)).to_have_count(0)
        page.goto('https://campfire.dawoai.com/admin')
        page.get_by_role('button', name='GEO运营数据', exact=True).click()
        for notice in notices:
            expect(page.get_by_text(notice, exact=True)).to_be_visible()
        page.goto('https://campfire.dawoai.com/assets/')
        expect(page.get_by_role('button', name='查看分镜视频')).to_be_visible()
        expect(page.get_by_text('.env', exact=False)).to_have_count(0)
        expect(page.get_by_text('未配置视觉能力', exact=False)).to_have_count(0)
        expect(page.get_by_text('未配置完整的视觉模型参数', exact=False)).to_have_count(0)
        expect(page.get_by_text('图片暂未完成识别，可重新识别或手动编辑标签。', exact=True)).to_be_visible()
        page.get_by_role('button', name='查看分镜视频').click()
        expect(page.get_by_text('分镜生成失败：旧的生成错误', exact=True)).to_be_visible()
        jobs.insert(0, {'id': 'new', 'status': 'generating_shots'})
        page.locator('.clips-modal__footer').get_by_role('button', name='刷新', exact=True).click()
        expect(page.get_by_text('分镜生成中，完成后会显示在这里。', exact=True)).to_be_visible()
        expect(page.locator('.clips-modal .asset-card__error')).to_have_count(0)
        jobs[0]['status'] = 'pending_review'
        page.locator('.clips-modal__footer').get_by_role('button', name='刷新', exact=True).click()
        expect(page.get_by_text('分镜生成中，完成后会显示在这里。', exact=True)).to_have_count(0)
        expect(page.locator('.clips-modal .asset-card__error')).to_have_count(0)
        jobs[0].update(status='failed', error='新的生成错误')
        page.locator('.clips-modal__footer').get_by_role('button', name='刷新', exact=True).click()
        expect(page.get_by_text('分镜生成失败：新的生成错误', exact=True)).to_be_visible()
        expect(page.get_by_text('分镜生成失败：旧的生成错误', exact=True)).to_have_count(0)
        browser.close()
