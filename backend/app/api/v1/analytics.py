from __future__ import annotations

import uuid
from datetime import date, timedelta, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.asset import Asset
from app.models.cost import CostRecord
from app.models.digital_employee import DigitalEmployee
from app.models.task import OperationTask
from app.models.user import User
from app.models.video_project import VideoProject
from app.models.publishing import PublishJob

router = APIRouter()


@router.get('/{company_id}/analytics/works')
def analytics_works(company_id: uuid.UUID, page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100), platform: str | None = Query(None, pattern='^(douyin|wechat_channels)$'),
    task_id: uuid.UUID | None = None,
    current_user: User = Depends(require_permission(Permission.ANALYTICS_VIEW)), db: Session = Depends(get_db)):
    from app.services.work_metrics import summary
    return summary(db, company_id, page, page_size, platform, task_id, current_user.id)


@router.post('/{company_id}/analytics/works/sync', status_code=202)
def sync_work_metrics(company_id: uuid.UUID, background_tasks: BackgroundTasks,
    _: User = Depends(require_permission(Permission.PUBLISH_CREATE)), db: Session = Depends(get_db)):
    from app.services.work_metrics import request_sync, run_sync
    accounts = request_sync(db, company_id)
    if accounts: background_tasks.add_task(run_sync, company_id)
    return {'queued_accounts':len(accounts), 'message':'已提交采集，请稍后刷新；同账号五分钟内不重复采集。'}


@router.get("/{company_id}/analytics/overview")
def analytics_overview(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.ANALYTICS_VIEW)),
    db: Session = Depends(get_db),
):
    """Dashboard summary: counts of key resources and recent activity."""
    task_count = (
        db.query(func.count(OperationTask.id))
        .filter(OperationTask.company_id == company_id)
        .scalar()
    )
    completed_tasks = (
        db.query(func.count(OperationTask.id))
        .filter(
            OperationTask.company_id == company_id,
            OperationTask.status == "completed",
        )
        .scalar()
    )
    asset_count = (
        db.query(func.count(Asset.id))
        .filter(Asset.company_id == company_id, Asset.is_deleted == False)
        .scalar()
    )
    video_count = (
        db.query(func.count(VideoProject.id))
        .filter(VideoProject.company_id == company_id, VideoProject.is_deleted == False)
        .scalar()
    )
    employee_count = (
        db.query(func.count(DigitalEmployee.id))
        .filter(
            DigitalEmployee.company_id == company_id,
            DigitalEmployee.is_deleted == False,
            DigitalEmployee.is_active == True,
        )
        .scalar()
    )
    total_cost = (
        db.query(func.sum(CostRecord.total_cost_cents))
        .filter(CostRecord.company_id == company_id)
        .scalar()
        or 0
    )
    from app.models.approval import Approval
    local_now = datetime.now(ZoneInfo('Asia/Shanghai'))
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    now = local_now.astimezone(timezone.utc)
    monthly_cost = db.query(func.sum(CostRecord.total_cost_cents)).filter(
        CostRecord.company_id == company_id, CostRecord.created_at >= month_start, CostRecord.created_at <= now).scalar() or 0
    return {
        'active_tasks': db.query(func.count(OperationTask.id)).filter(
            OperationTask.company_id == company_id, OperationTask.status.in_(['pending','queued','running','waiting_external','waiting_retry'])).scalar(),
        'pending_approvals': db.query(func.count(Approval.id)).filter(
            Approval.company_id == company_id, Approval.status == 'pending',
            (Approval.expires_at.is_(None) | (Approval.expires_at > now))).scalar(),
        'videos_this_month': db.query(func.count(VideoProject.id)).filter(
            VideoProject.company_id == company_id, VideoProject.is_deleted == False,
            VideoProject.created_at >= month_start, VideoProject.created_at <= now).scalar(),
        'total_cost_this_month_usd': float(monthly_cost) / 100,
        'tasks_completed_today': db.query(func.count(OperationTask.id)).filter(
            OperationTask.company_id == company_id, OperationTask.status == 'completed',
            OperationTask.completed_at >= today_start, OperationTask.completed_at <= now).scalar(),
        'timezone': 'Asia/Shanghai',
        "total_tasks": task_count,
        "completed_tasks": completed_tasks,
        "total_assets": asset_count,
        "total_video_projects": video_count,
        "active_employees": employee_count,
        "total_cost_cents": float(total_cost),
        "published_posts": db.query(func.count(PublishJob.id)).filter(PublishJob.company_id == company_id, PublishJob.status == "published").scalar(),
    }


@router.get("/{company_id}/analytics/orders")
def analytics_orders(
    company_id: uuid.UUID,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    _: User = Depends(require_permission(Permission.ANALYTICS_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Order metrics computed from orders synchronised from 订单来了.

    Never fabricates figures: with no connector/orders the response says so and
    metrics that cannot be computed are null with an explanation.
    """
    from app.connectors.hotel.service import HotelConnectorService

    service = HotelConnectorService(company_id, db)
    config = service.get_config()
    if config is None or config.status not in ("connected", "configured", "error"):
        return {
            "status": "NOT_CONNECTED",
            "message": "尚未配置酒店连接器，暂无订单数据",
            "metrics": None,
        }

    end = date_to or date.today()
    start = date_from or (end - timedelta(days=29))
    metrics = service.metrics(start.isoformat(), end.isoformat())
    if metrics["total_orders"] == 0:
        return {
            "status": "NO_DATA",
            "message": "数据不足：所选时间范围内没有已同步的订单，请先执行订单同步",
            "last_sync_at": config.last_sync_at,
            "metrics": metrics,
        }
    return {
        "status": "OK",
        "last_sync_at": config.last_sync_at,
        "metrics": metrics,
        "definitions": {
            "scope": "按订单创建时间落在所选日期范围内统计；订单来了仅提供最近 90 天数据",
            "revenue": "未取消订单的订单应付总金额(actualAmount)之和，币种以接口返回为准",
            "room_nights": "未取消订单中未取消房间的每日房价条目数",
            "average_room_nightly_rate": "revenue / room_nights（含非房费消费，仅为近似口径）",
            "occupancy_rate": "room_nights / (房间总数 × 天数)；缺少房量或间夜数据时为 null",
            "cancellation_rate": "已取消订单数 / 订单总数",
        },
    }


@router.get("/{company_id}/analytics/content")
def analytics_content(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.ANALYTICS_VIEW)),
    db: Session = Depends(get_db),
):
    """Content output metrics: assets and video projects."""
    assets_by_type = (
        db.query(Asset.asset_type, func.count(Asset.id))
        .filter(Asset.company_id == company_id, Asset.is_deleted == False)
        .group_by(Asset.asset_type)
        .all()
    )
    videos_by_status = (
        db.query(VideoProject.project_status, func.count(VideoProject.id))
        .filter(VideoProject.company_id == company_id, VideoProject.is_deleted == False)
        .group_by(VideoProject.project_status)
        .all()
    )
    published = db.query(PublishJob).filter(PublishJob.company_id == company_id, PublishJob.status == "published").all()
    platform_metrics = {}
    account_metrics = {}
    from app.services.work_metrics import work_values
    seen_works = set()
    for job in published:
        values = work_values(job)
        identity = (job.platform_connection_id, job.provider_post_id or str(job.id))
        if identity not in seen_works:
            for key, value in values.items():
                platform_metrics[key] = platform_metrics.get(key, 0) + value
            seen_works.add(identity)
        metrics = job.metrics or {}
        if metrics.get('scope') == 'account':
            previous = account_metrics.get(str(job.platform_connection_id))
            if not previous or str(metrics.get('captured_at', '')) > str(previous.get('captured_at', '')):
                account_metrics[str(job.platform_connection_id)] = metrics
            continue
        for key in ("views", "likes", "comments", "shares", "clicks", "conversions"):
            if not values and metrics.get('scope') == 'work' and metrics.get(key) is not None:
                platform_metrics[key] = platform_metrics.get(key, 0) + float(metrics[key])
    return {
        "posts_created": sum(count for _, count in assets_by_type),
        "videos_created": sum(count for _, count in videos_by_status),
        "images_generated": dict(assets_by_type).get("image", 0),
        "words_generated": 0,
        "period": "all",
        "assets_by_type": {row[0]: row[1] for row in assets_by_type},
        "videos_by_status": {row[0]: row[1] for row in videos_by_status},
        "published_posts": len(published),
        "platform_metrics": platform_metrics,
        "platform_account_metrics": account_metrics,
    }


@router.get("/{company_id}/analytics/tasks")
def analytics_tasks(
    company_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.ANALYTICS_VIEW)),
    db: Session = Depends(get_db),
):
    """Task completion metrics."""
    tasks_by_status = (
        db.query(OperationTask.status, func.count(OperationTask.id))
        .filter(OperationTask.company_id == company_id)
        .group_by(OperationTask.status)
        .all()
    )
    tasks_by_type = (
        db.query(OperationTask.task_type, func.count(OperationTask.id))
        .filter(OperationTask.company_id == company_id)
        .group_by(OperationTask.task_type)
        .all()
    )
    statuses = dict(tasks_by_status)
    return {
        'completed': statuses.get('completed', 0),
        'running': statuses.get('running', 0),
        'failed': statuses.get('failed', 0),
        "tasks_by_status": {row[0]: row[1] for row in tasks_by_status},
        "tasks_by_type": {row[0]: row[1] for row in tasks_by_type},
    }
