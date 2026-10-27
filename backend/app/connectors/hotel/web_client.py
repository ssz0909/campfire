"""Read-only PMS web protocol, verified against public bundles on 2026-10-15.

See docs/dingdandao_web_connector.md for evidence and unverified boundaries.
Session tokens here are NOT open-platform authAccessTokens.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
import uuid
from datetime import date, datetime, time as dtime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

BASE_URL = "https://www.dingdandao.com"
SHANGHAI = ZoneInfo("Asia/Shanghai")
LOGIN = "/v2/user/public/checkDevice/login"
STORES = "/v2/user/web/user/ntw/list"
SELECT_STORE = "/v2/user/user/changeNtw"
PROFILE = "/v2/ntw/web/ntw/get"
ROOMS = "/v2/core/web/accom/roomType/room/list/auth"
ORDERS = "/v2/hm-b/web/accom/order/getPage"
PRO_ORDERS = "/v2/hm-b/pro/web/accom/order/getPage"
DAILY_REPORT = "/v2/um-b/web/pro/report/biz/daily/stats"
READ_PATHS = {STORES, SELECT_STORE, PROFILE, ROOMS, ORDERS, PRO_ORDERS, DAILY_REPORT}


class DddWebError(Exception):
    def __init__(self, message: str, *, code: str = "WEB_ERROR", **_ignored):
        self.code = str(code)
        self.message = message
        super().__init__(message)

    @property
    def is_auth_error(self):
        return self.code in {"5", "7", "SESSION_EXPIRED", "NO_SESSION"}


def aes_encrypt(plaintext: str) -> str:
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(b"cp913dfkylscr1jr"), modes.CBC(b"fh312fpz7zqv6dkq")).encryptor()
    return base64.b64encode(enc.update(padded) + enc.finalize()).decode()


def login_body(phone: str, password: str, timestamp: int, *, sms_captcha="", login_ticket=None):
    body = {
        "phone": phone if phone.startswith("+") else "+86" + phone,
        "password": aes_encrypt(password), "smsCaptcha": sms_captcha,
        "loginType": 2 if sms_captcha else 1,
    }
    if login_ticket:
        body["loginTicket"] = login_ticket
    body.update(timestamp=timestamp, systemId=1, siteId=1, uid=None)
    # JS: Object.values(body).concat(localStorage.token).sort().join("").
    # Array.join renders null/undefined as empty strings.
    values = ["null" if v is None else str(v) for v in body.values()] + ["null"]
    values.sort()
    body["sign"] = hashlib.md5("".join(v for v in values if v != "null").encode()).hexdigest()
    return body


def signed_headers(body_text: str, timestamp: int, token: str | None, uid: Any, device_id: str):
    content = f"reqBody={body_text}&timestamp={timestamp}&version=1"
    return {
        "Accept": "application/json, text/plain, */*", "Content-Type": "application/json;charset=UTF-8",
        "Origin": BASE_URL, "Referer": BASE_URL + "/pmsManage/", "User-Agent": "AIwork-HotelConnector/1.0",
        "uid": str(uid) if uid is not None else "null", "token": token or "null",
        "terminal": "1", "version": "1", "timestamp": str(timestamp),
        "sign": hashlib.md5(content.encode()).hexdigest(), "notSign": "notSign",
        "deviceId": device_id, "qdll-request-id": uuid.uuid4().hex,
    }


class DddWebClient:
    def __init__(self, *, token=None, uid=None, ntw_num=None, device_id=None, timeout=20.0, transport=None):
        self.token, self.uid = token, uid
        self.ntw_num = str(ntw_num) if ntw_num else ""
        self.device_id = device_id or uuid.uuid4().hex
        self.timeout, self.transport = timeout, transport

    async def _request(self, path: str, body: dict, *, login=False):
        if (login and path != LOGIN) or (not login and path not in READ_PATHS):
            raise ValueError("Unsupported PMS operation")
        if not login and (not self.token or self.uid is None):
            raise DddWebError("请先登录订单来了", code="NO_SESSION")
        if not login:
            body = {"TIMEZONEOFFSET": -480, "ntwNum": self.ntw_num, **body}
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        # Only read calls retry; never replay login or store switching automatically.
        for attempt in range(3):
            headers = signed_headers(text, int(time.time()*1000), self.token, self.uid, self.device_id)
            try:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                    response = await client.post(BASE_URL + path, content=text, headers=headers)
            except httpx.HTTPError as exc:
                if not login and path != SELECT_STORE and attempt < 2:
                    await asyncio.sleep(0.3 * 2**attempt)
                    continue
                raise DddWebError("订单来了网络请求失败，请重试", code="HTTP_ERROR") from exc
            if response.status_code in {429, 502, 503, 504} and not login and path != SELECT_STORE and attempt < 2:
                await asyncio.sleep(0.3 * 2**attempt)
                continue
            if response.status_code in {401, 403}:
                raise DddWebError("会话失效或账号无权限，请重新登录或检查门店权限", code="SESSION_EXPIRED")
            if response.status_code != 200:
                raise DddWebError(f"订单来了返回 HTTP {response.status_code}", code="HTTP_ERROR")
            try:
                payload = response.json()
            except ValueError as exc:
                raise DddWebError("订单来了响应不是 JSON，接口可能已变更", code="BAD_RESPONSE") from exc
            if not isinstance(payload, dict):
                raise DddWebError("订单来了响应格式已变更", code="BAD_RESPONSE")
            code = str(payload.get("code"))
            if code not in {"1", "11023"}:
                # Do not propagate remote text: it can contain credentials or guest PII.
                message = {"5": "账号已在其他地方登录，请重新连接", "7": "会话已过期，请重新登录",
                           "17": "当前账号无权访问此酒店数据", "21": "当前账号的 IP 访问权限受限",
                           "13": "请求频率受限，请稍后重试"}.get(code, "订单来了拒绝请求，请检查账号权限或在官网完成验证")
                raise DddWebError(message, code=code)
            data = payload.get("data")
            if not isinstance(data, dict):
                raise DddWebError("订单来了 data 格式已变更", code="BAD_RESPONSE")
            return data

    async def login(self, phone, password, *, sms_captcha="", login_ticket=None):
        data = await self._request(LOGIN, login_body(phone, password, int(time.time()*1000),
                                   sms_captcha=sms_captcha, login_ticket=login_ticket), login=True)
        if not data.get("token") or data.get("userId") is None:
            if data.get("loginTicket"):
                return {"verification_required": True, "login_ticket": data["loginTicket"], "device_id": self.device_id}
            raise DddWebError("登录响应缺少会话信息，请在官网检查账号状态", code="BAD_RESPONSE")
        self.token, self.uid = data["token"], data["userId"]
        return {"token": self.token, "uid": self.uid, "device_id": self.device_id}

    async def list_stores(self):
        data = await self._request(STORES, {})
        rows = data.get("list")
        if not isinstance(rows, list) or any(not isinstance(x, dict) or not x.get("id") or not x.get("ntwNum") for x in rows):
            raise DddWebError("门店列表格式已变更", code="SCHEMA_CHANGED")
        return [{"id": str(x["id"]), "ntw_num": str(x["ntwNum"]),
                 "name": x.get("name") or x.get("ntwName"), "version": x.get("versionIdentify")}
                for x in rows]

    async def select_store(self, ntw_id):
        return await self._request(SELECT_STORE, {"ntwId": str(ntw_id)})

    async def profile(self):
        return await self._request(PROFILE, {})

    async def rooms(self):
        data = await self._request(ROOMS, {})
        if not isinstance(data.get("list"), list):
            raise DddWebError("房型列表格式已变更", code="SCHEMA_CHANGED")
        return data["list"]

    async def order_page(self, begin_date, end_date, page_num=1, *, pro=False):
        begin, end = date.fromisoformat(begin_date), date.fromisoformat(end_date)
        body = {"selectType": 0, "pageNum": page_num, "pageSize": 100, "orderBy": 0, "order": False,
                "createTimeStart": int(datetime.combine(begin, dtime.min, SHANGHAI).timestamp()*1000),
                "createTimeEnd": int((datetime.combine(end+timedelta(days=1), dtime.min, SHANGHAI).timestamp()*1000)-1)}
        data = await self._request(PRO_ORDERS if pro else ORDERS, body)
        if not isinstance(data.get("list"), list) or not isinstance(data.get("total"), int) or data["total"] < 0:
            raise DddWebError("订单分页格式已变更，已停止同步", code="SCHEMA_CHANGED")
        return data

    async def daily_report(self, biz_date):
        date.fromisoformat(biz_date)
        data = await self._request(DAILY_REPORT, {"bizDate": biz_date})
        if not isinstance(data.get("list"), list):
            raise DddWebError("营业日报表格式已变更", code="SCHEMA_CHANGED")
        return data["list"]
