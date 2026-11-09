"""Tenant-scoped uploaded soundtracks, independent of video model billing."""
import uuid
import random
from fastapi import HTTPException
from app.models.asset import Asset


def music_asset(db, company_id, asset_id):
    if not asset_id:
        return None
    asset = db.query(Asset).filter_by(id=uuid.UUID(str(asset_id)),company_id=company_id,
        asset_type='audio',is_deleted=False,is_available=True,processing_status='ready').first()
    if not asset:
        raise HTTPException(422,'请选择本企业已处理完成且可用的音频素材')
    return asset


def resolve_music_settings(db, company_id, overrides=None):
    from app.models.company import Company
    from app.schemas.video_project import MusicSettings
    overrides=overrides or {}
    company=db.query(Company).filter_by(id=company_id,is_deleted=False).first()
    defaults=((company.business_goals or {}).get('default_video_music') or {}) if company else {}
    if 'video_music' in overrides:
        choice = task_music_config(db, company_id, overrides['video_music'])
        if choice['selection_mode'] == 'workspace':
            overrides = {}
        else:
            defaults = choice
            overrides = {}
            if choice['selection_mode'] == 'model':
                defaults = {}
    explicit = 'music_asset_id' in overrides or 'music_disabled' in overrides
    selected = overrides if explicit else defaults
    if selected.get('selection_mode') == 'none' or selected.get('music_disabled') is True:
        return MusicSettings(music_disabled=True).model_dump()
    if not explicit and defaults.get('selection_mode') == 'random':
        candidates=db.query(Asset.id).filter_by(company_id=company_id,asset_type='audio',is_deleted=False,
            is_available=True,processing_status='ready').order_by(Asset.id).all()
        if not candidates:
            raise HTTPException(422,'已启用随机配乐，但素材库暂无可用音频，请上传音乐或关闭随机配乐')
        selected={**defaults,'music_asset_id':random.choice(candidates)[0]}
    data=MusicSettings.model_validate(selected)
    music_asset(db,company_id,data.music_asset_id)
    return data.model_dump()


def task_music_config(db, company_id, value):
    from pydantic import ValidationError
    from app.schemas.video_project import TaskMusicSettings
    try:
        data = TaskMusicSettings.model_validate(value)
    except ValidationError as exc:
        raise HTTPException(422, '任务配乐配置无效：请选择配乐方式；固定配乐需选择音频，音量需在0至1之间') from exc
    data.music_disabled = data.selection_mode == 'none'
    if data.selection_mode == 'fixed':
        music_asset(db, company_id, data.music_asset_id)
    else:
        data.music_asset_id = None
    return data.model_dump(mode='json')


def set_default_music(db, company_id, data):
    from app.models.company import Company
    mode = getattr(data, 'selection_mode', 'fixed')
    if mode == 'none':
        data = data.model_copy(update={'music_asset_id': None, 'music_disabled': True})
    elif mode in ('fixed', 'random'):
        data = data.model_copy(update={'music_disabled': False})
    if mode == 'fixed':
        music_asset(db,company_id,data.music_asset_id)
    company=db.query(Company).filter_by(id=company_id,is_deleted=False).with_for_update().first()
    if not company:
        raise HTTPException(404,'Company not found')
    company.business_goals={**(company.business_goals or {}),'default_video_music':data.model_dump(mode='json')}
    db.commit();db.refresh(company)
    return company


def apply_music(db, project, content, storage):
    if getattr(project, 'music_disabled', False):
        from app.services.media_processing import remove_video_audio
        return remove_video_audio(content)
    asset = music_asset(db,project.company_id,project.music_asset_id)
    if asset is None:
        return content
    from app.services.media_processing import replace_background_music
    return replace_background_music(content,storage.get_file(asset.file_key),project.music_volume)


def model_audio_enabled(project):
    from app.config import settings
    return False if getattr(project, 'music_disabled', False) or project.music_asset_id else settings.VIDEO_AUDIO
