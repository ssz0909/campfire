from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.worker.celery_app import celery_app
from app.database import SessionLocal
from app.models.asset import Asset

vision_worker=ThreadPoolExecutor(max_workers=2,thread_name_prefix='asset-vision')


@celery_app.task(bind=True, name="app.worker.tasks.asset_tasks.process_asset")
def process_asset(self, asset_id: str) -> dict:
    """
    Extract metadata from an uploaded asset, generate a thumbnail, and
    update the asset's processing_status in the database.
    """
    db = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.id == uuid.UUID(asset_id)).first()
        if not asset:
            return {"status": "error", "detail": f"Asset {asset_id} not found"}

        asset.processing_status = "processing"
        db.commit()

        try:
            _extract_metadata(asset, db)
            asset.processing_status = "ready"
            db.commit()
            if asset.asset_type=='image' and asset.processing_status=='ready':
                asset.asset_metadata={**(asset.asset_metadata or {}),'vision_analysis':{'status':'pending'}}
                db.commit()
                analyze_image_content.delay(asset_id)
            return {"status": "ready", "asset_id": asset_id}
        except Exception as exc:
            asset.processing_status = "failed"
            asset.processing_error = str(exc)
            db.commit()
            raise self.retry(exc=exc, countdown=30, max_retries=2)
    finally:
        db.close()


def _extract_metadata(asset: Asset, db) -> None:
    """
    Extract image/video metadata and write it back to the asset record.
    Uses Pillow for images; video metadata extraction requires ffprobe (not
    included as a dependency — stub for now).
    """
    from app.config import settings
    from pathlib import Path

    if asset.asset_type == "image":
        _extract_image_metadata(asset, db)
    elif asset.asset_type == "video":
        from app.services.media_processing import enrich_video_asset
        from app.services import get_storage_service
        enrich_video_asset(asset, get_storage_service())
        db.commit()
    elif asset.asset_type == 'audio':
        from app.services.media_processing import inspect_audio
        from app.services import get_storage_service
        metadata = inspect_audio(get_storage_service().get_file(asset.file_key))
        asset.duration_seconds = metadata['duration_seconds']
        asset.codec = metadata['codec']
        db.commit()


def _extract_image_metadata(asset: Asset, db) -> None:
    from PIL import Image
    import io
    from app.services import get_storage_service

    storage = get_storage_service()
    try:
        raw = storage.get_file(asset.file_key)
        img = Image.open(io.BytesIO(raw))
        asset.width = img.width
        asset.height = img.height
        asset.resolution = f"{img.width}x{img.height}"
        # Generate a small thumbnail
        img.thumbnail((320, 320))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        thumb_buf = io.BytesIO()
        img.save(thumb_buf, format="JPEG", quality=75)
        thumb_key = asset.file_key.rsplit(".", 1)[0] + "_thumb.jpg"
        thumb_url = storage.upload_file(thumb_buf.getvalue(), thumb_key, "image/jpeg")
        asset.thumbnail_url = thumb_url
        db.commit()
    except Exception as exc:
        raise RuntimeError(f"Image metadata extraction failed: {exc}") from exc


@celery_app.task(name="app.worker.tasks.asset_tasks.analyze_image_content")
def analyze_image_content(asset_id: str):
    db=SessionLocal()
    try:
        asset=db.query(Asset).filter(Asset.id==uuid.UUID(asset_id),Asset.asset_type=='image',Asset.is_deleted==False).with_for_update().first()
        if not asset:return {'status':'missing'}
        analysis_state=((asset.asset_metadata or {}).get('vision_analysis') or {}).get('status')
        previous=(asset.asset_metadata or {}).get('vision_analysis') or {}
        started=previous.get('started_at')
        if analysis_state=='running' and started:
            try:
                if (datetime.now(timezone.utc)-datetime.fromisoformat(started)).total_seconds()<180:
                    return {'status':'already_running','asset_id':asset_id}
            except ValueError:pass
        asset.asset_metadata={**(asset.asset_metadata or {}),'vision_analysis':{'status':'running','started_at':datetime.now(timezone.utc).isoformat()}}
        db.commit()
        from app.services import get_storage_service
        from app.services.asset_vision import analyze_image
        try:
            analysis=analyze_image(get_storage_service().get_file(asset.file_key),asset.mime_type)
            db.refresh(asset)
            if asset.is_deleted:return {'status':'missing'}
            asset.asset_metadata={**(asset.asset_metadata or {}),'vision_analysis':analysis}
            if analysis.get('status')=='completed' and not (asset.asset_metadata or {}).get('manual_classification'):
                asset.category=analysis['category'];asset.tags=analysis['tags']
                asset.source_description=asset.source_description or analysis.get('caption')
        except Exception:
            asset.asset_metadata={**(asset.asset_metadata or {}),'vision_analysis':{
                'status':'failed','error':'图片识别失败，请检查模型是否支持视觉输入后重试'}}
            db.commit()
            return {'status':'failed','asset_id':asset_id}
        db.commit()
        return {'status':analysis.get('status'),'asset_id':asset_id}
    finally:db.close()


