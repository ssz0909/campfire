"""
订单来了 (Dingdanlai) hotel connector — public entry point.

The implementation lives in:
* ``models.py``   SQLAlchemy models
* ``crypto.py``   RSA2 signing, AES-256-CBC decryption, callback verification
* ``client.py``   signed HTTP client for the open platform
* ``service.py``  credentials, connect test, order sync, metrics

This module re-exports the models so existing imports keep working.
"""
from __future__ import annotations

from app.connectors.hotel.models import (  # noqa: F401
    HotelConnectorConfig,
    HotelOrder,
    HotelSyncJob,
    PlatformKeyValue,
)
from app.connectors.hotel.service import HotelConnectorService  # noqa: F401

__all__ = [
    "HotelConnectorConfig",
    "HotelOrder",
    "HotelSyncJob",
    "PlatformKeyValue",
    "HotelConnectorService",
]
