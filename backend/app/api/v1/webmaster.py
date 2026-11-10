"""Platform-admin webmaster setup; tenant reports use their existing metrics ACL."""
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.v1.admin import require_platform_admin
from app.models.user import User
from app.models.audit_log import AuditLog
from app.services import webmaster as service

router=APIRouter(prefix='/admin/webmaster',tags=['webmaster'])
Provider=Literal['google','bing','baidu']

class Config(BaseModel):
    verification_token:str=Field('',max_length=1000)
    property:str=Field(service.ORIGIN+'/',max_length=150)
    service_account_json:str=Field('',max_length=20000)
    clear_credentials:bool=False
    auto_sync:bool=False


def audit(db,user,action,provider,details=None):
    db.add(AuditLog(user_id=user.id,action=action,resource_type='webmaster',resource_id=provider,details=details or {}))

@router.get('')
def read(_:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    return service.settings_view(db)

@router.put('/{provider}')
def save(provider:Provider,data:Config,user:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    try:service.save_config(db,provider,data.model_dump())
    except service.WebmasterError as exc:raise HTTPException(422,str(exc)) from None
    audit(db,user,'webmaster.config',provider);db.commit()
    return service.settings_view(db)

@router.post('/google/sync',status_code=202)
def sync(user:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    try:result=service.enqueue(db)
    except service.WebmasterError as exc:raise HTTPException(422,str(exc)) from None
    audit(db,user,'webmaster.sync_requested','google');db.commit()
    return result

@router.get('/report-template.csv')
def report_template(_:User=Depends(require_platform_admin)):
    return Response('\ufeffday,page,clicks,impressions,position\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="webmaster-report-template.csv"'})

@router.post('/{provider}/import')
async def import_report(provider:Provider,file:UploadFile=File(...),source_name:str=Form(...,min_length=2,max_length=140),
    confirmed:bool=Form(False),user:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    if not confirmed:raise HTTPException(422,'请确认这是对应渠道导出的真实搜索表现报表')
    if len(source_name.strip())<2:raise HTTPException(422,'请填写至少2字的报表来源说明')
    data=await file.read(2*1024*1024+1)
    if len(data)>2*1024*1024:raise HTTPException(413,'报表不得超过2MB')
    try:
        rows=service.parse_csv(data)
        result=service.store_rows(db,provider,rows,'manual_report',source_name.strip())
    except service.WebmasterError as exc:raise HTTPException(422,str(exc)) from None
    audit(db,user,'webmaster.report_import',provider,{**result,'source_name':source_name.strip()});db.commit()
    return result
