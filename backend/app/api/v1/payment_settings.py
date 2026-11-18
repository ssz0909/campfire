"""Admin-only payment configuration; no charge or external verification occurs."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.orm import Session

from app.api.v1.admin import require_platform_admin
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.payment_settings import public_settings, update_payment_settings

router = APIRouter(prefix='/admin/payment-settings', tags=['admin'])
Channel = Literal['wechat', 'alipay']
Text = Annotated[str, Field(max_length=2048)]


class PaymentSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool | None = None
    app_id: Text | None = None
    seller_id: Text | None = None
    merchant_id: Text | None = None
    merchant_serial_no: Text | None = None
    wechat_public_key_id: Text | None = None
    notify_url: Text | None = None
    return_url: Text | None = None
    api_v3_key: SecretStr | None = None
    merchant_private_key: SecretStr | None = None
    wechat_public_key: SecretStr | None = None
    app_private_key: SecretStr | None = None
    alipay_public_key: SecretStr | None = None
    clear_secrets: list[str] = Field(default_factory=list, max_length=5)


@router.get('')
def read_channels(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return {'channels': [public_settings(db, channel) for channel in ('wechat', 'alipay')]}


@router.put('/{channel}')
def save_channel(channel: Channel, data: PaymentSettingsUpdate, db: Session = Depends(get_db),
                 admin: User = Depends(require_platform_admin)):
    from fastapi import HTTPException
    from app.services.payment_settings import FIELDS, SECRETS
    changes = data.model_dump(exclude_unset=True)
    if set(changes) - set(FIELDS[channel]) - {'enabled', 'clear_secrets'}:
        raise HTTPException(422, '配置中含有其他支付渠道的字段')
    for field in SECRETS[channel]:
        value = changes.get(field)
        if value is not None:
            value = value.get_secret_value()
            if len(value) > 16384:
                raise HTTPException(422, '密钥内容过长，请检查格式')
            changes[field] = value
    result = update_payment_settings(db, channel, changes)
    db.add(AuditLog(user_id=admin.id, action='platform.payment.settings.update',
                    resource_type='platform', resource_id=f'payment_{channel}'))
    db.commit()
    return result
