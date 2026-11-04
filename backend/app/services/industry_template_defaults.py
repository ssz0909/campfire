"""First-release seed data; admin edits, not these defaults, drive runtime."""
GENERIC = {
    'name': '通用', 'description': '未选择行业或行业模板不可用时使用',
    'positioning': '根据企业实际业务、任务目标和素材事实组织短视频，不预设企业所属行业。',
    'themes': ['主体亮点', '使用或体验场景', '真实细节'],
    'material_hints': ['优先相关、清晰且场景互补的素材', '缺少资料或素材支持的内容直接省略，不推测补全'],
    'terminology': [], 'selection_keywords': [],
    'forbidden_expressions': ['无依据的价格、优惠、效果保证、设施和服务承诺', '无依据的排名、热度、销量及绝对化宣传'],
    'publish_tone': '自然、具体、有画面感，避免堆砌宣传词',
    'copy_guidance': '正文介绍本条成片实际展示的企业或品牌亮点，不把内部制作要求当作宣传文案。',
}
TRAVEL = {
    **GENERIC, 'name': '酒旅', 'description': '住宿、景区及周边打卡体验，共用一份按事实选取内容的模板',
    'positioning': '以真实景观、空间氛围和打卡体验吸引出游人群；住宿与景区不强制拆分。',
    'themes': ['景观与氛围', '周边探索', '特色体验', '住宿空间（仅业务资料支持时）'],
    'material_hints': ['根据任务选择景观、周边、空间及细节，不要求所有模块都出现',
                       '客房、入住与住宿服务仅在企业资料支持且有可用素材时展示',
                       '景区不得套用入住、客房或酒店预订表达；没有客房图片也不代表企业没有住宿业务',
                       '周边景点、距离及路线需要真实资料支持；素材不足明确提示，不编造打卡点',
                       '同类景观或泳池不要占满整片，兼顾画面差异与体验节奏'],
    'terminology': ['打卡', '探索', '放松', '出游', '体验'],
    'selection_keywords': ['景观', '风景', '绿意', '夜景', '周边', '空间', '客房', '泳池', '特色体验'],
    'forbidden_expressions': GENERIC['forbidden_expressions'] + ['未经证实的网红热度、恒温泳池、天然温泉、星级和地理距离'],
    'copy_guidance': '结合企业名称、成片景观和体验亮点组织文案；不默认要求订房或购票，遵循通用关注咨询引导。',
}
LEGACY_INDUSTRIES = {'ecommerce':'电商', 'retail':'零售', 'technology':'科技', 'healthcare':'医疗健康',
                     'finance':'金融', 'education':'教育', 'media':'传媒娱乐', 'real_estate':'房地产', 'other':'其他'}
SEEDS = {'generic': GENERIC, 'travel': TRAVEL,
         **{code: {**GENERIC, 'name': name, 'description': '暂使用通用创作规则，可由管理员完善行业模板'}
            for code, name in LEGACY_INDUSTRIES.items()}}
