"""
Public webhook receiver for 订单来了 push messages.

Authentication is the platform's RSA2 signature (no bearer token). Every request
is: AES-decrypted -> signature-verified -> timestamp-checked -> dispatched.
Nothing is acted on until the signature verifies.

Message actions (see the vendor document):
* ``TICKET``         platform pushes a fresh ticket roughly every 10 minutes
* ``ORDER_CHANGE``   an order changed; ``reqMsg`` carries orderNum/hotelNum/type
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.hotel.crypto import DdllCryptoError, aes_decrypt, signature_content, verify
from app.connectors.hotel.models import HotelConnectorConfig
from app.connectors.hotel.service import HotelConnectorService, store_ticket
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# Reject callbacks whose timestamp is too far from now (replay window).
MAX_CLOCK_SKEW_MS = 10 * 60 * 1000


def _ack(ok: bool = True, **extra: Any) -> dict[str, Any]:
    return {"code": "1" if ok else "0", "msg": "success" if ok else "failure", **extra}


@router.post("/callbacks/ddll")
async def ddll_callback(request: Request, db: Session = Depends(get_db)):
    if not settings.DDLL_AES_KEY or not settings.DDLL_PLATFORM_PUBLIC_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Callback not configured")

    try:
        body = await request.json()
        encrypted = str(body["msg"])
        signature = str(body["sign"])
        app_code = str(body["appCode"])
        nonce = str(body["nonce"])
        timestamp = str(body["timestamp"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed callback body")

    if settings.DDLL_APP_CODE and app_code != str(settings.DDLL_APP_CODE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown app")

    try:
        message_text = aes_decrypt(encrypted, settings.DDLL_AES_KEY)
    except DdllCryptoError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Undecryptable message")

    content = signature_content(
        {"appCode": app_code, "timestamp": timestamp, "nonce": nonce, "msg": message_text}
    )
    if not verify(content, signature, settings.DDLL_PLATFORM_PUBLIC_KEY):
        logger.warning("ddll callback rejected: bad signature")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature")

    try:
        skew = abs(int(time.time() * 1000) - int(timestamp))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid timestamp")
    if skew > MAX_CLOCK_SKEW_MS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Stale timestamp")

    try:
        message = json.loads(message_text)
        action = message.get("action")
        req_msg = message.get("reqMsg")
        req = json.loads(req_msg) if isinstance(req_msg, str) else (req_msg or {})
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed message")

    if action == "TICKET":
        ticket = req.get("ticket")
        if ticket:
            store_ticket(db, str(ticket), req.get("expire"))
        return _ack()

    if action == "ORDER_CHANGE":
        hotel_num = req.get("hotelNum")
        try:
            hotel_key = int(hotel_num)
        except (TypeError, ValueError):
            return _ack(handled=False, reason="invalid hotelNum")
        config = (
            db.query(HotelConnectorConfig)
            .filter(HotelConnectorConfig.hotel_num == hotel_key)
            .first()
        )
        if config is None:
            # Unknown store: acknowledge so the platform stops retrying, but do nothing.
            return _ack(handled=False, reason="unknown hotel")
        result = HotelConnectorService(config.company_id, db).apply_order_change(
            req, event_type=req.get("type")
        )
        return _ack(**result)

    # Unknown actions are acknowledged and ignored (forward compatible).
    logger.info("ddll callback ignored action=%s", action)
    return _ack(handled=False, reason="ignored action")
