from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "aiops",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.worker.tasks.asset_tasks",
        "app.worker.tasks.agent_tasks",
        "app.worker.tasks.video_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
    task_routes={
        "app.worker.tasks.asset_tasks.*": {"queue": "assets"},
        "app.worker.tasks.agent_tasks.*": {"queue": "agents"},
        "app.worker.tasks.video_tasks.*": {"queue": "video"},
    },
)
