"""Domain verification, attributed report import and bounded GSC API collection."""
import csv
import html
import io
import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlsplit, urlunsplit
import httpx
from sqlalchemy import func, case
from app.connectors.hotel.models import PlatformKeyValue
from app.core.secrets import _fernet, encrypt_json
from app.models.geo import GeoSearchDaily, GeoSlug

ORIGIN = 'https://campfire.dawoai.com'
PROVIDERS = {
    'google': {'name':'Google Search Console','url':'https://search.google.com/search-console','meta':'google-site-verification'},
    'bing': {'name':'Bing Webmaster Tools','url':'https://www.bing.com/webmasters/','meta':'msvalidate.01'},
    'baidu': {'name':'百度搜索资源平台','url':'https://ziyuan.baidu.com/','meta':'baidu-site-verification'},
}
KEY = 'platform.geo.webmaster.'

class WebmasterError(ValueError):
    pass

def read(db, key):
    row=db.get(PlatformKeyValue,KEY+key)
    return json.loads(_fernet().decrypt(row.encrypted_value.encode())) if row else {}

def write(db,key,value):
    row=db.get(PlatformKeyValue,KEY+key)
    if row is None:
        row=PlatformKeyValue(key=KEY+key);db.add(row)
    row.encrypted_value=encrypt_json(value);row.updated_at=datetime.now(timezone.utc)
    db.flush()

def config(db,provider):
    return read(db,'config.'+provider)

def save_config(db,provider,values):
    old=config(db,provider)
    token=values.get('verification_token','').strip()
    # Accept a complete provider tag for convenience, but only store its token.
    if token.startswith('<meta'):
        from html.parser import HTMLParser
        class Meta(HTMLParser):
            values=[]
            def handle_starttag(self,tag,attrs):
                d=dict(attrs)
                if tag=='meta' and d.get('name')==PROVIDERS[provider]['meta']:self.values.append(d.get('content',''))
        parser=Meta();parser.values=[];parser.feed(token)
        if len(parser.values)!=1:raise WebmasterError('请粘贴对应渠道的一个验证标签或仅填写content值')
        token=parser.values[0]
    if token and not re.fullmatch(r'[A-Za-z0-9_.=\-]{1,300}',token):raise WebmasterError('验证值格式不正确，请填写HTML标签中的content值')
    result={'verification_token':token,'auto_sync':bool(values.get('auto_sync',False))}
    if provider=='google':
        prop=values.get('property') or ORIGIN+'/'
        if prop not in (ORIGIN+'/', 'sc-domain:campfire.dawoai.com'):raise WebmasterError('资源只能选择营火HTTPS网址前缀或营火子域名资源')
        result['property']=prop
        credentials=old.get('service_account',{})
        if values.get('clear_credentials'):credentials={}
        if values.get('service_account_json','').strip():
            try:
                credentials=json.loads(values['service_account_json'])
                if credentials.get('type')!='service_account' or not credentials.get('client_email','').endswith('.gserviceaccount.com'):raise ValueError()
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                key=load_pem_private_key(credentials['private_key'].encode(),password=None)
                from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
                if not isinstance(key,RSAPrivateKey):raise ValueError()
            except (ValueError,KeyError,TypeError,AttributeError):raise WebmasterError('服务账号JSON无效，请使用Google下载的服务账号密钥文件内容') from None
            credentials={k:credentials[k] for k in ('type','client_email','private_key')}
        result['service_account']=credentials
        if result['auto_sync'] and not credentials:raise WebmasterError('启用自动同步前请先保存Google服务账号凭据')
    elif result['auto_sync']:raise WebmasterError('该渠道目前使用报表导入，不支持自动同步')
    write(db,'config.'+provider,result)

def state(db,provider):return read(db,'state.'+provider)

def settings_view(db):
    items=[]
    for provider,info in PROVIDERS.items():
        c=config(db,provider)
        items.append({'provider':provider,**info,'verification_token':c.get('verification_token',''),
            'verification_status':'configured_not_verified' if c.get('verification_token') else 'not_configured',
            'property':c.get('property',ORIGIN+'/'),'auto_sync':c.get('auto_sync',False),
            'credentials_configured':bool(c.get('service_account')),
            'service_account_email':c.get('service_account',{}).get('client_email',''),
            'mode':'api_and_import' if provider=='google' else 'report_import',
            'sync':state(db,provider)})
    return {'origin':ORIGIN,'sitemap':ORIGIN+'/sitemap.xml','items':items}

def verification_tags(db):
    tags=[]
    for provider,info in PROVIDERS.items():
        token=config(db,provider).get('verification_token')
        if token:tags.append('<meta name="'+info['meta']+'" content="'+html.escape(token,quote=True)+'">')
    return ''.join(tags)


def normalize_page(raw):
    url=urlsplit(raw.strip())
    if not url.scheme and raw.startswith('/') and not raw.startswith('//'):url=urlsplit(ORIGIN+raw)
    if url.scheme!='https' or url.netloc!='campfire.dawoai.com':raise WebmasterError('报表只接受https://campfire.dawoai.com下的页面')
    if len(url.path)+len(url.query)>900:raise WebmasterError('页面地址过长')
    return urlunsplit(('https',url.netloc,url.path or '/',url.query,''))

def row_values(raw):
    try:
        day=date.fromisoformat(str(raw['day']))
        if not date.today()-timedelta(days=730)<=day<=date.today():raise ValueError()
        clicks=int(raw['clicks']);impressions=int(raw['impressions'])
        if str(clicks)!=str(raw['clicks']).strip() or str(impressions)!=str(raw['impressions']).strip():raise ValueError()
        if not 0<=clicks<=impressions<=10**12:raise ValueError()
        pos=None if raw.get('position') in ('',None) else float(raw['position'])
        if pos is not None and (not math.isfinite(pos) or pos<1):raise ValueError()
    except (ValueError,TypeError,KeyError):raise WebmasterError('日期、点击、曝光或排名格式错误；日期需在近730天内，点击/曝光为非负整数') from None
    return {'page':normalize_page(str(raw.get('page',''))),'day':day.isoformat(),'clicks':clicks,'impressions':impressions,'position':pos}

def parse_csv(data):
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:raise WebmasterError('请上传UTF-8编码CSV文件') from None
    aliases={'日期':'day','date':'day','页面':'page','网址':'page','url':'page','点击':'clicks','曝光':'impressions','展现':'impressions','平均排名':'position'}
    reader=csv.DictReader(io.StringIO(text));result=[];seen=set()
    headers=[aliases.get(str(k).strip().lower(),str(k).strip().lower()) for k in (reader.fieldnames or [])]
    if len(set(headers))!=len(headers) or not {'day','page','clicks','impressions'}.issubset(headers):raise WebmasterError('CSV列名需包含day,page,clicks,impressions且不能重复')
    for n,row in enumerate(reader,2):
        if len(result)>=10000:raise WebmasterError('每次最多导入10000条记录')
        if None in row or any(v is None for v in row.values()):raise WebmasterError(f'第{n}行CSV列数不一致')
        raw={aliases.get(str(k).strip().lower(),str(k).strip().lower()):v for k,v in row.items() if k is not None}
        try:item=row_values(raw)
        except WebmasterError as exc:raise WebmasterError(f'第{n}行：{exc}') from None
        key=(item['page'],item['day'])
        if key in seen:raise WebmasterError(f'第{n}行存在重复页面/日期，请先按页面和日期汇总')
        seen.add(key);result.append(item)
    if not result:raise WebmasterError('CSV没有数据，列名需为day,page,clicks,impressions,position（排名可空）')
    return result

def store_rows(db,provider,rows,source,source_name):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
    slugs={s.slug:s.site_id for s in db.query(GeoSlug).all()};matched=0
    for row in rows:
        path=urlsplit(row['page']).path.split('/')
        site_id=slugs.get(path[2]) if len(path)>=3 and path[1]=='shop' else None
        if site_id:matched+=1
        values={**row,'provider':provider,'site_id':site_id,'source':source,'source_name':source_name,'updated_at':datetime.now(timezone.utc)}
        statement=insert(GeoSearchDaily).values(**values)
        db.execute(statement.on_conflict_do_update(index_elements=['provider','page','day'],set_={k:v for k,v in values.items() if k not in ('provider','page','day')}))
    return {'rows':len(rows),'matched_enterprise_rows':matched,'other_rows':len(rows)-matched}


def external_metrics(db,site=None,days=30,homepage=False):
    q=db.query(GeoSearchDaily).filter(GeoSearchDaily.day>=(date.today()-timedelta(days=days-1)).isoformat())
    if site:q=q.filter(GeoSearchDaily.site_id==site.id)
    if homepage:q=q.filter(GeoSearchDaily.page==ORIGIN+'/')
    rows=q.with_entities(GeoSearchDaily.provider,func.sum(GeoSearchDaily.clicks),func.sum(GeoSearchDaily.impressions),func.max(GeoSearchDaily.day),func.max(GeoSearchDaily.updated_at),func.sum(GeoSearchDaily.position*GeoSearchDaily.impressions),func.sum(case((GeoSearchDaily.position.is_not(None),GeoSearchDaily.impressions),else_=0))).group_by(GeoSearchDaily.provider).all()
    items=[]
    for p,clicks,impressions,last_day,updated,weighted,known in rows:
        sources=[v for (v,) in q.filter(GeoSearchDaily.provider==p).with_entities(GeoSearchDaily.source_name).distinct().all()]
        items.append({'provider':p,'name':PROVIDERS[p]['name'],'clicks':clicks,'impressions':impressions,
            'ctr':clicks/impressions if impressions else 0,'average_position':weighted/known if known else None,'last_data_day':last_day,'updated_at':updated.isoformat(), 'sources':sources})
    return {'status':'available' if items else 'no_data','items':items,
        'message':'搜索表现按渠道分别统计；数据有延迟，报表导入保留来源，不代表收录数量或模型推荐。' if items else '暂无外部搜索数据；管理员可在GEO站长工具中配置Google同步或导入渠道报表。'}


def google_rows(c):
    from jose import jwt
    credentials=c.get('service_account')
    if not credentials:raise WebmasterError('请先配置Google服务账号，并将其邮箱添加为Search Console资源用户')
    now=int(time.time())
    assertion=jwt.encode({'iss':credentials['client_email'],'scope':'https://www.googleapis.com/auth/webmasters.readonly',
        'aud':'https://oauth2.googleapis.com/token','iat':now,'exp':now+3600},credentials['private_key'],algorithm='RS256')
    # Fixed official endpoints only; credentials never follow administrator-supplied URLs.
    with httpx.Client(timeout=25,follow_redirects=False) as client:
        auth=client.post('https://oauth2.googleapis.com/token',data={'grant_type':'urn:ietf:params:oauth:grant-type:jwt-bearer','assertion':assertion})
        if auth.status_code!=200:raise WebmasterError(f'Google令牌授权失败 HTTP {auth.status_code}，请检查服务账号密钥')
        token=auth.json().get('access_token')
        if not token:raise WebmasterError('Google未返回访问令牌')
        end=date.today()-timedelta(days=3);start=end-timedelta(days=29)
        url='https://www.googleapis.com/webmasters/v3/sites/'+quote(c.get('property',ORIGIN+'/'),safe='')+'/searchAnalytics/query'
        rows=[]
        for offset in range(0,10001,2500):
            response=client.post(url,headers={'Authorization':'Bearer '+token},json={'startDate':start.isoformat(),'endDate':end.isoformat(),
                'dimensions':['date','page'],'dimensionFilterGroups':[{'filters':[{'dimension':'page','operator':'contains','expression':ORIGIN+'/'}]}],'rowLimit':2500,'startRow':offset,'dataState':'final','type':'web'})
            if response.status_code!=200:raise WebmasterError(f'Google搜索数据读取失败 HTTP {response.status_code}，请检查资源权限和Search Console API启用状态')
            page=response.json().get('rows',[])
            if not isinstance(page,list):raise WebmasterError('Google返回的数据结构异常，未保存本次结果')
            if offset==10000 and page:raise WebmasterError('本次数据超过10000条，请改用按日期拆分的报表导入；本次未写入')
            for row in page:
                keys=row.get('keys',[])
                if len(keys)!=2:raise WebmasterError('Google返回维度不完整，未保存本次结果')
                # A domain property may contain other subdomains; only collect this origin.
                if urlsplit(keys[1]).netloc!='campfire.dawoai.com' or urlsplit(keys[1]).scheme!='https':continue
                raw={'day':keys[0],'page':keys[1],'clicks':int(row['clicks']),'impressions':int(row['impressions']),'position':row.get('position')}
                rows.append(row_values(raw))
            if len(page)<2500:break
        return rows


def enqueue(db):
    c=config(db,'google')
    if not c.get('service_account'):raise WebmasterError('请先保存Google服务账号凭据，并在Search Console中授予资源读取权限')
    s=state(db,'google')
    if s.get('status') in ('queued','running'):return s
    s={'status':'queued','requested_at':datetime.now(timezone.utc).isoformat()}
    write(db,'state.google',s)
    return s


def run_due(db):
    """Called only by the dedicated, globally serialized collector worker."""
    c=config(db,'google');s=state(db,'google');now=datetime.now(timezone.utc)
    elapsed=(now-datetime.fromisoformat(s['started_at'])).total_seconds() if s.get('started_at') else 10**9
    due=s.get('status')=='queued' or (s.get('status')=='running' and elapsed>900) or (c.get('auto_sync') and elapsed>86400)
    if not due:return
    if not c.get('service_account'):return
    s={**s,'status':'running','started_at':now.isoformat(),'error':''}
    write(db,'state.google',s);db.commit()
    try:
        rows=google_rows(c)
        # Only replace API evidence in the queried period after every page was read.
        end=date.today()-timedelta(days=3);start=end-timedelta(days=29)
        db.query(GeoSearchDaily).filter(GeoSearchDaily.provider=='google',GeoSearchDaily.source=='api',
            GeoSearchDaily.day>=start.isoformat(),GeoSearchDaily.day<=end.isoformat()).delete(synchronize_session=False)
        summary=store_rows(db,'google',rows,'api','Google Search Console API · web · final · date/page')
        s.update(status='success',summary=summary,data_start=start.isoformat(),data_end=end.isoformat(),
                 note='已读取API返回记录；搜索分析接口可能只返回主要记录，不代表全量收录或全量搜索。')
    except Exception as exc:
        db.rollback()
        # Never persist HTTP exception strings: they may contain credentials or payloads.
        s.update(status='error',error=str(exc) if isinstance(exc,WebmasterError) else '同步异常，未修改本次数据；请检查网络、凭据和接口返回')
    s['finished_at']=datetime.now(timezone.utc).isoformat()
    write(db,'state.google',s);db.commit()


def start():
    """One API collector; never occupies the publishing/scheduled-task worker."""
    from threading import Event, Thread
    from sqlalchemy import text
    from app.database import engine, SessionLocal
    stop=Event()
    def loop():
        while not stop.is_set():
            connection=None;locked=False
            try:
                connection=engine.connect()
                postgres=connection.dialect.name=='postgresql'
                locked=bool(connection.execute(text('SELECT pg_try_advisory_lock(727431934)')).scalar()) if postgres else True
                connection.commit()
                if locked:
                    with SessionLocal() as db:run_due(db)
            except Exception:
                import logging
                logging.getLogger(__name__).warning('Webmaster collector unavailable; will retry without blocking publishing')
            finally:
                if connection is not None:
                    if locked and connection.dialect.name=='postgresql':
                        try:
                            connection.execute(text('SELECT pg_advisory_unlock(727431934)'));connection.commit()
                        except Exception:connection.invalidate()
                    connection.close()
            stop.wait(30)
    Thread(target=loop,name='webmaster-collector',daemon=True).start()
    return stop
