"""Subject motion is independent of camera motion; never invent unseen people."""
import re

MOTION_VERSION = 'human-action-v1'

DIRECTOR_MOTION_RULES = '''
人物动态规则（优先于通用慢运镜建议）：画面已有人物时，镜头运动不能代替人物动作。每个人物镜头必须根据素材可见姿态、手中物品和场景设计一个明确动作，写入visual_description、generation_prompt或subshot.description；写清身体哪个部位移动、动作方向、起始与结束状态。
动作从前0.3秒开始，在成片实际保留时段内出现清楚可见的动作变化；开场人物镜头先用动作吸引注意。按可见条件选择转身回眸、抬手招呼、迈步走近、展示手中物品、自然坐下或与已有场景互动，不要求人物同时完成多个动作。相邻人物镜头动作避免雷同，不把所有人都设为挥手。
吸引力来自姿态变化、自然表情和场景互动，不靠夸张扭动、性暗示、危险动作或突然瞬移。面部与身体身份保持一致、四肢手指自然、脚步与地面接触合理；不添加图外的人物、道具或设施。静态海报、雕塑、照片中的人不当作真人驱动。
人物动作优先选固定机位或轻微跟随，避免仅小幅轻拉远、缩放照片、只眨眼呼吸或衣摆晃动。没有真人的素材仍展示真实环境动态，不凭空加入人物。'''


def people_visible(asset):
    """Use explicit vision metadata first; text is only a legacy fallback."""
    if isinstance(asset,dict):
        analysis=(asset.get('asset_metadata') or {}).get('vision_analysis') or {}
        explicit=asset.get('people_visible',analysis.get('people_visible'))
        text=' '.join(str(asset.get(k) or '') for k in ('description','name','source_description'))
    else:
        analysis=(asset.asset_metadata or {}).get('vision_analysis') or {}
        explicit=analysis.get('people_visible')
        text=' '.join(str(v or '') for v in (asset.name,asset.source_description))
    if isinstance(explicit,bool):return explicit
    text+=' '+str(analysis.get('visual_description') or '')
    if re.search(r'无人|没有人物|无人物|不含人物|雕塑|人像画|人物海报',text):return False
    return bool(re.search(r'人物|游客|顾客|客人|女士|男士|女孩|男孩|孩子|儿童|模特|一家人|亲子|person|people|woman|man walking',text,re.I))


def motion_prompt(asset=None, retained=5, index=0):
    known=people_visible(asset) if asset is not None else False
    lead='当前参考素材已识别到人物：' if known else '若当前参考图有真实人物（没有则忽略人物动作，绝不新增人物）：'
    hooks=('以自然转身或视线转向形成动作钩子','以一次清晰的手部或上身互动形成动作钩子','以姿态变化或符合场景的迈步形成动作钩子')
    return (f'\n【人物动作执行要求】{lead}人物必须主动运动，不能只有摄影机轻拉远或照片缩放。'
        f'结合原图姿态与脚本，{hooks[index%len(hooks)]}；只选符合画面条件的一个动作，不具备条件则选择自然转头及上身姿态变化。'
        f'前0.3秒内启动，在本镜保留的前{retained:g}秒内展示明确的开始—动作变化—结束姿态；不把动作放到被剪掉的后半段。'
        '脚本中的人物动作优先于普通慢运镜建议；固定或轻微跟随机位，保持动作主体在画幅内。'
        '静止摆拍、仅眨眼呼吸、仅发丝衣物晃动不满足要求。保持脸部身份、服装与肢体结构稳定，动作自然有吸引力。'
        '只驱动参考图里真实可见的人，照片/雕塑/海报中的人不复活；不新增人物或道具，不做危险或色情动作。')
