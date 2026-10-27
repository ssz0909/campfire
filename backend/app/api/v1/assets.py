from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.asset import AssetResponse, AssetUpdate, DownloadUrlResponse
from app.services.asset_service import AssetService
from app.services.storage_service import StorageService
from app.config import settings
from app.utils.pagination import PaginatedResponse

router = APIRouter()


def get_asset_service(db: Session = Depends(get_db)) -> AssetService:
    storage = StorageService(backend=settings.STORAGE_BACKEND)
    return AssetService(db=db, storage=storage)


@router.post(
    "/{company_id}/assets/upload",
    response_model=AssetResponse,
    status_code=201,
)
async def upload_asset(
    company_id: uuid.UUID,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    current_user: User = Depends(require_permission(Permission.ASSET_UPLOAD)),
    service: AssetService = Depends(get_asset_service),
):
    file_data = await file.read()
    asset = service.upload_asset(
        company_id=company_id,
        uploaded_by=current_user.id,
        file_data=file_data,
        original_filename=file.filename or "upload",
        claimed_content_type=file.content_type or "application/octet-stream",
        name=name,
    )
    # Enqueue background processing
    from app.worker.tasks.asset_tasks import process_asset
    if settings.TASK_EXECUTION_MODE == 'inline':
        from app.worker.tasks.asset_tasks import _extract_metadata
        try:
            _extract_metadata(asset, service.db)
            asset.processing_status = 'ready'
        except Exception:
            service.db.rollback()
            asset.processing_status = 'failed'
            asset.processing_error = '素材解析失败，请检查文件及 FFmpeg 配置'
        service.db.commit()
        service.db.refresh(asset)
        if asset.asset_type=='image' and asset.processing_status=='ready':
            asset.asset_metadata={**(asset.asset_metadata or {}),'vision_analysis':{'status':'pending'}}
            service.db.commit()
            from app.worker.tasks.asset_tasks import vision_worker, analyze_image_content
            vision_worker.submit(analyze_image_content,str(asset.id))
    else:
        process_asset.delay(str(asset.id))
    return asset


@router.get("/{company_id}/assets", response_model=PaginatedResponse[AssetResponse])
def list_assets(
    company_id: uuid.UUID,
    asset_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    q: str | None = Query(None, max_length=100),
    tag: str | None = Query(None, max_length=40),
    _: User = Depends(require_permission(Permission.ASSET_VIEW)),
    service: AssetService = Depends(get_asset_service),
):
    items, total = service.list_assets(company_id, asset_type, page, page_size, category, q, tag)
    return PaginatedResponse.create(items, total, page, page_size)


@router.get("/{company_id}/assets/{asset_id}", response_model=AssetResponse)
def get_asset(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.ASSET_VIEW)),
    service: AssetService = Depends(get_asset_service),
):
    return service.get_asset(company_id, asset_id)


@router.post("/{company_id}/assets/{asset_id}/analyze", response_model=AssetResponse)
def analyze_asset(company_id: uuid.UUID, asset_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.ASSET_UPLOAD)),
    service: AssetService = Depends(get_asset_service)):
    return service.analyze_image(company_id,asset_id)


@router.get(
    "/{company_id}/assets/{asset_id}/download-url",
    response_model=DownloadUrlResponse,
)
def get_download_url(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.ASSET_VIEW)),
    service: AssetService = Depends(get_asset_service),
):
    url = service.get_download_url(company_id, asset_id)
    return DownloadUrlResponse(download_url=url, expires_in_seconds=3600)


@router.put("/{company_id}/assets/{asset_id}", response_model=AssetResponse)
def update_asset(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    data: AssetUpdate,
    _: User = Depends(require_permission(Permission.ASSET_UPLOAD)),
    service: AssetService = Depends(get_asset_service),
):
    return service.update_asset(company_id, asset_id, data)


@router.patch("/{company_id}/assets/{asset_id}", response_model=AssetResponse)
def patch_asset(company_id: uuid.UUID, asset_id: uuid.UUID, data: AssetUpdate,
    _: User = Depends(require_permission(Permission.ASSET_UPLOAD)),
    service: AssetService = Depends(get_asset_service)):
    return service.update_asset(company_id, asset_id, data)


@router.delete("/{company_id}/assets/{asset_id}", status_code=204)
def delete_asset(
    company_id: uuid.UUID,
    asset_id: uuid.UUID,
    _: User = Depends(require_permission(Permission.ASSET_DELETE)),
    service: AssetService = Depends(get_asset_service),
):
    service.delete_asset(company_id, asset_id)
    return None
