from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_serializer

class PublishRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    location_name: str | None = Field(default=None, min_length=1, max_length=100)
    task_id: uuid.UUID | None = None
    video_project_id: uuid.UUID | None = None
    asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=35)
    media_url: str | None = None
    media_type: Literal['video', 'images'] = 'video'
    request_key: str = Field(min_length=8, max_length=100)

class RepublishRequest(BaseModel):
    location_name: str | None = Field(default=None, min_length=1, max_length=100)

class PlatformConnectionResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    platform: str
    status: str
    account_id: str | None = None
    account_name: str | None = None
    scopes: list | None = None
    last_error: str | None = None
    authorized_at: datetime | None = None
    model_config = {"from_attributes": True}

class MetricsUpdate(BaseModel):
    metrics: dict

class PublishJobResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    platform_connection_id: uuid.UUID
    requested_by: uuid.UUID
    task_id: uuid.UUID | None = None
    video_project_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    status: str
    provider_post_id: str | None = None
    provider_url: str | None = None
    metrics: dict | None = None
    error_message: str | None = None
    content_snapshot: dict | None = None
    reviewed_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

    @field_serializer('provider_url')
    def verified_content_url(self, value):
        # Old jobs stored the editor URL as if it were a published work.
        if self.status != 'published' or not value:
            return None
        from urllib.parse import urlparse
        path = urlparse(value).path.rstrip('/')
        if path.startswith('/creator-micro/') or path.startswith('/platform/'):
            return None
        return value
