import uuid
from typing import Literal
from datetime import date
import re
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.permissions import require_permission, Permission
from app.api.v1.admin import require_platform_admin
from app.models.user import User
from app.models.geo import GeoSite, GeoTemplate, GeoVersion, GeoSlug
from app.models.company import Company
from app.services import geo as service

router=APIRouter()

class Fact(BaseModel):
    key: str = Field(min_length=1,max_length=100)
    value: str = Field(min_length=1,max_length=1000)
    source: str = Field(min_length=1,max_length=500)
    status: Literal['pending','confirmed'] = 'pending'
    valid_until: date | None = None

class Content(BaseModel):
    name: str = Field('',max_length=120)
    description: str = Field('',max_length=6000)
    industry: str = Field('',max_length=80)
    region: str = Field('',max_length=120)
    address: str = Field('',max_length=300)
    contact: str = Field('',max_length=300)
    services: str = Field('',max_length=6000)
    faq: str = Field('',max_length=6000)
    template: str = Field('generic',max_length=64)
    cover_asset_id: str = Field("",max_length=36)
    brand_color: str = Field('#c05929',pattern=r'^#[0-9a-fA-F]{6}$')
    module_order: list[Literal['description','services','faq']] = Field(default_factory=lambda:['description','services','faq'],min_length=3,max_length=3)
    show_services: bool = True
    show_faq: bool = True
    facts: list[Fact] = Field(default_factory=list,max_length=30)
    confirmed: bool = False

class Draft(BaseModel):
    expected_revision: int
    content: Content

class Publish(BaseModel):
    expected_revision: int
    slug: str = Field(min_length=3,max_length=64)

class Change(BaseModel):
    reason: str = Field(min_length=4,max_length=500)
    slug: str | None = None
    status: str | None = None

class TemplateData(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    expected_revision: int = 0
    intro: str = Field('企业介绍',max_length=60)
    services: str = Field('产品与服务',max_length=60)
    faq: str = Field('常见问题',max_length=60)
    accent: str = Field('#c05929',pattern=r'^#[0-9a-fA-F]{6}$')

@router.get('/companies/{company_id}/geo')
def read(company_id:uuid.UUID,_:User=Depends(require_permission(Permission.COMPANY_VIEW)),db:Session=Depends(get_db)):
    company=db.get(Company,company_id)
    if not company:raise HTTPException(404,'企业不存在')
    result=service.describe(service.site_for(db,company_id))
    result['suggestion']={'name':company.name,'description':company.description or '', 'industry':company.industry or ''}
    result['suggested_slug']=company.slug if service.slug_valid(company.slug) else ''
    result['templates']=[{'code':t.code,'name':t.name,'revision':t.revision} for t in db.query(GeoTemplate).all()] or [{'code':k,'name':'通用企业' if k=='generic' else '酒旅','revision':1} for k in service.DEFAULTS]
    return result

@router.put('/companies/{company_id}/geo/draft')
def draft(company_id:uuid.UUID,data:Draft,user:User=Depends(require_permission(Permission.COMPANY_EDIT)),db:Session=Depends(get_db)):
    site=service.site_for(db,company_id,True)
    if site.revision!=data.expected_revision:raise HTTPException(409,'内容已变化，请重新加载')
    if data.content.cover_asset_id:
        from app.models.asset import Asset
        try: asset=db.get(Asset,uuid.UUID(data.content.cover_asset_id))
        except ValueError: raise HTTPException(422,'封面素材ID无效')
        if not asset or asset.company_id!=company_id or asset.is_deleted or asset.asset_type!='image' or asset.mime_type not in ('image/jpeg','image/png','image/webp'):
            raise HTTPException(422,'请从本企业选择有效的JPG、PNG或WebP图片')
    service.template_snapshot(db,data.content.template)
    if len(set(data.content.module_order))!=3:raise HTTPException(422,'每个模块只能出现一次')
    site.draft=data.content.model_dump(mode='json')
    site.revision+=1
    service.audit(db,user,site,'save_draft')
    service.commit(db)
    return service.describe(site)

@router.post('/companies/{company_id}/geo/publish')
def publish(company_id:uuid.UUID,data:Publish,tasks:BackgroundTasks,user:User=Depends(require_permission(Permission.COMPANY_EDIT)),db:Session=Depends(get_db)):
    site=service.site_for(db,company_id)
    if not site:raise HTTPException(422,'请先保存草稿')
    result=service.publish(db,site,user,data.expected_revision,data.slug)
    tasks.add_task(service.index_site,site.id,site.revision)
    return result

@router.post('/companies/{company_id}/geo/withdraw')
def withdraw(company_id:uuid.UUID,user:User=Depends(require_permission(Permission.COMPANY_EDIT)),db:Session=Depends(get_db)):
    site=service.site_for(db,company_id)
    if not site:raise HTTPException(404,'主页不存在')
    if site.status=='blocked':raise HTTPException(403,'请联系管理员处理下架')
    site.status='withdrawn';site.vector=None;site.revision+=1
    service.audit(db,user,site,'withdraw');service.commit(db)
    return service.describe(site)

@router.get('/companies/{company_id}/geo/versions')
def versions(company_id:uuid.UUID,page:int=Query(1,ge=1),_:User=Depends(require_permission(Permission.COMPANY_VIEW)),db:Session=Depends(get_db)):
    site=service.site_for(db,company_id)
    if not site:return {'items':[],'total':0}
    q=db.query(GeoVersion).filter_by(site_id=site.id)
    return {'items':[{'revision':v.revision,'created_at':v.created_at,'content':v.content} for v in q.order_by(GeoVersion.revision.desc()).offset((page-1)*10).limit(10)],'total':q.count()}

@router.get('/companies/{company_id}/geo/metrics')
def metrics(company_id:uuid.UUID,days:int=Query(30,ge=1,le=90),_:User=Depends(require_permission(Permission.ANALYTICS_VIEW)),db:Session=Depends(get_db)):
    site=service.site_for(db,company_id)
    return {'site':service.describe(site),'metrics':service.metrics(db,site,days) if site else None}

@router.get('/public/search')
def search(request:Request,q:str=Query('',max_length=120),region:str=Query('',max_length=120),industry:str=Query('',max_length=80),page:int=Query(1,ge=1,le=10000),db:Session=Depends(get_db)):
    service.public_limit(request,40)
    return service.search(db,q,region,industry,page)

class Event(BaseModel):
    event_id: uuid.UUID
    token: str = Field('',max_length=150)
    site_id: uuid.UUID | None = None
    kind: str = Field(pattern='^(view|contact|search_impression|search_click)$')
    visitor: str = Field('',max_length=64)
    referrer: str = Field('',max_length=500)
    self_test: bool = False

@router.post('/public/geo/events',status_code=202)
def event(data:Event,request:Request,db:Session=Depends(get_db)):
    if data.site_id:
        site=db.get(GeoSite,data.site_id)
        company=db.get(Company,site.company_id) if site else None
        if not site or site.status!='published' or not company or company.is_deleted or not company.is_active:raise HTTPException(404,'主页未公开')
    elif data.kind!='view':raise HTTPException(422,'缺少公开站点')
    if not service.verify_event_token(data.site_id,data.token):raise HTTPException(403,'统计凭据无效，请刷新页面')
    service.public_limit(request,120)
    origin=request.headers.get('origin','')
    if origin and origin not in ('https://campfire.dawoai.com','http://127.0.0.1:8000','http://localhost:5173','http://127.0.0.1:5173'):
        raise HTTPException(403,'统计请求来源无效')
    ua=request.headers.get('user-agent','').lower()
    bot=any(x in ua for x in ('bot','crawler','spider','headless','curl','python','monitor'))
    service.event(db,data.site_id,str(data.event_id),data.kind,data.referrer,data.visitor,'bot' if bot else ('self_test' if data.self_test else 'unknown'))
    return {'accepted':True}

@router.get('/admin/geo')
def admin(q:str=Query('',max_length=120),page:int=Query(1,ge=1),days:int=Query(30,ge=1,le=90),_:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    query=db.query(GeoSite,Company).join(Company,Company.id==GeoSite.company_id)
    if q:query=query.filter(Company.name.contains(q,autoescape=True))
    items=[]
    for site,company in query.order_by(GeoSite.updated_at.desc()).offset((page-1)*20).limit(20):
        items.append({'company_id':str(company.id),'company_name':company.name,'site':service.describe(site),'metrics':service.metrics(db,site,days)})
    return {'items':items,'total':query.count(),'page':page,'metrics':service.metrics(db,days=days),
            'homepage_metrics':service.metrics(db,days=days,homepage=True),
            'published':db.query(GeoSite).filter_by(status='published').count(),
            'templates':[{'code':t.code,'name':t.name,'revision':t.revision,'config':t.config} for t in db.query(GeoTemplate).all()]}

@router.post('/admin/geo/{site_id}/change')
def change(site_id:uuid.UUID,data:Change,user:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    site=db.query(GeoSite).filter_by(id=site_id).with_for_update().first()
    if not site:raise HTTPException(404,'站点不存在')
    old=site.slug
    if data.slug and data.slug!=site.slug:
        if not site.slug:raise HTTPException(422,'未发布站点不能提前占用标识')
        if not service.slug_valid(data.slug) or db.get(GeoSlug,data.slug):raise HTTPException(409,'标识不可用或已被保留')
        db.add(GeoSlug(slug=data.slug,site_id=site.id));site.slug=data.slug
    if data.status:
        if data.status not in ('blocked','withdrawn'):raise HTTPException(422,'仅支持下架或解除下架为撤回状态')
        site.status=data.status;site.vector=None
    site.revision+=1
    service.audit(db,user,site,'admin_change',{'reason':data.reason,'old_slug':old,'new_slug':site.slug,'status':site.status})
    service.commit(db)
    return service.describe(site)

@router.put('/admin/geo-templates/{code}')
def template(code:str,data:TemplateData,user:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,63}',code):raise HTTPException(422,'模板标识无效')
    row=db.query(GeoTemplate).filter_by(code=code).with_for_update().first()
    if row and row.revision!=data.expected_revision:raise HTTPException(409,'模板已更新，请刷新')
    if not row:
        if data.expected_revision:raise HTTPException(409,'模板不存在')
        row=GeoTemplate(code=code,revision=0);db.add(row)
    row.revision+=1;row.name=data.name;row.config=data.model_dump(exclude={'name','expected_revision'})
    from app.models.audit_log import AuditLog
    db.add(AuditLog(user_id=user.id,action='geo.template_publish',resource_type='geo_template',resource_id=code,details={'revision':row.revision,'config':row.config}))
    service.commit(db)
    return {'revision':row.revision}

@router.get('/companies/{company_id}/geo/preview')
def preview(company_id:uuid.UUID,_:User=Depends(require_permission(Permission.COMPANY_VIEW)),db:Session=Depends(get_db)):
    from app.api.geo_public import render_site
    site=service.site_for(db,company_id)
    if not site:raise HTTPException(404,'请先保存草稿')
    d=dict(site.draft);d['template_snapshot']=service.template_snapshot(db,d.get('template','generic'))
    return render_site(site,d,preview=True)

class Feedback(BaseModel):
    site_id: uuid.UUID
    message: str = Field(min_length=10,max_length=2000)

@router.post('/public/geo/feedback',status_code=202)
def feedback(data:Feedback,request:Request,db:Session=Depends(get_db)):
    from app.models.geo import GeoFeedback
    service.public_limit(request,5)
    site=db.get(GeoSite,data.site_id)
    company=db.get(Company,site.company_id) if site else None
    if not site or site.status!='published' or not company or company.is_deleted or not company.is_active:
        raise HTTPException(404,'主页未公开')
    db.add(GeoFeedback(site_id=site.id,message=data.message));db.commit()
    return {'accepted':True}

@router.get('/admin/geo-feedback')
def feedback_list(page:int=Query(1,ge=1),_:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    from app.models.geo import GeoFeedback
    q=db.query(GeoFeedback).order_by(GeoFeedback.created_at.desc())
    return {'total':q.count(),'items':[{'id':str(r.id),'site_id':str(r.site_id),'message':r.message,
            'status':r.status,'resolution':r.resolution,'created_at':r.created_at} for r in q.offset((page-1)*20).limit(20)]}

class Resolution(BaseModel):
    resolution: str = Field(min_length=4,max_length=2000)

@router.post('/admin/geo-feedback/{feedback_id}/resolve')
def resolve_feedback(feedback_id:uuid.UUID,data:Resolution,user:User=Depends(require_platform_admin),db:Session=Depends(get_db)):
    from app.models.geo import GeoFeedback
    item=db.get(GeoFeedback,feedback_id)
    if not item:raise HTTPException(404,'反馈不存在')
    item.status='resolved';item.resolution=data.resolution
    service.audit(db,user,db.get(GeoSite,item.site_id),'resolve_feedback',{'feedback_id':str(item.id),'resolution':data.resolution})
    service.commit(db)
    return {'status':item.status}

@router.post('/companies/{company_id}/geo/check')
def check(company_id:uuid.UUID,user:User=Depends(require_permission(Permission.COMPANY_EDIT)),db:Session=Depends(get_db)):
    site=service.site_for(db,company_id)
    if not site or site.status!='published':raise HTTPException(422,'请先发布主页')
    site.check_result=service.check_content(site,site.live)
    service.audit(db,user,site,'check')
    service.commit(db)
    return site.check_result


@router.get('/companies/{company_id}/geo/slug-availability')
def slug_availability(company_id:uuid.UUID,slug:str=Query(max_length=64),_:User=Depends(require_permission(Permission.COMPANY_VIEW)),db:Session=Depends(get_db)):
    site=service.site_for(db,company_id)
    registry=db.get(GeoSlug,slug)
    return {'slug':slug,'valid':service.slug_valid(slug),'available':service.slug_valid(slug) and (not registry or (site is not None and registry.site_id==site.id)),
            'locked':bool(site and site.slug)}
