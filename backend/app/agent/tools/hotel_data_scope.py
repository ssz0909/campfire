"""Resolve analysis dates and fill verified sync coverage before reading metrics."""
import asyncio
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.connectors.hotel.models import HotelSyncJob
from app.core.permissions import Permission


def analysis_period(params, goal, today=None):
    today = today or datetime.now(ZoneInfo('Asia/Shanghai')).date()
    start, end = params.get('date_from'), params.get('date_to')
    if start or end:
        if not start or not end:
            raise ValueError('分析时间范围需同时提供 date_from 和 date_to')
        start, end = date.fromisoformat(start), date.fromisoformat(end)
    else:
        dates = re.findall(r'(?<!\d)(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?', goal)
        if len(dates) == 2:
            start, end = [date(*map(int, value)) for value in dates]
        elif dates:
            raise ValueError('请明确分析起止日期，例如 2026-01-01 至 2026-10-20')
        elif any(word in goal for word in ('同比', '环比', '季度')):
            raise ValueError('比较分析需分别指定起止日期，当前请先创建单个明确区间的分析任务')
        elif match := re.search(r'(20\d{2})年(\d{1,2})月', goal):
            year, month = map(int, match.groups())
            start = date(year, month, 1)
            end = min((start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), today)
        elif any(word in goal for word in ('本年', '今年', '本年度')):
            start, end = date(today.year, 1, 1), today
        elif '去年' in goal:
            start, end = date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
        elif match := re.search(r'(20\d{2})年', goal):
            year = int(match[1])
            start, end = date(year, 1, 1), min(date(year, 12, 31), today)
        elif any(word in goal for word in ('本月', '这个月')):
            start, end = today.replace(day=1), today
        elif '上月' in goal:
            end = today.replace(day=1) - timedelta(days=1)
            start = end.replace(day=1)
        elif match := re.search(r'(?:近|最近|过去)(\d+)天', goal):
            start, end = today - timedelta(days=int(match[1]) - 1), today
        elif any(word in goal for word in ('季度', '同比', '环比', '月份', '全年', '年度', '月')):
            raise ValueError('该时间表达需明确起止日期，请提供 date_from/date_to 或完整日期范围')
        else:
            start, end = today - timedelta(days=29), today
    if start > end or end > today or (end - start).days > 366:
        raise ValueError('分析范围需为截至今天的有效起止日期，单次不超过 367 天')
    return start, end


def missing_windows(start, end, jobs):
    covered = sorted((date.fromisoformat(j.begin_date), date.fromisoformat(j.end_date))
                     for j in jobs if j.status == 'success' and j.begin_date and j.end_date)
    missing, cursor = [], start
    for left, right in covered:
        if right < cursor or left > end:
            continue
        if left > cursor:
            missing.append((cursor, min(end, left - timedelta(days=1))))
        cursor = max(cursor, right + timedelta(days=1))
    if cursor <= end:
        missing.append((cursor, end))
    # Refresh today even if a previous sync already covered it.
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    if end == today and not any(a <= today <= b for a, b in missing):
        missing.append((today, today))
    chunks = []
    for left, right in missing:
        while left <= right:
            stop = min(right, (left.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))
            chunks.append((left, stop))
            left = stop + timedelta(days=1)
    return chunks


def ensure_analysis_orders(service, task, tenant_context, runtime, start, end):
    db = service.db
    result = {'requested_period': [start.isoformat(), end.isoformat()],
              'complete': False, 'sync_job_ids': [], 'notes': [],
              'date_basis': '订单创建日期；不是入住日期或财务实收口径'}
    config = service.get_config()
    if not config or not config.hotel_num:
        result['notes'].append('酒店连接器未配置，无法自动补同步')
        return result
    jobs = db.query(HotelSyncJob).filter_by(company_id=task.company_id).all()
    windows = missing_windows(start, end, jobs)
    if any(j.status in ('queued', 'running') for j in jobs):
        result['notes'].append('已有酒店同步任务执行中，请完成后重试分析；本次数据未确认完整')
        return result
    if windows and not tenant_context.has_permission(Permission.CONNECTOR_CONFIG):
        result['notes'].append('任务发起人无连接器同步权限，未执行自动同步，请管理员补齐数据')
        return result
    if not service.is_web(config):
        earliest = datetime.now(ZoneInfo('Asia/Shanghai')).date() - timedelta(days=90)
        if any(left < earliest for left, _ in windows):
            result['notes'].append('当前开放 API 连接器限制最近90天，缺失历史范围无法自动获取；可使用 Web 连接器或补录历史数据')
            return result
    for left, right in windows:
        db.refresh(task, ['status'])
        if task.status == 'cancelled':
            raise ValueError('任务已取消，停止补同步')
        runtime._append_log(task, 'info', f'分析前自动同步订单：{left} 至 {right}')
        async def sync():
            job = await service.create_sync_job(trigger='agent', requested_by=task.created_by,
                begin_date=left.isoformat(), end_date=right.isoformat())
            return await service.run_sync(job)
        try:
            job = asyncio.run(sync())
        except Exception:
            db.rollback()
            result['notes'].append('订单补同步异常，停止后续同步；请检查连接器后重试，不能按完整区间下结论')
            return result
        result['sync_job_ids'].append(str(job.id))
        if job.status != 'success':
            result['notes'].append(f'{left} 至 {right} 同步未完整成功：{job.error or job.status}；请检查登录状态或平台范围限制')
            return result
    result['complete'] = True
    result['notes'].append('所需范围已有成功同步记录，已补齐缺失区间；历史订单后续变更以再次同步结果为准')
    return result
