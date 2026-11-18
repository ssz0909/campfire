"""Platform collection credentials. Configuration does not create payment orders."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.connectors.hotel.models import PlatformKeyValue
from app.core.secrets import _fernet, encrypt_json

FIELDS = {
    'wechat': ('app_id', 'merchant_id', 'merchant_serial_no', 'api_v3_key',
               'merchant_private_key', 'wechat_public_key_id', 'wechat_public_key', 'notify_url'),
    'alipay': ('app_id', 'seller_id', 'app_private_key', 'alipay_public_key', 'notify_url', 'return_url'),
}
SECRETS = {
    'wechat': ('api_v3_key', 'merchant_private_key', 'wechat_public_key'),
    'alipay': ('app_private_key', 'alipay_public_key'),
}
LABELS = {
    'app_id': '应用 App ID', 'seller_id': '支付宝商户 UID', 'merchant_id': '微信支付商户号',
    'merchant_serial_no': '商户 API 证书序列号', 'api_v3_key': 'API v3 密钥',
    'merchant_private_key': '商户 API 私钥', 'wechat_public_key_id': '微信支付公钥 ID',
    'wechat_public_key': '微信支付公钥', 'app_private_key': '应用私钥',
    'alipay_public_key': '支付宝公钥', 'notify_url': '异步通知地址', 'return_url': '支付完成返回地址',
}


def settings_key(channel: str) -> str:
    if channel not in FIELDS:
        raise HTTPException(404, '不支持的支付渠道')
    return f'platform.payment.{channel}.settings'


def get_payment_settings(db: Session, channel: str) -> dict:
    row = db.get(PlatformKeyValue, settings_key(channel))
    if row is None:
        return {'enabled': False, **dict.fromkeys(FIELDS[channel], '')}
    try:
        values = json.loads(_fernet().decrypt(row.encrypted_value.encode()).decode())
        if not isinstance(values, dict) or not isinstance(values.get('enabled'), bool):
            raise ValueError('Invalid settings')
        if any(not isinstance(values.get(field), str) for field in FIELDS[channel]):
            raise ValueError('Invalid settings')
        return values
    except Exception:
        # Never fall back to another merchant or expose decryption diagnostics.
        raise HTTPException(503, '支付配置无法解密或格式异常，请管理员检查加密配置及备份') from None


def public_settings(db: Session, channel: str) -> dict:
    values = get_payment_settings(db, channel)
    row = db.get(PlatformKeyValue, settings_key(channel))
    missing = [field for field in FIELDS[channel] if field != 'return_url' and not values.get(field)]
    return {
        'channel': channel, 'enabled': values['enabled'],
        **{field: values[field] for field in FIELDS[channel] if field not in SECRETS[channel]},
        'secret_configured': {field: bool(values[field]) for field in SECRETS[channel]},
        'configuration_complete': not missing, 'missing_fields': [LABELS[field] for field in missing],
        'updated_at': row.updated_at if row else None,
        'integration_status': 'native_qr_checkout',
    }


def _validate_key(value: str, label: str, private: bool) -> None:
    if not value:
        return
    try:
        raw = value.encode('ascii')
        if not value.startswith('-----BEGIN '):
            # Alipay commonly exports bare base64 DER keys.
            import base64
            raw = base64.b64decode(re.sub(r'\s+', '', value), validate=True)
            key = serialization.load_der_private_key(raw, None) if private else serialization.load_der_public_key(raw)
        else:
            key = serialization.load_pem_private_key(raw, None) if private else serialization.load_pem_public_key(raw)
        expected = rsa.RSAPrivateKey if private else rsa.RSAPublicKey
        if not isinstance(key, expected) or key.key_size < 2048:
            raise ValueError('RSA 2048 required')
    except Exception:
        raise HTTPException(422, f'{label}须为有效的 RSA 密钥（至少2048位）；私钥不可带密码，支持 PEM 或 Base64 格式') from None


def _validate_url(value: str, label: str) -> None:
    if not value:
        return
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme == 'https' and parsed.hostname and not (
            parsed.username or parsed.password or parsed.query or parsed.fragment)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, f'{label}须为 HTTPS 完整地址，不含账号、查询参数或片段')


def update_payment_settings(db: Session, channel: str, changes: dict) -> dict:
    key = settings_key(channel)
    # Serialize partial updates so a concurrent save cannot restore an old key.
    db.query(PlatformKeyValue).filter(PlatformKeyValue.key == key).with_for_update().first()
    current = get_payment_settings(db, channel)
    clear = changes.pop('clear_secrets', [])
    if len(set(clear)) != len(clear) or any(field not in SECRETS[channel] for field in clear):
        raise HTTPException(422, '仅支持清除本渠道指定的密钥字段')
    values = dict(current)
    for field in FIELDS[channel]:
        if field not in changes or changes[field] is None:
            continue
        value = changes[field].strip()
        if field in SECRETS[channel]:
            if field in clear and value:
                raise HTTPException(422, '同一密钥不能同时清除和替换')
            if not value:
                continue
        values[field] = value
    for field in clear:
        values[field] = ''
    if 'enabled' in changes and changes['enabled'] is not None:
        values['enabled'] = changes['enabled']
    if channel == 'wechat':
        if values['app_id'] and not re.fullmatch(r'wx[0-9A-Za-z]{16}', values['app_id']):
            raise HTTPException(422, '微信 App ID 应为 wx 开头的18位标识')
        if values['merchant_id'] and not re.fullmatch(r'[0-9]{6,32}', values['merchant_id']):
            raise HTTPException(422, '微信支付商户号应为6至32位数字')
        if values['merchant_serial_no'] and not re.fullmatch(r'[0-9A-Fa-f]{16,64}', values['merchant_serial_no']):
            raise HTTPException(422, '商户 API 证书序列号应为16至64位十六进制字符')
        if values['api_v3_key'] and (len(values['api_v3_key']) != 32 or not values['api_v3_key'].isascii()):
            raise HTTPException(422, 'API v3 密钥须为32位 ASCII 字符')
        if values['wechat_public_key_id'] and not re.fullmatch(r'PUB_KEY_ID_[0-9]+', values['wechat_public_key_id']):
            raise HTTPException(422, '微信支付公钥 ID 应为 PUB_KEY_ID_ 开头的数字标识')
        _validate_key(values['merchant_private_key'], LABELS['merchant_private_key'], True)
        _validate_key(values['wechat_public_key'], LABELS['wechat_public_key'], False)
    else:
        if values['seller_id'] and not re.fullmatch(r'[0-9]{16}', values['seller_id']):
            raise HTTPException(422, '支付宝商户 UID 应为16位数字')
        if values['app_id'] and not re.fullmatch(r'[0-9]{16,32}', values['app_id']):
            raise HTTPException(422, '支付宝 App ID 应为16至32位数字')
        _validate_key(values['app_private_key'], LABELS['app_private_key'], True)
        _validate_key(values['alipay_public_key'], LABELS['alipay_public_key'], False)
        _validate_url(values['return_url'], LABELS['return_url'])
    _validate_url(values['notify_url'], LABELS['notify_url'])
    if values['enabled']:
        missing = [LABELS[field] for field in FIELDS[channel] if field != 'return_url' and not values[field]]
        if missing:
            raise HTTPException(422, '启用前请补齐：' + '、'.join(missing))
    row = db.get(PlatformKeyValue, key)
    if row is None:
        row = PlatformKeyValue(key=key)
        db.add(row)
    row.encrypted_value = encrypt_json(values)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return public_settings(db, channel)
