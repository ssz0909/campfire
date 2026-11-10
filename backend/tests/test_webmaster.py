"""No external account or paid model calls; exercise trust boundaries and sync retries."""
import json
import uuid
from datetime import date,timedelta
import pytest
import httpx
from tests.test_geo import setup,published
from app.services import webmaster as w
from app.models.geo import GeoSearchDaily,GeoSlug
from app.connectors.hotel.models import PlatformKeyValue


def admin(db):
    user,company,h,url=setup(db);user.is_platform_admin=True;db.commit()
    return user,company,h,url


def test_admin_only_and_verification_head_without_scripts(db,client):
    _,_,h,_=setup(db)
    assert client.get('/api/v1/admin/webmaster',headers=h).status_code==403
    _,_,ah,_=admin(db)
    for p,meta in [('google','google-site-verification'),('bing','msvalidate.01'),('baidu','baidu-site-verification')]:
        r=client.put('/api/v1/admin/webmaster/'+p,headers=ah,json={'verification_token':f'<meta name="{meta}" content="test_{p}-123">'})
        assert r.status_code==200,r.text
        assert next(i for i in r.json()['items'] if i['provider']==p)['verification_status']=='configured_not_verified'
        home=client.get('/').text
        assert f'<meta name="{meta}" content="test_{p}-123">' in home.split('</head>')[0]
    assert client.put('/api/v1/admin/webmaster/bing',headers=ah,json={'verification_token':'"><script>alert(1)</script>'}).status_code==422
    assert 'alert(1)' not in client.get('/').text
    assert client.put('/api/v1/admin/webmaster/google',headers=ah,json={'property':'https://evil.example/'}).status_code==422
    assert client.put('/api/v1/admin/webmaster/baidu',headers=ah,json={'auto_sync':True}).status_code==422


def service_credentials():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption
    return {'type':'service_account','client_email':'collector@project.iam.gserviceaccount.com',
            'private_key':rsa.generate_private_key(public_exponent=65537,key_size=2048).private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()).decode()}


def test_credentials_encrypted_masked_and_queue(db,client):
    _,_,h,_=admin(db);credentials=service_credentials()
    r=client.put('/api/v1/admin/webmaster/google',headers=h,json={'service_account_json':json.dumps(credentials),'auto_sync':True})
    assert r.status_code==200,r.text
    assert 'PRIVATE KEY' not in r.text and 'private_key' not in r.text
    stored=db.get(PlatformKeyValue,w.KEY+'config.google').encrypted_value
    assert credentials['client_email'] not in stored and 'PRIVATE KEY' not in stored
    assert client.put('/api/v1/admin/webmaster/google',headers=h,json={'service_account_json':''}).status_code==200
    assert w.config(db,'google')['service_account']==credentials
    assert client.post('/api/v1/admin/webmaster/google/sync',headers=h).status_code==202
    first=w.state(db,'google')
    assert client.post('/api/v1/admin/webmaster/google/sync',headers=h).status_code==202
    assert w.state(db,'google')==first
    assert client.put('/api/v1/admin/webmaster/google',headers=h,json={'clear_credentials':True}).status_code==200
    assert not w.config(db,'google')['service_account']
    assert client.post('/api/v1/admin/webmaster/google/sync',headers=h).status_code==422


def test_import_attribution_idempotence_alias_and_tenant_isolation(db,client,monkeypatch):
    _,company,h,url,slug,site=published(db,client,monkeypatch)
    _,_,ah,_=admin(db)
    day=date.today().isoformat()
    db.add(GeoSlug(slug='historic-slug',site_id=uuid.UUID(site['id'])));db.commit()
    body=f'day,page,clicks,impressions,position\n{day},{w.ORIGIN}/shop/{slug},3,30,2\n{day},{w.ORIGIN}/shop/historic-slug/services,1,10,4\n{day},{w.ORIGIN}/,2,20,\n'
    def upload(data=body):return client.post('/api/v1/admin/webmaster/baidu/import',headers=ah,files={'file':('report.csv',data.encode('utf-8-sig'),'text/csv')},data={'source_name':'百度搜索表现真实导出','confirmed':'true'})
    assert upload().status_code==200
    assert upload().json()['matched_enterprise_rows']==2
    assert db.query(GeoSearchDaily).filter_by(provider='baidu').count()==3
    stats=client.get(url+'/metrics',headers=h).json()['metrics']['external_search']
    assert stats['items'][0]['clicks']==4 and stats['items'][0]['impressions']==40
    _,_,otherh,otherurl=setup(db)
    assert client.get(url+'/metrics',headers=otherh).status_code==403
    assert client.get(otherurl+'/metrics',headers=otherh).json()['metrics'] is None
    counts=db.query(GeoSearchDaily).count()
    bad=body+f'{day},https://evil.example/shop/test,1,2,\n'
    assert upload(bad).status_code==422
    assert db.query(GeoSearchDaily).count()==counts
    duplicate=body+f'{day},{w.ORIGIN}/,1,2,\n'
    assert upload(duplicate).status_code==422
    r=client.post('/api/v1/admin/webmaster/bing/import',headers=ah,files={'file':('r.csv',body.encode())},data={'source_name':'Bing报表','confirmed':'false'})
    assert r.status_code==422
    assert client.get('/api/v1/admin/webmaster/report-template.csv',headers=ah).status_code==200


@pytest.mark.parametrize('line',['2099-01-01,/shop/a,1,2,',f'{date.today()},/shop/a,2,1,',f'{date.today()},/shop/a,1.5,2,',f'{date.today()},/shop/a,1,2,nan',f'{date.today()},//evil.example/a,1,2,'])
def test_bad_reports_rejected(line):
    with pytest.raises(w.WebmasterError):w.parse_csv(('day,page,clicks,impressions,position\n'+line).encode())


def test_google_endpoint_token_pagination_and_failure_atomicity(db,monkeypatch):
    credentials=service_credentials();calls=[]
    day=(date.today()-timedelta(days=3)).isoformat()
    page={'keys':[day,w.ORIGIN+'/shop/test'],'clicks':2,'impressions':20,'position':3}
    class FakeClient:
        def __init__(self,**kwargs):assert kwargs['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kw):
            calls.append((url,kw))
            if url=='https://oauth2.googleapis.com/token':return httpx.Response(200,json={'access_token':'fake-token'})
            assert url.startswith('https://www.googleapis.com/webmasters/v3/sites/')
            assert kw['headers']['Authorization']=='Bearer fake-token'
            return httpx.Response(200,json={'rows':[page]})
    monkeypatch.setattr(w.httpx,'Client',FakeClient)
    rows=w.google_rows({'service_account':credentials,'property':w.ORIGIN+'/'})
    assert len(rows)==1 and rows[0]['clicks']==2
    assert calls[1][1]['json']['dimensions']==['date','page']
    w.save_config(db,'google',{'service_account_json':json.dumps(credentials)})
    w.enqueue(db);db.commit()
    monkeypatch.setattr(w,'google_rows',lambda c:rows)
    w.run_due(db)
    assert w.state(db,'google')['status']=='success'
    assert db.query(GeoSearchDaily).count()==1
    w.enqueue(db);db.commit()
    def fail(c):raise RuntimeError('secret-should-never-be-persisted')
    monkeypatch.setattr(w,'google_rows',fail)
    w.run_due(db)
    assert w.state(db,'google')['status']=='error'
    assert 'secret' not in json.dumps(w.state(db,'google'))
    assert db.query(GeoSearchDaily).count()==1
    w.enqueue(db);db.commit();monkeypatch.setattr(w,'google_rows',lambda c:[]);w.run_due(db)
    assert db.query(GeoSearchDaily).count()==0


def test_google_reads_next_page_and_stops_on_upstream_error(monkeypatch):
    credentials=service_credentials();offsets=[]
    day=(date.today()-timedelta(days=3)).isoformat()
    failure=False
    class FakeClient:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kw):
            if url.endswith('/token'):return httpx.Response(200,json={'access_token':'fake'})
            offset=kw['json']['startRow'];offsets.append(offset)
            if offset and failure:return httpx.Response(403,json={'error':'private-data-not-for-logs'})
            rows=[{'keys':[day,w.ORIGIN+'/shop/page-'+str(i)],'clicks':1,'impressions':10} for i in range(offset,offset+(2500 if offset==0 else 1))]
            return httpx.Response(200,json={'rows':rows})
    monkeypatch.setattr(w.httpx,'Client',FakeClient)
    assert len(w.google_rows({'service_account':credentials}))==2501
    assert offsets==[0,2500]
    failure=True
    with pytest.raises(w.WebmasterError,match='HTTP 403'):w.google_rows({'service_account':credentials})


def test_report_preserves_distinct_query_urls_and_rejects_malformed_columns():
    day=date.today().isoformat()
    rows=w.parse_csv(f'day,page,clicks,impressions,position\n{day},{w.ORIGIN}/shop/a?ref=one,1,10,\n{day},{w.ORIGIN}/shop/a?ref=two,2,20,\n'.encode())
    assert rows[0]['page']!=rows[1]['page']
    with pytest.raises(w.WebmasterError):w.parse_csv(f'day,page,clicks,impressions\n{day},/shop/a,1,10,extra'.encode())
    with pytest.raises(w.WebmasterError):w.parse_csv(f'day,page,clicks,impressions,position\n{day},/shop/a,1,10'.encode())
