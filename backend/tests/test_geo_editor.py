import json
from tests.test_geo import setup, content, image_content
from app.services import geo
from app.models.geo import GeoTemplate
from app.providers.llm.openai_provider import OpenAIProvider


def test_structured_publish_search_llms_and_clear(db,client,monkeypatch):
    user,company,h,url=setup(db)
    monkeypatch.setattr(geo,'index_site',lambda *args:None)
    d=content();d.update(image_content(db,company,user));d.update(service_items=[{'name':'定制体验','description':'仅接受事先咨询预约'}],faq_items=[{'question':'如何预约？','answer':'请通过官方渠道咨询。'}])
    r=client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':d})
    assert r.status_code==200,r.text
    assert r.json()['draft']['services']=='定制体验：仅接受事先咨询预约'
    slug='editor-'+str(company.id)[:10]
    assert client.post(url+'/publish',headers=h,json={'expected_revision':1,'slug':slug}).status_code==200
    public=client.get('/shop/'+slug).text
    assert '<h3>定制体验</h3>' in public and '<h3>如何预约？</h3>' in public
    assert '定制体验' in client.get('/shop/'+slug+'/llms.txt').text
    assert client.get('/api/v1/public/search?q=定制体验').json()['total']==1
    d.update(service_items=[],faq_items=[])
    r=client.put(url+'/draft',headers=h,json={'expected_revision':2,'content':d})
    assert r.json()['draft']['services']=='' and r.json()['draft']['faq']==''
    assert client.post(url+'/publish',headers=h,json={'expected_revision':3,'slug':slug}).status_code==200
    assert client.get('/shop/'+slug+'/services').status_code==404
    assert client.get('/shop/'+slug+'/faq').status_code==404


def test_preview_does_not_save_and_templates_remain_available(db,client):
    _,_,h,url=setup(db)
    db.add(GeoTemplate(code='custom',name='自定义',revision=1,config={'intro':'特别介绍'}));db.commit()
    t=client.get(url,headers=h).json()['templates']
    assert {'generic','scenic','custom'}<={i['code'] for i in t}
    d=content();d['template']='scenic';d['service_items']=[{'name':'<script>x</script>','description':'实际服务'}]
    r=client.post(url+'/preview',headers=h,json=d)
    assert r.status_code==200,r.text
    assert r.headers['cache-control']=='no-store' and 'noindex,nofollow' in r.text
    assert '&lt;script&gt;x&lt;/script&gt;' in r.text and '<script>x</script>' not in r.text
    assert client.get(url,headers=h).json()['revision']==0
    assert client.get(url,headers=h).json()['draft']=={}
    _,_,oh,_=setup(db)
    assert client.post(url+'/preview',headers=oh,json=d).status_code==403
    assert client.post(url+'/ai-draft',headers=oh,json=d).status_code==403


def test_ai_suggestions_only_and_grounding(db,client,monkeypatch):
    from app.services import geo_writing
    _,_,h,url=setup(db)
    monkeypatch.setattr(geo,'public_limit',lambda *a:None)
    monkeypatch.setattr(geo_writing,'get_llm_settings',lambda db:{'api_key':'test','base_url':'https://test.invalid/v1','model':'test'})
    calls=[]
    async def complete(self,messages,**kw):
        calls.append(messages)
        return {'content':json.dumps({'description':'真实企业介绍','service_items':[{'name':'预约服务','description':'仅限预约'}],'faq_items':[{'question':'如何咨询？','answer':'通过官方渠道'}]}),'finish_reason':'stop'}
    monkeypatch.setattr(OpenAIProvider,'complete',complete)
    r=client.post(url+'/ai-draft',headers=h,json=content())
    assert r.status_code==200,r.text
    assert r.json()['service_items'][0]['name']=='预约服务'
    assert 'services' in json.loads(calls[0][1]['content'])
    assert '禁止推测' in calls[0][0]['content']
    assert client.get(url,headers=h).json()['draft']=={}
    assert client.post(url+'/ai-draft',headers=h,json={'name':'只有名称'}).status_code==422
    async def broken(self,*a,**kw):return {'content':'<html>bad</html>'}
    monkeypatch.setattr(OpenAIProvider,'complete',broken)
    assert client.post(url+'/ai-draft',headers=h,json=content()).status_code==502
    async def timeout(self,*a,**kw):raise TimeoutError()
    monkeypatch.setattr(OpenAIProvider,'complete',timeout)
    assert client.post(url+'/ai-draft',headers=h,json=content()).status_code==504


def test_legacy_and_new_validation(db,client):
    _,_,h,url=setup(db)
    d=content();d['faq']='旧问答大段内容\n保持原文'
    r=client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':d})
    assert r.json()['draft']['faq']==d['faq']
    d.update(service_items=[{'name':'','description':'缺名称'}])
    assert client.put(url+'/draft',headers=h,json={'expected_revision':1,'content':d}).status_code==422
    d.update(service_items=[{'name':'名称','description':'字'*4000}]*2)
    assert client.put(url+'/draft',headers=h,json={'expected_revision':1,'content':d}).status_code==422


def test_legacy_maximum_length_can_be_migrated(db,client):
    _,_,h,url=setup(db)
    d=content();d['services']='字'*6000;d['faq']='答'*6000
    d['service_items']=[{'name':'产品与服务','description':d['services']}]
    d['faq_items']=[{'question':'常见问题与回答','answer':d['faq']}]
    r=client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':d})
    assert r.status_code==200,r.text
    assert r.json()['draft']['services']==d['services']
    assert r.json()['draft']['faq']==d['faq']


def test_three_image_layouts_privacy_and_snapshot(db,client,monkeypatch,tmp_path):
    from app.models.asset import Asset
    from app.config import settings
    from PIL import Image
    user,company,h,url=setup(db)
    monkeypatch.setattr(settings,'LOCAL_STORAGE_PATH',str(tmp_path))
    monkeypatch.setattr(geo,'index_site',lambda *a:None)
    ids=[]
    for i in range(4):
        Image.new('RGB',(300,200),(30+i*30,100,80)).save(tmp_path/f'{i}.png')
        a=Asset(company_id=company.id,uploaded_by=user.id,name=f'图{i}',original_filename=f'{i}.png',file_key=f'{i}.png',file_url=f'/files/{i}.png',asset_type='image',mime_type='image/png',file_size_bytes=100,processing_status='ready')
        db.add(a);db.flush();ids.append(str(a.id))
    db.commit()
    d=content();d.update(cover_asset_id=ids[0],gallery_asset_ids=ids[1:3],template='gallery')
    for code,layout in [('generic','classic'),('scenic','scenic'),('gallery','editorial'),('poster','poster')]:
        d['template']=code
        r=client.post(url+'/preview',headers=h,json=d)
        assert r.status_code==200,r.text
        assert 'class="layout-'+layout+'"' in r.text
        assert r.text.count('<img ')==3
        assert '发现企业' not in r.text and '登录工作台' not in r.text and '企业服务</a>' not in r.text
        assert '主页技术支持' in r.text
    assert client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':d}).status_code==200
    slug='images-'+str(company.id)[:10]
    assert client.post(url+'/publish',headers=h,json={'expected_revision':1,'slug':slug}).status_code==200
    assert client.get('/shop/'+slug+'/media/'+ids[1]).status_code==200
    assert client.get('/shop/'+slug+'/media/'+ids[3]).status_code==404
    # A fourth image is accepted; it is only made public after publishing.
    d['gallery_asset_ids']=ids[1:]
    assert client.put(url+'/draft',headers=h,json={'expected_revision':2,'content':d}).status_code==200
    assert client.get('/shop/'+slug+'/media/'+ids[3]).status_code==404
    assert client.post(url+'/publish',headers=h,json={'expected_revision':3,'slug':slug}).status_code==200
    html=client.get('/shop/'+slug).text
    assert html.count('<img ')==4
    import re
    assert re.search(r'id="description".*?data-gallery-slot="1".*?</section>',html)
    assert re.search(r'id="services".*?data-gallery-slot="2".*?</section>',html)
    assert re.search(r'class="visual-story"[^>]*>.*?data-gallery-slot="3"',html)
    assert client.get('/shop/'+slug+'/media/'+ids[3]).status_code==200
    # Four supplementary images exceed the limit.
    bad={**d,'gallery_asset_ids':ids}
    assert client.put(url+'/draft',headers=h,json={'expected_revision':4,'content':bad}).status_code==422
    # A private draft change does not expose its image until publishing.
    d['gallery_asset_ids']=[ids[3]]
    assert client.put(url+'/draft',headers=h,json={'expected_revision':4,'content':d}).status_code==200
    assert client.get('/shop/'+slug+'/media/'+ids[1]).status_code==200
    _,_,otherh,otherurl=setup(db)
    assert client.post(otherurl+'/preview',headers=otherh,json=d).status_code==422
    assert client.put(otherurl+'/draft',headers=otherh,json={'expected_revision':0,'content':d}).status_code==422
    assert client.post(url+'/withdraw',headers=h).status_code==200
    assert client.get('/shop/'+slug+'/media/'+ids[1]).status_code==404


def test_admin_add_layout_template(db,client):
    user,_,h,url=setup(db)
    user.is_platform_admin=True;db.commit()
    r=client.put('/api/v1/admin/geo-templates/new-style',headers=h,json={'name':'新风格','layout':'editorial','expected_revision':0})
    assert r.status_code==200,r.text
    templates=client.get(url,headers=h).json()['templates']
    assert next(t for t in templates if t['code']=='new-style')['config']['layout']=='editorial'
    d=content();d['template']='new-style'
    assert 'layout-editorial' in client.post(url+'/preview',headers=h,json=d).text
    assert client.put('/api/v1/admin/geo-templates/invalid-layout',headers=h,json={'name':'无效','layout':'arbitrary-html'}).status_code==422


def test_retired_industry_template_compatibility(db,client,monkeypatch):
    from app.models.geo import GeoSite
    user,company,h,url=setup(db)
    old={'intro':'目的地与体验','services':'住宿与游览服务','faq':'出行问答','layout':'scenic'}
    db.add(GeoTemplate(code='travel',name='酒旅',revision=1,config=old))
    site=GeoSite(company_id=company.id,draft={**content(),'template':'travel'},live={**content(),'template':'travel','template_snapshot':{'code':'travel','config':old}},status='draft')
    db.add(site);db.commit()
    r=client.get(url,headers=h).json()
    assert 'travel' not in [t['code'] for t in r['templates']]
    assert r['draft']['template']=='scenic'
    assert db.get(GeoSite,site.id).live['template_snapshot']['config']==old
    assert geo.template_snapshot(db,'travel')['code']=='scenic'
    d=content();d['template']='travel'
    r=client.post(url+'/preview',headers=h,json=d)
    assert r.status_code==200 and 'layout-scenic' in r.text and '目的地与体验' not in r.text
    assert client.put(url+'/draft',headers=h,json={'expected_revision':site.revision,'content':d}).json()['draft']['template']=='scenic'
    user.is_platform_admin=True;db.commit()
    templates=client.get('/api/v1/admin/geo',headers=h).json()['templates']
    assert 'travel' not in [t['code'] for t in templates]
    assert client.put('/api/v1/admin/geo-templates/travel',headers=h,json={'name':'酒旅'}).status_code==422


def test_full_framework_preview_never_persists_placeholders(db,client,monkeypatch):
    user,company,h,url=setup(db)
    monkeypatch.setattr(geo,'index_site',lambda *a:None)
    for code in ['generic','scenic','gallery','poster']:
        r=client.post(url+'/preview',headers=h,json={'template':code})
        assert r.status_code==200,r.text
        for marker in ['公开封面位置','补充图片 1 位置','补充图片 2 位置','补充图片 3 位置','id="description"','id="services"','id="faq"','id="contact"','未填写 · 位置示意']:
            assert marker in r.text,marker
    assert client.get(url,headers=h).json()['draft']=={}
    d=content();d['show_faq']=False
    assert 'id="faq"' not in client.post(url+'/preview',headers=h,json=d).text
    # Drafts can be saved without images; publication enforces three distinct images.
    assert client.put(url+'/draft',headers=h,json={'expected_revision':0,'content':d}).status_code==200
    r=client.post(url+'/publish',headers=h,json={'expected_revision':1,'slug':'framework-test'})
    assert r.status_code==422 and '公开封面' in r.text and '补充展示图片' in r.text
    images=image_content(db,company,user);d.update(images)
    d['gallery_asset_ids']=[d['cover_asset_id'],d['gallery_asset_ids'][0]]
    assert client.put(url+'/draft',headers=h,json={'expected_revision':1,'content':d}).status_code==200
    assert client.post(url+'/publish',headers=h,json={'expected_revision':2,'slug':'framework-test'}).status_code==422
    d.update(images)
    assert client.put(url+'/draft',headers=h,json={'expected_revision':2,'content':d}).status_code==200
    assert client.post(url+'/publish',headers=h,json={'expected_revision':3,'slug':'framework-test'}).status_code==200
    public=client.get('/shop/framework-test').text
    assert '位置示意' not in public and '公开封面位置' not in public
