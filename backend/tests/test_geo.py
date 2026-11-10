import uuid
from tests.conftest import create_test_user, create_test_company, auth_headers
from app.services import geo


def setup(db):
    user=create_test_user(db,email=str(uuid.uuid4())+'@example.com')
    company=create_test_company(db,user,slug='workspace-'+uuid.uuid4().hex[:10])
    return user,company,auth_headers(user),f'/api/v1/companies/{company.id}/geo'


def content(name='安吉测试酒店'):
    return {'name':name,'description':'安吉真实企业服务介绍','region':'浙江 湖州 安吉','industry':'酒旅 住宿','services':'亲子客房 停车场','contact':'请通过酒店官方渠道咨询','confirmed':True}


def image_content(db,company,user):
    from app.models.asset import Asset
    ids=[]
    for i in range(3):
        a=Asset(company_id=company.id,uploaded_by=user.id,name=f'发布测试图{i}',original_filename=f'{i}.png',file_key=f'geo-test/{company.id}/{i}.png',asset_type='image',mime_type='image/png',file_size_bytes=100,processing_status='ready')
        db.add(a);db.flush();ids.append(str(a.id))
    db.commit()
    return {'cover_asset_id':ids[0],'gallery_asset_ids':ids[1:]}


def published(db,client,monkeypatch):
    monkeypatch.setattr(geo,'index_site',lambda *args:None)
    user,company,h,url=setup(db)
    r=client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':{**content(),**image_content(db,company,user)}})
    assert r.status_code==200,r.text
    slug='test-'+uuid.uuid4().hex[:12]
    r=client.post(url+'/publish',headers=h,json={'expected_revision':1,'slug':slug})
    assert r.status_code==200,r.text
    return user,company,h,url,slug,r.json()


def test_draft_private_and_cross_tenant_denied(db,client):
    u,c,h,url=setup(db)
    assert client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':content()}).status_code==200
    assert client.get('/shop/'+c.slug).status_code==404
    assert client.get('/api/v1/public/search?q=安吉').json()['total']==0
    other,oc,oh,_=setup(db)
    assert client.get(url,headers=oh).status_code==403
    assert client.get(url+'/metrics',headers=oh).status_code==403
    assert client.get('/api/v1/admin/geo',headers=h).status_code==403


def test_snapshot_search_withdraw(db,client,monkeypatch):
    u,c,h,url,slug,site=published(db,client,monkeypatch)
    response=client.get('/shop/'+slug)
    assert response.status_code==200 and '安吉测试酒店' in response.text
    assert 'application/ld+json' in response.text
    assert client.get('/api/v1/public/search?q=安吉亲子酒店').json()['total']==1
    assert client.get('/api/v1/public/search?q=安吉&region=北京').json()['total']==0
    assert client.get('/api/v1/public/search?q=不存在的服务').json()['total']==0
    assert client.put(url+'/draft',headers=h,json={'expected_revision':2,'content':content('修改后的名字')}).status_code==200
    assert '修改后的名字' not in client.get('/shop/'+slug).text
    assert client.post(url+'/publish',headers=h,json={'expected_revision':3,'slug':'another-slug'}).status_code==409
    assert client.post(url+'/withdraw',headers=h).status_code==200
    assert client.get('/shop/'+slug).status_code==404
    assert client.get('/api/v1/public/search?q=安吉').json()['total']==0
    assert slug not in client.get('/sitemap.xml').text


def test_duplicate_slug_and_admin_alias(db,client,monkeypatch):
    u,c,h,url,slug,site=published(db,client,monkeypatch)
    u2,c2,h2,url2=setup(db)
    client.put(url2+'/draft',headers=h2,json={'expected_revision':0,'content':{**content(),**image_content(db,c2,u2)}})
    assert client.post(url2+'/publish',headers=h2,json={'expected_revision':1,'slug':slug}).status_code==409
    admin=create_test_user(db,email='admin-'+uuid.uuid4().hex+'@example.com',is_platform_admin=True)
    ah=auth_headers(admin);new='renamed-'+uuid.uuid4().hex[:10]
    assert client.post('/api/v1/admin/geo/'+site['id']+'/change',headers=ah,json={'reason':'企业合法更名申请','slug':new}).status_code==200
    assert client.get('/shop/'+slug,follow_redirects=False).status_code==301
    assert client.get('/shop/'+slug,follow_redirects=False).headers['location']=='/shop/'+new
    assert client.post(url2+'/publish',headers=h2,json={'expected_revision':1,'slug':slug}).status_code==409
    assert client.post('/api/v1/admin/geo/'+site['id']+'/change',headers=ah,json={'reason':'资料存在争议处理','status':'blocked'}).status_code==200
    assert client.post(url+'/publish',headers=h,json={'expected_revision':4,'slug':new}).status_code==403


def test_events_dedupe_bots_selftest(db,client,monkeypatch):
    u,c,h,url,slug,site=published(db,client,monkeypatch)
    def emit(**kw):
        return client.post('/api/v1/public/geo/events',json={'event_id':str(uuid.uuid4()),'site_id':site['id'],'token':geo.event_token(site['id']),'kind':'view','visitor':'random-id',**kw},headers={'user-agent':'Test human browser'})
    eid=str(uuid.uuid4())
    assert emit(event_id=eid).status_code==202
    assert emit(event_id=eid).status_code==202
    assert emit(self_test=True).status_code==202
    assert client.post('/api/v1/public/geo/events',json={'event_id':str(uuid.uuid4()),'site_id':site['id'],'token':geo.event_token(site['id']),'kind':'view'},headers={'user-agent':'Googlebot'}).status_code==202
    result=client.get(url+'/metrics',headers=h).json()['metrics']
    assert result['counts']['view']==1
    assert result['bots']==1
    assert result['external_search']['status']=='not_connected'
    assert client.post('/api/v1/public/geo/events',json={'event_id':str(uuid.uuid4()),'site_id':str(uuid.uuid4()),'kind':'view'}).status_code==404


def test_stale_version_validation_xss(db,client,monkeypatch):
    u,c,h,url=setup(db)
    assert client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':{'name':'x'}}).status_code==200
    assert client.post(url+'/publish',headers=h,json={'expected_revision':1,'slug':'valid-slug'}).status_code==422
    assert client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':content()}).status_code==409
    assert client.put(url+'/draft',headers=h,json={'expected_revision':1,'content':{**content('<script>alert(1)</script>'),**image_content(db,c,u)}}).status_code==200
    monkeypatch.setattr(geo,'index_site',lambda *args:None)
    assert client.post(url+'/publish',headers=h,json={'expected_revision':2,'slug':'safe-page'}).status_code==200
    assert '<script>alert(1)</script>' not in client.get('/shop/safe-page').text
    assert client.get(url+'/preview',headers=h).headers.get('cache-control')=='no-store'


def test_template_snapshot_and_media_privacy(db,client,monkeypatch):
    from app.models.geo import GeoTemplate
    db.add(GeoTemplate(code='generic',name='通用',revision=1,config={'intro':'原始介绍','services':'服务','faq':'问答','accent':'#123456'}));db.commit()
    u,c,h,url,slug,site=published(db,client,monkeypatch)
    row=db.get(GeoTemplate,'generic');row.config={'intro':'已改模板'};row.revision=2;db.commit()
    assert '原始介绍' in client.get('/shop/'+slug).text
    assert '已改模板' not in client.get('/shop/'+slug).text
    assert client.get('/shop/'+slug+'/media/'+str(uuid.uuid4())).status_code==404


def test_public_pages(client):
    assert client.get('/').status_code==200
    assert '发现企业与服务' in client.get('/').text
    assert client.get('/search').headers['x-robots-tag']=='noindex,follow'
    assert 'Sitemap:' in client.get('/robots.txt').text
    assert '<urlset' in client.get('/sitemap.xml').text


def test_facts_module_checks_feedback_and_admin_totals(db,client,monkeypatch):
    u,c,h,url=setup(db)
    d=content();d.update(image_content(db,c,u));d.update(facts=[{'key':'营业时间','value':'9:00—18:00','source':'企业确认','status':'pending'}],show_services=False,brand_color='#123456')
    assert client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':d}).status_code==200
    assert client.post(url+'/publish',headers=h,json={'expected_revision':1,'slug':'fact-example'}).status_code==422
    d['facts'][0]['status']='confirmed';d['facts'][0]['valid_until']='2000-01-01'
    assert client.put(url+'/draft',headers=h,json={'expected_revision':1,'content':d}).status_code==200
    assert client.post(url+'/publish',headers=h,json={'expected_revision':2,'slug':'fact-example'}).status_code==422
    d['facts'][0]['valid_until']=None
    assert client.put(url+'/draft',headers=h,json={'expected_revision':2,'content':d}).status_code==200
    monkeypatch.setattr(geo,'index_site',lambda *a:None)
    response=client.post(url+'/publish',headers=h,json={'expected_revision':3,'slug':'fact-example'})
    assert response.status_code==200,response.text
    site_id=response.json()['id']
    assert all(i['passed'] for i in response.json()['check_result']['items'])
    html=client.get('/shop/fact-example').text
    assert '#123456' in html and '9:00—18:00' in html and '亲子客房' not in html
    assert client.get('/shop/fact-example/services').status_code==404
    assert client.get('/api/v1/public/search?q=亲子客房').json()['total']==0
    assert client.post('/api/v1/public/geo/feedback',json={'site_id':site_id,'message':'营业时间可能有误，请核实官方最新公布时间'}).status_code==202
    assert client.get('/api/v1/admin/geo-feedback',headers=h).status_code==403
    u.is_platform_admin=True;db.commit()
    feedback=client.get('/api/v1/admin/geo-feedback',headers=h).json()['items'][0]
    assert client.post('/api/v1/admin/geo-feedback/'+feedback['id']+'/resolve',headers=h,json={'resolution':'已联系企业核实并提醒更正'}).status_code==200
    for sid in (site_id,None):
        assert client.post('/api/v1/public/geo/events',json={'event_id':str(uuid.uuid4()),'site_id':sid,'token':geo.event_token(sid),'kind':'view','visitor':'test-visitor'}).status_code==202
    own=client.get(url+'/metrics',headers=h).json()['metrics']
    admin=client.get('/api/v1/admin/geo',headers=h).json()
    assert own['counts']['view']==admin['items'][0]['metrics']['counts']['view']==1
    assert admin['metrics']['counts']['view']==2
    assert admin['homepage_metrics']['counts']['view']==1
    assert client.get(url+'/slug-availability?slug=fact-example',headers=h).json()['locked']
