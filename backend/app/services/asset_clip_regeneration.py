"""Standalone library variants use durable provider jobs, never mutate source films."""
from copy import deepcopy
import uuid

from fastapi import HTTPException

from app.models.asset import Asset
from app.models.video_project import VideoProject

MODE = 'library_clip'
ACTIVE = ('analyzing', 'generating_shots', 'compositing', 'waiting_retry')


def info(asset):
    return ((asset.asset_metadata or {}).get('clip_library') or {})


def reference(db, asset):
    if asset is None:
        raise HTTPException(422, '参考图片已删除或不可用')
    if asset.asset_type == 'image':
        source_id = asset.id
    elif (asset.asset_metadata or {}).get('production_mode') == 'raw_model_clip':
        source_id = (info(asset).get('contract') or {}).get('source_asset_id')
    else:
        raise HTTPException(422, '请选择参考图片或 AI 原始分镜')
    try:
        source_id = uuid.UUID(str(source_id))
    except ValueError as exc:
        raise HTTPException(422, '分镜缺少有效的参考图片') from exc
    source = db.query(Asset).filter_by(id=source_id, company_id=asset.company_id,
        asset_type='image', is_deleted=False, is_available=True, processing_status='ready').first()
    if not source:
        raise HTTPException(422, '参考图片已删除或不可用，无法重新生成')
    return source


def create(db, asset, user_id, prompt, request_id, aspect_ratio='9:16'):
    prompt = prompt.strip()
    if len(prompt) < 4:
        raise HTTPException(422, '请填写至少4个字的分镜提示词')
    source = reference(db, asset)
    db.query(Asset).filter_by(id=source.id, company_id=asset.company_id).with_for_update().one()
    existing = db.get(VideoProject, request_id)
    if existing:
        if (existing.company_id != asset.company_id or existing.creation_mode != MODE
                or existing.reference_asset_id != source.id or existing.script != prompt or existing.is_deleted):
            raise HTTPException(409, '请求标识已使用，请重新打开生成窗口')
        return existing
    active = db.query(VideoProject).filter(VideoProject.company_id == asset.company_id,
        VideoProject.creation_mode == MODE, VideoProject.reference_asset_id == source.id,
        VideoProject.is_deleted == False, VideoProject.project_status.in_(ACTIVE)).first()
    if active:
        raise HTTPException(409, '该图片已有分镜正在生成，请等待完成')
    from app.services.industry_templates import resolve_snapshot
    contract = info(asset).get('contract') or {}
    description = ((source.asset_metadata or {}).get('vision_analysis') or {}).get('visual_description') or source.source_description or source.name
    # Variants never inherit the original film's task, music, brand or review state.
    mode = contract.get('generation_mode', 'quality')
    retained = min(float(contract.get('retained_duration') or (5 if mode == 'cost' else 3)), 5)
    shot = {'shot_number':1, 'source_asset_id':str(source.id), 'duration_seconds':retained,
        'purpose':'人工优化分镜', 'framing':contract.get('framing','wide'),
        'focal_x':contract.get('focal_x',0.5), 'focal_y':contract.get('focal_y',0.5),
        'visual_description':description[:1500], 'camera_movement':'按人工提示词自然运镜',
        'generation_prompt':prompt, 'opening_frame':'', 'closing_frame':'',
        'transition_out':'cut', 'transition_duration_seconds':0, 'transition_notes':''}
    if mode == 'cost':
        from app.services.video_cost_plan import cost_prompt
        shot['subshots'] = [{'duration_seconds':retained, 'description':prompt}]
        shot['generation_prompt'] = cost_prompt(shot['subshots'], retained)
    project = VideoProject(id=request_id, company_id=asset.company_id, created_by=user_id,
        title=f'{source.name[:210]} · 手动分镜', creation_mode=MODE,
        generation_mode=mode, reuse_policy='fresh', script=prompt,
        aspect_ratio=contract.get('aspect_ratio') or aspect_ratio,
        video_style=contract.get('video_style') or None,
        reference_asset_id=source.id, selected_asset_ids=[str(source.id)],
        reference_analysis={'library_clip':{'origin_asset_id':str(asset.id)}},
        target_duration_seconds=5, storyboard=[shot], project_status='analyzing',
        review_status='pending_review', music_disabled=True,
        industry_template_snapshot=resolve_snapshot(db, asset.company_id))
    from app.services.video_generation import provider, reference_url, enqueue
    try:
        provider()
        reference_url(db, project, source.id, shot=shot)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(project)
    db.commit()
    enqueue(project.id)
    return project


def render_job(project):
    return {'id':str(project.id), 'status':project.project_status,
        'output_asset_id':str(project.output_asset_id) if project.output_asset_id else None,
        'error':(project.quality_check_result or {}).get('note') if project.project_status == 'failed' else None,
        'prompt':project.script, 'created_at':project.created_at}


def related(db, asset, page=1, page_size=10):
    source = reference(db, asset)
    clips = db.query(Asset).filter_by(company_id=asset.company_id, asset_type='video',
        is_deleted=False).order_by(Asset.created_at.desc(), Asset.id.desc()).all()
    clips = [a for a in clips if (a.asset_metadata or {}).get('production_mode') == 'raw_model_clip'
        and (info(a).get('contract') or {}).get('source_asset_id') == str(source.id)]
    jobs = db.query(VideoProject).filter_by(company_id=asset.company_id,
        reference_asset_id=source.id, creation_mode=MODE, is_deleted=False).order_by(
            VideoProject.created_at.desc()).limit(10).all()
    return source, clips[(page-1)*page_size:page*page_size], len(clips), [render_job(j) for j in jobs]


def generate(db, project):
    from app.providers.video.base import VideoGenerationRequest
    from app.services.video_generation import _generate_clip, provider, reference_url
    from app.services.industry_templates import project_snapshot, visual_guidance
    from app.config import settings
    shot = deepcopy(project.storyboard[0])
    reference(db, db.get(Asset, project.reference_asset_id))
    prompt = (f"{shot['generation_prompt']}\n参考图片已识别的事实：{shot['visual_description']}。"
        f'生成5秒真实连续动态视频，{project.aspect_ratio}构图；只展示参考图中的主体与场景，'
        '保持建筑、人物和环境结构稳定，不新增未提供的人物或设施，不做照片轮播，'
        '不生成字幕、品牌、配乐或水印。' + visual_guidance(project_snapshot(db, project)))
    request = VideoGenerationRequest(prompt=prompt, duration_seconds=5,
        aspect_ratio=project.aspect_ratio, style=project.video_style,
        reference_image_url=reference_url(db, project, project.reference_asset_id, shot=shot),
        resolution=settings.VIDEO_RESOLUTION, audio=False)
    _, task = _generate_clip(db, project, provider(), request, shot_number=1)
    if not task.raw_asset_id:
        raise ValueError('视频模型已完成但未保存分镜文件，请检查生成记录')
    project.storyboard = [{**shot, 'output_asset_id':str(task.raw_asset_id), 'generation_status':'completed'}]
    project.output_asset_id = task.raw_asset_id
    project.project_status = 'pending_review'
    project.quality_check_result = {'status':'generated', 'note':'新分镜已生成，请预览后确认加入复用库'}
    db.commit()


def approve(db, asset):
    library = info(asset)
    if (asset.asset_metadata or {}).get('production_mode') != 'raw_model_clip' or not asset.is_available or asset.processing_status != 'ready':
        raise HTTPException(422, '请选择可用的 AI 原始分镜')
    try:
        project_id = uuid.UUID(str(library.get('source_project_id')))
    except ValueError as exc:
        raise HTTPException(422, '分镜来源无效') from exc
    project = db.query(VideoProject).filter_by(id=project_id,
        company_id=asset.company_id, is_deleted=False, creation_mode=MODE).with_for_update().first()
    if not project or project.output_asset_id != asset.id or project.project_status not in ('pending_review','completed'):
        raise HTTPException(409, '请使用来源成片审核入口；此处只确认手动生成的分镜')
    reference(db, asset)
    from app.services.video_clip_library import approve_project_clips
    project.review_status = 'approved'
    project.project_status = 'completed'
    approve_project_clips(db, project)
    db.commit()
    db.refresh(asset)
