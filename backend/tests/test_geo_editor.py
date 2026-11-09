import json
from tests.test_geo import setup, content
from app.services import geo
from app.models.geo import GeoTemplate
from app.providers.llm.openai_provider import OpenAIProvider


def test_structured_publish_search_llms_and_clear(db,client,monkeypatch):
    _,company,h,url=setup(db)
    monkeypatch.setattr(geo,'index_site',lambda *args:None)
    d=content();d.update(service_items=[{'name':'定制体验','description':'仅接受事先咨询预约'}],faq_items=[{'question':'如何预约？','answer':'请通过官方渠道咨询。'}])
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
    assert {'generic','travel','custom'}<={i['code'] for i in t}
    d=content();d['template']='travel';d['service_items']=[{'name':'<script>x</script>','description':'实际服务'}]
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
