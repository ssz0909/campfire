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


def select_assets_for_video(db,company_id,goal,limit=3):
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
        scored.append((score,asset.created_at,asset))
    scored.sort(key=lambda x:(x[0],x[1]),reverse=True)
    if scored and scored[0][0]>0:scored=[item for item in scored if item[0]>0]
    return [item[2] for item in scored[:limit]]
