"""Relevant, complementary source images with reproducible per-task rotation."""
import hashlib

from app.models.asset import Asset
from app.models.video_project import VideoProject

CATEGORY_TERMS={
    'exterior':('外观','门头','入口','外景','建筑','招牌','酒店外'),
    'lobby':('大堂','前台','大厅','接待','入住','公共区域'),
    'guest_room':('客房','房间','卧室','床','房型','住宿','房间环境'),
    'bathroom':('浴室','卫生间','洗漱','淋浴'),
    'restaurant':('餐厅','用餐','菜品','晚餐','餐饮'),
    'breakfast':('早餐','早饭','自助餐'),
    'amenities':('设施','健身','休闲','服务','配套'),
    'pool':('泳池','游泳','水景'),
    'meeting_room':('会议','宴会','会议室'),
    'staff':('员工','服务人员','服务流程'),
    'landscape':('景观','风景','花园','周边','自然','城市'),
}


def select_assets_for_video(db,company_id,goal,limit=40,template=None,rotation_key=None,exclude_task_id=None):
    assets=db.query(Asset).filter(Asset.company_id==company_id,Asset.asset_type=='image',
        Asset.is_deleted==False,Asset.is_available==True,Asset.processing_status=='ready').all()
    if not assets:return []
    topic=(goal or '').casefold()
    hints = ((template or {}).get('content') or {}).get('selection_keywords', [])
    recent = {}
    history_query = db.query(VideoProject).filter(VideoProject.company_id == company_id,
        VideoProject.is_deleted == False, VideoProject.project_status.notin_(['cancelled', 'failed']))
    if exclude_task_id is not None:
        from sqlalchemy import or_
        history_query = history_query.filter(or_(VideoProject.task_id.is_(None), VideoProject.task_id != exclude_task_id))
    history = history_query.order_by(VideoProject.created_at.desc(), VideoProject.id).limit(12).all()
    for position, project in enumerate(history):
        # Candidate pools are not usage: count only the sources actually in
        # the storyboard, falling back to selected IDs for legacy projects.
        ids = {str(s['source_asset_id']) for s in project.storyboard or []
               if isinstance(s, dict) and s.get('source_asset_id')} or set(map(str, project.selected_asset_ids or []))
        for asset_id in ids:
            recent[asset_id] = recent.get(asset_id, 0) + (3 if position < 2 else 1)
    scored=[]
    for asset in assets:
        analysis=(asset.asset_metadata or {}).get('vision_analysis') or {}
        if analysis.get('status')!='completed' and not (asset.asset_metadata or {}).get('manual_classification'):continue
        score=sum(1 for value in (asset.tags or []) if value and str(value).casefold() in topic)
        score+=sum(2 for term in CATEGORY_TERMS.get(asset.category,()) if term in topic)
        score+=sum(1 for value in [analysis.get('caption',''),asset.source_description or ''] if value and value.casefold() in topic)
        facts = ' '.join([asset.name or '', asset.source_description or '', analysis.get('visual_description', ''),
                          ' '.join(asset.tags or []), ' '.join(CATEGORY_TERMS.get(asset.category, ())) ]).casefold()
        # Industry is a tie-breaker only; the user's subject always ranks first.
        industry_score = min(0.5, sum(0.1 for word in hints if word.casefold() in facts))
        # Avoid tiny images and reward portrait-ready sources. Keep unmeasured
        # assets usable but rank measured, adequate images ahead of them.
        width,height=asset.width or 0,asset.height or 0
        if width and height and min(width,height)<320:continue
        quality=(2 if min(width,height)>=720 else 0)+(1 if height>width else 0)
        # A repeat is allowed when relevance is materially stronger, but a
        # recent source should lose to a comparable unused candidate.
        repeat_penalty = min(4, recent.get(str(asset.id), 0)) * 1.25
        tie = hashlib.sha256(f'{rotation_key or goal}:{asset.id}'.encode()).digest()
        scored.append((score-repeat_penalty,score,quality,asset,tie,industry_score))
    scored.sort(key=lambda x:(x[0],x[1],x[2],x[4]),reverse=True)
    if any(item[1]>0 for item in scored):scored=[item for item in scored if item[1]>0]
    # Keep recent references as a fallback, not the same unrestricted pool
    # the director sees every day. Preserve each scene category and enough
    # distinct sources for the requested shot budget when alternatives lack.
    unused=[item for item in scored if str(item[3].id) not in recent]
    categories={item[3].category for item in scored}
    if len(unused)>=limit and categories <= {item[3].category for item in unused}:
        scored=unused
    # Select complementary scenes before adding repeated categories. An
    # oversized pool is safe for the director to reduce, unlike a fixed 3 images.
    chosen=[];seen={}
    while scored and len(chosen)<limit:
        best=max(range(len(scored)),key=lambda i:(scored[i][0]-2*seen.get(scored[i][3].category,0),scored[i][5],scored[i][2],scored[i][4]))
        _,_,_,asset,_,_=scored.pop(best)
        chosen.append(asset);seen[asset.category]=seen.get(asset.category,0)+1
    return chosen
