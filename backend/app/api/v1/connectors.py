from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.connectors.hotel.web_client import DddWebError
from app.connectors.hotel.models import HotelSyncJob
from app.connectors.hotel.service import HotelConnectorService, ORDER_STATUS_LABELS
from app.core.permissions import Permission, require_permission
from app.database import SessionLocal, get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter()


class HotelConfigRequest(BaseModel):
    hotel_num: int = Field(..., gt=0, description="订单来了门店编号")
    # Optional on update so the hotel number can change without re-entering the token.
    auth_access_token: str | None = Field(None, min_length=1, description="可选：不填则由系统用应用凭证自动获取")


class SyncRequest(BaseModel):
    begin_date: date | None = None
    end_date: date | None = None


def _audit(db: Session, company_id: uuid.UUID, user: User, action: str, details: dict[str, Any]) -> None:
    db.add(
        AuditLog(
            company_id=company_id,
            user_id=user.id,
            action=action,
            resource_type="hotel_connector",
            resource_id=str(company_id),
            details=details,
        )
    )
    db.commit()


def _job_dict(job: HotelSyncJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "status": job.status,
        "trigger": job.trigger,
        "begin_date": job.begin_date,
        "end_date": job.end_date,
        "orders_found": job.orders_found,
        "orders_synced": job.orders_synced,
        "orders_failed": job.orders_failed,
        "error": job.error,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
    }


@router.get("/{company_id}/connectors")
def list_connectors(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.CONNECTOR_VIEW)),
    db: Session = Depends(get_db),
):
    summary = HotelConnectorService(company_id, db).masked_config_summary()
    return {
        "connectors": [
            {
                "type": "hotel",
                "provider": "dingdanlaile",
                "status": summary.get("status"),
                "last_sync_at": summary.get("last_sync_at"),
            }
        ]
    }


@router.get("/{company_id}/connectors/hotel")
def get_hotel_connector(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.CONNECTOR_VIEW)),
    db: Session = Depends(get_db),
):
    """Current configuration. The store token is only ever returned masked."""
    return HotelConnectorService(company_id, db).masked_config_summary()


@router.post("/{company_id}/connectors/hotel")
def configure_hotel_connector(
    company_id: uuid.UUID,
    data: HotelConfigRequest,
    current_user: User = Depends(require_permission(Permission.CONNECTOR_CONFIG)),
    db: Session = Depends(get_db),
):
    from sqlalchemy.exc import IntegrityError

    service = HotelConnectorService(company_id, db)
    try:
        service.save_config(hotel_num=data.hotel_num, auth_access_token=data.auth_access_token)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "该门店编号已被其他企业绑定")
    _audit(
        db,
        company_id,
        current_user,
        "connector.hotel.configure",
        {"hotel_num": data.hotel_num, "token_updated": bool(data.auth_access_token)},
    )
    return service.masked_config_summary()


@router.post("/{company_id}/connectors/hotel/test")
async def test_hotel_connector(
    company_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.CONNECTOR_CONFIG)),
    db: Session = Depends(get_db),
):
    """Perform a real call (hotel profile + room inventory) against 订单来了."""
    result = await HotelConnectorService(company_id, db).connect_test()
    _audit(db, company_id, current_user, "connector.hotel.test", {"connected": result["connected"]})
    return result


@router.post("/{company_id}/connectors/hotel/logout")
def logout_hotel_connector(
    company_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.CONNECTOR_CONFIG)),
    db: Session = Depends(get_db),
):
    """Remove the stored 订单来了 session and credentials for this company."""
    service = HotelConnectorService(company_id, db)
    config = service.get_config()
    if config is not None:
        config.encrypted_credentials = None
        config.status = "unconfigured"
        config.hotel_num = None
        config.hotel_name = None
        config.hotel_info = None
        config.room_types = None
        config.room_count = None
        config.last_connect_at = None
        db.commit()
    _audit(db, company_id, current_user, "connector.hotel.logout", {})
    return {"configured": False, "status": "unconfigured"}


# Kept for backward compatibility with the earlier GET status endpoint.
@router.get("/{company_id}/connectors/hotel/status")
async def hotel_connector_status(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.CONNECTOR_VIEW)),
    db: Session = Depends(get_db),
):
    return HotelConnectorService(company_id, db).masked_config_summary()


async def _run_sync_in_background(company_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """Runs with its own session: the request-scoped one is closed by then."""
    db = SessionLocal()
    try:
        job = db.get(HotelSyncJob, job_id)
        if job is not None:
            await HotelConnectorService(company_id, db).run_sync(job)
    finally:
        db.close()


@router.post("/{company_id}/connectors/hotel/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_hotel_sync(
    company_id: uuid.UUID,
    background: BackgroundTasks,
    data: SyncRequest | None = None,
    current_user: User = Depends(require_permission(Permission.CONNECTOR_CONFIG)),
    db: Session = Depends(get_db),
):
    """Queue an order synchronisation and return the job id for polling."""
    service = HotelConnectorService(company_id, db)
    config = service.get_config()
    if config is None or not config.hotel_num:
        raise HTTPException(status.HTTP_409_CONFLICT, "请先配置酒店连接器")

    running = (
        db.query(HotelSyncJob)
        .filter(
            HotelSyncJob.company_id == company_id,
            HotelSyncJob.status.in_(("queued", "running")),
        )
        .first()
    )
    if running is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "已有同步任务正在执行")

    data = data or SyncRequest()
    begin = data.begin_date or (date.today() - timedelta(days=30))
    end = data.end_date or date.today()
    if end < begin:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "结束日期不能早于开始日期")
    if not service.is_web(config) and (date.today() - begin).days > 90:
        # This restriction applies to the open API, not the Web date filters.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "订单来了仅提供最近 90 天的订单数据")

    if end > date.today():
        raise HTTPException(422, "同步结束日期不能晚于今天")

    job = await service.create_sync_job(
        trigger="manual",
        requested_by=current_user.id,
        begin_date=begin.isoformat(),
        end_date=end.isoformat(),
    )
    _audit(db, company_id, current_user, "connector.hotel.sync", {"job_id": str(job.id)})
    background.add_task(_run_sync_in_background, company_id, job.id)
    return _job_dict(job)


@router.get("/{company_id}/connectors/hotel/sync-jobs")
def list_sync_jobs(
    company_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    _: User = Depends(require_permission(Permission.CONNECTOR_VIEW)),
    db: Session = Depends(get_db),
):
    jobs = (
        db.query(HotelSyncJob)
        .filter(HotelSyncJob.company_id == company_id)
        .order_by(HotelSyncJob.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_job_dict(j) for j in jobs]


@router.get("/{company_id}/connectors/hotel/orders")
def get_hotel_orders(
    company_id: uuid.UUID,
    status_filter: int | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_permission(Permission.CONNECTOR_VIEW)),
    db: Session = Depends(get_db),
):
    """Locally synchronised orders (no live call to 订单来了)."""
    orders = HotelConnectorService(company_id, db).list_orders(
        status=status_filter, limit=limit, offset=offset
    )
    return {
        "orders": [
            {
                "order_num": o.order_num,
                "status": o.status,
                "status_label": ORDER_STATUS_LABELS.get(o.status),
                "channel_name": o.channel_name,
                "actual_amount": float(o.actual_amount) if o.actual_amount is not None else None,
                "paid_amount": float(o.paid_amount) if o.paid_amount is not None else None,
                "currency": o.currency,
                "room_count": o.room_count,
                "room_nights": o.room_nights,
                "order_created_at": o.order_created_at,
                "check_in_at": o.check_in_at,
                "check_out_at": o.check_out_at,
                "synced_at": o.synced_at,
                "order_amount": (o.detail or {}).get("sumAmount"),
                "source": (o.detail or {}).get("source", "dingdanlaile_open_api"),
            }
            for o in orders
        ],
        "count": len(orders),
    }


@router.get("/{company_id}/connectors/hotel/daily-report")
async def hotel_daily_report(
    company_id: uuid.UUID,
    biz_date: date = Query(..., description="营业日，不能晚于今天"),
    _: User = Depends(require_permission(Permission.CONNECTOR_VIEW)),
    db: Session = Depends(get_db),
):
    if biz_date > date.today():
        raise HTTPException(422, "营业日不能晚于今天")
    service = HotelConnectorService(company_id, db)
    config = service.get_config()
    if config is None or not service.is_web(config):
        raise HTTPException(409, "请先使用订单来了账号连接门店")
    try:
        return await service.web_daily_report(config, biz_date.isoformat())
    except DddWebError as exc:
        raise _web_error(exc) from exc


@router.get("/{company_id}/connectors/hotel/rooms")
def get_hotel_rooms(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.CONNECTOR_VIEW)),
    db: Session = Depends(get_db),
):
    """Room inventory captured at the last successful connection test."""
    config = HotelConnectorService(company_id, db).get_config()
    if config is None:
        return {"room_types": [], "room_count": None}
    return {
        "hotel_name": config.hotel_name,
        "room_count": config.room_count,
        "room_types": config.room_types or [],
    }


class DddWebLoginRequest(BaseModel):
    phone: str = Field(..., pattern=r"^(?:\+86)?1\d{10}$", max_length=14)
    password: str = Field(..., min_length=1, max_length=256, repr=False)
    sms_captcha: str = Field("", pattern=r"^(?:\d{6})?$", repr=False)


class DddStoreRequest(BaseModel):
    ntw_id: str = Field(..., pattern=r"^\d+$", max_length=30)


def _web_error(exc):
    code = 409 if exc.code in {"STORE_CONFLICT", "NO_SESSION", "STORE_MISMATCH"} else 502
    return HTTPException(code, {"code":exc.code, "message":exc.message})


@router.post("/{company_id}/connectors/hotel/ddd-login")
async def ddd_web_login(
    company_id: uuid.UUID,
    data: DddWebLoginRequest,
    current_user: User = Depends(require_permission(Permission.CONNECTOR_CONFIG)),
    db: Session = Depends(get_db),
):
    """Authenticate once; keep encrypted session server-side. Never return a token."""
    service = HotelConnectorService(company_id, db)
    try:
        result = await service.web_login(data.phone, data.password, data.sms_captcha)
    except DddWebError as exc:
        raise _web_error(exc) from exc
    _audit(db, company_id, current_user, "connector.hotel.web_login",
           {"verification_required":result["verification_required"]})
    return result


@router.post("/{company_id}/connectors/hotel/ddd-store")
async def ddd_select_store(
    company_id: uuid.UUID,
    data: DddStoreRequest,
    current_user: User = Depends(require_permission(Permission.CONNECTOR_CONFIG)),
    db: Session = Depends(get_db),
):
    from sqlalchemy.exc import IntegrityError
    service = HotelConnectorService(company_id, db)
    try:
        result = await service.web_bind(data.ntw_id)
    except DddWebError as exc:
        raise _web_error(exc) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "该门店已被其他企业绑定") from exc
    _audit(db, company_id, current_user, "connector.hotel.web_bind", {"hotel_num":result["hotel_num"]})
    return result
