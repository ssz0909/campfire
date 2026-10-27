"""
Hotel connector tools for agent workflows.

These read from the locally synchronised order store (see
``app/connectors/hotel``). They never fabricate data: when the connector is not
connected or no orders are synced, the result says so explicitly.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session


async def get_hotel_orders(
    company_id: uuid.UUID,
    db: Session,
    limit: int = 50,
) -> dict[str, Any]:
    from app.connectors.hotel.service import HotelConnectorService, ORDER_STATUS_LABELS

    service = HotelConnectorService(company_id, db)
    config = service.get_config()
    if config is None:
        return {"status": "NOT_CONNECTED", "orders": [], "total": 0,
                "note": "酒店连接器尚未配置"}
    orders = service.list_orders(limit=limit)
    return {
        "status": "OK" if orders else "NO_DATA",
        "last_sync_at": config.last_sync_at.isoformat() if config.last_sync_at else None,
        "total": len(orders),
        "orders": [
            {
                "order_num": o.order_num,
                "status": ORDER_STATUS_LABELS.get(o.status),
                "channel": o.channel_name,
                "actual_amount": float(o.actual_amount) if o.actual_amount is not None else None,
                "room_nights": o.room_nights,
                "created_at": o.order_created_at.isoformat() if o.order_created_at else None,
                "check_in_at": o.check_in_at.isoformat() if o.check_in_at else None,
            }
            for o in orders
        ],
        "note": "" if orders else "数据不足：尚无已同步订单",
    }


async def get_hotel_analytics(
    company_id: uuid.UUID,
    db: Session,
    days: int = 30,
) -> dict[str, Any]:
    from app.connectors.hotel.service import HotelConnectorService

    service = HotelConnectorService(company_id, db)
    if service.get_config() is None:
        return {"status": "NOT_CONNECTED", "metrics": None, "note": "酒店连接器尚未配置"}
    end = date.today()
    metrics = service.metrics((end - timedelta(days=days - 1)).isoformat(), end.isoformat())
    return {
        "status": "OK" if metrics["total_orders"] else "NO_DATA",
        "metrics": metrics,
        "note": "" if metrics["total_orders"] else "数据不足：所选范围内无已同步订单",
    }
