from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app.providers.video.base import (
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoProvider,
)

# In-memory task store for the mock provider (not suitable for production).
# Maps provider_task_id -> (submitted_at_timestamp, request)
_mock_tasks: dict[str, tuple[float, VideoGenerationRequest]] = {}

# Simulated time-to-completion in seconds
_MOCK_COMPLETION_DELAY = 5.0
_MOCK_PLACEHOLDER_URL = "https://example.com/MOCK_VIDEO_PLACEHOLDER.mp4"


class MockVideoProvider(VideoProvider):
    """
    MOCK video generation provider for development and testing.

    All responses are clearly labeled MOCK. No real video is generated.
    Simulates async behaviour: returns 'processing' immediately, transitions
    to 'completed' after approximately 5 seconds.
    """

    async def submit_generation(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        task_id = f"MOCK-{uuid.uuid4().hex}"
        _mock_tasks[task_id] = (datetime.now(timezone.utc).timestamp(), request)
        return VideoGenerationResult(
            provider_task_id=task_id,
            status="processing",
            output_url=None,
            duration_seconds=None,
            cost_cents=None,
            error=None,
        )

    async def get_task_status(
        self, provider_task_id: str
    ) -> VideoGenerationResult:
        if provider_task_id not in _mock_tasks:
            return VideoGenerationResult(
                provider_task_id=provider_task_id,
                status="failed",
                error="MOCK: Unknown task ID",
            )

        submitted_at, request = _mock_tasks[provider_task_id]
        elapsed = datetime.now(timezone.utc).timestamp() - submitted_at

        if elapsed < _MOCK_COMPLETION_DELAY:
            return VideoGenerationResult(
                provider_task_id=provider_task_id,
                status="processing",
            )

        # Simulate completion
        return VideoGenerationResult(
            provider_task_id=provider_task_id,
            status="completed",
            output_url=_MOCK_PLACEHOLDER_URL,
            duration_seconds=request.duration_seconds,
            cost_cents=int(request.duration_seconds * 10),  # $0.10 per second (mock)
            error=None,
        )

    async def cancel_task(self, provider_task_id: str) -> bool:
        if provider_task_id in _mock_tasks:
            del _mock_tasks[provider_task_id]
            return True
        return False
