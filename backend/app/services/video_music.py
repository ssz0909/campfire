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
    selected = overrides if 'music_asset_id' in overrides else defaults
    if 'music_asset_id' not in overrides and defaults.get('selection_mode') == 'random':
        candidates=db.query(Asset.id).filter_by(company_id=company_id,asset_type='audio',is_deleted=False,
            is_available=True,processing_status='ready').order_by(Asset.id).all()
        if not candidates:
            raise HTTPException(422,'已启用随机配乐，但素材库暂无可用音频，请上传音乐或关闭随机配乐')
        selected={**defaults,'music_asset_id':random.choice(candidates)[0]}
    data=MusicSettings.model_validate(selected)
    music_asset(db,company_id,data.music_asset_id)
    return data.model_dump()


def set_default_music(db, company_id, data):
    from app.models.company import Company
    if getattr(data,'selection_mode','fixed') != 'random':
        music_asset(db,company_id,data.music_asset_id)
    company=db.query(Company).filter_by(id=company_id,is_deleted=False).with_for_update().first()
    if not company:
        raise HTTPException(404,'Company not found')
    company.business_goals={**(company.business_goals or {}),'default_video_music':data.model_dump(mode='json')}
    db.commit();db.refresh(company)
    return company


def apply_music(db, project, content, storage):
    asset = music_asset(db,project.company_id,project.music_asset_id)
    if asset is None:
        return content
    from app.services.media_processing import replace_background_music
    return replace_background_music(content,storage.get_file(asset.file_key),project.music_volume)
