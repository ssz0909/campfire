"""Validated editorial plans: edit timing is separate from billable model timing."""
import math
import re
from typing import Literal
from pydantic import BaseModel, Field


DIRECTOR_PROMPT = '''你是酒店短视频导演和剪辑师。先选材和设计节奏，再输出结构化分镜。
成片时长15至60秒，优先遵守 video_brief.target_duration_seconds，未指定默认30秒。
不要按一张图片固定5秒规划。每个成片镜头1.5至3.5秒，开头镜头不超过2秒；
用“视觉钩子→体验展开→细节证明→酒店记忆点/行动引导”的结构。镜头总时长必须等于目标时长。
素材是候选池，不必全部使用，不限3张。只从 data_sources.selected_assets 的ID中选择。
每张素材在整片最多使用一次，改变裁切或运镜也不能重复引用。优先覆盖目标涉及的不同场景，不用同类泳池画面填满整片。素材不足时明确说明缺口，不得循环补足时长。
可重新排序，优先相关、清晰、适合目标画幅且场景互补的图片，在不同素材间安排不同景别与构图。
整片不能重复使用同一素材；数量不足时提示补充素材，不编造新场景。
合理交替wide/medium/detail景别，避免所有镜头缓慢推进。每镜只安排一个克制运镜：固定、轻推、侧移或轻拉远。
按素材证实的主体写动作和光线，不新增人物、建筑或设施；建筑直线、泳池边界、床型等必须稳定。
输出video_script作为可审阅的整体脚本；另必须输出video_storyboard数组，每项为：
{source_asset_id, duration_seconds, purpose, framing, camera_movement, visual_description, generation_prompt, focal_x, focal_y, opening_frame, closing_frame, transition_out, transition_duration_seconds, transition_notes}。
framing仅wide/medium/detail；focal_x/focal_y是0到1的裁切中心，无法确定时均为0.5。
每条generation_prompt仅描述当前一个连续镜头：主体、起止构图、唯一运镜、真实环境动态、光线和需保持的结构。
不得复制整片脚本到每镜，不要求视频模型生成字幕、酒店文字或结尾卡片。
必须逐镜设计衔接：opening_frame和closing_frame写真实的起止构图、主体位置、运镜方向和光线；相邻镜头运动方向、视觉重心尽量相接。
transition_out仅cut（直接切镜）、match_cut（构图/动作匹配）、dissolve（短叠化）、fade（淡出接淡入）。
transition_duration_seconds：cut/match_cut为0；dissolve/fade建议0.2至0.5秒，不得超过0.6秒。最后一镜transition_out为cut、时长0，不虚构下一场景。
transition_notes写明与下一镜头如何衔接；同场景优先cut或match_cut，跨场景可短叠化，昼夜跨度可淡化，不能每镜都使用特效。
generation_prompt必须包含当前镜头起止构图及其负责的转场动作；转场放在成片实际保留时段内，不放到模型5秒片段将被剪掉的末尾。
当前每次仅提交一张当前场景参考图、独立生成片段：不要要求生成未提供的下一张参考图场景。
淡出可在当前镜头末端实现，下一镜头的淡入在下一条prompt中描述；叠化和匹配切换写清相邻构图、光线与动作衔接意图，模型不支持时仅保留自然起止构图，不把建筑变形为其他场景。
video_script逐镜标注转场类型、时长及衔接画面，明确是生成要求而非已执行特效；字幕/音效仍为后期建议。
模型可能最少生成5秒，但成片只剪取每镜需要的短片段，不把模型生成时长当作成片镜头时长。'''


class DirectorShot(BaseModel):
    source_asset_id: str
    duration_seconds: float = Field(ge=1.5, le=3.5, allow_inf_nan=False)
    purpose: str = Field(min_length=1, max_length=200)
    framing: str = Field(pattern=r'^(wide|medium|detail)$')
    camera_movement: str = Field(min_length=1, max_length=160)
    visual_description: str = Field(min_length=1, max_length=1500)
    generation_prompt: str = Field(min_length=1, max_length=2500)
    opening_frame: str = Field(default='', max_length=600)
    closing_frame: str = Field(default='', max_length=600)
    transition_out: Literal['cut', 'match_cut', 'dissolve', 'fade'] = 'cut'
    transition_duration_seconds: float = Field(default=0, ge=0, le=0.6, allow_inf_nan=False)
    transition_notes: str = Field(default='', max_length=1000)
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


def validate_plan(shots, assets, duration, *, allow_legacy_reuse=False):
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
    from collections import Counter
    usage = Counter(s['source_asset_id'] for s in plan)
    if not allow_legacy_reuse and max(usage.values()) > 1:
        raise ValueError('分镜重复引用同一素材，每张图片只能使用一次，请重新选材或补充素材')
    for index, shot in enumerate(plan):
        if shot['transition_out'] in ('cut', 'match_cut') and shot['transition_duration_seconds'] != 0:
            raise ValueError('直接切镜或匹配切换的转场时长必须为0')
        if shot['transition_out'] in ('dissolve', 'fade') and shot['transition_duration_seconds'] <= 0:
            raise ValueError('叠化或淡化必须指定大于0的转场时长')
        if index == len(plan)-1 and shot['transition_out'] != 'cut':
            raise ValueError('最后一镜没有下一镜头，转场必须为cut')
        if index and len(allowed) > 1 and shot['source_asset_id'] == plan[index-1]['source_asset_id']:
            raise ValueError('相邻镜头不得重复同一素材，请调整分镜')
        if index and shot['source_asset_id'] == plan[index-1]['source_asset_id'] and shot['framing'] == plan[index-1]['framing']:
            raise ValueError('同图连续复用必须改变景别，请调整分镜')
        shot.update(planning_version=2, shot_number=index+1, generation_duration_seconds=5)
    return plan


def shot_generation_prompt(plan, index):
    """Carry both sides of the editorial boundary into independent requests."""
    shot = plan[index]
    previous = plan[index-1] if index else None
    following = plan[index+1] if index+1 < len(plan) else None
    labels = {'cut':'直接切镜', 'match_cut':'构图/动作匹配切换', 'dissolve':'短叠化', 'fade':'淡出接淡入'}
    parts = [shot['generation_prompt']]
    if shot.get('opening_frame'):
        parts.append('起始画面：' + shot['opening_frame'])
    if shot.get('closing_frame'):
        parts.append('结束画面：' + shot['closing_frame'])
    if previous and previous.get('transition_out', 'cut') != 'cut':
        parts.append(f"承接上一镜：{labels[previous['transition_out']]}，{previous.get('transition_duration_seconds', 0)}秒；"
                     f"上一镜结束构图：{previous.get('closing_frame', '')}；衔接意图：{previous.get('transition_notes', '')}。"
                     '仅用于匹配本镜开场构图、光线和运动，不重新生成上一场景。')
        if previous['transition_out'] == 'fade':
            parts.append('本镜从起始即完成短淡入，然后恢复正常亮度。')
    if following and shot.get('transition_out', 'cut') != 'cut':
        parts.append(f"出镜衔接：{labels[shot['transition_out']]}，{shot.get('transition_duration_seconds', 0)}秒；"
                     f"衔接意图：{shot.get('transition_notes', '')}；下一镜起始构图参考：{following.get('opening_frame', '')}。"
                     '只调整当前参考场景的结束画面，不生成下一场景或形变建筑。')
        if shot['transition_out'] == 'fade':
            parts.append('在本镜实际保留时段结束前完成短淡出。')
        elif shot['transition_out'] == 'dissolve':
            parts.append('若模型支持叠化则按衔接意图处理；缺少下一场景参考或不支持时保持自然柔和收尾，不虚构叠化目标。')
    parts.append(f"成片只保留生成片段前{shot['duration_seconds']}秒，所有起止构图和转场动作必须安排在此时段内；后续时长保持稳定。")
    return '\n'.join(parts)


def fallback_plan(assets, duration=30):
    """Honest local draft with varied shots, used only without an LLM plan."""
    if not assets:
        raise ValueError('缺少已识别且可用的酒店图片，请上传素材后再制作')
    minimum = max(5, 1 + math.ceil((duration - 2) / 3.5))
    if len(assets) < minimum:
        raise ValueError(f'制作{duration}秒且不重复素材至少需要{minimum}张不同图片，当前仅{len(assets)}张，请补充素材')
    count = min(len(assets), max(6, math.ceil(duration / 2.5)))
    remaining = duration - 2
    plan = []
    for i in range(count):
        asset = assets[i]
        framing = ('wide', 'medium', 'detail')[(i + i//len(assets)) % 3]
        movement = ('固定机位，环境自然动态', '轻微侧移', '缓慢拉远')[i % 3]
        description = asset.get('description') or asset.get('name') or '参考图中的酒店环境'
        plan.append(dict(source_asset_id=str(asset['id']), duration_seconds=2 if i == 0 else round(remaining/(count-1), 3),
            purpose='开场钩子' if i == 0 else '酒店记忆点与咨询引导' if i == count-1 else '体验与细节',
            framing=framing, camera_movement=movement, visual_description=description,
            generation_prompt=f'单个连续镜头：{description}。{movement}，保持参考图中的空间、建筑直线和真实光线；不添加新人物或设施。'))
    plan[-1]['duration_seconds'] += duration - sum(s['duration_seconds'] for s in plan)
    return validate_plan(plan, assets, duration)
