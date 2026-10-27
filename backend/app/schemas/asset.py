from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field, field_serializer


class AssetBase(BaseModel):
    name: str
    tags: list | None = None
    category: str | None = None
    copyright_info: str | None = None
    source_description: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    tags: list | None = None
    category: str | None = None
    copyright_info: str | None = None
    source_description: str | None = None


class AssetResponse(AssetBase):
    id: uuid.UUID
    company_id: uuid.UUID
    uploaded_by: uuid.UUID
    original_filename: str
    file_key: str
    file_url: str | None = None
    asset_type: str
    mime_type: str
    file_size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    resolution: str | None = None
    fps: float | None = None
    codec: str | None = None
    thumbnail_url: str | None = None
    processing_status: str
    processing_error: str | None = None
    metadata: dict | None = Field(default=None, validation_alias=AliasChoices('asset_metadata','metadata'))
    is_available: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer('file_url', 'thumbnail_url')
    def signed_media_url(self, value, info):
        # Keep stable storage references in the database and sign on every read.
        # Older image records may not have an original URL populated.
        if info.field_name == 'file_url' and not value:
            from app.services.storage_service import StorageService
            from app.config import settings
            return StorageService(settings.STORAGE_BACKEND).generate_presigned_url(self.file_key)
        if value and value.startswith('/files/') and not value.startswith('/files/signed/'):
            from app.services.storage_service import StorageService
            from app.config import settings
            return StorageService(settings.STORAGE_BACKEND).generate_presigned_url(value[len('/files/'):])
        return value


class AssetUploadResponse(AssetResponse):
    pass


class DownloadUrlResponse(BaseModel):
    download_url: str
    expires_in_seconds: int
