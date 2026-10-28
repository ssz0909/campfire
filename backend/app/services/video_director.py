"""Validated editorial plans: edit timing is separate from billable model timing."""
import math
import re
from pydantic import BaseModel, Field


DIRECTOR_PROMPT = '''你是酒店短视频导演和剪辑师。先选材和设计节奏，再输出结构化分镜。
成片时长15至60秒，优先遵守 video_brief.target_duration_seconds，未指定默认30秒。
不要按一张图片固定5秒规划。每个成片镜头1.5至3.5秒，开头镜头不超过2秒；
用“视觉钩子→体验展开→细节证明→酒店记忆点/行动引导”的结构。镜头总时长必须等于目标时长。
素材是候选池，不必全部使用，不限3张。只从 data_sources.selected_assets 的ID中选择。
可重新排序，优先相关、清晰、适合目标画幅且场景互补的图片。先用不同素材，同图复用需不同景别/构图，
不能连续使用同一素材；仅有一张时明确素材不足并用不同裁切做有限变化，不编造新场景。
合理交替wide/medium/detail景别，避免所有镜头缓慢推进。每镜只安排一个克制运镜：固定、轻推、侧移或轻拉远。
按素材证实的主体写动作和光线，不新增人物、建筑或设施；建筑直线、泳池边界、床型等必须稳定。
输出video_script作为可审阅的整体脚本；另必须输出video_storyboard数组，每项为：
{source_asset_id, duration_seconds, purpose, framing, camera_movement, visual_description, generation_prompt, focal_x, focal_y}。
framing仅wide/medium/detail；focal_x/focal_y是0到1的裁切中心，无法确定时均为0.5。
每条generation_prompt仅描述当前一个连续镜头：主体、起止构图、唯一运镜、真实环境动态、光线和需保持的结构。
不得复制整片脚本到每镜，不要求视频模型生成字幕、酒店文字、结尾卡片或跨场景转场。
字幕/音效可在video_script中标注为后期建议，不声称已经实现。统一光线与色彩，优先直接切镜。
模型可能最少生成5秒，但成片只剪取每镜需要的短片段，不把模型生成时长当作成片镜头时长。'''


class DirectorShot(BaseModel):
    source_asset_id: str
    duration_seconds: float = Field(ge=1.5, le=3.5, allow_inf_nan=False)
    purpose: str = Field(min_length=1, max_length=200)
    framing: str = Field(pattern=r'^(wide|medium|detail)$')
    camera_movement: str = Field(min_length=1, max_length=160)
    visual_description: str = Field(min_length=1, max_length=1500)
    generation_prompt: str = Field(min_length=1, max_length=2500)
    focal_x: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    focal_y: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)


def target_duration(params=None, goal=''):
    value = (params or {}).get('target_duration_seconds')
    if value is None:
        match = re.search(r'(\d+(?:\.\d+)?)\s*(秒|[sS]\b|分钟|分|[mM][iI][nN]\b)', goal or '')
        value = float(match[1]) * (60 if match[2].lower() in ('分钟', '分', 'min') else 1) if match else 30
    value = float(value)
    if not math.isfinite(value) or not 15 <= value <= 60:
        raise ValueError('视频制作员的成片时长必须为15至60秒')
    return round(value)


def validate_plan(shots, assets, duration):
    allowed = {str(a['id']) for a in assets}
    if not 5 <= len(shots) <= 40:
        raise ValueError('分镜需包含5至40个短镜头，以覆盖15至60秒成片')
    plan = [DirectorShot.model_validate(s).model_dump() for s in shots]
    if abs(sum(s['duration_seconds'] for s in plan) - duration) > 0.05:
        raise ValueError('分镜时长之和与目标成片时长不一致，请重新生成脚本')
    if plan[0]['duration_seconds'] > 2:
        raise ValueError('开头钩子镜头不得超过2秒')
    if any(s['source_asset_id'] not in allowed for s in plan):
        raise ValueError('分镜引用了候选池之外的素材，已停止制作')
    for index, shot in enumerate(plan):
        if index and len(allowed) > 1 and shot['source_asset_id'] == plan[index-1]['source_asset_id']:
            raise ValueError('相邻镜头不得重复同一素材，请调整分镜')
        if index and shot['source_asset_id'] == plan[index-1]['source_asset_id'] and shot['framing'] == plan[index-1]['framing']:
            raise ValueError('同图连续复用必须改变景别，请调整分镜')
        shot.update(planning_version=2, shot_number=index+1, generation_duration_seconds=5)
    return plan


def fallback_plan(assets, duration=30):
    """Honest local draft with varied shots, used only without an LLM plan."""
    if not assets:
        raise ValueError('缺少已识别且可用的酒店图片，请上传素材后再制作')
    count = max(6, math.ceil(duration / 2.5))
    remaining = duration - 2
    plan = []
    for i in range(count):
        asset = assets[i % len(assets)]
        framing = ('wide', 'medium', 'detail')[(i + i//len(assets)) % 3]
        movement = ('固定机位，环境自然动态', '轻微侧移', '缓慢拉远')[i % 3]
        description = asset.get('description') or asset.get('name') or '参考图中的酒店环境'
        plan.append(dict(source_asset_id=str(asset['id']), duration_seconds=2 if i == 0 else round(remaining/(count-1), 3),
            purpose='开场钩子' if i == 0 else '酒店记忆点与咨询引导' if i == count-1 else '体验与细节',
            framing=framing, camera_movement=movement, visual_description=description,
            generation_prompt=f'单个连续镜头：{description}。{movement}，保持参考图中的空间、建筑直线和真实光线；不添加新人物或设施。'))
    plan[-1]['duration_seconds'] += duration - sum(s['duration_seconds'] for s in plan)
    return validate_plan(plan, assets, duration)
