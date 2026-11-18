import base64
import copy
import json
import time
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

from app.models.billing import AIUsage, PaymentOrder, SubscriptionPeriod
from app.services import billing, payment_gateway as gateway, payment_settings as settings
from app.services.billing_catalog import Catalog, DEFAULT, SCALE, get_catalog, save_catalog
from tests.conftest import auth_headers, create_test_company, create_test_user


@pytest.fixture
def keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode(),
            key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())


def configure(db, keys, channel):
    private, public = keys
    config = ({'app_id': 'wx1234567890abcdef', 'merchant_id': '1234567890',
        'merchant_serial_no': 'ABCDEF0123456789', 'api_v3_key': 'x' * 32,
        'merchant_private_key': private, 'wechat_public_key_id': 'PUB_KEY_ID_123456',
        'wechat_public_key': public} if channel == 'wechat' else {
        'app_id': '2026111800000000', 'seller_id': '2088000000000000',
        'app_private_key': private, 'alipay_public_key': public})
    config.update(enabled=True, notify_url='https://example.test/api/v1/payments/' + channel + '/notify')
    settings.update_payment_settings(db, channel, config)
    db.commit()
    return settings.get_payment_settings(db, channel)


def identity(db):
    user = create_test_user(db)
    company = create_test_company(db, user)
    return user, company, auth_headers(user), '/api/v1/companies/' + str(company.id) + '/subscription'


def order(db, user, company, channel='wechat'):
    plan = {**copy.deepcopy(DEFAULT['plans'][0]), 'rates': {k:v for k,v in DEFAULT.items() if '_points_' in k}}
    row = PaymentOrder(company_id=company.id, created_by=user.id, order_no='CF'+uuid.uuid4().hex[:30],
        idempotency_key=str(uuid.uuid4()), channel=channel, plan_code='starter', plan_snapshot=plan,
        amount_fen=19900, merchant_snapshot={'app_id':'app','merchant_id':'merchant'},
        status='pending', expires_at=billing.now()+timedelta(minutes=15))
    db.add(row); db.commit()
    return row


def paid_period(db, user, company):
    row=order(db,user,company)
    billing.settle_order(db,row.order_no,row.channel,'transaction-'+row.order_no,row.amount_fen,row.merchant_snapshot)
    return billing.active_period(db,company.id)


def enforce(db):
    catalog=get_catalog(db);catalog['enforce_billing']=True
    save_catalog(db,Catalog(**catalog));db.commit()


def test_settings_admin_only_encrypted_no_echo_and_retained(client,db,keys):
    user=create_test_user(db)
    assert client.get('/api/v1/admin/payment-settings',headers=auth_headers(user)).status_code==403
    admin=create_test_user(db,email='admin-pay@example.test',is_platform_admin=True)
    config=configure(db,keys,'wechat')
    headers=auth_headers(admin)
    result=client.get('/api/v1/admin/payment-settings',headers=headers)
    assert result.status_code==200
    assert keys[0] not in result.text and 'x'*32 not in result.text
    from app.connectors.hotel.models import PlatformKeyValue
    assert keys[0] not in db.get(PlatformKeyValue,settings.settings_key('wechat')).encrypted_value
    response=client.put('/api/v1/admin/payment-settings/wechat',headers=headers,json={'merchant_private_key':''})
    assert response.status_code==200 and response.json()['secret_configured']['merchant_private_key']
    assert settings.get_payment_settings(db,'wechat')['merchant_private_key']==config['merchant_private_key']
    assert client.put('/api/v1/admin/payment-settings/wechat',headers=headers,json={'merchant_private_key':'private-secret-invalid'}).status_code==422
    assert settings.get_payment_settings(db,'wechat')['merchant_private_key']==config['merchant_private_key']
    assert client.put('/api/v1/admin/payment-settings/wechat',headers=headers,json={'clear_secrets':['merchant_private_key']}).status_code==422


def test_corrupt_credentials_fail_closed(db):
    from app.connectors.hotel.models import PlatformKeyValue
    db.add(PlatformKeyValue(key=settings.settings_key('alipay'),encrypted_value='broken',updated_at=billing.now()));db.commit()
    with pytest.raises(HTTPException) as exc: settings.get_payment_settings(db,'alipay')
    assert exc.value.status_code==503


@pytest.mark.parametrize('channel',['wechat','alipay'])
def test_checkout_server_price_idempotency_and_company_isolation(client,db,keys,monkeypatch,channel):
    user,company,headers,url=identity(db)
    configure(db,keys,channel)
    calls=[]
    monkeypatch.setattr(gateway,'create_checkout',lambda *args: calls.append(args[2].amount_fen) or 'https://qr.example.test/checkout')
    data={'plan_code':'starter','channel':channel,'idempotency_key':str(uuid.uuid4()),'amount_fen':1}
    first=client.post(url+'/orders',headers=headers,json=data)
    assert first.status_code==200
    row=first.json();assert row['amount_fen']==19900 and row['qr_image'].startswith('data:image/png;base64,')
    assert client.post(url+'/orders',headers=headers,json=data).json()['id']==row['id']
    assert calls==[19900]
    assert client.post(url+'/orders',headers=headers,json={**data,'idempotency_key':str(uuid.uuid4())}).status_code==409
    other=create_test_user(db,email='outsider@example.test')
    assert client.get(url+'/orders/'+row['id'],headers=auth_headers(other)).status_code==403
    snapshot=db.get(PaymentOrder,uuid.UUID(row['id'])).plan_snapshot
    assert snapshot['rates']['video_points_per_second']==50


def test_unconfigured_channel_and_invalid_plan(client,db):
    _,_,headers,url=identity(db)
    assert client.post(url+'/orders',headers=headers,json={'plan_code':'starter','channel':'wechat','idempotency_key':str(uuid.uuid4())}).status_code==409


def test_settlement_duplicate_mismatch_renewal_and_rate_snapshot(db):
    user,company,_,_=identity(db);row=order(db,user,company)
    with pytest.raises(HTTPException): billing.settle_order(db,row.order_no,'wechat','tx',1,row.merchant_snapshot)
    assert db.query(SubscriptionPeriod).count()==0
    billing.settle_order(db,row.order_no,'wechat','tx',19900,row.merchant_snapshot)
    billing.settle_order(db,row.order_no,'wechat','tx',19900,row.merchant_snapshot)
    assert db.query(SubscriptionPeriod).count()==1
    first=billing.active_period(db,company.id)
    second=order(db,user,company)
    billing.settle_order(db,second.order_no,'wechat','tx2',19900,second.merchant_snapshot)
    periods=db.query(SubscriptionPeriod).order_by(SubscriptionPeriod.starts_at).all()
    assert len(periods)==2 and periods[1].starts_at==first.ends_at
    catalog=get_catalog(db);catalog['video_points_per_second']=100
    save_catalog(db,Catalog(**catalog));db.commit()
    record=billing.reserve(db,company.id,'video:snapshot','video',video_seconds=5)
    assert record.reserved_units==250*SCALE


def test_reserve_settle_release_unknown_and_small_token_precision(db):
    user,company,_,_=identity(db);period=paid_period(db,user,company);enforce(db)
    record=billing.reserve(db,company.id,'llm:one','llm',input_tokens=1000,output_tokens=500)
    assert record.reserved_units==700000
    billing.finish(db,record.usage_key,'settle',input_tokens=1,output_tokens=1)
    assert record.charged_units==1200 and record.cost_micro_yuan==12 and record.reserved_units==0
    before=period.used_units
    billing.finish(db,record.usage_key,'settle',input_tokens=1000000)
    assert period.used_units==before and period.reserved_units==0
    unknown=billing.reserve(db,company.id,'video:unknown','video',video_seconds=5)
    billing.finish(db,unknown.usage_key,'unknown')
    assert period.reserved_units==250*SCALE
    billing.finish(db,unknown.usage_key,'release')
    assert period.reserved_units==0 and unknown.reserved_units==0
    with pytest.raises(HTTPException) as exc: billing.reserve(db,company.id,'video:too-many','video',video_seconds=1000)
    assert exc.value.status_code==402 and db.query(AIUsage).count()==2


def test_no_subscription_or_expired_cannot_generate(db):
    user,company,_,_=identity(db);enforce(db)
    with pytest.raises(HTTPException): billing.reserve(db,company.id,'video:no-plan','video',video_seconds=5)
    period=paid_period(db,user,company);period.starts_at=billing.now()-timedelta(days=31);period.ends_at=billing.now()-timedelta(days=1);db.commit()
    with pytest.raises(HTTPException): billing.reserve(db,company.id,'video:expired','video',video_seconds=5)


def test_wechat_verified_encrypted_callback_idempotent_and_forgery(client,db,keys):
    user,company,_,_=identity(db);config=configure(db,keys,'wechat');row=order(db,user,company)
    row.merchant_snapshot=gateway.merchant_identity('wechat',config);db.commit()
    data={'out_trade_no':row.order_no,'transaction_id':'wx-tx','appid':config['app_id'],'mchid':config['merchant_id'],
          'trade_state':'SUCCESS','amount':{'total':19900,'currency':'CNY'}}
    nonce='012345678901';associated='transaction'
    encrypted=AESGCM(config['api_v3_key'].encode()).encrypt(nonce.encode(),json.dumps(data).encode(),associated.encode())
    body=json.dumps({'event_type':'TRANSACTION.SUCCESS','resource':{'algorithm':'AEAD_AES_256_GCM','nonce':nonce,
        'associated_data':associated,'ciphertext':base64.b64encode(encrypted).decode()}})
    stamp=str(int(time.time()));headers={'Wechatpay-Timestamp':stamp,'Wechatpay-Nonce':'nonce','Wechatpay-Serial':config['wechat_public_key_id'],
        'Wechatpay-Signature':gateway.sign(chr(10).join([stamp,'nonce',body,'']),keys[0]),'Content-Type':'application/json'}
    url='/api/v1/payments/wechat/notify'
    assert client.post(url,content=body,headers=headers).status_code==200
    assert client.post(url,content=body,headers=headers).status_code==200
    assert db.query(SubscriptionPeriod).count()==1
    assert client.post(url,content=body+' ',headers=headers).status_code==400
    assert client.post(url,content=body,headers={**headers,'Wechatpay-Serial':'wrong'}).status_code==400


def test_alipay_verified_callback_wrong_amount_and_duplicate(client,db,keys):
    user,company,_,_=identity(db);config=configure(db,keys,'alipay');row=order(db,user,company,'alipay')
    row.merchant_snapshot=gateway.merchant_identity('alipay',config);db.commit()
    def signed(amount):
        data={'out_trade_no':row.order_no,'trade_no':'ali-tx','app_id':config['app_id'],'seller_id':config['seller_id'],
            'trade_status':'TRADE_SUCCESS','total_amount':amount,'sign_type':'RSA2'}
        canonical='&'.join(k+'='+data[k] for k in sorted(data) if k!='sign_type')
        data['sign']=gateway.sign(canonical,keys[0]);return urlencode(data)
    url='/api/v1/payments/alipay/notify';headers={'Content-Type':'application/x-www-form-urlencoded'}
    assert client.post(url,content=signed('0.01'),headers=headers).status_code==400
    assert db.query(SubscriptionPeriod).count()==0
    body=signed('199.00')
    assert client.post(url,content=body,headers=headers).text=='success'
    assert client.post(url,content=body,headers=headers).text=='success'
    assert db.query(SubscriptionPeriod).count()==1
    assert client.post(url,content=body+'&total_amount=199.00',headers=headers).status_code==400


def test_admin_reconciliation_protected_audited_and_no_double_release(client,db):
    user,company,headers,_=identity(db);period=paid_period(db,user,company)
    row=billing.reserve(db,company.id,'video:admin','video',video_seconds=5)
    billing.finish(db,row.usage_key,'unknown')
    url='/api/v1/admin/billing-usage/'+str(row.id)+'/resolve'
    assert client.post(url,headers=headers,json={'outcome':'release','note':'已核对失败记录'}).status_code==403
    admin=create_test_user(db,email='billing-admin@example.test',is_platform_admin=True)
    headers=auth_headers(admin)
    assert client.post(url,headers=headers,json={'outcome':'settle','note':'已核对成功记录','video_seconds':5}).status_code==200
    assert row.status=='settled' and period.used_units==250*SCALE and period.reserved_units==0
    assert client.post(url,headers=headers,json={'outcome':'release','note':'重复操作不能释放'}).json()['status']=='settled'


@pytest.mark.asyncio
async def test_llm_metering_before_http_success_and_rejection(db,monkeypatch):
    from app.providers.llm.openai_provider import OpenAIProvider
    user,company,_,_=identity(db);period=paid_period(db,user,company);enforce(db)
    calls=[]
    class Client:
        def __init__(self,**kwargs): pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):
            assert period.reserved_units>0 and 'billing_company_id' not in kwargs['json']
            calls.append(kwargs)
            return httpx.Response(200,json={'choices':[{'message':{'content':'ok'}}], 'usage':{'prompt_tokens':100,'completion_tokens':200}})
    monkeypatch.setattr(httpx,'AsyncClient',Client)
    provider=OpenAIProvider(config={'base_url':'https://example.test/v1','model':'test','api_key':'test'})
    await provider.complete([{'role':'user','content':'hi'}],billing_company_id=company.id)
    assert len(calls)==1 and period.used_units==220000 and period.reserved_units==0
    period.used_units=period.included_units;db.commit()
    with pytest.raises(HTTPException) as exc: await provider.complete([{'role':'user','content':'hi'}],billing_company_id=company.id)
    assert exc.value.status_code==402 and len(calls)==1


def test_video_credit_rejection_never_submits_and_is_retryable(db):
    from unittest.mock import AsyncMock
    from app.models.video_project import VideoProject,ProviderTask
    from app.providers.video.base import VideoGenerationRequest
    from app.services.video_generation import _generate_clip
    user,company,_,_=identity(db);enforce(db)
    project=VideoProject(company_id=company.id,created_by=user.id,title='Credit rejection',creation_mode='prompt_to_video')
    db.add(project);db.commit();provider=AsyncMock()
    with pytest.raises(HTTPException):_generate_clip(db,project,provider,VideoGenerationRequest(prompt='demo',duration_seconds=5,aspect_ratio='9:16'),1)
    provider.submit_generation.assert_not_called()
    assert db.query(ProviderTask).one().status=='rejected'


@pytest.mark.parametrize('channel', ['wechat','alipay'])
def test_official_gateway_signed_requests_and_verified_responses(db,keys,monkeypatch,channel):
    user,company,_,_=identity(db);config=configure(db,keys,channel);row=order(db,user,company,channel)
    original=httpx.Client
    def handle(request):
        assert request.url.host in ('api.mch.weixin.qq.com','openapi.alipay.com')
        if channel=='wechat':
            import re
            auth=dict(re.findall(r'([a-z_]+)="([^"]*)"',request.headers['Authorization']))
            canonical=chr(10).join([request.method,request.url.raw_path.decode(),auth['timestamp'],auth['nonce_str'],request.content.decode(),''])
            gateway.verify(canonical,auth['signature'],keys[1])
            body=json.dumps({'code_url':'weixin://wxpay/test'})
            stamp=str(int(time.time()));nonce='server-nonce'
            return httpx.Response(200,text=body,headers={'Wechatpay-Timestamp':stamp,'Wechatpay-Nonce':nonce,
                'Wechatpay-Serial':config['wechat_public_key_id'],
                'Wechatpay-Signature':gateway.sign(chr(10).join([stamp,nonce,body,'']),keys[0])})
        from urllib.parse import parse_qsl
        data=dict(parse_qsl(request.content.decode()))
        gateway.verify('&'.join(k+'='+data[k] for k in sorted(data) if k!='sign'),data['sign'],keys[1])
        assert json.loads(data['biz_content'])['total_amount']=='199.00'
        body=json.dumps({'code':'10000','out_trade_no':row.order_no,'qr_code':'https://qr.alipay.test/checkout'},ensure_ascii=False)
        envelope='{"alipay_trade_precreate_response":'+body+',"sign":'+json.dumps(gateway.sign(body,keys[0]))+'}'
        return httpx.Response(200,text=envelope)
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    assert gateway.create_checkout(channel,config,row) in ('weixin://wxpay/test','https://qr.alipay.test/checkout')


def test_query_recovers_missing_callback_and_preserves_merchant_snapshot(client,db,keys,monkeypatch):
    user,company,headers,url=identity(db);config=configure(db,keys,'wechat');row=order(db,user,company)
    row.merchant_snapshot=gateway.merchant_identity('wechat',config);row.status='unknown';row.error_message='下单结果待核对';db.commit()
    calls=[]
    def query(*args):calls.append(1);return 'query-tx',19900,row.merchant_snapshot
    monkeypatch.setattr(gateway,'query_payment',query)
    response=client.post(url+'/orders/'+str(row.id)+'/query',headers=headers)
    assert response.status_code==200,response.text
    assert response.json()['status']=='paid' and response.json()['error_message'] is None
    assert client.post(url+'/orders/'+str(row.id)+'/query',headers=headers).status_code==200
    assert calls==[1] and db.query(SubscriptionPeriod).count()==1


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [(400,'released'),(524,'unknown')])
async def test_llm_failure_releases_only_definite_rejections(db,monkeypatch,status,expected):
    from app.providers.llm.openai_provider import OpenAIProvider
    _,company,_,_=identity(db)
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):return httpx.Response(status)
    monkeypatch.setattr(httpx,'AsyncClient',Client)
    provider=OpenAIProvider(config={'base_url':'https://example.test/v1','model':'test','api_key':'test'})
    with pytest.raises(ValueError):await provider.complete([{'role':'user','content':'hi'}],billing_company_id=company.id)
    row=db.query(AIUsage).one()
    assert row.status==expected
    assert (row.reserved_units==0)==(expected=='released')
