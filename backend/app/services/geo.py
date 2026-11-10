"""Bounded public search, publishing and first-party analytics."""
import hashlib
import json
import math
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.models.geo import GeoSite, GeoSlug, GeoVersion, GeoTemplate, GeoEvent, GeoDaily, GeoVisitor
from app.models.company import Company
from app.models.audit_log import AuditLog

DEFAULTS = {
 'generic': {'layout':'classic','intro':'企业介绍','services':'产品与服务','faq':'常见问题','accent':'#c05929'},
}

from app.services.geo_site_design import TEMPLATES
for _code,_template in TEMPLATES.items():
    DEFAULTS[_code]={**DEFAULTS['generic'],**{k:v for k,v in _template.items() if k!='name'}}

def site_for(db, company_id, create=False):
    site = db.query(GeoSite).filter_by(company_id=company_id).with_for_update().first()
    if not site and create:
        company = db.get(Company, company_id)
        if not company or company.is_deleted: raise HTTPException(404, '企业不存在')
        site = GeoSite(company_id=company_id, draft={}, live={})
        db.add(site)
        db.flush()
    return site

def audit(db, user, site, action, details=None):
    db.add(AuditLog(company_id=site.company_id, user_id=user.id, action='geo.'+action,
                    resource_type='geo_site', resource_id=str(site.id), details=details or {}))

def slug_valid(slug):
    return bool(re.fullmatch(r'[a-z0-9][a-z0-9-]{1,62}[a-z0-9]', slug)) and slug not in {
        'admin','api','search','login','register','campfire','assets','dashboard','shop','www','support','official'}

def validate(content):
    issues=[]
    for key, label in [('name','公开名称'),('description','企业介绍'),('contact','公开联系信息')]:
        if not content.get(key,'').strip(): issues.append(label+'不能为空')
    images=[content.get('cover_asset_id'),*content.get('gallery_asset_ids',[])]
    if not content.get('cover_asset_id'):issues.append('请选择一张公开封面')
    if not 2<=len(content.get('gallery_asset_ids',[]))<=3:issues.append('请选择2至3张补充展示图片')
    if len(set(images))!=len(images):issues.append('封面和补充图片请使用不同的素材')
    if not content.get('confirmed'): issues.append('请确认公开资料真实且已获得公开授权')
    for fact in content.get('facts',[]):
        if fact.get('status')!='confirmed':issues.append('事实“'+fact.get('key','')+'”尚未确认')
        if fact.get('valid_until') and fact['valid_until'] < datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat():issues.append('事实“'+fact.get('key','')+'”已过期')
    return issues

def template_snapshot(db, code):
    # Historical industry choice becomes a general visual style on next edit/publish.
    if code=='travel':code='scenic'
    t=db.get(GeoTemplate,code)
    if not t and code not in DEFAULTS: raise HTTPException(422,'模板不存在')
    return {'renderer_version':1,'code':code,'revision':t.revision if t else 1,'name':t.name if t else TEMPLATES.get(code,{}).get('name',code),
            'config':{**DEFAULTS.get(code,{}),**(t.config or {})} if t else DEFAULTS[code]}

def describe(site):
    if not site: return {'status':'draft','revision':0,'draft':{},'live':{},'slug':None}
    draft=dict(site.draft or {})
    if draft.get('template')=='travel':draft['template']='scenic'
    return {'id':str(site.id),'status':site.status,'revision':site.revision,'draft':draft,
            'live':site.live,'slug':site.slug,'published_at':site.published_at,'index_status':site.index_status,
            'check_result':site.check_result,'url':'/shop/'+site.slug if site.slug else None,'issues':validate(site.draft or {})}

def commit(db):
    try: db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409,'网址已被占用或内容发生冲突，请刷新后重试') from exc

def publish(db,site,user,expected,slug):
    if site.revision!=expected: raise HTTPException(409,'公开版本已变化，请重新加载')
    if site.status=='blocked': raise HTTPException(403,'平台已下架，请联系管理员')
    if site.slug and site.slug!=slug: raise HTTPException(409,'首次发布后网址已锁定，仅管理员可特殊更名')
    if not slug_valid(slug): raise HTTPException(422,'网址使用3—64位小写字母、数字和中划线，不得使用系统保留词')
    issues=validate(site.draft or {})
    if issues: raise HTTPException(422,'；'.join(issues))
    if not site.slug:
        registry=db.get(GeoSlug,slug)
        if registry: raise HTTPException(409,'网址已被占用')
        site.slug=slug
        db.add(GeoSlug(slug=slug,site_id=site.id))
    from app.api.v1.geo import checked_cover
    for asset_id in [site.draft.get('cover_asset_id'), *site.draft.get('gallery_asset_ids',[])]:
        checked_cover(db,site.company_id,asset_id)
    content=dict(site.draft)
    content['template_snapshot']=template_snapshot(db,content.get('template','generic'))
    site.revision+=1
    site.live=content
    site.status='published'
    site.published_at=datetime.now(timezone.utc)
    site.vector=None
    site.vector_model=None
    site.index_status='keyword_only'
    site.check_result=check_content(site,content)
    db.add(GeoVersion(site_id=site.id,revision=site.revision,content=content))
    audit(db,user,site,'publish',{'revision':site.revision})
    commit(db)
    return describe(site)

def document(site):
    d=site.live
    return ' '.join(str(d.get(k,'')) for k in ('name','description','region','industry','services','faq') if k not in ('services','faq') or d.get('show_'+k,True))[:18000]

_embedding_cache={}
_public_buckets={}
_retention_day=''

def public_limit(request,limit=40):
    import time
    now=int(time.monotonic()//60)
    host=request.client.host if request.client else 'unknown'
    key=(host,request.url.path,now)
    if len(_public_buckets)>10000:
        for k in list(_public_buckets):
            if k[2]!=now:_public_buckets.pop(k,None)
    count=_public_buckets.get(key,0)+1
    _public_buckets[key]=count
    if count>limit:raise HTTPException(429,'操作频繁，请稍后重试')

def embeddings(texts):
    from app.config import settings
    import httpx
    base=getattr(settings,'EMBEDDING_BASE_URL','').rstrip('/')
    key=getattr(settings,'EMBEDDING_API_KEY','')
    model=getattr(settings,'EMBEDDING_MODEL','')
    if not (base and key and model): return None
    import time
    cache_key=(base,model,hashlib.sha256(json.dumps(texts).encode()).hexdigest())
    cached=_embedding_cache.get(cache_key)
    if cached and cached[0]>time.monotonic():return cached[1]
    with httpx.Client(timeout=5) as client:
        response=client.post(base+'/embeddings',headers={'Authorization':'Bearer '+key},json={'model':model,'input':texts})
        response.raise_for_status()
        rows=sorted(response.json()['data'],key=lambda x:x['index'])
        result=[x['embedding'] for x in rows]
        if len(result)!=len(texts) or any(not v or len(v)>8192 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in v) for v in result):
            raise ValueError('Invalid embeddings')
        if len(_embedding_cache)>=128:_embedding_cache.pop(next(iter(_embedding_cache)))
        _embedding_cache[cache_key]=(time.monotonic()+300,result)
        return result

def index_site(site_id,revision):
    from app.database import SessionLocal
    with SessionLocal() as db:
        site=db.get(GeoSite,site_id)
        if not site or site.status!='published' or site.revision!=revision:return
        text=document(site)
    try:
        result=embeddings([text])
        from app.config import settings
        with SessionLocal() as db:
            site=db.get(GeoSite,site_id)
            if site and site.status=='published' and site.revision==revision:
                site.vector=result[0] if result else None
                site.vector_model=settings.EMBEDDING_MODEL if result else None
                site.index_status='semantic_ready' if result else 'keyword_only'
                db.commit()
    except Exception:
        with SessionLocal() as db:
            site=db.get(GeoSite,site_id)
            if site and site.revision==revision:
                site.index_status='semantic_error';db.commit()

def search(db,q,region='',industry='',page=1,size=12):
    # Hard cap protects the small production host; PostgreSQL indexed/vector search
    # can replace this adapter when tenant volume outgrows the first deployment.
    rows=db.query(GeoSite).join(Company,Company.id==GeoSite.company_id).filter(
        GeoSite.status=='published',Company.is_active==True,Company.is_deleted==False).order_by(GeoSite.published_at.desc()).limit(2001).all()
    if len(rows)>2000: raise HTTPException(503,'搜索索引容量待扩展，请联系平台管理员')
    query=re.sub(r'[^\w\u4e00-\u9fff-]','',q.lower())
    meaningful=re.sub(r'有哪些|推荐|搜索|适合|哪里|有没有|请问|帮我|想找|找一下|服务','',query)
    grams=set(meaningful[i:i+2] for i in range(max(0,len(meaningful)-1)))
    from app.config import settings
    vector=None
    if q and settings.GEO_SEMANTIC_SEARCH_ENABLED:
        try:
            result=embeddings([q]);vector=result[0] if result else None
        except Exception: pass
    from app.config import settings
    matches=[]
    for site in rows:
        d=site.live;text=document(site).lower();name=d.get('name','').lower()
        if region and region.lower() not in d.get('region','').lower():continue
        if industry and industry.lower() not in d.get('industry','').lower():continue
        hit=[g for g in grams if g in text]
        exact=bool(query and (query in name or name in query))
        score=100 if exact else (20 if meaningful and meaningful in text else len(hit)/max(1,len(grams))*10)
        if vector and site.vector and site.vector_model==settings.EMBEDDING_MODEL and len(vector)==len(site.vector):
            norm=math.sqrt(sum(x*x for x in vector)*sum(x*x for x in site.vector))
            sim=sum(x*y for x,y in zip(vector,site.vector))/norm if norm else 0
            if sim>.55:score+=sim*8
        if q and score<2:continue
        matches.append((score,{'site_id':str(site.id),'slug':site.slug,'name':d.get('name'),
           'description':d.get('description'),'region':d.get('region'),'industry':d.get('industry'),
           'check_result':site.check_result,'url':'/shop/'+site.slug,'cover_url':'/shop/'+site.slug+'/media/'+d['cover_asset_id'] if d.get('cover_asset_id') else None,'updated_at':site.published_at,
           'reason':'最新公开资料' if not q else '企业名称匹配' if exact else ('资料包含：'+'、'.join(sorted(hit)[:6]) if hit else '语义相关，请核对企业服务资料')}))
    matches.sort(key=lambda x:x[0],reverse=True)
    return {'items':[r for _,r in matches[(page-1)*size:page*size]],'total':len(matches),'page':page,
            'semantic_status':'available' if vector else 'keyword_only','scope':'营火站内搜索'}

def source_for(ref):
    try:host=(urlparse(ref).hostname or '').lower()
    except ValueError:return 'unknown'
    if not host:return 'unknown'
    if host=='campfire.dawoai.com':return 'internal'
    for domain in ('chatgpt.com','perplexity.ai','doubao.com','deepseek.com','kimi.com','bing.com','google.com','baidu.com'):
        if host==domain or host.endswith('.'+domain):return domain
    return 'external'

def event(db,site_id,key,kind,source='',visitor='',audience='unknown'):
    now=datetime.now(timezone.utc)
    # Daily retention work is independent of dashboard reads.
    global _retention_day
    today=now.date().isoformat()
    if _retention_day!=today:
        retention(db,now)
        _retention_day=today
    record=GeoEvent(site_id=site_id,event_key=key,kind=kind,source=source_for(source),
        visitor=hashlib.sha256((now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()+visitor).encode()).hexdigest() if visitor else '',
        audience=audience,day=now.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat(),created_at=now)
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
            # The event and rollups share one savepoint: duplicate retries cannot
            # increment totals. Dialect UPSERT prevents lost concurrent updates.
            if db.bind.dialect.name=='postgresql':
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            values=dict(site_key=str(site_id) if site_id else 'home',day=record.day,
                        kind=kind,source=record.source,audience=audience,count=1)
            statement=insert(GeoDaily).values(**values)
            db.execute(statement.on_conflict_do_update(
                index_elements=['site_key','day','kind','source','audience'],
                set_={'count':GeoDaily.count+1}))
            if audience not in ('bot','self_test') and kind=='view' and record.visitor:
                db.execute(insert(GeoVisitor).values(site_key=values['site_key'],day=record.day,
                    visitor=record.visitor).on_conflict_do_nothing())
    except IntegrityError:
        pass
    db.commit()

def metrics(db,site=None,days=30,homepage=False):
    cutoff=(datetime.now(ZoneInfo('Asia/Shanghai')).date()-timedelta(days=days-1)).isoformat()
    query=db.query(GeoDaily).filter(GeoDaily.day>=cutoff)
    visitors_query=db.query(GeoVisitor).filter(GeoVisitor.day>=cutoff)
    if site:
        query=query.filter(GeoDaily.site_key==str(site.id))
        visitors_query=visitors_query.filter(GeoVisitor.site_key==str(site.id))
    if homepage:
        query=query.filter(GeoDaily.site_key=='home')
        visitors_query=visitors_query.filter(GeoVisitor.site_key=='home')
    clean=query.filter(GeoDaily.audience.notin_(['bot','self_test']))
    counts=dict(clean.with_entities(GeoDaily.kind,func.sum(GeoDaily.count)).group_by(GeoDaily.kind).all())
    visitors=visitors_query.with_entities(func.count(func.distinct(GeoVisitor.visitor))).scalar()
    trends=clean.with_entities(GeoDaily.day,GeoDaily.kind,func.sum(GeoDaily.count)).group_by(GeoDaily.day,GeoDaily.kind).order_by(GeoDaily.day).all()
    sources=clean.filter(GeoDaily.kind=='view').with_entities(GeoDaily.source,func.sum(GeoDaily.count)).group_by(GeoDaily.source).all()
    return {'days':days,'counts':counts,'daily_visitor_estimates':visitors,'trend':[{'day':d,'kind':k,'count':n} for d,k,n in trends],
       'sources':dict(sources),'bots':query.filter(GeoDaily.audience=='bot').with_entities(func.coalesce(func.sum(GeoDaily.count),0)).scalar(),
       'external_search':{'status':'not_connected','message':'未接入站长工具，暂无搜索曝光或收录证据'},
       'model_citations':{'status':'not_connected','message':'未配置联网检索监测渠道，暂无引用样本'},
       'consultations':{'status':'not_connected','message':'联系点击不等于实际咨询；尚未接入客服或咨询表单'},
       'timezone':'Asia/Shanghai','updated_at':datetime.now(timezone.utc).isoformat(),
       'definition':'近90天最小化事件；访客为逐日匿名估算，同一人跨日可能重复。来源缺失归未知；试搜与自测不代表获客。'}


def retention(db,now=None):
    from sqlalchemy import delete
    now=now or datetime.now(timezone.utc)
    db.execute(delete(GeoEvent).where(GeoEvent.created_at < now-timedelta(days=90)))
    db.execute(delete(GeoDaily).where(GeoDaily.day < (now-timedelta(days=730)).date().isoformat()))
    db.execute(delete(GeoVisitor).where(GeoVisitor.day < (now-timedelta(days=90)).date().isoformat()))


def check_content(site,content):
    from app.api.geo_public import render_site
    rendered=render_site(site,content).body.decode()
    return {'checked_at':datetime.now(timezone.utc).isoformat(),
        'scope':'发布快照结构检查；不代表外部收录或推荐',
        'items':[{'name':name,'passed':bool(passed)} for name,passed in [
            ('公开资料完整',not validate(content)),
            ('无需JavaScript即可读取介绍',html_escaped(content.get('description','')) in rendered),
            ('包含结构化数据','application/ld+json' in rendered),
            ('包含规范网址','rel="canonical"' in rendered),
            ('有公开联系入口','data-contact' in rendered)]]}


def html_escaped(value):
    import html
    return html.escape(str(value or ''),quote=True)

_maintenance_date=''

def maintenance(db):
    """Run once a day in the existing single-concurrency scheduler, without browsers."""
    global _maintenance_date
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    if _maintenance_date==today:return
    retention(db)
    for site in db.query(GeoSite).filter_by(status='published').yield_per(100):
        site.check_result=check_content(site,site.live)
    db.commit()
    _maintenance_date=today


def event_token(site_id,bucket=None):
    import hmac
    import time
    from app.config import settings
    bucket=int(time.time()//3600) if bucket is None else bucket
    message=f'geo:{site_id or "home"}:{bucket}'
    signature=hmac.new(settings.SECRET_KEY.encode(),message.encode(),hashlib.sha256).hexdigest()
    return f'{bucket}.{signature}'


def verify_event_token(site_id,token):
    import hmac
    import time
    try:
        bucket=int(token.split('.')[0])
        if abs(int(time.time()//3600)-bucket)>1:return False
        return hmac.compare_digest(token,event_token(site_id,bucket))
    except (ValueError,TypeError):return False
