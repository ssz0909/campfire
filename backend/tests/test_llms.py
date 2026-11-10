import uuid

from app.models.company import Company
from app.models.geo import GeoSite, GeoSlug
from tests.conftest import auth_headers
from tests.test_geo import content, published, setup


def test_llms_live_lifecycle_and_alias(db, client, monkeypatch):
    user, company, headers, url, slug, site = published(db, client, monkeypatch)
    text = client.get('/llms.txt')
    assert text.status_code == 200
    assert text.headers['content-type'] == 'text/plain; charset=utf-8'
    assert text.headers['cache-control'] == 'no-store'
    assert f'https://campfire.dawoai.com/shop/{slug}' in text.text
    assert '安吉测试酒店' in text.text
    assert client.head('/llms.txt').status_code == 200
    document = client.get(f'/shop/{slug}/llms.txt')
    assert document.status_code == 200
    assert '亲子客房 停车场' in document.text
    assert '请通过酒店官方渠道咨询' in document.text
    assert 'application/ld+json' not in document.text
    changed = {**site['live'],'name':'更新后企业'}
    assert client.put(url+'/draft', headers=headers, json={'expected_revision': 2, 'content': changed}).status_code == 200
    assert '更新后企业' not in client.get('/llms.txt').text
    assert '更新后企业' not in client.get(f'/shop/{slug}/llms.txt').text
    assert client.post(url+'/publish', headers=headers, json={'expected_revision': 3, 'slug': slug}).status_code == 200
    assert '更新后企业' in client.get('/llms.txt').text
    assert '更新后企业' in client.get(f'/shop/{slug}/llms.txt').text
    user.is_platform_admin = True
    db.commit()
    new_slug = 'renamed-'+uuid.uuid4().hex[:10]
    assert client.post('/api/v1/admin/geo/'+site['id']+'/change', headers=headers,
                       json={'reason': '企业更名更新网址', 'slug': new_slug}).status_code == 200
    assert '/shop/'+slug not in client.get('/llms.txt').text
    redirect = client.get(f'/shop/{slug}/llms.txt', follow_redirects=False)
    assert redirect.status_code == 301
    assert redirect.headers['location'] == f'/shop/{new_slug}/llms.txt'
    assert client.post(url+'/withdraw', headers=headers).status_code == 200
    assert '更新后企业' not in client.get('/llms.txt').text
    assert client.get(f'/shop/{new_slug}/llms.txt').status_code == 404
    assert client.post(url+'/publish', headers=headers, json={'expected_revision': 6, 'slug': new_slug}).status_code == 200
    assert client.post('/api/v1/admin/geo/'+site['id']+'/change', headers=headers,
                       json={'reason': '争议信息暂停公开', 'status': 'blocked'}).status_code == 200
    assert new_slug not in client.get('/llms.txt').text
    assert client.get(f'/shop/{new_slug}/llms.txt').status_code == 404


def test_llms_public_boundary_and_markdown(db, client, monkeypatch):
    user, company, headers, url, slug, result = published(db, client, monkeypatch)
    private = 'DO_NOT_EXPOSE_PRIVATE_COMPANY_PROFILE'
    company.description = private
    site = db.get(GeoSite, uuid.UUID(result['id']))
    site.draft = {'name': 'DO_NOT_EXPOSE_DRAFT'}
    d = dict(site.live)
    d.update(name='品牌](https://evil.example)\n## 假标题',
             description='<script>alert(1)</script>\n[伪链接](https://evil.example)',
             show_services=False, show_faq=False, services='DO_NOT_EXPOSE_HIDDEN_SERVICE', faq='DO_NOT_EXPOSE_HIDDEN_FAQ',
             facts=[{'key': '旧活动', 'value': 'DO_NOT_EXPOSE_EXPIRED_VALUE', 'source': '企业活动表', 'status': 'confirmed', 'valid_until': '2000-01-01'},
                    {'key': '未经确认', 'value': 'DO_NOT_EXPOSE_PENDING_FACT', 'source': '未知', 'status': 'pending'}])
    site.live = d
    db.commit()
    for path in ['/llms.txt', '/shop/'+slug+'/llms.txt']:
        text = client.get(path).text
        assert 'DO_NOT_EXPOSE' not in text
        assert '<script>' not in text
        assert '\n## 假标题' not in text
        assert '](https://evil.example)' not in text
    assert '资料已过期' in client.get('/shop/'+slug+'/llms.txt').text
    for field in ['is_active', 'is_deleted']:
        setattr(company, field, field == 'is_deleted')
        db.commit()
        assert slug not in client.get('/llms.txt').text
        assert client.get('/shop/'+slug+'/llms.txt').status_code == 404
        setattr(company, field, field == 'is_active')
        db.commit()


def test_llms_bounded_directory_and_empty_state(db, client):
    empty = client.get('/llms.txt')
    assert empty.status_code == 200
    assert '暂无已发布的企业主页' in empty.text
    assert '/login' not in empty.text
    user, _, _, _ = setup(db)
    for i in range(101):
        company = Company(owner_id=user.id, name=f'目录企业{i:03}', slug=f'directory-{i:03}', is_active=True)
        db.add(company)
        db.flush()
        site = GeoSite(company_id=company.id, slug=f'directory-{i:03}', status='published',
                       live={'name': f'目录企业{i:03}', 'description': '企业确认的公开介绍'})
        db.add(site)
        db.flush()
        db.add(GeoSlug(slug=site.slug, site_id=site.id))
    db.commit()
    root = client.get('/llms.txt').text
    assert '当前公开企业 101 家' in root
    assert '目录企业000' in root and '目录企业099' in root and '目录企业100' not in root
    assert 'https://campfire.dawoai.com/llms/companies/2.txt' in root
    page2 = client.get('/llms/companies/2.txt')
    assert page2.status_code == 200
    assert '目录企业100' in page2.text and '目录企业099' not in page2.text
    assert 'https://campfire.dawoai.com/llms.txt' in page2.text
    assert client.get('/llms/companies/1.txt').status_code == 200
    assert client.get('/llms/companies/0.txt').status_code == 404
    assert client.get('/llms/companies/3.txt').status_code == 404
    assert client.get('/shop/unknown/llms.txt').status_code == 404
