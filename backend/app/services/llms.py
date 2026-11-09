"""Read-only Markdown navigation generated exclusively from published snapshots."""
import html
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import load_only

from app.models.company import Company
from app.models.geo import GeoSite

PAGE_SIZE = 100


def markdown_text(value, limit=None):
    # Enterprise fields are data, never Markdown structure, HTML or instructions
    # supplied by this service. Keep each value on one line and escape syntax.
    text = ' '.join(str(value or '').split())
    text = ''.join(c for c in text if c.isprintable())
    if limit and len(text) > limit:
        text = text[:limit] + '…'
    text = html.escape(text, quote=False)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', text)


def public_sites(db):
    return db.query(GeoSite).join(Company, Company.id == GeoSite.company_id).filter(
        GeoSite.status == 'published', GeoSite.slug.isnot(None),
        Company.is_active.is_(True), Company.is_deleted.is_(False),
    )


def directory(db, origin, page=1, root=False):
    query = public_sites(db)
    total = query.count()
    pages = max(1, math.ceil(total / PAGE_SIZE))
    if page > pages:
        raise HTTPException(404, '企业目录页不存在')
    # Bounded snapshots, stable ordering: no draft, private profile or credentials.
    sites = query.options(load_only(GeoSite.slug, GeoSite.live, GeoSite.published_at)).order_by(
        GeoSite.slug.asc(), GeoSite.id.asc(),
    ).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    lines = [
        '# 营火AI' if root else f'# 营火AI公开企业目录 · 第{page}页',
        '', '> 面向小企业的AI运营平台与企业公开信息服务。', '',
        '营火AI提供企业公开资料与服务信息导航。企业资料由对应企业维护并确认，主页提供企业介绍、服务信息、公开联系方式及最近发布时间。',
        '本导航随企业主页发布状态自动更新；获取完整资料及最新服务信息，请访问对应企业主页。', '',
    ]
    if root:
        lines += ['## 平台信息', '',
                  f'- [企业服务]({origin}/business)：平台功能与服务范围。',
                  f'- [关于与信息说明]({origin}/about)：信息来源与纠错说明。',
                  f'- [隐私说明]({origin}/privacy)：访问统计及公开信息处理。',
                  f'- [站点地图]({origin}/sitemap.xml)：已发布页面与更新时间。', '']
    lines += ['## 企业公开主页', '', f'当前公开企业 {total} 家；第 {page}/{pages} 页，每页最多 {PAGE_SIZE} 家。', '']
    if not sites:
        lines += ['暂无已发布的企业主页。', '']
    for site in sites:
        d = site.live or {}
        summary = '；'.join(filter(None, [markdown_text(d.get('region'), 120),
                            markdown_text(d.get('industry'), 80), markdown_text(d.get('description'), 180)]))
        lines.append(f'- [{markdown_text(d.get("name"), 120)}]({origin}/shop/{site.slug})：{summary}')
    lines += ['', '## Optional', '']
    if page > 1:
        previous = '/llms.txt' if page == 2 else f'/llms/companies/{page - 1}.txt'
        lines.append(f'- [上一页企业目录]({origin}{previous})')
    if page < pages:
        lines.append(f'- [下一页企业目录]({origin}/llms/companies/{page + 1}.txt)')
    if not root:
        lines.append(f'- [平台内容导航]({origin}/llms.txt)')
    lines.append('企业主页另提供 /shop/{公开标识}/llms.txt 纯文本版本，与当前公开快照同步。')
    return '\n'.join(lines) + '\n'


def company_document(site, origin):
    d = site.live or {}
    base = f'{origin}/shop/{site.slug}'
    lines = [f'# {markdown_text(d.get("name"))}', '',
             '> 企业公开资料由对应企业维护并确认。完整介绍与最新服务信息请见规范主页。', '',
             f'规范主页：{base}', f'最近发布：{site.published_at.isoformat() if site.published_at else "未记录"}', '']
    for key, label in [('industry', '行业'), ('region', '地区'), ('address', '地址')]:
        if d.get(key):
            lines += [f'{label}：{markdown_text(d[key])}', '']
    labels = {'description': '企业介绍', 'services': '产品与服务', 'faq': '常见问题'}
    for key in d.get('module_order', ['description', 'services', 'faq']):
        if key in ('services', 'faq') and not d.get('show_' + key, True):
            continue
        if d.get(key):
            lines += [f'## {labels[key]}', '', markdown_text(d[key]), '']
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    facts = [f for f in d.get('facts', []) if f.get('status') == 'confirmed']
    if facts:
        lines += ['## 企业确认资料', '']
        for fact in facts:
            expired = bool(fact.get('valid_until') and fact['valid_until'] < today)
            value = '资料已过期，等待企业更新' if expired else markdown_text(fact.get('value'))
            lines += [f'- {markdown_text(fact.get("key"))}：{value}；来源：{markdown_text(fact.get("source"))}'
                      + (f'；有效期至 {markdown_text(fact["valid_until"])}' if fact.get('valid_until') else '')]
        lines.append('')
    if d.get('contact'):
        lines += ['## 公开联系信息', '', markdown_text(d['contact']), '']
    lines += ['## Optional', '', f'- [企业主页]({base})']
    for key, label in [('services', '服务详情'), ('faq', '常见问题')]:
        if d.get(key) and d.get('show_' + key, True):
            lines.append(f'- [{label}]({base}/{key})')
    lines.append(f'- [平台内容导航]({origin}/llms.txt)')
    return '\n'.join(lines) + '\n'
