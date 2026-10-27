from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class VideoGenerationRequest(BaseModel):
    prompt: str
    duration_seconds: float
    aspect_ratio: str
    style: str | None = None
    reference_image_url: str | None = None
    resolution: str = "720P"
    audio: bool = True


class VideoGenerationResult(BaseModel):
    provider_task_id: str
    status: str
    output_url: str | None = None
    duration_seconds: float | None = None
    cost_cents: int | None = None
    error: str | None = None


class VideoProvider(ABC):
    @abstractmethod
    async def submit_generation(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        """Submit a new video generation job. Returns immediately with a task ID."""
        ...

    @abstractmethod
    async def get_task_status(
        self, provider_task_id: str
    ) -> VideoGenerationResult:
        """Poll for the current status of a previously submitted task."""
        ...

    @abstractmethod
    async def cancel_task(self, provider_task_id: str) -> bool:
        """Attempt to cancel a running task. Returns True if successful."""
        ...
