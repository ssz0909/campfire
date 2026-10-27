from __future__ import annotations

from app.services.storage_service import StorageService
from app.config import settings


def get_storage_service() -> StorageService:
    return StorageService(backend=settings.STORAGE_BACKEND)
