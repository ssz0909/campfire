"""Server-rendered public pages; no SPA login or JavaScript needed to read facts."""
import html
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.geo import GeoSite, GeoSlug
from app.models.company import Company
from app.services import geo, public_design

router=APIRouter()
ORIGIN='https://campfire.dawoai.com'
e=lambda value:html.escape(str(value or ''),quote=True)
CSS='''*{box-sizing:border-box}body{margin:0;background:#faf8f4;color:#26332f;font:16px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}a{color:inherit}header,main,footer{max-width:1160px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #ddd8ce}nav{display:flex;gap:24px}header a{text-decoration:none}.logo{font-size:23px;font-weight:800;color:#b34d26}.hero{padding:60px 0 35px;max-width:850px}h1{font-size:clamp(32px,5vw,58px);line-height:1.25;letter-spacing:-1px}h2{font-size:25px}.eyebrow{color:#a95532;text-transform:uppercase;letter-spacing:2px;font-size:13px}.muted,small{color:#68746c}.buttons{display:flex;gap:14px;flex-wrap:wrap}.button,button{background:#b44d25;color:white;border:0;border-radius:8px;padding:12px 22px;text-decoration:none;cursor:pointer;font:inherit}.secondary{background:#ece6db;color:#26332f}form{display:flex;gap:10px;flex-wrap:wrap;background:white;padding:20px;border-radius:14px;border:1px solid #ddd8ce}textarea{width:100%;font:inherit;border:1px solid #ccc;border-radius:7px;padding:12px}input{min-width:140px;flex:1;border:1px solid #d4d9d1;border-radius:7px;padding:12px;font:inherit}input[name=q]{flex:3}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px;margin:25px 0}.card{background:white;border:1px solid #e0e2d9;border-radius:14px;padding:26px}.card h3{margin-top:0}.card p,.facts{white-space:pre-wrap;overflow-wrap:anywhere}.tag{font-size:13px;color:#28766a}.section{padding:25px 0}.notice{padding:14px 0;color:#68746c;font-size:14px}.cover{width:100%;max-height:460px;object-fit:cover;border-radius:14px}.contact{background:#f2ecdf;padding:24px;border-radius:14px}footer{font-size:13px;border-top:1px solid #ddd8ce;margin-top:40px}details{padding:12px 0}summary{cursor:pointer}@media(max-width:600px){header,main,footer{padding:18px}nav{gap:12px;font-size:14px}.hero{padding:35px 0}input,button{width:100%}}'''

CSS += public_design.CSS

def script(site_id=None,kind='view'):
    # Daily anonymous visitor estimate, no fingerprint or IP stored. Referrer is reduced
    # to origin before transmission to avoid leaking query strings.
    return '''<script>(()=>{let v='';try{v=sessionStorage.getItem('cf-geo-v')||crypto.randomUUID();sessionStorage.setItem('cf-geo-v',v)}catch{}let ref='';try{ref=new URL(document.referrer).origin}catch{}function emit(kind,site,token){fetch('/api/v1/public/geo/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_id:crypto.randomUUID(),kind,site_id:site,token:token||pageToken,visitor:v,referrer:ref,self_test:new URLSearchParams(location.search).has('self_test')}),keepalive:true}).catch(()=>{})}const site='''+json.dumps(str(site_id) if site_id else None)+''',pageToken='''+json.dumps(geo.event_token(site_id))+''';emit('view',site);const f=document.getElementById('feedback-form');if(f)f.addEventListener('submit',async ev=>{ev.preventDefault();const out=document.getElementById('feedback-result');try{const r=await fetch('/api/v1/public/geo/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({site_id:site,message:f.elements.message.value})});out.textContent=r.ok?'反馈已收到':'提交失败，请稍后重试';if(r.ok)f.reset()}catch{out.textContent='网络异常，请稍后重试'}});const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){emit('search_impression',entry.target.dataset.site,entry.target.dataset.token);observer.unobserve(entry.target)}}),{threshold:0.5});document.querySelectorAll('[data-site]').forEach(a=>{const id=a.dataset.site;observer.observe(a);if(new URLSearchParams(location.search).has('self_test'))a.href+='?self_test=1';a.addEventListener('click',()=>emit('search_click',id,a.dataset.token))});document.querySelectorAll('[data-contact]').forEach(a=>a.addEventListener('toggle',()=>{if(a.open)emit('contact',site)}))})()</script>'''

def page(title,body,path='/',description='',schema=None,extra='',preview=False):
    structured=json.dumps(schema or {'@context':'https://schema.org','@type':'Organization','name':'营火AI','url':ORIGIN},ensure_ascii=False).replace('<','\\u003c')
    return HTMLResponse('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><meta name="description" content="'+e(description)+'"><link rel="alternate" type="text/plain" href="/llms.txt" title="LLM内容导航"><link rel="canonical" href="'+ORIGIN+e(path)+'">'+('<meta name="robots" content="noindex,nofollow">' if preview else '')+'<style>'+CSS+'</style><script type="application/ld+json">'+structured+'</script></head><body><header><a class="logo" href="/">'+public_design.BRAND_ICON+'营火AI</a><nav><a href="/search">发现企业</a><a class="nav-business" href="/business">企业服务</a><a class="nav-login" href="/login">登录工作台</a></nav></header><main>'+body+'</main>'+public_design.footer()+extra+'</body></html>',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin'})

def form(q='',region='',industry=''):
    return '<form action="/search"><input name="q" maxlength="120" aria-label="企业或服务需求" placeholder="搜索企业，或试试：安吉亲子酒店" value="'+e(q)+'"><input name="region" maxlength="120" aria-label="地区筛选" placeholder="地区（可选）" value="'+e(region)+'"><input name="industry" maxlength="80" aria-label="行业筛选" placeholder="行业（可选）" value="'+e(industry)+'"><button>搜索</button></form>'

def cards(result):
    if not result['items']:return '<div class="public-empty"><div class="company-avatar" aria-hidden="true">↗</div><div><h3>每一家好企业，都值得一个清晰的介绍。</h3><p>暂无匹配的已发布企业，可调整搜索条件。企业发布主页后，会在这里呈现。</p></div></div>'
    return '<div class="grid">'+''.join('<article class="card">'+('<img class="enterprise-cover" src="'+e(i['cover_url'])+'" alt="'+e(i['name'])+'公开封面" width="800" height="520" loading="lazy">' if i.get('cover_url') else '<div class="company-avatar" aria-hidden="true">'+e((i['name'] or '企')[:1])+'</div>')+'<span class="tag">'+e(' · '.join(filter(None,[i['region'],i['industry']])) or '企业公开主页')+'</span><h3><a data-site="'+i['site_id']+'" data-token="'+geo.event_token(i['site_id'])+'" href="'+i['url']+'">'+e(i['name'])+'</a></h3><p>'+e(i['description'][:180])+'</p><div class="card-meta"><small>'+e(i['reason'])+'<br>资料更新时间：'+e(str(i['updated_at'])[:10])+'</small></div></article>' for i in result['items'])+'</div>'

@router.get('/public-media/{filename}')
def public_media(filename:str):
    from pathlib import Path
    if filename not in ('landscape.svg','food.svg','studio.svg','hospitality.webp','dining.webp','workspace.webp'):
        raise HTTPException(404)
    return FileResponse(Path(__file__).resolve().parents[1]/'public_media'/filename,
                        media_type='image/webp' if filename.endswith('.webp') else 'image/svg+xml',headers={'Cache-Control':'public, max-age=3600','X-Content-Type-Options':'nosniff'})


@router.get('/',response_class=HTMLResponse)
def home(db:Session=Depends(get_db)):
    result=geo.search(db,'',size=3)
    body=public_design.hero()+public_design.showcase()+'<section class="home-discover" id="discover"><div class="section-head"><div><p class="section-kicker">DISCOVER WITH CAMPFIRE</p><h2>发现企业与服务</h2><p>搜索企业名称，看看它的公开主页。</p></div><a href="/search">浏览全部企业 <span aria-hidden="true">↗</span></a></div>'+form()+ '<p class="home-scope">营火站内搜索 · 依据企业已发布的公开资料匹配</p>'+cards(result)+'</section>'+public_design.benefits()
    return page('营火AI｜AI运营平台',body,description='营火AI为小企业提供数字员工、内容制作、多账号发布、企业公开主页与效果统计。',extra=script())

@router.get('/search',response_class=HTMLResponse)
def search(request:Request,q:str=Query('',max_length=120),region:str=Query('',max_length=120),industry:str=Query('',max_length=80),p:int=Query(1,ge=1,le=10000),db:Session=Depends(get_db)):
    geo.public_limit(request,40)
    result=geo.search(db,q,region,industry,p)
    body='<h1 style="font-size:36px">发现企业与服务</h1><p>营火站内搜索 · 仅使用已发布企业资料，不代表外部大模型推荐</p>'+form(q,region,industry)+'<p class="muted">找到 '+str(result['total'])+' 家企业 · '+('语义与关键词匹配' if result['semantic_status']=='available' else '当前使用企业资料关键词匹配')+'</p>'+cards(result)
    for n,label in [(p-1,'上一页'),(p+1,'下一页')]:
        if n>=1 and (n-1)*12<result['total']:body+='<a class="button secondary" href="/search?'+e(urlencode({'q':q,'region':region,'industry':industry,'p':n}))+'">'+label+'</a> '
    response=page('企业搜索｜营火AI',body,'/search',extra=script())
    response.headers['X-Robots-Tag']='noindex,follow'
    return response

def public_site(db,slug):
    registry=db.get(GeoSlug,slug)
    site=db.get(GeoSite,registry.site_id) if registry else None
    company=db.get(Company,site.company_id) if site else None
    if not site or site.status!='published' or not company or company.is_deleted or not company.is_active:raise HTTPException(404,'企业主页未公开')
    return site

def render_site(site,d,section='',preview=False):
    name=d.get('name','');config=d.get('template_snapshot',{}).get('config',geo.DEFAULTS['generic'])
    body=('<p class="notice">草稿预览 · 不计入公开访问，尚未发布</p>' if preview else '')+'<p class="eyebrow">'+e(d.get('industry'))+' · '+e(d.get('region'))+'</p><h1>'+e(name)+'</h1><style>.eyebrow{color:'+(d.get('brand_color') or config.get('accent','#c05929'))+'}</style><p class="muted">企业提供并确认 · '+e(str(site.published_at or '')[:10])+' · 非平台独立认证</p>'
    if d.get('cover_asset_id'):body+='<img class="cover" src="/shop/'+e(site.slug)+'/media/'+e(d['cover_asset_id'])+'" alt="'+e(name)+'公开封面">' if site.slug and not preview else ''
    labels={'description':config.get('intro','企业介绍'),'services':config.get('services','产品与服务'),'faq':config.get('faq','常见问题')}
    for key in d.get('module_order',['description','services','faq']):
        label=labels[key]
        if key in ('services','faq') and not d.get('show_'+key,True):continue
        if d.get(key) and (not section or key==section):body+='<section class="section"><h2>'+e(label)+'</h2><div class="facts">'+e(d[key])+'</div></section>'
    if d.get('facts'):
        body+='<section><h2>企业确认资料</h2>'+''.join('<p><strong>'+e(f['key'])+'：</strong>'+(e(f['value']) if not f.get('valid_until') or f['valid_until']>=datetime.now(timezone.utc).date().isoformat() else '资料已过期，等待企业更新')+'<br><small>来源：'+e(f['source'])+(' · 有效期至 '+e(f['valid_until']) if f.get('valid_until') else '')+'</small></p>' for f in d['facts'])+'</section>'
    body+='<section class="contact"><h2>位置与联系</h2><p class="facts">'+e(d.get('address'))+'</p><details data-contact><summary>查看联系信息</summary><p class="facts">'+e(d.get('contact'))+'</p></details></section><p class="notice">信息由该企业维护；服务与价格请联系企业确认。如有错误，可通过联系信息向企业反馈，或联系营火平台管理员核实。</p>'
    if not preview:
        if d.get('services') and d.get('show_services',True):body+='<a href="/shop/'+e(site.slug)+'/services">服务详情</a> · '
        if d.get('faq') and d.get('show_faq',True):body+='<a href="/shop/'+e(site.slug)+'/faq">常见问题</a>'
    schema={'@context':'https://schema.org','@type':'Organization','@id':ORIGIN+'/entities/'+str(site.company_id),'name':name,'description':d.get('description'),'url':ORIGIN+'/shop/'+str(site.slug)}
    if d.get('address'):schema['address']={'@type':'PostalAddress','streetAddress':d['address']}
    if not preview:
        body+='<details><summary>反馈信息错误</summary><form id="feedback-form"><label>请说明不准确信息及核实依据（请勿填写个人敏感信息）<textarea name="message" minlength="10" maxlength="2000" required rows="4"></textarea></label><button>提交给营火管理员</button><span id="feedback-result" role="status"></span></form></details>'
    return page(name+'｜营火AI企业主页' ,body,'/shop/'+str(site.slug)+('/'+section if section else ''),d.get('description','')[:180],schema,extra='' if preview else script(site.id),preview=preview)

def llms_response(content):
    return Response(content, media_type='text/plain', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


@router.api_route('/llms.txt', methods=['GET', 'HEAD'])
def llms_index(db:Session=Depends(get_db)):
    from app.services.llms import directory
    return llms_response(directory(db, ORIGIN, root=True))


@router.api_route('/llms/companies/{page_number}.txt', methods=['GET', 'HEAD'])
def llms_directory(page_number:int, db:Session=Depends(get_db)):
    from app.services.llms import directory
    if page_number < 1:raise HTTPException(404, '企业目录页不存在')
    return llms_response(directory(db, ORIGIN, page_number))


# Register before the generic /shop/{slug}/{section} route.
@router.api_route('/shop/{slug}/llms.txt', methods=['GET', 'HEAD'])
def llms_company(slug:str, db:Session=Depends(get_db)):
    from app.services.llms import company_document
    site=public_site(db,slug)
    if slug!=site.slug:return RedirectResponse('/shop/'+site.slug+'/llms.txt',301)
    return llms_response(company_document(site, ORIGIN))


@router.get('/shop/{slug}',response_class=HTMLResponse)
@router.get('/shop/{slug}/{section}',response_class=HTMLResponse)
def shop(slug:str,request:Request,section:str='',db:Session=Depends(get_db)):
    if section not in ('','services','faq'):raise HTTPException(404)
    site=public_site(db,slug)
    if slug!=site.slug:return RedirectResponse('/shop/'+site.slug+('/'+section if section else ''),301)
    if section and (not site.live.get(section) or not site.live.get('show_'+section,True)):raise HTTPException(404)
    return render_site(site,site.live,section)

@router.get('/shop/{slug}/media/{asset_id}')
def media(slug:str,asset_id:uuid.UUID,db:Session=Depends(get_db)):
    from app.models.asset import Asset
    from app.config import settings
    from pathlib import Path
    site=public_site(db,slug)
    if str(asset_id)!=site.live.get('cover_asset_id'):raise HTTPException(404)
    asset=db.get(Asset,asset_id)
    if not asset or asset.company_id!=site.company_id or asset.is_deleted or asset.asset_type!='image' or asset.mime_type not in ('image/jpeg','image/png','image/webp'):raise HTTPException(404)
    root=Path(settings.LOCAL_STORAGE_PATH).resolve();path=(root/asset.file_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise HTTPException(404)
    return FileResponse(path,media_type=asset.mime_type,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@router.get('/sitemap.xml')
def sitemap(db:Session=Depends(get_db)):
    sites=db.query(GeoSite).join(Company).filter(GeoSite.status=='published',Company.is_active==True,Company.is_deleted==False).all()
    urls=['<url><loc>'+ORIGIN+p+'</loc></url>' for p in ('/','/business','/about')]
    for s in sites:
        for path in ['']+[p for p in ('services','faq') if s.live.get(p) and s.live.get('show_'+p,True)]:
            urls.append('<url><loc>'+ORIGIN+'/shop/'+e(s.slug)+('/'+path if path else '')+'</loc><lastmod>'+str(s.published_at)[:10]+'</lastmod></url>')
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(urls)+'</urlset>',media_type='application/xml')

@router.get('/robots.txt')
def robots():return Response('User-agent: *\nAllow: /shop/\nDisallow: /api/\nDisallow: /admin\nDisallow: /dashboard\nDisallow: /search\nSitemap: '+ORIGIN+'/sitemap.xml\n',media_type='text/plain')

@router.get('/business')
def business():return page('企业服务｜营火AI','<h1>让企业持续运营起来</h1><div class="grid"><div class="card"><h2>数字员工协作</h2><p>运营总管规划任务，内容策划、分析员、助理和视频制作员按职责执行。</p></div><div class="card"><h2>内容与授权发布</h2><p>使用企业资料与素材制作内容，按质量或成本模式生成视频，向已授权账号发布。</p></div><div class="card"><h2>公开主页与反馈</h2><p>发布企业主页，在营火内被搜索发现，并查看真实访问和联系点击。</p></div></div><p>外部搜索收录及大模型推荐由对应服务决定。套餐和可用额度以工作台及实际服务约定为准。</p><a class="button" href="/register">开始使用</a>','/business')

@router.get('/about')
def about():return page('关于与信息说明｜营火AI','<h1>关于营火AI</h1><p>营火AI为小企业提供AI运营工具与企业公开信息服务。</p><h2>信息来源</h2><p>企业主页资料由企业维护并确认，平台提供托管与信息检查。企业自述不等于平台独立核验；站内搜索不等于外部大模型推荐。</p><h2>纠错与联系</h2><p>企业可在工作台更新资料或撤回主页；其他用户可联系企业核实，涉及平台问题请由工作区联系平台管理员处理。平台保留更名及下架审计。</p>','/about')

@router.get('/privacy')
def privacy():return page('公开主页隐私说明｜营火AI','<h1>公开主页隐私说明</h1><p>公开主页仅展示企业确认发布的资料。访问统计记录页面、日期、来源类别、联系入口点击及按日匿名访客估算；不使用设备指纹，不在统计中收集咨询正文或联系方式。</p><p>浏览器会话中的随机标识用于估算访问；拒绝或无法使用存储时仍可浏览。原始统计事件保留90天。来源可能缺失，无法据此识别全部AI访问。企业内部经营资料及平台账号凭证不会进入公开搜索。</p>','/privacy')
