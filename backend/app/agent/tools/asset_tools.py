from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.asset import Asset


async def list_company_assets(
    company_id: uuid.UUID,
    db: Session,
    asset_type: str | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    List available assets for a company, optionally filtered by type or tags.
    Used by agent workflows to find media for content generation.
    """
    query = db.query(Asset).filter(
        Asset.company_id == company_id,
        Asset.is_deleted == False,
        Asset.is_available == True,
        Asset.processing_status == "ready",
    )
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    assets = query.limit(limit).all()

    return {
        "assets": [
            {
                "id": str(a.id),
                "name": a.name,
                "asset_type": a.asset_type,
                "mime_type": a.mime_type,
                "file_url": a.file_url,
                "thumbnail_url": a.thumbnail_url,
                "tags": a.tags or [],
                "category": a.category,
                "width": a.width,
                "height": a.height,
                "duration_seconds": float(a.duration_seconds) if a.duration_seconds else None,
            }
            for a in assets
        ],
        "total": len(assets),
    }


async def get_asset_detail(
    asset_id: uuid.UUID,
    company_id: uuid.UUID,
    db: Session,
) -> dict[str, Any]:
    """Retrieve full detail for a single asset."""
    asset = (
        db.query(Asset)
        .filter(
            Asset.id == asset_id,
            Asset.company_id == company_id,
            Asset.is_deleted == False,
        )
        .first()
    )
    if not asset:
        return {"error": f"Asset {asset_id} not found"}

    return {
        "id": str(asset.id),
        "name": asset.name,
        "asset_type": asset.asset_type,
        "mime_type": asset.mime_type,
        "file_key": asset.file_key,
        "file_url": asset.file_url,
        "thumbnail_url": asset.thumbnail_url,
        "tags": asset.tags or [],
        "category": asset.category,
        "copyright_info": asset.copyright_info,
        "width": asset.width,
        "height": asset.height,
        "duration_seconds": float(asset.duration_seconds) if asset.duration_seconds else None,
        "metadata": asset.asset_metadata or {},
    }
