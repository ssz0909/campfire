"""Durable AI metering. Reserve before calls, settle once, retain uncertain charges."""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_CEILING
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.billing import AIUsage, SubscriptionPeriod, PaymentOrder
from app.models.company import Company
from app.models.subscription import Subscription
from app.services.billing_catalog import get_catalog, SCALE


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def lock_company(db, company_id):
    company = db.query(Company).filter_by(id=company_id, is_deleted=False).with_for_update().first()
    if company is None:
        raise HTTPException(404, '企业不存在')
    return company


def active_period(db, company_id):
    stamp = now()
    return db.query(SubscriptionPeriod).filter(SubscriptionPeriod.company_id == company_id,
        SubscriptionPeriod.starts_at <= stamp, SubscriptionPeriod.ends_at > stamp).order_by(
        SubscriptionPeriod.starts_at.desc()).populate_existing().first()


def quantities(rates, kind, *, input_tokens=0, output_tokens=0, video_seconds=0):
    if kind not in ('video', 'llm') or min(input_tokens, output_tokens, video_seconds) < 0:
        raise ValueError('Invalid AI usage quantities')
    if kind == 'video':
        ms = int((Decimal(str(video_seconds)) * 1000).to_integral_value(rounding=ROUND_CEILING))
        units = ms * rates['video_points_per_second'] * SCALE // 1000
        cost = ms * rates['video_cost_fen_per_second'] * 10
        return units, cost, ms
    units = input_tokens * rates['llm_input_points_per_million'] + output_tokens * rates['llm_output_points_per_million']
    cost = int((Decimal(input_tokens * rates['llm_input_cost_fen_per_million'] +
                        output_tokens * rates['llm_output_cost_fen_per_million']) / 100).to_integral_value(rounding=ROUND_CEILING))
    return units, cost, 0


def reserve(db: Session, company_id, usage_key, kind, **usage):
    lock_company(db, company_id)
    existing = db.query(AIUsage).filter_by(usage_key=usage_key).first()
    if existing:
        if existing.company_id != company_id:
            raise HTTPException(409, '用量标识冲突')
        return existing
    catalog = get_catalog(db)
    period = active_period(db, company_id)
    rates = {**catalog, **(period.rates if period else {})}
    # Contracted credit rates are immutable; internal cost estimates use current costs.
    rates.update({k: v for k, v in catalog.items() if '_cost_' in k})
    units, _, _ = quantities(rates, kind, **usage)
    if catalog['enforce_billing']:
        if period is None:
            raise HTTPException(402, '当前没有有效订阅，请在订阅页面购买套餐后继续')
        if period.used_units + period.reserved_units + units > period.included_units:
            raise HTTPException(402, '本期AI额度不足，暂未提交模型请求；请等待续期或联系管理员')
    if period:
        period.reserved_units += units
    record = AIUsage(company_id=company_id, period_id=period.id if period else None,
        usage_key=usage_key, kind=kind, status='reserved', reserved_units=units, rates=rates)
    db.add(record); db.commit(); db.refresh(record)
    return record


def finish(db: Session, usage_key: str, outcome: str, *, note=None, **usage):
    if outcome not in ('unknown', 'release', 'settle'):
        raise ValueError('Invalid settlement outcome')
    record = db.query(AIUsage).filter_by(usage_key=usage_key).first()
    if record is None:
        return
    lock_company(db, record.company_id)
    db.refresh(record)
    if record.status in ('settled', 'released'):
        return record
    if outcome == 'unknown':
        record.status = 'unknown'; record.note = note or '上游结果不确定，额度暂时冻结，待核对'
        db.commit(); return record
    period = db.get(SubscriptionPeriod, record.period_id) if record.period_id else None
    if period:
        period.reserved_units -= record.reserved_units
    if outcome == 'release':
        record.status = 'released'; record.charged_units = 0
    else:
        units, cost, ms = quantities(record.rates, record.kind, **usage)
        record.status = 'settled'; record.charged_units = units; record.cost_micro_yuan = cost
        record.input_tokens = usage.get('input_tokens', 0); record.output_tokens = usage.get('output_tokens', 0)
        record.video_milliseconds = ms
        if period:
            period.used_units += units
    record.reserved_units = 0
    record.note = note
    db.commit(); return record


def reserve_call(company_id, key, kind, **usage):
    with SessionLocal() as db:
        return reserve(db, company_id, key, kind, **usage).id


def finish_call(key, outcome, **kwargs):
    with SessionLocal() as db:
        finish(db, key, outcome, **kwargs)


def settle_order(db: Session, order_no, channel, transaction_id, amount_fen, merchant):
    order = db.query(PaymentOrder).filter_by(order_no=order_no, channel=channel).first()
    if order is None:
        raise HTTPException(400, '支付订单不存在')
    lock_company(db, order.company_id)
    order = db.query(PaymentOrder).filter_by(id=order.id).populate_existing().with_for_update().one()
    if (type(amount_fen) is not int or order.amount_fen != amount_fen or
        order.merchant_snapshot != merchant or not isinstance(transaction_id, str) or
        not transaction_id or len(transaction_id) > 100):
        raise HTTPException(400, '支付金额或商户身份不匹配')
    if order.status == 'paid':
        if order.provider_transaction_id != transaction_id:
            raise HTTPException(409, '支付流水不一致')
        return order
    duplicate = db.query(PaymentOrder).filter_by(channel=channel, provider_transaction_id=transaction_id).first()
    if duplicate and duplicate.id != order.id:
        raise HTTPException(409, '支付流水已使用')
    # A provider-confirmed late payment still grants exactly one period.
    latest = db.query(SubscriptionPeriod).filter_by(company_id=order.company_id).order_by(SubscriptionPeriod.ends_at.desc()).first()
    start = max(now(), aware(latest.ends_at)) if latest else now()
    end = start + timedelta(days=30)
    plan = order.plan_snapshot
    db.add(SubscriptionPeriod(company_id=order.company_id, order_id=order.id,
        plan_code=order.plan_code, plan_name=plan['name'], starts_at=start, ends_at=end,
        included_units=plan['included_points'] * SCALE, rates=plan.get('rates', {})))
    order.status = 'paid'; order.paid_at = now(); order.provider_transaction_id = transaction_id
    order.error_message = None
    subscription = db.query(Subscription).filter_by(company_id=order.company_id).order_by(Subscription.created_at.desc()).first()
    if subscription:
        if not latest or aware(latest.ends_at) <= now():
            subscription.plan_name = order.plan_code; subscription.starts_at = start
        subscription.status = 'active'; subscription.ends_at = end
    db.commit(); db.refresh(order)
    return order
