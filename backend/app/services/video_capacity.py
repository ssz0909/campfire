"""Shared image/time contract for planning, handoffs and video execution."""
import math
import re

QUALITY_MIN_SHOTS = 5
QUALITY_OPENING_MAX = 2
QUALITY_SHOT_MAX = 3.5
COST_SEGMENT_SECONDS = 5
_RANGE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:秒|[sS]\b)?\s*[-—–~～至到]\s*(\d+(?:\.\d+)?)\s*(秒|[sS]\b|分钟|分|[mM][iI][nN]\b)')
_SINGLE = re.compile(r'(\d+(?:\.\d+)?)\s*(秒|[sS]\b|分钟|分|[mM][iI][nN]\b)')


def duration_request(params=None, goal=''):
    params = params or {}
    stored = params.get('video_duration_request')
    if stored:
        low, high, source = stored['min_seconds'], stored['max_seconds'], stored['source']
    elif params.get('target_duration_seconds') is not None:
        low = high = params['target_duration_seconds']
        source = 'fixed'
    else:
        match = _RANGE.search(goal or '')
        if match:
            factor = 60 if match[3].lower() in ('分钟', '分', 'min') else 1
            low, high = float(match[1]) * factor, float(match[2]) * factor
            source = 'range'
        else:
            match = _SINGLE.search(goal or '')
            if match:
                low = high = float(match[1]) * (60 if match[2].lower() in ('分钟', '分', 'min') else 1)
                source = 'fixed'
            else:
                low, high, source = 15, 30, 'default'
    low, high = float(low), float(high)
    if not all(math.isfinite(v) for v in (low, high)) or not 15 <= low <= high <= 60:
        raise ValueError('视频制作员的成片时长必须为15至60秒')
    low, high = math.ceil(low), math.floor(high)
    if low > high:
        raise ValueError('视频时长范围内没有可用的整数秒')
    return {'min_seconds': low, 'max_seconds': high, 'source': source}


def task_duration_request(db, task):
    """Recover original ranges in legacy handoffs that stored only the upper bound."""
    params = task.input_params or {}
    if params.get('video_duration_request'):
        return duration_request(params)
    origin = task
    seen = set()
    while origin.parent_task_id and origin.id not in seen:
        seen.add(origin.id)
        from app.models.task import OperationTask
        parent = db.query(OperationTask).filter_by(id=origin.parent_task_id, company_id=task.company_id).first()
        if parent is None:
            break
        origin = parent
    original = origin.input_params or {}
    # Legacy closed-loop descendants inherit their root duration; recover its intent.
    if origin.id != task.id and params.get('execution_goal') and params.get('execution_goal') == (original.get('execution_goal') or original.get('goal') or origin.title):
        return duration_request(original, original.get('execution_goal') or original.get('goal') or origin.title)
    return duration_request(params, params.get('execution_goal') or params.get('goal') or task.title)


def minimum_images(duration, mode='quality'):
    if mode == 'cost':
        return math.ceil(duration / COST_SEGMENT_SECONDS)
    return max(QUALITY_MIN_SHOTS, 1 + math.ceil((duration - QUALITY_OPENING_MAX) / QUALITY_SHOT_MAX))


def maximum_duration(count, mode='quality'):
    if mode == 'cost':
        return min(60, count * COST_SEGMENT_SECONDS)
    return min(60, math.floor(QUALITY_OPENING_MAX + (count - 1) * QUALITY_SHOT_MAX)) if count >= QUALITY_MIN_SHOTS else 0


def capacity_brief(assets, request, mode='quality'):
    count = len({str(a['id']) for a in assets})
    maximum = maximum_duration(count, mode)
    feasible = maximum >= request['min_seconds']
    duration = min(request['max_seconds'], maximum) if feasible else request['min_seconds']
    required = minimum_images(duration, mode)
    label = '成本优先' if mode == 'cost' else '质量优先'
    note = (f'{label}，可用不同图片{count}张；本次成片{duration}秒，至少需要{required}张，整片不重复引用图片。' if feasible else
            f'{label}制作{duration}秒且不重复素材至少需要{required}张不同图片，当前仅{count}张，还缺{required-count}张。请补充素材；如调整时长或制作模式，请先修改任务要求。')
    return {'target_duration_seconds': duration, 'aspect_ratio': '9:16', 'generation_mode': mode,
            'duration_request': request, 'available_image_count': count, 'minimum_image_count': required,
            'maximum_supported_duration_seconds': maximum, 'feasible': feasible, 'capacity_note': note}


def require_capacity(brief):
    if not brief['feasible']:
        raise ValueError(brief['capacity_note'])
