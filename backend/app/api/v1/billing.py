"""Company subscription checkout and signed provider callbacks."""
import base64
import io
import uuid
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.v1.admin import require_platform_admin
from app.core.permissions import Permission, require_permission, get_user_permissions
from app.database import get_db
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.billing import PaymentOrder, SubscriptionPeriod, AIUsage
from app.services import billing, payment_gateway
from app.services.billing_catalog import get_catalog, save_catalog, Catalog, SCALE
from app.services.payment_settings import get_payment_settings, public_settings

router = APIRouter()


def order_view(order):
    result = {key: getattr(order, key) for key in ('id', 'order_no', 'channel', 'plan_code', 'amount_fen',
        'status', 'expires_at', 'paid_at', 'created_at', 'error_message')}
    result['plan_name'] = order.plan_snapshot['name']
    result['included_points'] = order.plan_snapshot['included_points']
    if order.code_url and order.status == 'pending' and billing.aware(order.expires_at) > billing.now():
        import qrcode
        output = io.BytesIO()
        qrcode.make(order.code_url).save(output, format='PNG')
        result['qr_image'] = 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()
    else:
        result['qr_image'] = None
    return result


def company_order(db, company_id, order_id):
    order = db.query(PaymentOrder).filter_by(id=order_id, company_id=company_id).first()
    if order is None: raise HTTPException(404, '订单不存在')
    return order


@router.get('/companies/{company_id}/subscription')
def subscription(company_id: uuid.UUID, db: Session = Depends(get_db),
                 _user: User = Depends(require_permission(Permission.SUBSCRIPTION_VIEW))):
    catalog = get_catalog(db)
    period = billing.active_period(db, company_id)
    upcoming = db.query(SubscriptionPeriod).filter(SubscriptionPeriod.company_id == company_id,
        SubscriptionPeriod.starts_at > billing.now()).order_by(SubscriptionPeriod.starts_at).all()
    def period_view(row):
        return {'id': row.id, 'plan_name': row.plan_name, 'plan_code': row.plan_code,
            'starts_at': row.starts_at, 'ends_at': row.ends_at, 'included_points': row.included_units / SCALE,
            'used_points': row.used_units / SCALE, 'reserved_points': row.reserved_units / SCALE,
            'remaining_points': max(0, row.included_units - row.used_units - row.reserved_units) / SCALE,
            'rates': row.rates}
    return {'period': period_view(period) if period else None,
        'upcoming_periods': [period_view(row) for row in upcoming],
        'enforce_billing': catalog['enforce_billing'],
        'plans': [p for p in catalog['plans'] if p['enabled']],
        'rates': {k: v for k, v in catalog.items() if '_points_' in k},
        'channels': [{'channel': c, 'available': public_settings(db, c)['enabled'] and
                       public_settings(db, c)['configuration_complete']} for c in ('wechat', 'alipay')],
        'renewal_policy': 'manual_30_days', 'currency': 'CNY',
        'can_manage': Permission.SUBSCRIPTION_MANAGE in get_user_permissions(_user.id, company_id, db)}


class Checkout(BaseModel):
    plan_code: str = Field(min_length=1, max_length=30)
    channel: Literal['wechat', 'alipay']
    idempotency_key: uuid.UUID


@router.post('/companies/{company_id}/subscription/orders')
def checkout(company_id: uuid.UUID, data: Checkout, db: Session = Depends(get_db),
             user: User = Depends(require_permission(Permission.SUBSCRIPTION_MANAGE))):
    billing.lock_company(db, company_id)
    existing = db.query(PaymentOrder).filter_by(company_id=company_id, idempotency_key=str(data.idempotency_key)).first()
    if existing:
        if existing.channel != data.channel or existing.plan_code != data.plan_code:
            raise HTTPException(409, '同一请求标识不能用于不同套餐或渠道')
        return order_view(existing)
    # At most one unpaid checkout per company. A lost response can be recovered from order history.
    pending = db.query(PaymentOrder).filter(PaymentOrder.company_id == company_id,
        PaymentOrder.status.in_(['creating', 'pending', 'unknown']), PaymentOrder.expires_at > billing.now()).first()
    if pending:
        raise HTTPException(409, '已有待支付订单，请在订单记录中继续支付或等待到期')
    config = get_payment_settings(db, data.channel)
    if not config['enabled'] or not public_settings(db, data.channel)['configuration_complete']:
        raise HTTPException(409, '该支付渠道尚未开通，请联系管理员')
    plan = next((p for p in get_catalog(db)['plans'] if p['code'] == data.plan_code and p['enabled']), None)
    if not plan: raise HTTPException(404, '套餐不存在或已下架')
    snapshot = {**plan, 'rates': {k: v for k, v in get_catalog(db).items() if '_points_' in k}}
    order = PaymentOrder(company_id=company_id, created_by=user.id,
        order_no='CF' + uuid.uuid4().hex[:30], idempotency_key=str(data.idempotency_key),
        channel=data.channel, plan_code=plan['code'], plan_snapshot=snapshot, amount_fen=plan['price_fen'],
        merchant_snapshot=payment_gateway.merchant_identity(data.channel, config), status='creating',
        expires_at=billing.now() + timedelta(minutes=15))
    db.add(order); db.commit(); db.refresh(order)
    try:
        code_url = payment_gateway.create_checkout(data.channel, config, order)
    except Exception:
        # Never generate a second provider order automatically after an uncertain request.
        db.rollback(); db.refresh(order)
        if order.status != 'paid':
            order.status = 'unknown'; order.error_message = '支付下单结果待确认，请查询此订单，勿重复付款'
            db.commit()
        return order_view(order)
    db.refresh(order)
    if order.status != 'paid':
        order.code_url = code_url; order.status = 'pending'; db.commit()
    return order_view(order)


@router.get('/companies/{company_id}/subscription/orders')
def orders(company_id: uuid.UUID, page: int = Query(1, ge=1), db: Session = Depends(get_db),
           _user: User = Depends(require_permission(Permission.SUBSCRIPTION_VIEW))):
    query = db.query(PaymentOrder).filter_by(company_id=company_id)
    return {'items': [order_view(row) for row in query.order_by(PaymentOrder.created_at.desc()).offset((page-1)*20).limit(20)],
            'total': query.count(), 'page': page, 'page_size': 20}


@router.get('/companies/{company_id}/subscription/orders/{order_id}')
def read_order(company_id: uuid.UUID, order_id: uuid.UUID, db: Session = Depends(get_db),
               _user: User = Depends(require_permission(Permission.SUBSCRIPTION_VIEW))):
    return order_view(company_order(db, company_id, order_id))


@router.post('/companies/{company_id}/subscription/orders/{order_id}/query')
def query_order(company_id: uuid.UUID, order_id: uuid.UUID, db: Session = Depends(get_db),
                _user: User = Depends(require_permission(Permission.SUBSCRIPTION_MANAGE))):
    order = company_order(db, company_id, order_id)
    if order.status == 'paid': return order_view(order)
    # Serialize and throttle provider queries across tabs and backend workers.
    billing.lock_company(db, company_id)
    throttle_key = 'payment_query_' + str(order.id)
    from app.connectors.hotel.models import PlatformKeyValue
    from app.core.secrets import encrypt_json
    stamp = db.get(PlatformKeyValue, throttle_key)
    if stamp and (billing.now() - billing.aware(stamp.updated_at)).total_seconds() < 10:
        return order_view(order)
    if stamp is None:
        stamp = PlatformKeyValue(key=throttle_key); db.add(stamp)
    stamp.encrypted_value = encrypt_json({}); stamp.updated_at = billing.now(); db.commit()
    config = get_payment_settings(db, order.channel)
    if payment_gateway.merchant_identity(order.channel, config) != order.merchant_snapshot:
        raise HTTPException(409, '商户配置已变更，请管理员核对原支付订单')
    try:
        result = payment_gateway.query_payment(order.channel, config, order)
    except Exception:
        raise HTTPException(502, '暂未能确认渠道支付结果，请稍后重试；请勿重复付款') from None
    if result:
        transaction_id, amount, merchant = result
        billing.settle_order(db, order.order_no, order.channel, transaction_id, amount, merchant)
    elif billing.aware(order.expires_at) <= billing.now():
        db.refresh(order)
        if order.status != 'paid': order.status = 'expired'; db.commit()
    db.refresh(order)
    return order_view(order)


@router.get('/companies/{company_id}/subscription/usage')
def usage(company_id: uuid.UUID, page: int = Query(1, ge=1), db: Session = Depends(get_db),
          _user: User = Depends(require_permission(Permission.SUBSCRIPTION_VIEW))):
    query = db.query(AIUsage).filter_by(company_id=company_id)
    return {'items': [{'id': row.id, 'kind': row.kind, 'status': row.status,
        'charged_points': row.charged_units / SCALE, 'reserved_points': row.reserved_units / SCALE,
        'input_tokens': row.input_tokens, 'output_tokens': row.output_tokens,
        'video_seconds': row.video_milliseconds / 1000, 'created_at': row.created_at, 'note': row.note}
        for row in query.order_by(AIUsage.created_at.desc()).offset((page-1)*20).limit(20)],
        'total': query.count(), 'page': page, 'page_size': 20}


@router.post('/payments/wechat/notify')
async def wechat_notify(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if len(body) > 65536: raise HTTPException(413, '通知过大')
    config = get_payment_settings(db, 'wechat')
    try: decoded = body.decode('utf-8')
    except UnicodeDecodeError: raise HTTPException(400, '支付通知编码无效') from None
    data = payment_gateway.decode_wechat_callback(config, request.headers, decoded)
    billing.settle_order(db, data['out_trade_no'], 'wechat', data['transaction_id'], data['amount']['total'],
        {'app_id': data.get('appid'), 'merchant_id': data.get('mchid')})
    return {'code': 'SUCCESS', 'message': '成功'}


@router.post('/payments/alipay/notify')
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if len(body) > 65536: raise HTTPException(413, '通知过大')
    from urllib.parse import parse_qsl
    config = get_payment_settings(db, 'alipay')
    try: decoded = body.decode('utf-8')
    except UnicodeDecodeError: raise HTTPException(400, '支付通知编码无效') from None
    data = payment_gateway.decode_alipay_callback(config, parse_qsl(decoded, keep_blank_values=True))
    billing.settle_order(db, data['out_trade_no'], 'alipay', data['trade_no'], payment_gateway.to_fen(data['total_amount']),
        {'app_id': data.get('app_id'), 'seller_id': data.get('seller_id')})
    return Response('success', media_type='text/plain')


@router.get('/admin/billing-settings')
def read_catalog(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return get_catalog(db)


@router.put('/admin/billing-settings')
def update_catalog(data: Catalog, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    result = save_catalog(db, data)
    db.add(AuditLog(user_id=admin.id, action='platform.billing.settings.update', resource_type='platform', resource_id='billing_catalog'))
    db.commit()
    return result


@router.get('/admin/payment-orders')
def admin_orders(page: int = Query(1, ge=1), db: Session = Depends(get_db),
                 _admin: User = Depends(require_platform_admin)):
    query = db.query(PaymentOrder)
    return {'items': [{**order_view(o), 'company_id': o.company_id} for o in query.order_by(PaymentOrder.created_at.desc()).offset((page-1)*20).limit(20)],
            'total': query.count()}


@router.get('/admin/billing-usage')
def admin_usage(page: int = Query(1, ge=1), db: Session = Depends(get_db),
                _admin: User = Depends(require_platform_admin)):
    query = db.query(AIUsage)
    return {'items': [{'id': row.id, 'company_id': row.company_id, 'kind': row.kind, 'status': row.status,
        'points': row.charged_units / SCALE, 'reserved_points': row.reserved_units / SCALE,
        'cost_yuan': row.cost_micro_yuan / 1_000_000, 'created_at': row.created_at}
        for row in query.order_by(AIUsage.created_at.desc()).offset((page-1)*20).limit(20)], 'total': query.count()}


class UsageResolution(BaseModel):
    outcome: Literal['settle', 'release']
    note: str = Field(min_length=5, max_length=250)
    input_tokens: int = Field(default=0, ge=0, le=100_000_000, strict=True)
    output_tokens: int = Field(default=0, ge=0, le=100_000_000, strict=True)
    video_seconds: int = Field(default=0, ge=0, le=3600, strict=True)


@router.post('/admin/billing-usage/{usage_id}/resolve')
def resolve_usage(usage_id: uuid.UUID, data: UsageResolution, db: Session = Depends(get_db),
                  admin: User = Depends(require_platform_admin)):
    if len(data.note.strip()) < 5: raise HTTPException(422, '核对依据至少5字')
    row = db.get(AIUsage, usage_id)
    if row is None: raise HTTPException(404, '用量记录不存在')
    billing.lock_company(db, row.company_id)
    db.refresh(row)
    if row.status in ('settled', 'released'):
        return {'status': row.status}
    if row.status == 'reserved' and (billing.now() - billing.aware(row.created_at)).total_seconds() < 3600:
        raise HTTPException(409, '请求可能仍在执行，预留满1小时后才能手动核对；请勿中断在途计量')
    if data.outcome == 'settle':
        if row.kind == 'video' and (data.video_seconds <= 0 or data.input_tokens or data.output_tokens):
            raise HTTPException(422, '视频结算需填写实际生成秒数，不可填写Token')
        if row.kind == 'llm' and (data.video_seconds or data.input_tokens + data.output_tokens <= 0):
            raise HTTPException(422, '文本结算需填写实际Token数，不可填写视频秒数')
    db.add(AuditLog(user_id=admin.id, action='platform.billing.usage.' + data.outcome,
        resource_type='ai_usage', resource_id=str(row.id)))
    billing.finish(db, row.usage_key, data.outcome, note=data.note.strip(),
        input_tokens=data.input_tokens, output_tokens=data.output_tokens, video_seconds=data.video_seconds)
    return {'status': row.status}
