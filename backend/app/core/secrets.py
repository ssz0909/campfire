"""
At-rest encryption for third-party credentials (Fernet / AES-128-CBC + HMAC).

The key comes from ``CREDENTIAL_ENCRYPTION_KEY`` (a Fernet key). When unset a
key is derived from ``SECRET_KEY`` so development works out of the box; in
production set it explicitly so rotating the JWT secret does not make stored
credentials unreadable.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    if settings.CREDENTIAL_ENCRYPTION_KEY:
        return Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
    if settings.ENVIRONMENT == "production":
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must be set in production")
    digest = hashlib.sha256(("credentials:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_json(data: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(blob: str | None) -> dict[str, Any]:
    if not blob:
        return {}
    try:
        return json.loads(_fernet().decrypt(blob.encode()).decode())
    except (InvalidToken, ValueError):
        return {}


def mask(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    return value[:keep] + "***" if len(value) > keep else "***"
