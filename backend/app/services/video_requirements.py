"""Explicit user constraints are eligibility rules, not keyword bonuses."""
import re

from app.services.video_motion import people_visible


def requires_people_opening(text):
    # Work per clause so a later request for no captions cannot negate people.
    for clause in re.split(r'[，,。；;\n]', text or ''):
        if re.search(r'不(?:要|用|需(?:要)?)|无需|禁止|避免', clause):
            continue
        if re.search(r'人物|真人|人像|模特|人物?出镜|人物?入镜|人物?入境', clause) and re.search(r'开头|开场|首镜|第一(?:个)?镜头|起始', clause):
            return True
    return False


def task_visual_text(task):
    params = task.input_params or {}
    parts = [params.get('goal'), params.get('execution_goal'), task.description, task.title]
    return '\n'.join(str(part) for part in parts if part)


def mark_opening_candidates(assets, required):
    if not required:
        return assets
    marked = [{**asset, 'required_people_opening': True} for asset in assets]
    if not any(people_visible(asset) for asset in marked):
        raise ValueError('任务要求人物出镜开头，但没有识别到符合条件的真人图片，请补充素材或重新识别；不会用风景替代人物开场')
    return marked


def validate_opening(plan, assets):
    if not any(asset.get('required_people_opening') for asset in assets):
        return
    by_id = {str(asset['id']): asset for asset in assets}
    if not plan or not people_visible(by_id.get(str(plan[0].get('source_asset_id')), {})):
        raise ValueError('分镜首镜不符合人物出镜开头要求，请重新规划；未提交视频生成')


def opening_first(assets):
    if not any(asset.get('required_people_opening') for asset in assets):
        return assets
    first = next((index for index, asset in enumerate(assets) if people_visible(asset)), None)
    if first is None:
        raise ValueError('缺少符合人物开场要求的真人图片，请补充或重新识别素材')
    return [assets[first], *assets[:first], *assets[first + 1:]]
