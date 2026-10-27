"""Tenant-bound web sessions and PMS snapshots. Passwords are never persisted."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.connectors.hotel.models import HotelConnectorConfig, HotelOrder
from app.connectors.hotel.web_client import DddWebClient, DddWebError, SHANGHAI
from app.core.secrets import decrypt_json, encrypt_json


def local_dt(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise DddWebError("时间字段格式变更", code="SCHEMA_CHANGED")
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError as exc:
        raise DddWebError("时间字段格式变更", code="SCHEMA_CHANGED") from exc


def normalize_order(row):
    """Allowlist only; no contact details, guest names, staff names or remarks."""
    if not isinstance(row, dict) or not row.get("orderNum") or not isinstance(row.get("serviceList"), list):
        raise DddWebError("订单字段变更，无法安全转换", code="SCHEMA_CHANGED")
    safe = {k: row[k] for k in ("orderNum", "orderStatus", "originName", "sumAmount", "createTime", "currency") if k in row}
    services = []
    nights = []
    checkins, checkouts = [], []
    for room in row["serviceList"]:
        if not isinstance(room, dict):
            raise DddWebError("住宿字段变更", code="SCHEMA_CHANGED")
        service = {k:room[k] for k in ("accomServiceId", "roomTypeName", "roomId", "roomName", "status",
                   "checkinTime", "checkoutTime", "amount", "roomFee", "night", "checkinType", "guestNumber") if k in room}
        services.append(service)
        if room.get("status") not in {40, 70, 80}:
            continue
        ci, co = local_dt(room.get("checkinTime")), local_dt(room.get("checkoutTime"))
        if ci: checkins.append(ci)
        if co: checkouts.append(co)
        # Only exact upstream night counts are used (hourly rooms and NoShow must not inflate occupancy).
        count = room.get("night")
        if not isinstance(count, int) or not ci or not co or count < 0 or count > 730:
            continue
        if count != (co.date()-ci.date()).days:
            continue
        for day in range(count):
            nights.append({"date": (ci.date()+timedelta(days=day)).isoformat(), "room_code": room.get("roomId"),
                           "room_type": room.get("roomTypeName"), "amount": None,
                           "service_status": room.get("status")})
    safe["serviceList"] = services
    safe["source"] = "dingdandao_web"
    return safe, nights, checkins, checkouts


class HotelWebServiceMixin:
    def is_web(self, config=None):
        config = config or self.get_config()
        return bool(config and decrypt_json(config.encrypted_credentials).get("web_session"))

    def web_client(self, config=None):
        config = config or self.get_config()
        creds = decrypt_json(config.encrypted_credentials) if config else {}
        session = creds.get("web_session")
        if not session or not config.hotel_num:
            raise DddWebError("请先登录并选择门店", code="NO_SESSION")
        return DddWebClient(**session, ntw_num=config.hotel_num)

    async def web_login(self, phone, password, sms_captcha=""):
        config = self.get_config()
        creds = decrypt_json(config.encrypted_credentials) if config else {}
        pending = creds.get("web_pending") or {}
        if sms_captcha and (not pending.get("login_ticket") or pending.get("expires_at",0)<datetime.now(timezone.utc).timestamp()):
            raise DddWebError("验证已过期，请重新登录", code="VERIFICATION_EXPIRED")
        client = DddWebClient(device_id=pending.get("device_id"))
        result = await client.login(phone, password, sms_captcha=sms_captcha, login_ticket=pending.get("login_ticket") if sms_captcha else None)
        if config is None:
            config = HotelConnectorConfig(company_id=self.company_id, status="unconfigured")
            self.db.add(config)
        if result.get("verification_required"):
            creds["web_pending"] = {**result, "expires_at":datetime.now(timezone.utc).timestamp()+300}
            stores = []
        else:
            stores = await client.list_stores()
            creds["web_pending"] = {**result, "expires_at":datetime.now(timezone.utc).timestamp()+900}
        config.encrypted_credentials = encrypt_json(creds)
        self.db.commit()
        return {"verification_required": bool(result.get("verification_required")), "stores": stores}

    async def web_bind(self, ntw_id):
        config = self.get_config()
        creds = decrypt_json(config.encrypted_credentials) if config else {}
        pending = creds.get("web_pending") or {}
        if not pending.get("token") or pending.get("expires_at",0)<datetime.now(timezone.utc).timestamp():
            raise DddWebError("登录已过期，请重新登录后选择门店", code="NO_SESSION")
        session = {k:pending[k] for k in ("token","uid","device_id")}
        client = DddWebClient(**session)
        stores = await client.list_stores()
        store = next((s for s in stores if s["id"]==str(ntw_id)), None)
        if not store:
            raise DddWebError("该门店不在当前账号的授权列表中", code="STORE_FORBIDDEN")
        if config.hotel_num and str(config.hotel_num) != store["ntw_num"]:
            raise DddWebError("该企业已绑定另一门店，请使用独立企业空间，避免混入历史订单", code="STORE_CONFLICT")
        # Check local binding before touching the upstream session context.
        other = self.db.query(HotelConnectorConfig).filter(HotelConnectorConfig.hotel_num==int(store["ntw_num"]),
                    HotelConnectorConfig.company_id!=self.company_id).first()
        if other:
            raise DddWebError("该门店已被其他企业绑定", code="STORE_CONFLICT")
        client.ntw_num = store["ntw_num"]
        await client.select_store(store["id"])
        profile = await client.profile()
        if str(profile.get("ntwNum")) != store["ntw_num"] or str(profile.get("id")) != store["id"]:
            raise DddWebError("会话门店不匹配，请重新登录", code="STORE_MISMATCH")
        rooms = await client.rooms()
        config.hotel_num = int(store["ntw_num"])
        config.hotel_name = profile.get("name")
        config.hotel_info = {k:profile[k] for k in ("id","ntwNum","name","finalVersion","regionName","introduction") if k in profile}
        config.room_types = rooms
        config.room_count = sum(len(x.get("roomList") or []) for x in rooms)
        # Store only the selected store session, never password or an open-platform token.
        config.encrypted_credentials = encrypt_json({"web_session":session, "web_store_id":store["id"], "web_version":store.get("version")})
        config.status = "connected"
        config.last_connect_at = datetime.now(timezone.utc)
        config.last_sync_error = None
        self.db.commit()
        return self.masked_config_summary()

    async def web_daily_report(self, config, biz_date: str) -> dict:
        client = self.web_client(config)
        rows = await client.daily_report(biz_date)
        def clean(row):
            if not isinstance(row, dict) or not isinstance(row.get("itemName"), str):
                raise DddWebError("营业日报字段变更", code="SCHEMA_CHANGED")
            out = {k: row.get(k) for k in ("itemName", "today", "month", "year")}
            children = row.get("list") or []
            if not isinstance(children, list):
                raise DddWebError("营业日报层级字段变更", code="SCHEMA_CHANGED")
            out["list"] = [clean(x) for x in children]
            return out
        return {"biz_date": biz_date, "source": "dingdandao_web", "metrics": [clean(r) for r in rows]}

    async def web_connect_test(self, config):
        try:
            client = self.web_client(config)
            profile = await client.profile()
            creds = decrypt_json(config.encrypted_credentials)
            if str(profile.get("ntwNum")) != str(config.hotel_num) or str(profile.get("id")) != creds.get("web_store_id"):
                raise DddWebError("会话门店不匹配，请重新登录选择绑定门店", code="STORE_MISMATCH")
            rooms = await client.rooms()
            config.hotel_name = profile.get("name")
            config.room_types = rooms
            config.room_count = sum(len(x.get("roomList") or []) for x in rooms)
            config.status = "connected"
            config.last_connect_at = datetime.now(timezone.utc)
            config.last_sync_error = None
            self.db.commit()
            return {"connected":True,"status":"connected","message":"Web 会话连接成功", "hotel_name":config.hotel_name,
                    "room_count":config.room_count,"room_type_count":len(rooms)}
        except DddWebError as exc:
            config.status = "error"
            config.last_sync_error = f"[{exc.code}] {exc.message}"
            self.db.commit()
            return {"connected":False,"status":"error","code":exc.code,"message":exc.message}

    def _upsert_web_order(self, config, row):
        safe, nights, checkins, checkouts = normalize_order(row)
        order = self.db.query(HotelOrder).filter_by(company_id=self.company_id,hotel_num=config.hotel_num,order_num=row["orderNum"]).first()
        if order is None:
            order = HotelOrder(company_id=self.company_id,hotel_num=config.hotel_num,order_num=row["orderNum"])
            self.db.add(order)
        order.status = row.get("orderStatus")
        order.is_invalid = False
        order.channel_name = row.get("originName")
        order.currency = row.get("currency") or "CNY"
        order.actual_amount = None  # order total is not cash received
        order.paid_amount = None
        order.order_created_at = local_dt(row.get("createTime"))
        order.check_in_at = min(checkins) if checkins else None
        order.check_out_at = max(checkouts) if checkouts else None
        order.room_count = sum(s.get("status") in {40,70,80} for s in safe["serviceList"])
        order.room_nights = len(nights)
        order.nights, order.detail = nights, safe
        order.synced_at = datetime.now(timezone.utc)
        return order

    async def run_web_sync(self, job, config):
        if job.company_id != self.company_id:
            raise ValueError("Sync job tenant mismatch")
        job.status, job.started_at = "running", datetime.now(timezone.utc)
        self.db.commit()
        try:
            check = await self.web_connect_test(config)
            if not check["connected"]:
                raise DddWebError(check["message"], code=check["code"])
            client = self.web_client(config)
            creds = decrypt_json(config.encrypted_credentials)
            pro = creds.get("web_version") in {"pro","biz","etp"} or (config.hotel_info or {}).get("finalVersion") in {"pro","biz","etp"}
            seen = set()
            for page_num in range(1, 1001):
                result = await client.order_page(job.begin_date,job.end_date,page_num,pro=pro)
                rows = result["list"]
                if not rows and len(seen) < result["total"]:
                    raise DddWebError("订单分页提前结束，请重试",code="PAGINATION_ERROR")
                page_ids = {str(r.get("orderNum")) for r in rows if isinstance(r,dict)}
                if rows and (not page_ids or page_ids.issubset(seen)):
                    raise DddWebError("订单分页重复，请重试",code="PAGINATION_ERROR")
                for row in rows:
                    order_num = str(row.get("orderNum")) if isinstance(row,dict) else ""
                    if order_num in seen:continue
                    seen.add(order_num)
                    try:
                        with self.db.begin_nested():
                            self._upsert_web_order(config,row)
                            self.db.flush()
                        job.orders_synced += 1
                    except (DddWebError,ValueError,TypeError):
                        job.orders_failed += 1
                job.orders_found = len(seen)
                self.db.commit()  # completed pages survive a later timeout
                if result.get("boolLastPage") is True or len(seen)>=result["total"]:break
                await asyncio.sleep(0.2)
            else:
                raise DddWebError("超过分页上限，请缩小日期范围", code="PAGE_LIMIT")
            job.status = "partial" if job.orders_failed else "success"
            job.error = f"{job.orders_failed} 个订单字段异常" if job.orders_failed else None
            config.status = "connected"
        except DddWebError as exc:
            job.status = "partial" if job.orders_synced else "failed"
            job.error = f"[{exc.code}] {exc.message}"
            if exc.is_auth_error:config.status = "error"
        except Exception as exc:
            self.db.rollback()
            job.status = "partial" if job.orders_synced else "failed"
            job.error = f"同步异常: {type(exc).__name__}"
        job.finished_at = datetime.now(timezone.utc)
        config.last_sync_status, config.last_sync_error = job.status,job.error
        config.last_sync_stats = {"found":job.orders_found,"synced":job.orders_synced,"failed":job.orders_failed}
        if job.status=="success":config.last_sync_at=job.finished_at
        self.db.commit()
        return job
