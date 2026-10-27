"""
Business logic for the 订单来了 hotel connector.

Responsibilities
----------------
* Store/read the store-scoped ``authAccessToken`` (encrypted at rest).
* Hold the platform-pushed ticket (encrypted, platform-level state).
* Connect test, order synchronisation and callback processing.
* Redact personal identifiers before persisting order payloads.
* Derive robust business metrics; report insufficient data instead of guessing.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, time as dtime, timezone, timedelta
from typing import Any, Iterable
from decimal import Decimal

from sqlalchemy.orm import Session

from app.connectors.hotel.client import DdllApiError, DdllClient
from app.connectors.hotel.models import (
    HotelConnectorConfig,
    HotelOrder,
    HotelSyncJob,
    PlatformKeyValue,
)
from app.core.secrets import decrypt_json, encrypt_json, mask
from app.config import settings

logger = logging.getLogger(__name__)

TICKET_KEY = "ddll_ticket"
COMPONENT_TOKEN_KEY = "ddll_component_token"
# Re-mint the store token when fewer than this many seconds remain.
TOKEN_REFRESH_MARGIN_S = 300
STORE_REFRESH_TOKEN_TTL_S = 30 * 24 * 3600  # authRefreshToken lifetime (per vendor doc)
ORDER_STATUS_LABELS = {2: "已预订", 3: "进行中", 4: "已取消", 7: "已完成"}
ACTIVE_STATUSES = (2, 3, 7)
CANCELLED_STATUS = 4

# Personal-data keys removed (or masked) from stored order payloads.
_PII_KEYS = {"reservePhone", "phone", "identityNo", "reserveName", "name"}


def _dt(value: Any) -> datetime | None:
    """Parse the platform's date/datetime strings; return None when unparseable."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[: len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _date(value: Any) -> str | None:
    parsed = _dt(value)
    return parsed.strftime("%Y-%m-%d") if parsed else None


def _redact(payload: Any) -> Any:
    """Remove/mask personal identifiers from a nested structure."""
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            if key in _PII_KEYS:
                # Keep a masked hint only where it aids operations; drop names entirely.
                out[key] = mask(str(value)) if key.lower().endswith("phone") else None
            else:
                out[key] = _redact(value)
        return out
    if isinstance(payload, list):
        return [_redact(item) for item in payload]
    return payload


def store_ticket(db: Session, ticket: str, expire: Any = None) -> None:
    """Persist the platform-pushed ticket (platform-level, encrypted)."""
    now = datetime.now(timezone.utc)
    blob = encrypt_json({"ticket": ticket, "expire": expire})
    row = db.get(PlatformKeyValue, TICKET_KEY)
    if row is None:
        row = PlatformKeyValue(key=TICKET_KEY, encrypted_value=blob, updated_at=now)
    else:
        row.encrypted_value = blob
        row.updated_at = now
    db.add(row)
    db.commit()


def get_ticket(db: Session) -> dict[str, Any]:
    row = db.get(PlatformKeyValue, TICKET_KEY)
    return decrypt_json(row.encrypted_value) if row else {}


from app.connectors.hotel.web_service import HotelWebServiceMixin


class HotelConnectorService(HotelWebServiceMixin):
    def __init__(self, company_id: uuid.UUID, db: Session) -> None:
        self.company_id = company_id
        self.db = db

    def get_config(self) -> HotelConnectorConfig | None:
        return (
            self.db.query(HotelConnectorConfig)
            .filter(HotelConnectorConfig.company_id == self.company_id)
            .first()
        )

    def save_config(
        self,
        *,
        hotel_num: int | str | None = None,
        auth_access_token: str | None = None,
    ) -> HotelConnectorConfig:
        """
        Create or update the connector. The store token is optional: when omitted
        it is minted automatically from the app credentials + platform ticket. A
        manually supplied token is kept encrypted and used until it fails.
        """
        config = self.get_config()
        if config is None:
            config = HotelConnectorConfig(company_id=self.company_id)
            self.db.add(config)
        if config.hotel_num and hotel_num is not None and config.hotel_num != int(hotel_num):
            raise ValueError("该企业已绑定另一门店，请使用独立企业空间")
        if self.is_web(config):
            raise ValueError("Web 连接请使用账号登录与门店选择更新")
        if hotel_num is not None:
            config.hotel_num = int(hotel_num)
        if auth_access_token:
            config.encrypted_credentials = encrypt_json({"auth_access_token": auth_access_token})
        config.status = "configured"
        self.db.commit()
        self.db.refresh(config)
        return config

    def masked_config_summary(self) -> dict[str, Any]:
        config = self.get_config()
        if config is None:
            return {"configured": False, "status": "unconfigured"}
        creds = decrypt_json(config.encrypted_credentials)
        token = creds.get("auth_access_token")
        expires_at = creds.get("auth_expires_at")
        if creds.get("auth_refresh_token"):
            mode = "auto"
        elif token:
            mode = "manual"
        else:
            mode = "none"
        return {
            "configured": bool(config.hotel_num),
            "connection_mode": "web" if self.is_web(config) else "open_api",
            "web_session_active": self.is_web(config),
            "status": config.status,
            "hotel_num": config.hotel_num,
            "hotel_name": config.hotel_name,
            "room_count": config.room_count,
            "auth_access_token": mask(token),
            "token_mode": "web" if self.is_web(config) else mode,
            "token_expires_at": (
                datetime.fromtimestamp(expires_at, timezone.utc).isoformat() if expires_at else None
            ),
            "auto_token_available": bool(settings.DDLL_APP_CODE and settings.DDLL_APP_SECRET),
            "last_connect_at": config.last_connect_at,
            "last_sync_at": config.last_sync_at,
            "last_sync_status": config.last_sync_status,
            "last_sync_error": config.last_sync_error,
            "last_sync_stats": config.last_sync_stats,
        }

    def _client(self, config: HotelConnectorConfig) -> DdllClient:
        token = decrypt_json(config.encrypted_credentials).get("auth_access_token")
        return DdllClient(
            app_code=settings.DDLL_APP_CODE,
            app_secret=settings.DDLL_APP_SECRET,
            auth_access_token=token,
        )

    # ------------------------------------------------------------------
    # Token lifecycle
    #   ticket (pushed ~10 min) -> componentAccessToken -> authAccessToken (2h)
    # ------------------------------------------------------------------

    def _app_client(self) -> DdllClient:
        return DdllClient(app_code=settings.DDLL_APP_CODE, app_secret=settings.DDLL_APP_SECRET)

    async def _component_token(self, client: DdllClient, *, force: bool = False) -> str:
        row = self.db.get(PlatformKeyValue, COMPONENT_TOKEN_KEY)
        cached = decrypt_json(row.encrypted_value) if row else {}
        if not force and cached.get("token") and cached.get("expires_at", 0) > time.time() + 60:
            return cached["token"]

        ticket = get_ticket(self.db).get("ticket")
        if not ticket:
            raise DdllApiError(
                "NO_TICKET",
                "尚未收到订单来了推送的 ticket：请确认回调地址已在平台登记且可公网访问，"
                "或由平台管理员手动录入当前 ticket",
                endpoint="/open/platform/api/tp/token",
            )
        data = await client.request_component_token(ticket=ticket)
        token = data.get("componentAccessToken")
        if not token:
            raise DdllApiError(
                "NO_COMPONENT_TOKEN",
                f"响应中缺少 componentAccessToken（实际字段: {sorted(data)}）",
                endpoint="/open/platform/api/tp/token",
            )
        try:
            ttl = float(data.get("expire") or data.get("expiresIn") or 3600)
        except (TypeError, ValueError):
            ttl = 3600.0
        now = datetime.now(timezone.utc)
        blob = encrypt_json({"token": token, "expires_at": time.time() + ttl - 60})
        if row is None:
            row = PlatformKeyValue(key=COMPONENT_TOKEN_KEY, encrypted_value=blob, updated_at=now)
        else:
            row.encrypted_value, row.updated_at = blob, now
        self.db.add(row)
        self.db.commit()
        return token

    async def ensure_store_token(
        self, config: HotelConnectorConfig, *, force: bool = False
    ) -> str | None:
        """
        Return a usable store call credential, minting a new one when absent,
        expired (or about to), or ``force`` is set.

        A manually entered token has no known expiry and is used as-is unless
        ``force`` is set or app credentials are missing (then it is all we have).
        The 30-day ``authRefreshToken`` is stored for the day its endpoint is
        documented; until then expiry is handled by minting again.
        """
        creds = decrypt_json(config.encrypted_credentials)
        token = creds.get("auth_access_token")
        expires_at = creds.get("auth_expires_at")
        still_valid = token and (
            expires_at is None or expires_at > time.time() + TOKEN_REFRESH_MARGIN_S
        )
        if still_valid and not force:
            return token
        if not (settings.DDLL_APP_CODE and settings.DDLL_APP_SECRET and config.hotel_num):
            return token  # cannot mint; fall back to whatever we hold

        client = self._app_client()
        try:
            component = await self._component_token(client)
            data = await client.request_store_token(
                component_access_token=component, hotel_num=config.hotel_num
            )
        except DdllApiError as exc:
            if exc.code in {"-5", "-7", "70004", "70005"}:  # app credential expired/invalid
                component = await self._component_token(client, force=True)
                data = await client.request_store_token(
                    component_access_token=component, hotel_num=config.hotel_num
                )
            else:
                raise

        new_token = data.get("authAccessToken")
        if not new_token:
            raise DdllApiError(
                "NO_STORE_TOKEN",
                f"响应中缺少 authAccessToken（实际字段: {sorted(data)}）",
                endpoint="/open/platform/api/tp/auth/token",
            )
        try:
            ttl = float(data.get("expire") or 7200)
        except (TypeError, ValueError):
            ttl = 7200.0
        now = time.time()
        config.encrypted_credentials = encrypt_json(
            {
                "auth_access_token": new_token,
                "auth_expires_at": now + ttl,
                "auth_refresh_token": data.get("authRefreshToken"),
                "refresh_expires_at": now + STORE_REFRESH_TOKEN_TTL_S,
            }
        )
        self.db.commit()
        return new_token

    async def _authed_client(
        self, config: HotelConnectorConfig, *, force: bool = False
    ) -> DdllClient:
        await self.ensure_store_token(config, force=force)
        return self._client(config)

    # ------------------------------------------------------------------
    # Connect test
    # ------------------------------------------------------------------

    async def connect_test(self) -> dict[str, Any]:
        config = self.get_config()
        if config is None or not config.hotel_num:
            return {
                "connected": False,
                "status": "unconfigured",
                "message": "尚未配置门店编号与授权门店调用凭证",
            }
        if self.is_web(config):
            return await self.web_connect_test(config)
        if not settings.DDLL_APP_CODE or not settings.DDLL_APP_SECRET:
            return {
                "connected": False,
                "status": "missing_app_credentials",
                "message": "服务端缺少 DDLL_APP_CODE / DDLL_APP_SECRET",
            }
        try:
            client = await self._authed_client(config)
            try:
                hotel = await client.fetch_hotel(config.hotel_num)
            except DdllApiError as exc:
                if exc.code not in {"70012", "70013", "-1", "-5"}:
                    raise
                client = await self._authed_client(config, force=True)  # token expired: re-mint once
                hotel = await client.fetch_hotel(config.hotel_num)
            rooms = await client.list_room_infos(config.hotel_num)
            config.hotel_name = hotel.get("hotelName") or config.hotel_name
            config.hotel_info = hotel
            room_types = rooms.get("roomTypeList") or []
            config.room_types = room_types
            config.room_count = sum(len(rt.get("roomList") or []) for rt in room_types)
            config.status = "connected"
            config.last_connect_at = datetime.now(timezone.utc)
            config.last_sync_error = None
            self.db.commit()
            return {
                "connected": True,
                "status": "connected",
                "message": "连接成功",
                "hotel_name": config.hotel_name,
                "room_type_count": len(room_types),
                "room_count": config.room_count,
                "hotel_status": hotel.get("status"),
            }
        except DdllApiError as exc:
            config.status = "error"
            config.last_sync_error = f"[{exc.code}] {exc.message}"
            self.db.commit()
            return {
                "connected": False,
                "status": "error",
                "code": exc.code,
                "message": exc.message,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("connect test failed for company %s", self.company_id)
            return {
                "connected": False,
                "status": "error",
                "message": f"连接异常: {type(exc).__name__}",
            }

    # ------------------------------------------------------------------
    # Order sync
    # ------------------------------------------------------------------

    async def create_sync_job(
        self,
        *,
        trigger: str = "manual",
        requested_by: uuid.UUID | None = None,
        begin_date: str | None = None,
        end_date: str | None = None,
    ) -> HotelSyncJob:
        today = datetime.now().date()
        job = HotelSyncJob(
            company_id=self.company_id,
            trigger=trigger,
            status="queued",
            requested_by=requested_by,
            begin_date=begin_date or (today - timedelta(days=30)).isoformat(),
            end_date=end_date or today.isoformat(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    async def run_sync(self, job: HotelSyncJob) -> HotelSyncJob:
        """Sync order numbers in the job's window, then fetch each order's detail."""
        config = self.get_config()
        if config is None or not config.hotel_num:
            job.status = "failed"
            job.error = "连接器未配置"
            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            return job

        if job.company_id != self.company_id:
            raise ValueError("Sync job tenant mismatch")
        if self.is_web(config):
            return await self.run_web_sync(job, config)

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()

        try:
            client = await self._authed_client(config)
            page = 1
            seen = 0
            synced = 0
            failed = 0
            while True:
                result = await client.search_orders(
                    hotel_num=config.hotel_num,
                    date_type=1,
                    begin_date=job.begin_date,
                    end_date=job.end_date,
                    page_num=page,
                )
                order_nums = result.get("list") or []
                seen += len(order_nums)
                for order_num in order_nums:
                    try:
                        detail = await client.order_detail(
                            hotel_num=config.hotel_num, order_num=order_num
                        )
                        self._upsert_order(config.hotel_num, str(order_num), detail)
                        synced += 1
                    except DdllApiError as exc:
                        # An order that no longer resolves is marked invalid, not failed.
                        if exc.code == "AO-50017":
                            self._mark_invalid(config.hotel_num, str(order_num))
                        else:
                            failed += 1
                            logger.warning("order %s sync failed: %s", order_num, exc)
                    except Exception:  # noqa: BLE001
                        failed += 1
                        logger.exception("order %s sync error", order_num)
                if result.get("boolLastPage") or not order_nums:
                    break
                page += 1

            job.orders_found = seen
            job.orders_synced = synced
            job.orders_failed = failed
            job.status = "success" if failed == 0 else "partial"
            job.finished_at = datetime.now(timezone.utc)

            config.last_sync_at = datetime.now(timezone.utc)
            config.last_sync_status = job.status
            config.last_sync_stats = {"found": seen, "synced": synced, "failed": failed}
            config.last_sync_error = None if failed == 0 else f"{failed} 个订单同步失败"
            self.db.commit()
            return job
        except DdllApiError as exc:
            job.status = "failed"
            job.error = f"[{exc.code}] {exc.message}"
            job.finished_at = datetime.now(timezone.utc)
            if config:
                config.last_sync_status = "failed"
                config.last_sync_error = job.error
            self.db.commit()
            return job
        except Exception as exc:  # noqa: BLE001
            logger.exception("sync job %s failed", job.id)
            job.status = "failed"
            job.error = f"同步异常: {type(exc).__name__}"
            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            return job

    def _upsert_order(
        self, hotel_num: int, order_num: str, detail: dict[str, Any]
    ) -> HotelOrder:
        order = (
            self.db.query(HotelOrder)
            .filter(
                HotelOrder.company_id == self.company_id,
                HotelOrder.hotel_num == hotel_num,
                HotelOrder.order_num == order_num,
            )
            .first()
        )
        if order is None:
            order = HotelOrder(
                company_id=self.company_id, hotel_num=hotel_num, order_num=order_num
            )
            self.db.add(order)

        rows = detail.get("list") or []
        record = rows[0] if rows else {}
        nights: list[dict[str, Any]] = []
        check_ins: list[datetime] = []
        check_outs: list[datetime] = []
        for room in record.get("accomOrderInfos") or []:
            if room.get("status") == 50:  # 已取消的房间不计入
                continue
            ci, co = _dt(room.get("checkInTime")), _dt(room.get("checkOutTime"))
            if ci:
                check_ins.append(ci)
            if co:
                check_outs.append(co)
            for entry in room.get("dateAmountInfos") or []:
                nights.append(
                    {
                        "date": _date(entry.get("date")),
                        "room_code": room.get("roomCode"),
                        "room_type": room.get("roomTypeName"),
                        "amount": entry.get("amount"),
                    }
                )

        order.status = record.get("status")
        order.is_invalid = False
        order.channel_type = record.get("channelType")
        order.channel_name = str(record.get("channelName")) if record.get("channelName") is not None else None
        order.pay_type = record.get("payType")
        order.currency = record.get("currency") or "CNY"
        order.actual_amount = record.get("actualAmount")
        order.paid_amount = record.get("paidAmount")
        order.order_created_at = _dt(record.get("createTime"))
        order.check_in_at = min(check_ins) if check_ins else None
        order.check_out_at = max(check_outs) if check_outs else None
        order.room_count = len([r for r in (record.get("accomOrderInfos") or []) if r.get("status") != 50])
        order.room_nights = sum(1 for n in nights if n.get("date"))
        order.nights = nights
        order.detail = _redact(detail)
        order.synced_at = datetime.now(timezone.utc)
        return order

    def _mark_invalid(self, hotel_num: int, order_num: str) -> None:
        order = (
            self.db.query(HotelOrder)
            .filter(
                HotelOrder.company_id == self.company_id,
                HotelOrder.hotel_num == hotel_num,
                HotelOrder.order_num == order_num,
            )
            .first()
        )
        if order:
            order.is_invalid = True
            order.synced_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Callback processing
    # ------------------------------------------------------------------

    def apply_order_change(self, payload: dict[str, Any], event_type: int | None = None) -> dict[str, Any]:
        """
        Record an order-change notification. The message only carries identifiers
        plus the change type, so we update status/invalidity and let the next sync
        fetch the full detail.
        """
        order_num = str(payload.get("orderNum") or "")
        if not order_num:
            return {"handled": False, "reason": "missing orderNum"}
        order = (
            self.db.query(HotelOrder)
            .filter(
                HotelOrder.company_id == self.company_id,
                HotelOrder.order_num == order_num,
            )
            .first()
        )
        if event_type == 3:
            action = "cancelled"
            if order:
                order.status = CANCELLED_STATUS
        elif event_type == 4:
            action = "completed"
            if order:
                order.status = 7
        elif event_type == 9:
            action = "merged_away"
            if order:
                order.is_invalid = True
        else:
            action = "needs_resync"

        if order:
            order.last_event_type = event_type
            order.synced_at = datetime.now(timezone.utc)
        self.db.commit()
        return {"handled": True, "action": action, "order_num": order_num, "event_type": event_type}

    # ------------------------------------------------------------------
    # Queries & metrics
    # ------------------------------------------------------------------

    def list_orders(
        self,
        *,
        status: int | None = None,
        include_invalid: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HotelOrder]:
        query = self.db.query(HotelOrder).filter(HotelOrder.company_id == self.company_id)
        if not include_invalid:
            query = query.filter(HotelOrder.is_invalid == False)  # noqa: E712
        if status is not None:
            query = query.filter(HotelOrder.status == status)
        return (
            query.order_by(HotelOrder.order_created_at.desc().nullslast())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def metrics(self, date_from: str, date_to: str) -> dict[str, Any]:
        """
        Compute order metrics for the window. ``occupancy_rate`` is only produced
        when room capacity AND per-date room-nights are both available; otherwise
        it is reported as unavailable with the reason.
        """
        start = datetime.combine(datetime.fromisoformat(date_from).date(), dtime.min)
        end = datetime.combine(datetime.fromisoformat(date_to).date(), dtime.max)
        orders = (
            self.db.query(HotelOrder)
            .filter(
                HotelOrder.company_id == self.company_id,
                HotelOrder.order_created_at >= start,
                HotelOrder.order_created_at <= end,
            )
            .all()
        )

        total = len(orders)
        cancelled = sum(1 for o in orders if o.status == CANCELLED_STATUS)
        active = [o for o in orders if o.status in ACTIVE_STATUSES]
        room_nights = sum(o.room_nights or 0 for o in active)
        revenue = sum(float(o.actual_amount or 0) for o in active)

        metrics: dict[str, Any] = {
            "date_from": date_from,
            "date_to": date_to,
            "total_orders": total,
            "cancelled_orders": cancelled,
            "cancellation_rate": round(cancelled / total, 4) if total else None,
            "active_orders": len(active),
            "room_nights": room_nights,
            "revenue": round(revenue, 2),
            "average_room_nightly_rate": round(revenue / room_nights, 2) if room_nights else None,
            "average_order_value": round(revenue / len(active), 2) if active else None,
            "orders_by_status": _count_by(orders, lambda o: o.status),
        }

        if self.is_web():
            web_orders = [o for o in orders if (o.detail or {}).get("source") == "dingdandao_web"]
            amounts = [Decimal(str(o.detail["sumAmount"])) for o in web_orders if o.status in ACTIVE_STATUSES and o.detail.get("sumAmount") is not None]
            metrics.update(revenue=None, average_room_nightly_rate=None, average_order_value=None,
                           order_amount=float(sum(amounts)) if amounts else None,
                           revenue_note="Web 订单列表提供订单/住宿金额，不提供实收营收；不得视为财务收入",
                           occupancy_rate=None, occupancy_note="数据不足：订单按创建日期同步，尚不构成完整营业日入住数据",
                           metric_basis="order_created_at Asia/Shanghai")
            metrics["average_lead_time_days"] = self._lead_time_days(active)
            return metrics

        capacity = self._capacity_room_nights(date_from, date_to)
        if capacity is None or not room_nights:
            metrics["occupancy_rate"] = None
            metrics["occupancy_note"] = (
                "数据不足：需要门店房量信息与逐日间夜数据才能计算入住率"
            )
        else:
            metrics["occupancy_rate"] = round(min(room_nights / capacity, 1.0), 4)
            metrics["capacity_room_nights"] = capacity

        metrics["average_lead_time_days"] = self._lead_time_days(active)
        return metrics

    def _capacity_room_nights(self, date_from: str, date_to: str) -> int | None:
        config = self.get_config()
        if not config or not config.room_count:
            return None
        try:
            days = (datetime.fromisoformat(date_to).date() - datetime.fromisoformat(date_from).date()).days + 1
        except ValueError:
            return None
        return max(config.room_count * days, 0)

    @staticmethod
    def _lead_time_days(orders: Iterable[HotelOrder]) -> float | None:
        leads = [
            (o.check_in_at - o.order_created_at).days
            for o in orders
            if o.check_in_at and o.order_created_at
        ]
        return round(sum(leads) / len(leads), 2) if leads else None


def _count_by(orders: Iterable[HotelOrder], key) -> dict[str, int]:
    counts: dict[str, int] = {}
    for order in orders:
        label = key(order)
        counts[str(label)] = counts.get(str(label), 0) + 1
    return counts
