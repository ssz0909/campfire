from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.cost import CostRecord
from app.models.subscription import Subscription, UsageRecord


class CostService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_cost_records(
        self,
        company_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CostRecord], int]:
        query = (
            self.db.query(CostRecord)
            .filter(CostRecord.company_id == company_id)
            .order_by(CostRecord.created_at.desc())
        )
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_cost_summary(
        self,
        company_id: uuid.UUID,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> dict:
        query = self.db.query(CostRecord).filter(CostRecord.company_id == company_id)
        records = query.all()

        total = sum(float(r.total_cost_cents) for r in records)
        by_provider: dict[str, float] = {}
        by_type: dict[str, float] = {}

        for r in records:
            by_provider[r.provider] = by_provider.get(r.provider, 0.0) + float(
                r.total_cost_cents
            )
            by_type[r.record_type] = by_type.get(r.record_type, 0.0) + float(
                r.total_cost_cents
            )

        return {
            "period_start": period_start or "all",
            "period_end": period_end or "all",
            "total_cost_cents": total,
            "by_provider": by_provider,
            "by_type": by_type,
        }

    def get_usage(self, company_id: uuid.UUID) -> dict:
        subscription = (
            self.db.query(Subscription)
            .filter(
                Subscription.company_id == company_id,
                Subscription.status == "active",
            )
            .first()
        )

        usage_record = (
            self.db.query(UsageRecord)
            .filter(UsageRecord.company_id == company_id)
            .order_by(UsageRecord.period_start.desc())
            .first()
        )

        return {
            "company_id": company_id,
            "plan_name": subscription.plan_name if subscription else "free",
            "period_start": usage_record.period_start if usage_record else None,
            "period_end": usage_record.period_end if usage_record else None,
            "tasks_used": usage_record.tasks_used if usage_record else 0,
            "tasks_quota": subscription.monthly_task_quota if subscription else None,
            "videos_used": usage_record.videos_used if usage_record else 0,
            "videos_quota": subscription.video_quota if subscription else None,
            "model_calls_used": usage_record.model_calls_used if usage_record else 0,
            "model_calls_quota": subscription.model_call_quota if subscription else None,
            "storage_bytes_used": usage_record.storage_bytes_used if usage_record else 0,
            "storage_bytes_quota": subscription.storage_bytes_quota if subscription else None,
            "total_cost_cents": usage_record.total_cost_cents if usage_record else 0,
        }
