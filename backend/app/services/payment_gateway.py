"""Official direct-merchant QR checkout. Credentials stay on the backend."""
import base64
import json
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

WECHAT = 'https://api.mch.weixin.qq.com'
ALIPAY = 'https://openapi.alipay.com/gateway.do'


def load_key(value, private=False):
    raw = value.encode('ascii')
    if value.startswith('-----BEGIN '):
        return serialization.load_pem_private_key(raw, None) if private else serialization.load_pem_public_key(raw)
    raw = base64.b64decode(''.join(value.split()), validate=True)
    return serialization.load_der_private_key(raw, None) if private else serialization.load_der_public_key(raw)


def sign(value, private_key):
    return base64.b64encode(load_key(private_key, True).sign(value.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()


def verify(value, signature, public_key):
    try:
        load_key(public_key).verify(base64.b64decode(signature, validate=True), value.encode(), padding.PKCS1v15(), hashes.SHA256())
    except Exception:
        raise HTTPException(400, '支付签名验证失败') from None


def merchant_identity(channel, config):
    return {'app_id': config['app_id'], **({'merchant_id': config['merchant_id']} if channel == 'wechat' else {'seller_id': config['seller_id']})}


def wechat_verify(headers, body, config):
    stamp, nonce = headers.get('Wechatpay-Timestamp', ''), headers.get('Wechatpay-Nonce', '')
    try:
        if abs(time.time() - int(stamp)) > 300 or not nonce: raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, '支付响应时间戳无效') from None
    if headers.get('Wechatpay-Serial') != config['wechat_public_key_id']:
        raise HTTPException(400, '微信支付公钥 ID 不匹配')
    verify(chr(10).join([stamp, nonce, body, '']), headers.get('Wechatpay-Signature', ''), config['wechat_public_key'])


def wechat_request(config, method, path, payload=None):
    body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False) if payload is not None else ''
    stamp, nonce = str(int(time.time())), secrets.token_hex(16)
    signature = sign(chr(10).join([method, path, stamp, nonce, body, '']), config['merchant_private_key'])
    authorization = ('WECHATPAY2-SHA256-RSA2048 mchid="{}",nonce_str="{}",timestamp="{}",serial_no="{}",signature="{}"'
        .format(config['merchant_id'], nonce, stamp, config['merchant_serial_no'], signature))
    with httpx.Client(timeout=httpx.Timeout(20, connect=10)) as client:
        response = client.request(method, WECHAT + path, content=body.encode() if body else None,
            headers={'Authorization': authorization, 'Accept': 'application/json', 'Content-Type': 'application/json',
                     'Wechatpay-Serial': config['wechat_public_key_id']})
    if response.status_code >= 400:
        raise HTTPException(502, '微信支付未接受请求，请检查商户产品权限和配置')
    wechat_verify(response.headers, response.text, config)
    return response.json()


def alipay_request(config, method, biz):
    params = {'app_id': config['app_id'], 'method': method, 'format': 'JSON', 'charset': 'utf-8',
              'sign_type': 'RSA2', 'timestamp': datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'),
              'version': '1.0', 'biz_content': json.dumps(biz, ensure_ascii=False, separators=(',', ':'))}
    if method == 'alipay.trade.precreate': params['notify_url'] = config['notify_url']
    params['sign'] = sign('&'.join(f'{key}={params[key]}' for key in sorted(params) if params[key] != ''), config['app_private_key'])
    with httpx.Client(timeout=httpx.Timeout(20, connect=10)) as client:
        response = client.post(ALIPAY, data=params)
    if response.status_code >= 400:
        raise HTTPException(502, '支付宝请求失败，请稍后查询订单状态')
    envelope = response.json()
    response_key = method.replace('.', '_') + '_response'
    start = response.text.find(json.dumps(response_key))
    if start < 0 or not envelope.get('sign'):
        raise HTTPException(502, '支付宝未返回可验证的响应')
    start = response.text.index(':', start + len(json.dumps(response_key))) + 1
    while response.text[start].isspace(): start += 1
    data, consumed = json.JSONDecoder().raw_decode(response.text[start:])
    verify(response.text[start:start+consumed], envelope['sign'], config['alipay_public_key'])
    if data.get('code') != '10000':
        raise HTTPException(502, '支付宝未确认请求，请检查商户产品权限或稍后查询订单')
    return data


def create_checkout(channel, config, order):
    title = '营火AI · {} · 30天订阅'.format(order.plan_snapshot['name'])
    if channel == 'wechat':
        result = wechat_request(config, 'POST', '/v3/pay/transactions/native', {
            'appid': config['app_id'], 'mchid': config['merchant_id'], 'description': title,
            'out_trade_no': order.order_no, 'notify_url': config['notify_url'],
            'time_expire': order.expires_at.replace(tzinfo=timezone.utc).isoformat(),
            'amount': {'total': order.amount_fen, 'currency': 'CNY'}})
        code = result.get('code_url', '')
    else:
        result = alipay_request(config, 'alipay.trade.precreate', {'out_trade_no': order.order_no,
            'total_amount': f'{Decimal(order.amount_fen) / 100:.2f}', 'subject': title, 'timeout_express': '15m'})
        if result.get('out_trade_no') != order.order_no: raise HTTPException(502, '支付宝返回订单号不匹配')
        code = result.get('qr_code', '')
    if not isinstance(code, str) or not code or len(code) > 4096: raise HTTPException(502, '支付渠道未返回有效二维码')
    return code


def query_payment(channel, config, order):
    if channel == 'wechat':
        path = f'/v3/pay/transactions/out-trade-no/{order.order_no}?' + urlencode({'mchid': config['merchant_id']})
        data = wechat_request(config, 'GET', path)
        if data.get('out_trade_no') != order.order_no: raise HTTPException(502, '支付订单号不匹配')
        if data.get('trade_state') != 'SUCCESS': return None
        if data.get('amount', {}).get('currency') != 'CNY': raise HTTPException(400, '支付币种不匹配')
        return data['transaction_id'], data['amount']['total'], {'app_id': data.get('appid'), 'merchant_id': data.get('mchid')}
    data = alipay_request(config, 'alipay.trade.query', {'out_trade_no': order.order_no})
    if data.get('out_trade_no') != order.order_no: raise HTTPException(502, '支付订单号不匹配')
    if data.get('trade_status') not in ('TRADE_SUCCESS', 'TRADE_FINISHED'): return None
    return data['trade_no'], to_fen(data['total_amount']), {'app_id': config['app_id'], 'seller_id': data.get('seller_id')}


def to_fen(value):
    try:
        amount = Decimal(str(value)) * 100
        if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value(): raise ValueError()
        return int(amount)
    except Exception:
        raise HTTPException(400, '支付金额格式无效') from None


def decode_wechat_callback(config, headers, body):
    wechat_verify(headers, body, config)
    try:
        event = json.loads(body)
        if event.get('event_type') != 'TRANSACTION.SUCCESS': raise ValueError()
        resource = event['resource']
        if resource['algorithm'] != 'AEAD_AES_256_GCM': raise ValueError()
        raw = AESGCM(config['api_v3_key'].encode()).decrypt(resource['nonce'].encode(),
            base64.b64decode(resource['ciphertext'], validate=True), resource.get('associated_data', '').encode())
        data = json.loads(raw)
        if data['trade_state'] != 'SUCCESS' or data['amount']['currency'] != 'CNY': raise ValueError()
        if not all(isinstance(data.get(k), str) and data[k] for k in ('out_trade_no', 'transaction_id', 'appid', 'mchid')):
            raise ValueError()
        if type(data['amount']['total']) is not int or data['amount']['total'] <= 0: raise ValueError()
        return data
    except Exception:
        raise HTTPException(400, '微信支付通知内容校验失败') from None


def decode_alipay_callback(config, pairs):
    if len(pairs) != len(dict(pairs)): raise HTTPException(400, '支付通知含重复字段')
    data = dict(pairs)
    if data.get('sign_type') != 'RSA2': raise HTTPException(400, '支付签名类型无效')
    canonical = '&'.join(f'{key}={data[key]}' for key in sorted(data) if key not in ('sign', 'sign_type') and data[key] != '')
    verify(canonical, data.get('sign', ''), config['alipay_public_key'])
    if data.get('trade_status') not in ('TRADE_SUCCESS', 'TRADE_FINISHED'): raise HTTPException(400, '尚未支付成功')
    if not all(data.get(k) for k in ('out_trade_no', 'trade_no', 'app_id', 'seller_id', 'total_amount')):
        raise HTTPException(400, '支付宝通知缺少交易信息')
    return data
