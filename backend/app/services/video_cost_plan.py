"""One reference scene, one 5-second generation, up to two related views.

The relay currently defines only first_frame. Never pretend that a second
unsubmitted scene is a supplied reference, or invent a multi-image API type.
"""
import math
from typing import Literal

from pydantic import BaseModel, Field


COST_DIRECTOR_PROMPT = '''你是通用短视频导演，按企业档案和任务主题制作，当前选择成本优先。成片时长遵守video_brief.target_duration_seconds（15至60秒）。
每次模型调用生成5秒，video_storyboard必须恰好包含ceil(目标时长/5)个片段，按顺序拼接。
每段duration_seconds为5，最后一段只保留剩余秒数。每段内部设计1至2个相关分镜subshots，时长之和等于该段保留时长。
每段只从data_sources.selected_assets选一张首帧，不同片段不得重复使用同一素材。当前接口只提交这张图，不能假设第二张图片已被提交。
内部两镜应为同一参考图中可见的整体与细节或不同景别，保持空间、光线和运动一致，不能变出另一处设施。
按视觉钩子→体验展开→主题或品牌记忆点安排整片节奏，优先相关且互补的素材，避免全片重复推镜。
每项结构：{source_asset_id,duration_seconds,purpose,framing,camera_movement,visual_description,focal_x,focal_y,subshots:[{duration_seconds,description}]}。
framing仅wide/medium/detail，focal_x和focal_y为0至1的裁切中心；保证所有内部镜头的主体在裁切后仍可见。
每个subshot.description写具体主体、构图、动作和起止景别，不复制整片脚本。两个分镜可在段内直接切镜；不支持时退化为自然连续运镜。
video_script使用字符串逐段描述时间轴及内部镜头，不要求模型生成文字、品牌或字幕，不虚构人物、设施和优惠。'''


class CostSubshot(BaseModel):
    duration_seconds: float = Field(gt=0, le=5, allow_inf_nan=False)
    description: str = Field(min_length=1, max_length=2000)


class CostShot(BaseModel):
    source_asset_id: str
    duration_seconds: float = Field(gt=0, le=5, allow_inf_nan=False)
    purpose: str = Field(min_length=1, max_length=200)
    framing: Literal['wide', 'medium', 'detail'] = 'wide'
    camera_movement: str = Field(min_length=1, max_length=160)
    visual_description: str = Field(min_length=1, max_length=1500)
    focal_x: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    focal_y: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    subshots: list[CostSubshot] = Field(min_length=1, max_length=2)


def cost_plan(assets, duration=30):
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 15 <= duration <= 60:
        raise ValueError('成本优先成片时长必须为15至60秒')
    count = math.ceil(duration / 5)
    unique = list({str(a['id']): a for a in assets}.values())
    if len(unique) < count:
        raise ValueError(f'成本优先制作{duration}秒视频至少需要{count}张不同场景图片，不会循环补足')
    plan = []
    for index, asset in enumerate(unique[:count]):
        seconds = min(5, duration - index * 5)
        description = asset.get('description') or asset.get('name') or '参考图中的真实主体与场景'
        views = ([{'duration_seconds': 2, 'description': f'展示{description}的整体构图，克制侧移'},
                  {'duration_seconds': seconds - 2, 'description': '切换至同一场景中已可见主体的中景或细节，保持空间和光线一致'}]
                 if seconds >= 4 else [{'duration_seconds': seconds, 'description': f'{description}，自然连续运镜'}])
        plan.append({'planning_version': 3, 'shot_number': index + 1, 'generation_duration_seconds': 5,
            'duration_seconds': seconds, 'source_asset_id': str(asset['id']), 'framing': 'wide',
            'focal_x': 0.5, 'focal_y': 0.5, 'purpose': '主题内容展开', 'camera_movement': '轻侧移后切同场景细节',
            'visual_description': description, 'subshots': views, 'transition_out': 'cut',
            'generation_prompt': cost_prompt(views, seconds)})
    return plan


def cost_prompt(views, retained):
    start = 0
    lines = ['生成一个5秒动态视频片段，使用当前唯一首帧参考图。片段内按以下时间轴制作1至2个相关镜头：']
    for view in views:
        end = start + view['duration_seconds']
        lines.append(f'{start:g}至{end:g}秒：{view["description"]}。')
        start = end
    lines.append(f'只保留前{retained:g}秒；镜头衔接在保留区间内完成。保持参考场景真实结构、相同光线和运动连续性。'
                 '只能切换当前图中可见主体的景别，不生成未提供的另一场景、不变形建筑，不添加人物、设施、文字或标志。'
                 '如不支持内部切镜，保持同场景自然运镜，不生成拼图、照片轮播或幻灯片。')
    return '\n'.join(lines)


def validate_cost_plan(plan, assets, duration):
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 15 <= duration <= 60:
        raise ValueError('成本优先成片时长必须为15至60秒')
    if not isinstance(plan, list):
        raise ValueError('成本优先分镜必须为数组')
    allowed = {str(a['id']) for a in assets}
    if len(plan) != math.ceil(duration / 5):
        raise ValueError('成本优先片段数量必须等于成片时长除以5后向上取整')
    used = set()
    validated = []
    for index, raw in enumerate(plan):
        shot = CostShot.model_validate(raw).model_dump()
        source = shot.get('source_asset_id')
        if source not in allowed or source in used:
            raise ValueError('成本优先片段引用素材缺失或重复')
        used.add(source)
        seconds = min(5, duration - index * 5)
        if abs(shot['duration_seconds'] - seconds) > 0.01:
            raise ValueError('成本优先片段时长不正确')
        views = shot.get('subshots') or []
        if not 1 <= len(views) <= 2 or any(not isinstance(v.get('duration_seconds'), (int, float)) or v['duration_seconds'] <= 0 for v in views):
            raise ValueError('每个成本优先片段需包含1至2个有效分镜')
        if abs(sum(v['duration_seconds'] for v in views) - seconds) > 0.01:
            raise ValueError('片段内分镜总时长不一致')
        validated.append({**raw, **shot, 'planning_version': 3, 'shot_number': index + 1,
            'generation_duration_seconds': 5, 'duration_seconds': seconds, 'transition_out': 'cut',
            'generation_prompt': cost_prompt(views, seconds)})
    return validated
