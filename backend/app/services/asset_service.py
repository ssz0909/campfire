from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.cost import CostRecord
from app.schemas.asset import AssetUpdate
from app.services.storage_service import StorageService
from app.utils.file_utils import classify_asset_type, generate_storage_key, validate_file_type
from app.config import settings


class AssetService:
    def __init__(self, db: Session, storage: StorageService) -> None:
        self.db = db
        self.storage = storage

    def upload_asset(
        self,
        company_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        file_data: bytes,
        original_filename: str,
        claimed_content_type: str,
        name: str | None = None,
    ) -> Asset:
        # Validate size
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(file_data) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB",
            )

        # Validate type using magic bytes
        allowed_types = settings.get_all_allowed_types()
        is_valid, actual_mime = validate_file_type(file_data, claimed_content_type, allowed_types)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File type '{actual_mime}' is not allowed",
            )

        asset_type = classify_asset_type(actual_mime)
        key = generate_storage_key(company_id, asset_type, original_filename)

        # Upload to storage
        file_url = self.storage.upload_file(file_data, key, actual_mime)

        asset = Asset(
            company_id=company_id,
            uploaded_by=uploaded_by,
            name=name or original_filename,
            original_filename=original_filename,
            file_key=key,
            file_url=file_url,
            asset_type=asset_type,
            mime_type=actual_mime,
            file_size_bytes=len(file_data),
            processing_status="pending",
        )
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def get_asset(self, company_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
        asset = (
            self.db.query(Asset)
            .filter(
                Asset.id == asset_id,
                Asset.company_id == company_id,
                Asset.is_deleted == False,
            )
            .first()
        )
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        return asset

    def list_assets(
        self,
        company_id: uuid.UUID,
        asset_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        query_text: str | None = None,
        tag: str | None = None,
    ) -> tuple[list[Asset], int]:
        query = self.db.query(Asset).filter(
            Asset.company_id == company_id,
            Asset.is_deleted == False,
        )
        if asset_type:
            query = query.filter(Asset.asset_type == asset_type)
        if category:
            query = query.filter(Asset.category == category)
        items = query.order_by(Asset.created_at.desc()).all()
        if tag:
            items=[a for a in items if tag in (a.tags or [])]
        if query_text:
            needle=query_text.strip().casefold()
            items=[a for a in items if needle in ' '.join([a.name,a.category or '',a.source_description or '',
                *[str(t) for t in (a.tags or [])],str((a.asset_metadata or {}).get('vision_analysis',{}).get('visual_description',''))]).casefold()]
        total=len(items)
        items=items[(page-1)*page_size:page*page_size]
        return items, total

    def analyze_image(self, company_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
        asset=self.get_asset(company_id,asset_id)
        if asset.asset_type!='image':raise HTTPException(422,'目前仅支持识别图片素材')
        if not asset.is_available:raise HTTPException(409,'素材当前不可用')
        from app.worker.tasks.asset_tasks import analyze_image_content
        result=analyze_image_content(str(asset.id))
        self.db.refresh(asset)
        if result.get('status')!='completed':raise HTTPException(503,result.get('detail') or '图片识别未完成，请检查视觉模型是否支持图片输入后重试')
        return asset

    def update_asset(
        self, company_id: uuid.UUID, asset_id: uuid.UUID, data: AssetUpdate
    ) -> Asset:
        asset = self.get_asset(company_id, asset_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(asset, field, value)
        if any(field in data.model_fields_set for field in ('category','tags','source_description')):
            asset.asset_metadata={**(asset.asset_metadata or {}),'manual_classification':True}
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def delete_asset(self, company_id: uuid.UUID, asset_id: uuid.UUID) -> None:
        asset = self.get_asset(company_id, asset_id)
        asset.is_deleted = True
        asset.deleted_at = datetime.now(timezone.utc)
        asset.is_available = False
        self.db.commit()

    def get_download_url(self, company_id: uuid.UUID, asset_id: uuid.UUID) -> str:
        asset = self.get_asset(company_id, asset_id)
        return self.storage.generate_presigned_url(asset.file_key)
