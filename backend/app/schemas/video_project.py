from __future__ import annotations

import uuid
from typing import Literal
from datetime import datetime

from pydantic import BaseModel, Field


class MusicSettings(BaseModel):
    music_asset_id: uuid.UUID | None = None
    music_volume: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)


class DefaultMusicSettings(MusicSettings):
    selection_mode: Literal['fixed','random'] = 'fixed'


class VideoProjectCreate(MusicSettings):
    title: str
    script: str | None = None
    creation_mode: str
    marketing_goal: str | None = None
    target_audience: str | None = None
    product_name: str | None = None
    key_selling_points: str | None = None
    video_theme: str | None = None
    target_duration_seconds: int | None = Field(default=None, ge=15, le=60)
    aspect_ratio: Literal['9:16', '16:9', '1:1'] = "9:16"
    video_style: str | None = None
    voiceover_language: str | None = None
    subtitle_required: bool = False
    cta_text: str | None = None
    budget_limit_cents: int | None = None
    reference_asset_id: uuid.UUID | None = None
    selected_asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=40)
    digital_employee_id: uuid.UUID | None = None


class VideoProjectUpdate(BaseModel):
    music_asset_id: uuid.UUID | None = None
    music_volume: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    title: str | None = None
    marketing_goal: str | None = None
    target_audience: str | None = None
    product_name: str | None = None
    key_selling_points: str | None = None
    video_theme: str | None = None
    target_duration_seconds: int | None = Field(default=None, ge=15, le=60)
    aspect_ratio: Literal['9:16', '16:9', '1:1'] | None = None
    video_style: str | None = None
    voiceover_language: str | None = None
    subtitle_required: bool | None = None
    cta_text: str | None = None
    selected_asset_ids: list[uuid.UUID] | None = Field(default=None, max_length=40)
    budget_limit_cents: int | None = None


class StoryboardUpdate(BaseModel):
    storyboard: list[dict]


class ShotRegenerateRequest(BaseModel):
    reason: str | None = None
    updated_description: str | None = None


class VideoProjectResponse(BaseModel):
    music_asset_id: uuid.UUID | None = None
    music_volume: float = 0.25
    id: uuid.UUID
    company_id: uuid.UUID
    created_by: uuid.UUID
    digital_employee_id: uuid.UUID | None = None
    title: str
    creation_mode: str
    marketing_goal: str | None = None
    target_audience: str | None = None
    product_name: str | None = None
    key_selling_points: str | None = None
    video_theme: str | None = None
    target_duration_seconds: int | None = None
    aspect_ratio: str
    video_style: str | None = None
    voiceover_language: str | None = None
    subtitle_required: bool
    cta_text: str | None = None
    budget_limit_cents: int | None = None
    reference_asset_id: uuid.UUID | None = None
    selected_asset_ids: list[uuid.UUID] | None = None
    reference_analysis: dict | None = None
    script: str | None = None
    storyboard: list | None = None
    output_asset_id: uuid.UUID | None = None
    output_thumbnail_url: str | None = None
    output_video_url: str | None = None
    estimated_cost_cents: int | None = None
    actual_cost_cents: int | None = None
    review_status: str
    project_status: str
    quality_check_result: dict | None = None
    publish_title: str | None = None
    publish_description: str | None = None
    publish_platforms: list[str] = Field(default_factory=list)
    task_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
