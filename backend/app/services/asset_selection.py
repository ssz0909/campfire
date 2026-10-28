"""Tenant-scoped, deterministic topic matching for video source images."""
from app.models.asset import Asset

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


def select_assets_for_video(db,company_id,goal,limit=40):
    assets=db.query(Asset).filter(Asset.company_id==company_id,Asset.asset_type=='image',
        Asset.is_deleted==False,Asset.is_available==True,Asset.processing_status=='ready').all()
    if not assets:return []
    topic=(goal or '').casefold()
    scored=[]
    for asset in assets:
        analysis=(asset.asset_metadata or {}).get('vision_analysis') or {}
        if analysis.get('status')!='completed' and not (asset.asset_metadata or {}).get('manual_classification'):continue
        score=sum(1 for value in (asset.tags or []) if value and str(value).casefold() in topic)
        score+=sum(2 for term in CATEGORY_TERMS.get(asset.category,()) if term in topic)
        score+=sum(1 for value in [analysis.get('caption',''),asset.source_description or ''] if value and value.casefold() in topic)
        # Avoid tiny images and reward portrait-ready sources. Keep unmeasured
        # assets usable but rank measured, adequate images ahead of them.
        width,height=asset.width or 0,asset.height or 0
        if width and height and min(width,height)<320:continue
        quality=(2 if min(width,height)>=720 else 0)+(1 if height>width else 0)
        scored.append((score,quality,asset.created_at,asset))
    scored.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True)
    if scored and scored[0][0]>0:scored=[item for item in scored if item[0]>0]
    # Select complementary scenes before adding repeated categories. An
    # oversized pool is safe for the director to reduce, unlike a fixed 3 images.
    chosen=[];seen={}
    while scored and len(chosen)<limit:
        best=max(range(len(scored)),key=lambda i:(scored[i][0]-2*seen.get(scored[i][3].category,0),scored[i][1],scored[i][2]))
        _,_,_,asset=scored.pop(best)
        chosen.append(asset);seen[asset.category]=seen.get(asset.category,0)+1
    return chosen
