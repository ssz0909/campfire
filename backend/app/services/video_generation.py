"""Persistent video generation jobs; never retry a billable submission blindly."""
import asyncio
import logging
import time
import uuid
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import httpx
from app.config import settings
from app.database import SessionLocal
from app.models.video_project import VideoProject, ProviderTask
from app.models.asset import Asset
from app.services.storage_service import StorageService

worker = ThreadPoolExecutor(max_workers=2, thread_name_prefix='video-generation')
logger = logging.getLogger(__name__)
_active = set()
_active_lock = threading.Lock()

def _finalize_content(db, project, content, storage):
    from app.services.video_music import apply_music
    from app.services.video_branding import apply_opening_branding
    content = apply_music(db, project, content, storage)
    return apply_opening_branding(db, project, content)

def reference_url(db, project, asset_id=None, shot=None):
    reference_id = asset_id or project.reference_asset_id
    if not reference_id:
        if project.creation_mode in ('reference_inspired', 'reference_inspired_video'):
            raise ValueError('参考图生成需要选择一张本企业可用图片')
        return None
    asset = db.query(Asset).filter_by(id=reference_id, company_id=project.company_id,
        is_deleted=False, is_available=True, processing_status='ready').first()
    if not asset or asset.asset_type != 'image':
        raise ValueError('首帧只支持本企业已处理完成且授权可用的图片，参考视频分析尚未支持')
    storage = StorageService(settings.STORAGE_BACKEND)
    if settings.STORAGE_BACKEND == 'local' and not settings.PUBLIC_BASE_URL:
        raise ValueError('本地参考图需要配置公网可访问的 PUBLIC_BASE_URL，供模型读取首帧')
    from app.services.media_processing import normalize_reference_image
    crop = {key:shot[key] for key in ('framing','focal_x','focal_y') if key in shot} if shot else {}
    normalized = normalize_reference_image(storage.get_file(asset.file_key), project.aspect_ratio, **crop)
    import hashlib, json
    suffix = '-' + hashlib.sha256(json.dumps(crop, sort_keys=True).encode()).hexdigest()[:12] if crop else ''
    key = f'{project.company_id}/video-references/{asset.id}-{project.aspect_ratio.replace(":", "x")}{suffix}.jpg'
    storage.upload_file(normalized, key, 'image/jpeg')
    url = storage.generate_presigned_url(key)
    if url.startswith('/'):
        if not settings.PUBLIC_BASE_URL:
            raise ValueError('本地参考图需要配置公网可访问的 PUBLIC_BASE_URL，供模型读取首帧')
        url = settings.PUBLIC_BASE_URL.rstrip('/') + url
    if urlparse(url).scheme not in ('http', 'https'):
        raise ValueError('参考图必须是模型服务可访问的 HTTP 地址')
    return url


def _compose_selected_images(db, project, selected_ids):
    """Generate each reference as a real model clip, then assemble the clips."""
    assets = db.query(Asset).filter(Asset.company_id==project.company_id, Asset.id.in_(selected_ids),
        Asset.asset_type=='image', Asset.is_deleted==False, Asset.is_available==True,
        Asset.processing_status=='ready').all()
    by_id = {asset.id:asset for asset in assets}
    if len(by_id) != len(selected_ids):
        raise ValueError('所选图片有缺失或不可用，请更新视频项目素材')
    from app.providers.video.base import VideoGenerationRequest
    from app.services.media_processing import assemble_model_clips, enrich_video_asset
    storage = StorageService(settings.STORAGE_BACKEND)
    client = None
    clips, shots = [], []
    original_plan = project.storyboard or []
    cost = getattr(project, 'generation_mode', 'quality') == 'cost'
    planned = bool(project.storyboard and project.storyboard[0].get('planning_version') == 2)
    if cost:
        from app.services.video_cost_plan import validate_cost_plan
        plan = validate_cost_plan(project.storyboard, [{'id':str(v)} for v in selected_ids], project.target_duration_seconds)
        duration = project.target_duration_seconds
    elif planned:
        from app.services.video_director import validate_plan
        plan = validate_plan(project.storyboard, [{'id':str(v)} for v in selected_ids], project.target_duration_seconds, allow_legacy_reuse=True)
        duration = project.target_duration_seconds
    else:
        duration = max(float(project.target_duration_seconds or 5), 5 * len(selected_ids))
        plan = [{'source_asset_id':str(asset_id), 'duration_seconds':duration/len(selected_ids)} for asset_id in selected_ids]
    from app.services.video_clip_library import plan_reuse, read_reused_clip, record_use
    # Validation strips execution metadata. Restore only trusted server-side
    # pins, then revalidate approval and compatibility in plan_reuse.
    pins = {s.get('shot_number'): s.get('reused_asset_id') for s in original_plan}
    project.storyboard = [
        {**s, 'shot_number':i, **({'reused_asset_id':pins[i]} if pins.get(i) else {})}
        for i,s in enumerate(plan, 1)
    ]
    plan = plan_reuse(db, project, storage)
    project.storyboard = plan
    db.commit()
    generated_count, reused_count = 0, 0
    for number, shot in enumerate(plan, 1):
        asset_id = uuid.UUID(shot['source_asset_id'])
        asset = by_id[asset_id]
        analysis = (asset.asset_metadata or {}).get('vision_analysis') or {}
        description = analysis.get('visual_description') or asset.source_description or asset.name
        clip_duration = shot['duration_seconds']
        if cost:
            from app.services.video_cost_plan import cost_prompt
            prompt = cost_prompt(shot['subshots'], clip_duration) + f'\n当前参考图可见事实：{description}。'
        elif planned:
            from app.services.video_director import shot_generation_prompt
            prompt = (f"{shot_generation_prompt(plan, number-1)}\n当前镜头可见事实：{description}。"
                      f"景别：{shot['framing']}；运镜：{shot['camera_movement']}。"
                      '只生成当前参考场景的动态镜头，可执行脚本指定的淡入淡出与衔接动作，不凭空切换到其他场景；不生成字幕、标志或文字，不添加参考图外的人物与设施；'
                      '保持建筑直线与主体结构，避免闪烁、扭曲。动作从片段起始即自然展开。')
        else:
            prompt = (f'{project.script or project.marketing_goal or project.title}\n'
                      f'现在只生成第{number}个动态镜头：{description}。保持参考图中的真实主体与场景，'
                      f'统一{project.aspect_ratio}构图。自然缓慢推进或横移，不得生成照片轮播或虚构设施。')
        if shot.get('reused_asset_id'):
            clip, reused_asset = read_reused_clip(db, project, shot, storage)
            record_use(db, project, reused_asset)
            task_id, output_asset_id = None, str(reused_asset.id)
            reused_count += 1
        else:
            if project.reuse_policy == 'reuse_only':
                raise ValueError('仅用已有素材模式禁止提交视频模型')
            request = VideoGenerationRequest(prompt=prompt, duration_seconds=5 if planned or cost else clip_duration,
                aspect_ratio=project.aspect_ratio, style=project.video_style,
                reference_image_url=reference_url(db, project, asset_id, shot=shot) if planned or cost else reference_url(db, project, asset_id),
                resolution=settings.VIDEO_RESOLUTION, audio=False if project.music_asset_id else settings.VIDEO_AUDIO)
            if client is None:
                client = provider()
            clip, task = _generate_clip(db, project, client, request, shot_number=number)
            task_id, output_asset_id = task.provider_task_id, str(task.raw_asset_id) if task.raw_asset_id else None
            generated_count += 1
        clips.append(clip)
        shots.append({**shot, 'shot_number':number, 'visual_description':shot.get('visual_description') or description,
            'duration_seconds':clip_duration, 'source_asset_id':str(asset.id),
            'generation_status':'completed', 'generation_task_id':task_id, 'output_asset_id':output_asset_id})
        project.storyboard = list(shots) + plan[number:] if planned or cost else list(shots)
        db.commit()
    project.project_status = 'compositing'; db.commit()
    content = assemble_model_clips(clips, project.aspect_ratio, [s['duration_seconds'] for s in plan] if planned or cost else clip_duration)
    content, branding = _finalize_content(db, project, content, storage)
    key = f'{project.company_id}/generated/{uuid.uuid4()}.mp4'
    asset = Asset(company_id=project.company_id, uploaded_by=project.created_by, name=project.title,
        original_filename='generated-video.mp4', file_key=key,
        file_url=storage.upload_file(content, key, 'video/mp4'), asset_type='video', mime_type='video/mp4',
        file_size_bytes=len(content), processing_status='ready', source_description='视频模型生成的多镜头主题短片',
        asset_metadata={'production_mode':'video_model_multi_shot', 'source_asset_ids':[str(v) for v in selected_ids],
            'generation_mode':getattr(project, 'generation_mode', 'quality'),
            'reuse_policy':project.reuse_policy, 'reused_clips':reused_count,
            'opening_brand': branding})
    enrich_video_asset(asset, storage, content)
    db.add(asset); db.flush()
    project.output_asset_id = asset.id
    project.target_duration_seconds = int(duration)
    project.project_status = 'pending_review'
    project.quality_check_result = {'status':'generated', 'production_mode':'video_model_multi_shot',
        'generation_mode':getattr(project, 'generation_mode', 'quality'), 'generation_requests':generated_count,
        'reused_clips':reused_count, 'reuse_policy':project.reuse_policy,
        'note':f'本片复用 {reused_count} 个分镜，使用 {generated_count} 个模型生成片段，已统一画幅合成，请审核成片与发布文案。'}
    db.commit()


def provider():
    if settings.VIDEO_PROVIDER == 'mock':
        raise ValueError('请启用 relay 视频服务；Mock 不会生成真实视频')
    from app.providers.video.relay_provider import RelayVideoProvider
    return RelayVideoProvider()

def enqueue(project_id):
    key = str(project_id)
    with _active_lock:
        if key in _active:
            return
        _active.add(key)
    future = worker.submit(run, key)
    def done(_):
        with _active_lock:
            _active.discard(key)
    future.add_done_callback(done)

def recover():
    with SessionLocal() as db:
        projects = db.query(VideoProject).filter(VideoProject.is_deleted == False,
            VideoProject.project_status.in_(['analyzing','generating_shots','compositing','waiting_retry'])).all()
        for project in projects:
            task = db.query(ProviderTask).filter_by(video_project_id=project.id,company_id=project.company_id).order_by(ProviderTask.created_at.desc()).first()
            if task and task.provider_task_id:
                enqueue(project.id)
            else:
                project.project_status = 'failed'
                project.quality_check_result = {'status':'interrupted',
                    'note':'服务重启时未找到已确认的模型任务 ID，请核对中转后台后再操作，未自动重新提交'}
        db.commit()

def _generate_clip(db, project, client, request, shot_number=None):
    task = db.query(ProviderTask).filter_by(video_project_id=project.id, company_id=project.company_id, shot_number=shot_number).order_by(ProviderTask.created_at.desc(), ProviderTask.id.desc()).first()
    if task and task.status == 'completed' and task.raw_asset_id:
        from app.services.video_clip_library import load_raw_clip
        content = load_raw_clip(db, project, task, StorageService(settings.STORAGE_BACKEND))
        if content is not None:
            return content, task
    if task and task.status == 'retry_requested':
        task = None
    if task and task.status == 'completed' and task.output_url:
        from app.providers.video.base import VideoGenerationResult
        result = VideoGenerationResult(provider_task_id=task.provider_task_id, status='completed',output_url=task.output_url)
    elif task and task.provider_task_id and task.status != 'failed':
        result = asyncio.run(client.get_task_status(task.provider_task_id))
    elif task and not task.provider_task_id:
        raise ValueError('上次提交结果不确定，禁止自动重复计费；请核对中转后台任务')
    elif task and task.status == 'failed':
        raise ValueError('该镜头生成失败，请核对中转后台后另建项目，避免重复计费')
    else:
        task = ProviderTask(video_project_id=project.id,company_id=project.company_id,
            provider_name='relay',task_type='video_generation',status='pending',shot_number=shot_number,
            input_params=request.model_dump(), submitted_at=datetime.now(timezone.utc))
        db.add(task);db.commit()
        try:
            result = asyncio.run(client.submit_generation(request))
        except Exception as exc:
            from app.providers.video.relay_provider import RelayVideoRequestError
            if isinstance(exc, RelayVideoRequestError) and exc.status_code in (400, 401, 403, 404, 405, 413, 415, 422, 429):
                task.status = 'rejected'
            else:
                task.status = 'submission_unknown'
            task.error_message = str(exc) if isinstance(exc, ValueError) else '提交结果不确定，请核对中转后台任务'
            db.commit()
            raise
    task.provider_task_id = result.provider_task_id
    task.status = result.status
    task.output_url = result.output_url
    if result.status == 'failed':
        task.error_message = '模型服务返回生成失败'
    project.project_status = 'generating_shots'
    db.commit()
    resumed_at = (task.input_params or {}).get('_retry_poll_started_at')
    submitted = datetime.fromisoformat(resumed_at) if resumed_at else (task.submitted_at or datetime.now(timezone.utc))
    if submitted.tzinfo is None: submitted = submitted.replace(tzinfo=timezone.utc)
    remaining = settings.VIDEO_TIMEOUT_SECONDS - (datetime.now(timezone.utc)-submitted).total_seconds()
    deadline = time.monotonic() + remaining
    while result.status == 'processing':
        if time.monotonic() >= deadline: raise ValueError('视频生成超时，请检查中转服务任务状态，勿重复提交')
        time.sleep(max(1,settings.VIDEO_POLL_SECONDS))
        result = asyncio.run(client.get_task_status(result.provider_task_id))
        task.status = result.status;task.output_url = result.output_url;db.commit()
        if result.status == 'failed':
            task.error_message = '模型服务返回生成失败'
            db.commit()
    if result.status != 'completed': raise ValueError('视频生成失败，请检查中转服务任务详情')
    project.project_status = 'compositing';db.commit()
    with httpx.Client(timeout=120,follow_redirects=True) as download:
        with download.stream('GET',result.output_url) as response:
            response.raise_for_status()
            content_type = response.headers.get('content-type','').split(';')[0]
            if not content_type.startswith('video/') and content_type != 'application/octet-stream':
                raise ValueError('服务返回的结果不是视频文件')
            chunks=[];size=0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024: raise ValueError('生成视频超过存储大小限制')
                chunks.append(chunk)
    content = b''.join(chunks)
    if not content: raise ValueError('生成视频文件为空')
    from app.services.media_processing import inspect_video
    inspect_video(content)
    from app.services.video_clip_library import save_raw_clip
    save_raw_clip(db, project, task, content, StorageService(settings.STORAGE_BACKEND))
    task.status='completed'
    task.completed_at=datetime.now(timezone.utc)
    task.error_message=None
    from app.models.cost import CostRecord
    if result.cost_cents is not None and not db.query(CostRecord).filter_by(video_project_id=project.id, provider_request_id=result.provider_task_id).first():
        db.add(CostRecord(company_id=project.company_id, video_project_id=project.id,
            provider='video_relay', model_name=client.model, record_type='video_generation',
            quantity=float(request.duration_seconds), unit='seconds',
            unit_cost_cents=float(result.cost_cents) / max(float(request.duration_seconds), 1),
            total_cost_cents=float(result.cost_cents), is_estimate=False,
            provider_request_id=result.provider_task_id, requested_at=datetime.now(timezone.utc).isoformat()))
    db.commit()
    return content, task


def run(project_id):
    db = SessionLocal()
    project = None
    task = None
    lease = None
    lease_key = uuid.UUID(project_id).int % (2 ** 63 - 1)
    try:
        # Hold a session lock on a dedicated connection across commits/downloads.
        if db.get_bind().dialect.name == 'postgresql':
            from sqlalchemy import text
            lease = db.get_bind().connect()
            if not lease.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key':lease_key}).scalar():
                return
        project = db.get(VideoProject, uuid.UUID(project_id))
        if not project or project.project_status not in ('analyzing','generating_shots','compositing','waiting_retry'): return
        if project.is_deleted:
            return
        if project.output_asset_id:
            project.project_status = 'completed' if project.review_status == 'approved' else 'pending_review'
            db.commit()
            return
        selected_ids=[uuid.UUID(str(value)) for value in (project.selected_asset_ids or [])]
        if selected_ids and project.storyboard and (getattr(project, 'generation_mode', 'quality') == 'cost' or project.storyboard[0].get('planning_version') == 2):
            _compose_selected_images(db, project, selected_ids)
            return
        if len(selected_ids)>1:
            _compose_selected_images(db, project, selected_ids)
            return
        if project.reuse_policy == 'reuse_only':
            raise ValueError('仅用已有素材需要图片分镜计划；未调用视频模型')
        client = provider()
        from app.providers.video.base import VideoGenerationRequest
        selected = db.query(Asset).filter(Asset.company_id==project.company_id, Asset.id.in_(selected_ids)).all() if selected_ids else []
        visual_notes = []
        for index, asset in enumerate(selected, 1):
            analysis = (asset.asset_metadata or {}).get('vision_analysis') or {}
            visual_notes.append(f'素材{index}：{analysis.get("visual_description") or asset.source_description or asset.name}')
        prompt = chr(10).join(str(v) for v in [project.title,project.marketing_goal,project.video_theme,
            project.target_audience,project.key_selling_points,project.cta_text,project.script] if v)
        if visual_notes:
            prompt += '\n参考素材画面要点：\n' + '\n'.join(visual_notes)
        prompt += (f'\n必须生成真正连续运动的视频，不得做图片轮播、幻灯片或静态画面拼接。'
                   f'画面比例严格为 {project.aspect_ratio}，所有主体保持完整，禁止横竖屏混排、拉伸和黑边。'
                   '如提供首帧参考图，保持其真实主体与场景，添加自然镜头运动及可见主体的合理动态，不虚构素材之外的人物或设施；未提供参考图时按用户脚本和主题生成。')
        request = VideoGenerationRequest(prompt=prompt,duration_seconds=project.target_duration_seconds or 5,
            aspect_ratio=project.aspect_ratio,style=project.video_style,
            reference_image_url=reference_url(db, project), resolution=settings.VIDEO_RESOLUTION, audio=False if project.music_asset_id else settings.VIDEO_AUDIO)
        content, task = _generate_clip(db, project, client, request)
        from app.services.media_processing import assemble_model_clips
        content = assemble_model_clips([content], project.aspect_ratio, project.target_duration_seconds or 5)
        content, branding = _finalize_content(db, project, content, StorageService(settings.STORAGE_BACKEND))
        size = len(content)
        key = f'{project.company_id}/generated/{uuid.uuid4()}.mp4'
        url = StorageService(settings.STORAGE_BACKEND).upload_file(content,key,'video/mp4')
        asset = Asset(company_id=project.company_id,uploaded_by=project.created_by,name=project.title,
            original_filename='generated.mp4',file_key=key,file_url=url,asset_type='video',mime_type='video/mp4',
            file_size_bytes=size,processing_status='ready',source_description='AI 视频生成',
            asset_metadata={'provider':'relay','provider_task_id':task.provider_task_id,'opening_brand':branding})
        from app.services.media_processing import enrich_video_asset
        enrich_video_asset(asset, StorageService(settings.STORAGE_BACKEND), content)
        db.add(asset);db.flush()
        project.output_asset_id=asset.id
        project.project_status='pending_review'
        project.quality_check_result={'status':'generated','note':'视频模型已生成动态成片，请审核画面、比例与文案后批准使用。',
            'production_mode':'video_model'}
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception('Video generation failed for project %s',project_id)
        if project:
            project = db.get(VideoProject,uuid.UUID(project_id))
            if not project:
                return
            project.project_status='failed'
            detail = str(exc) if isinstance(exc, ValueError) else '服务连接或结果保存失败，请查看后端日志'
            project.quality_check_result={'status':'failed','note':detail}
            if task:
                task.error_message = detail
            db.commit()
    finally:
        # Runs after final assembly, thumbnail and music for every production path.
        if project and project.project_status == 'pending_review':
            try:
                from app.services.auto_execution import approve_video
                approve_video(db, project)
            except Exception as exc:
                db.rollback()
                db.refresh(project)
                project.quality_check_result = {**(project.quality_check_result or {}),
                    'automation_error': str(getattr(exc, 'detail', None) or exc)}
                db.commit()
                logger.exception('Automatic video review blocked for project %s', project_id)
        db.close()
        if lease is not None:
            from sqlalchemy import text
            try:
                lease.rollback()
                lease.execute(text('SELECT pg_advisory_unlock(:key)'), {'key':lease_key})
            finally:
                lease.close()
