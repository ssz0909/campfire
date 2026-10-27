from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agent.workflows.base import BaseWorkflow
from app.core.tenant_context import TenantContext
from app.models.task import OperationTask


class VideoCreationWorkflow(BaseWorkflow):
    """
    Workflow for video_generation tasks.
    Orchestrates script generation, storyboard creation, and video rendering.
    """

    def run(
        self,
        task: OperationTask,
        tenant_context: TenantContext,
        db: Session,
        runtime: Any,
    ) -> dict[str, Any]:
        runtime._append_log(task, "info", "Starting video creation workflow")

        params = task.input_params or {}
        video_project_id = params.get("video_project_id")

        if not video_project_id:
            raise ValueError("video_project_id is required in input_params for video_generation tasks")

        runtime._append_log(task, "info", f"Processing video project: {video_project_id}")
        task.progress = 10
        db.commit()

        from app.services.video_generation import enqueue
        enqueue(video_project_id)
        task.progress = 20
        runtime._append_log(task, "info", "已启动视频模型生成任务")
        db.commit()

        return {
            "video_project_id": video_project_id,
            "celery_task_id": None,
            "status": "queued",
            "note": "Video generation pipeline started. Poll task status for progress.",
        }
