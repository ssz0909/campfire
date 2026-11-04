"""Private, durable raw clips. Cross-project reuse requires approved footage.

Conservative v1 matching uses the actual reference image and camera contract,
not a category-only guess. Never reuse a final film with music or a wordmark.
"""
import uuid
from datetime import datetime, timezone
from botocore.exceptions import ClientError

from app.models.asset import Asset
from app.models.video_project import VideoProject, ProviderTask

POLICIES = {'fresh', 'prefer_reuse', 'reuse_only'}


def shot_contract(project, shot):
    previous = next((s for s in project.storyboard or [] if s.get('shot_number') == shot.get('shot_number', 1) - 1), {})
    return {
        'source_asset_id': str(shot.get('source_asset_id') or project.reference_asset_id or ''),
        'aspect_ratio': project.aspect_ratio,
        'generation_mode': project.generation_mode or 'quality',
        'framing': shot.get('framing', 'wide'),
        'focal_x': shot.get('focal_x', 0.5), 'focal_y': shot.get('focal_y', 0.5),
        'camera_movement': shot.get('camera_movement', ''),
        'transition_out': shot.get('transition_out', 'cut'),
        'transition_in': previous.get('transition_out', 'cut'),
        'video_style': project.video_style or '',
        'visual_description': shot.get('visual_description', ''),
        'generation_prompt': shot.get('generation_prompt', ''),
        'opening_frame': shot.get('opening_frame', ''),
        'closing_frame': shot.get('closing_frame', ''),
        'retained_duration': shot.get('duration_seconds'),
        'subshots': shot.get('subshots') or [],
    }


def save_raw_clip(db, project, task, content, storage):
    from app.services.media_processing import enrich_video_asset
    if task.raw_asset_id:
        existing = db.query(Asset).filter_by(id=task.raw_asset_id, company_id=project.company_id,
            is_deleted=False, is_available=True, processing_status='ready').first()
        if existing:
            return existing
    shot = next((s for s in project.storyboard or [] if s.get('shot_number') == task.shot_number), {})
    source_id = shot.get('source_asset_id') or project.reference_asset_id
    source = db.query(Asset).filter_by(id=uuid.UUID(str(source_id)), company_id=project.company_id,
        is_deleted=False).first() if source_id else None
    key = f'{project.company_id}/generated-clips/{task.id}.mp4'
    asset = Asset(company_id=project.company_id, uploaded_by=project.created_by,
        name=f'{project.title[:220]} · 分镜{task.shot_number or 1}',
        original_filename=f'clip-{task.id}.mp4', file_key=key,
        file_url=storage.upload_file(content, key, 'video/mp4'), asset_type='video', mime_type='video/mp4',
        file_size_bytes=len(content), processing_status='ready',
        category=source.category if source else None,
        tags=list(dict.fromkeys([*(source.tags or []), 'AI分镜'])) if source else ['AI分镜'],
        source_description=shot.get('visual_description') or (source.source_description if source else None) or 'AI原始分镜片段',
        asset_metadata={'production_mode': 'raw_model_clip', 'clip_library': {
            'version': 1, 'source_project_id': str(project.id), 'provider_task_id': str(task.id),
            'contract': shot_contract(project, shot),
            'prompt': (task.input_params or {}).get('prompt'),
            'review_status': 'pending', 'usage_count': 0,
            'music_applied': False, 'branding_applied': False,
        }})
    enrich_video_asset(asset, storage, content)
    db.add(asset); db.flush()
    task.raw_asset_id = asset.id
    db.commit()
    return asset


def load_raw_clip(db, project, task, storage):
    if not task.raw_asset_id:
        return None
    asset = db.query(Asset).filter_by(id=task.raw_asset_id, company_id=project.company_id,
        is_deleted=False, is_available=True, processing_status='ready').first()
    if not asset:
        return None
    try:
        return storage.get_file(asset.file_key)
    except (OSError, ValueError, ClientError):
        return None


def approved_candidates(db, project):
    # Approval is verified against the source project as well as the asset.
    assets = db.query(Asset).filter_by(company_id=project.company_id, asset_type='video',
        processing_status='ready', is_deleted=False, is_available=True).all()
    approved = {str(row.id) for row in db.query(VideoProject).filter_by(company_id=project.company_id,
        review_status='approved', is_deleted=False).all()}
    return [a for a in assets if (a.asset_metadata or {}).get('production_mode') == 'raw_model_clip'
        and ((a.asset_metadata or {}).get('clip_library') or {}).get('review_status') == 'approved'
        and ((a.asset_metadata or {}).get('clip_library') or {}).get('source_project_id') in approved]


def compatible(project, shot, asset):
    info = (asset.asset_metadata or {}).get('clip_library') or {}
    contract = info.get('contract') or {}
    target = shot_contract(project, shot)
    if not target['source_asset_id'] or info.get('music_applied') or info.get('branding_applied'):
        return False
    # Transition-bearing footage is tied to its neighbours. Do not silently
    # reuse its fade/dissolve under a different edit.
    if any(c.get(k) != 'cut' for c in (contract, target) for k in ('transition_in', 'transition_out')):
        return False
    match_keys = ('source_asset_id', 'aspect_ratio', 'generation_mode',
                  'framing', 'focal_x', 'focal_y', 'camera_movement',
                  'transition_in', 'transition_out', 'video_style',
                  'visual_description', 'generation_prompt', 'opening_frame', 'closing_frame',
                  'retained_duration', 'subshots')
    if any(contract.get(key) != target.get(key) for key in match_keys):
        return False
    return float(asset.duration_seconds or 0) >= float(shot['duration_seconds']) - 0.01


def plan_reuse(db, project, storage):
    """Reserve every reused clip before any paid generation; retries keep pins."""
    policy = project.reuse_policy or 'fresh'
    if policy not in POLICIES:
        raise ValueError('素材策略无效')
    plan = [dict(s) for s in project.storyboard or []]
    if policy == 'fresh':
        for shot in plan:
            shot.pop('reused_asset_id', None)
        return plan
    candidates = approved_candidates(db, project)
    used = set()
    missing = []
    for shot in plan:
        number = shot['shot_number']
        existing = db.query(ProviderTask).filter_by(video_project_id=project.id, company_id=project.company_id,
            shot_number=number).first()
        if existing:
            # A prior provider submission always wins; don't bypass an unknown
            # submission by choosing another clip and risking duplicate billing.
            if policy == 'reuse_only':
                raise ValueError('仅用已有素材的项目存在模型提交记录，请另建项目')
            shot.pop('reused_asset_id', None)
            continue
        pinned = shot.get('reused_asset_id')
        choices = sorted(candidates, key=lambda a: (
            0 if str(a.id) == pinned else 1,
            ((a.asset_metadata or {}).get('clip_library') or {}).get('usage_count', 0),
            ((a.asset_metadata or {}).get('clip_library') or {}).get('last_used_at') or '', str(a.id)))
        selected = None
        for candidate in choices:
            if candidate.id in used or not compatible(project, shot, candidate):
                continue
            try:
                if not storage.get_file(candidate.file_key):
                    continue
            except (OSError, ValueError, ClientError):
                continue
            selected = candidate
            break
        if selected:
            shot['reused_asset_id'] = str(selected.id)
            used.add(selected.id)
        else:
            shot.pop('reused_asset_id', None)
            missing.append(number)
    if missing and policy == 'reuse_only':
        raise ValueError(f'仅用已有素材：镜头{", ".join(map(str, missing))}缺少已审核且画幅、构图、运镜相符的分镜，请补充素材或改为不足补生成；未调用视频模型')
    return plan


def read_reused_clip(db, project, shot, storage):
    asset = next((a for a in approved_candidates(db, project) if str(a.id) == shot['reused_asset_id']), None)
    if not asset or not compatible(project, shot, asset):
        raise ValueError('已选复用分镜失效或未审核，请重新执行以重新匹配；未重新提交该镜头')
    return storage.get_file(asset.file_key), asset


def record_use(db, project, asset):
    # One project counts once even after retry/recovery. Serialise metadata
    # writes so concurrent projects do not lose usage records.
    asset = db.query(Asset).filter_by(id=asset.id, company_id=project.company_id).with_for_update().populate_existing().one()
    metadata = dict(asset.asset_metadata or {})
    info = dict(metadata['clip_library'])
    projects = list(info.get('used_project_ids') or [])
    if str(project.id) not in projects:
        projects.append(str(project.id))
        info.update(used_project_ids=projects, usage_count=len(projects), last_used_at=datetime.now(timezone.utc).isoformat())
        asset.asset_metadata = {**metadata, 'clip_library': info}


def approve_project_clips(db, project):
    # Approve only raw clips referenced by the final storyboard. Older failed
    # attempts can remain attached to the project but must not enter inventory.
    used_asset_ids = {
        str(shot.get('output_asset_id'))
        for shot in (project.storyboard or [])
        if shot.get('output_asset_id') and not shot.get('reused_asset_id')
    }
    rows = db.query(ProviderTask).filter_by(video_project_id=project.id, company_id=project.company_id).all()
    for task in rows:
        if not task.raw_asset_id or str(task.raw_asset_id) not in used_asset_ids:
            continue
        asset = db.query(Asset).filter_by(id=task.raw_asset_id, company_id=project.company_id, is_deleted=False).with_for_update().first()
        info = ((asset.asset_metadata or {}).get('clip_library') or {}) if asset else {}
        if info.get('source_project_id') == str(project.id):
            asset.asset_metadata = {**asset.asset_metadata, 'clip_library': {**info, 'review_status': 'approved'}}
