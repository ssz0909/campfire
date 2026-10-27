"""
HTTP client for the 订单来了 (Dingdanlai) open platform.

Implements request signing (RSA2/SHA1withRSA over sorted params) and the four
business endpoints used by the private-data integration:

* ``POST /open/platform/api/tp/token``            app access token
* ``POST /open/pms/third/hotel/fetch``            hotel profile
* ``POST /open/pms/hotel/data/listRoomInfos``     room types / rooms
* ``POST /open/pms/hotel/data/order/search``      order number search
* ``POST /open/pms/hotel/data/order/detail``      order detail

The store-scoped ``authAccessToken`` is issued by the platform's authorization
flow and supplied by the operator; it is passed as a query parameter on every
business call, exactly as the document specifies.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.connectors.hotel.crypto import (
    DdllCryptoError,
    load_private_key_der,
    sign,
    signature_content,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Response ``code`` values that mean success.
_SUCCESS_CODES = {"1", 1}

_ERROR_MESSAGES: dict[str, str] = {
    "-1": "token 验证失败",
    "-2": "接口无权限",
    "-3": "应用 code 有误",
    "-4": "应用秘钥有误",
    "-5": "token 过期",
    "-6": "签名不存在",
    "-7": "TOKEN 不存在",
    "-8": "时间戳不存在",
    "-9": "应用编号不存在",
    "-10": "签名错误",
    "-11": "版本不存在",
    "-12": "请求非法：时间戳已过期",
    "-13": "版本错误",
    "2": "业务错误",
    "3": "系统内部错误",
    "4": "参数校验失败",
    "5": "接口不存在，请升级您的系统版本",
    "6": "接口已经废弃，请升级您的系统版本",
    "7": "验证失败",
    "8": "接口超时",
    "9": "服务不可用",
    "11": "数据库操作异常",
    "12": "重复的请求",
    "13": "请求被限流",
    "14": "参数解析失败",
    "15": "不支持的请求方法",
    "16": "日期转换异常",
    "17": "权限不足",
    "AO-50001": "酒店 id 不存在",
    "AO-50002": "不具备权限（酒店未授权）",
    "AO-50003": "房型 ID 不存在",
    "AO-50017": "未找到订单或无权限",
    "70002": "无效的 secret",
    "70003": "无效的 ticket",
    "70004": "应用调用凭证已过期",
    "70005": "应用调用凭证不正确",
    "70012": "授权门店调用凭证已过期",
    "70013": "授权门店调用凭证不正确",
    "70014": "token 与门店不匹配，请确认当前门店的 token 信息",
}


class DdllApiError(Exception):
    """Raised when the platform returns a non-success code or the call fails."""

    def __init__(self, code: str, message: str, *, endpoint: str, raw: Any = None):
        self.code = code
        self.message = message
        self.endpoint = endpoint
        self.raw = raw
        super().__init__(f"[{code}] {message} ({endpoint})")

    @property
    def is_auth_error(self) -> bool:
        return self.code in {"-1", "-5", "-10", "70004", "70005", "70012", "70013", "70014"}


class DdllClient:
    """Signed HTTP client. One instance per (app credentials, store token)."""

    def __init__(
        self,
        *,
        app_code: str,
        app_secret: str,
        auth_access_token: str | None = None,
        private_key_der: bytes | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.app_code = str(app_code)
        self.app_secret = app_secret
        self.auth_access_token = auth_access_token
        self.base_url = (base_url or settings.DDLL_BASE_URL).rstrip("/")
        self.api_version = api_version or settings.DDLL_API_VERSION
        self.timeout = timeout or settings.DDLL_HTTP_TIMEOUT_SECONDS
        self._transport = transport
        if private_key_der is None:
            if not settings.DDLL_PRIVATE_KEY_PATH and not settings.DDLL_PRIVATE_KEY:
                raise DdllCryptoError("No RSA private key configured (DDLL_PRIVATE_KEY_PATH)")
            private_key_der = load_private_key_der(
                settings.DDLL_PRIVATE_KEY_PATH or settings.DDLL_PRIVATE_KEY
            )
        self._private_key_der = private_key_der

    # ------------------------------------------------------------------
    # Signing / request plumbing
    # ------------------------------------------------------------------

    def _build_headers(self, req_body: str) -> dict[str, str]:
        timestamp = int(time.time() * 1000)
        params = {
            "appCode": self.app_code,
            "timestamp": str(timestamp),
            "version": self.api_version,
            "reqBody": req_body,
        }
        content = signature_content(params)
        headers = {
            "Content-Type": "application/json",
            "version": self.api_version,
            "appCode": self.app_code,
            "timestamp": str(timestamp),
            "sign": sign(content, self._private_key_der),
        }
        return headers

    async def _request(
        self,
        path: str,
        body: dict[str, Any],
        *,
        with_store_token: bool = False,
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        req_body = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        headers = self._build_headers(req_body)
        params: dict[str, str] = {"appCode": self.app_code, **(extra_params or {})}
        if with_store_token:
            if not self.auth_access_token:
                raise DdllApiError(
                    "NO_STORE_TOKEN",
                    "缺少授权门店调用凭证 authAccessToken",
                    endpoint=path,
                )
            params["authAccessToken"] = self.auth_access_token

        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport
            ) as client:
                response = await client.post(url, headers=headers, params=params, content=req_body)
        except httpx.HTTPError as exc:
            logger.warning("ddll request failed: %s %s", path, type(exc).__name__)
            raise DdllApiError("HTTP_ERROR", f"网络请求失败: {type(exc).__name__}", endpoint=path) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise DdllApiError(
                "BAD_RESPONSE",
                f"无法解析响应 (HTTP {response.status_code})",
                endpoint=path,
                raw=response.text[:500],
            ) from exc

        code = str(payload.get("code"))
        if code not in _SUCCESS_CODES:
            message = (
                payload.get("msg")
                or _ERROR_MESSAGES.get(code)
                or payload.get("errorDetail")
                or "未知错误"
            )
            raise DdllApiError(code or "UNKNOWN", str(message), endpoint=path, raw=payload)
        return payload

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    async def request_component_token(self, *, ticket: str) -> dict[str, Any]:
        """
        ``POST /open/platform/api/tp/token`` -> raw ``data`` object.

        Request: appCode, appSecret, ticket (the ticket is pushed to our callback
        about every 10 minutes). The document names the result "应用调用凭证" and the
        next endpoint consumes it as ``componentAccessToken``; the response field
        names themselves are not documented, so the caller extracts them and
        reports the available keys if they differ.
        """
        # Field order follows the documented example body exactly
        # (the signed reqBody must equal the body we send; we sign what we send).
        body = {
            "ticket": ticket,
            "appCode": self.app_code,
            "appSecret": self.app_secret,
        }
        payload = await self._request("/open/platform/api/tp/token", body)
        return payload.get("data") or {}

    async def request_store_token(
        self, *, component_access_token: str, hotel_num: int | str
    ) -> dict[str, Any]:
        """
        ``POST /open/platform/api/tp/auth/token`` — mint the store call credential.

        Returns ``authAccessToken`` (valid 2h), ``expire`` (seconds),
        ``authRefreshToken`` (valid 30 days) and ``ntwNum``. The body must be
        byte-identical to the signed ``reqBody`` (we sign and send the same
        compact JSON string).
        """
        payload = await self._request(
            "/open/platform/api/tp/auth/token",
            {"ntwNum": int(hotel_num)},
            extra_params={"componentAccessToken": component_access_token},
        )
        return payload.get("data") or {}

    async def fetch_hotel(self, hotel_num: int | str) -> dict[str, Any]:
        payload = await self._request(
            "/open/pms/third/hotel/fetch",
            {"hotelNum": int(hotel_num)},
            with_store_token=True,
        )
        return payload.get("data") or {}

    async def list_room_infos(
        self, hotel_num: int | str, room_type_codes: list[str] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"hotelNum": int(hotel_num)}
        if room_type_codes:
            body["roomTypeCodeList"] = room_type_codes
        payload = await self._request(
            "/open/pms/hotel/data/listRoomInfos", body, with_store_token=True
        )
        return payload.get("data") or {}

    async def search_orders(
        self,
        *,
        hotel_num: int | str,
        date_type: int,
        begin_date: str,
        end_date: str,
        status: int | None = None,
        query_type: int | None = None,
        query_value: str | None = None,
        page_num: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "hotelNum": int(hotel_num),
            "dateType": date_type,
            "beginDate": begin_date,
            "endDate": end_date,
        }
        if status is not None:
            body["status"] = status
        if query_type is not None:
            body["queryType"] = query_type
        if query_value is not None:
            body["queryValue"] = query_value
        if page_num is not None:
            body["pageNum"] = page_num
        payload = await self._request(
            "/open/pms/hotel/data/order/search", body, with_store_token=True
        )
        return payload.get("data") or {}

    async def order_detail(self, *, hotel_num: int | str, order_num: str) -> dict[str, Any]:
        payload = await self._request(
            "/open/pms/hotel/data/order/detail",
            {"hotelNum": int(hotel_num), "orderNum": str(order_num)},
            with_store_token=True,
        )
        return payload.get("data") or {}
