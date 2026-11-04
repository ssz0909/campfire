"""Tenant-scoped opening wordmarks, burned into finished videos without model calls."""
import math
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.company import Company


class VideoBrandingSettings(BaseModel):
    enabled: bool = False
    text: str = Field(default='', max_length=32)
    duration_seconds: float = Field(default=3, ge=1, le=8, allow_inf_nan=False)
    font: Literal['default', 'sans', 'serif'] = 'default'
    font_size_percent: float = Field(default=6.2, ge=2, le=15, allow_inf_nan=False)
    position: Literal['top_left', 'top_center', 'top_right', 'middle_left', 'middle_center',
        'middle_right', 'bottom_left', 'bottom_center', 'bottom_right'] = 'top_center'
    margin_x_percent: float = Field(default=8, ge=0, le=30, allow_inf_nan=False)
    margin_y_percent: float = Field(default=14, ge=0, le=30, allow_inf_nan=False)

    @field_validator('text')
    @classmethod
    def validate_text(cls, value):
        if any(unicodedata.category(char).startswith('C') or char in '\r\n\t' for char in value):
            raise ValueError('品牌名称不能包含换行或控制字符')
        return value.strip()

    @model_validator(mode='after')
    def enabled_requires_text(self):
        if self.enabled and not self.text:
            raise ValueError('开启视频片头时请填写品牌名称')
        return self


def set_video_branding(db, company_id, data):
    if data.enabled:
        try:
            brand_font_path(data.font)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    company = db.query(Company).filter_by(id=company_id, is_deleted=False).with_for_update().first()
    if not company:
        raise HTTPException(404, 'Company not found')
    company.business_goals = {**(company.business_goals or {}),
        'video_branding': data.model_dump(mode='json')}
    db.commit()
    db.refresh(company)
    return company


def brand_font_path(font='default'):
    from app.config import settings
    configured = settings.VIDEO_BRAND_FONT_PATH
    families = {
        'sans': ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc', '/System/Library/Fonts/PingFang.ttc'],
        'serif': ['/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',
            '/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc',
            '/System/Library/Fonts/Supplemental/Songti.ttc'],
    }
    if font not in ('default', *families):
        raise ValueError('不支持的品牌字体')
    candidates = families[font] if font != 'default' else ([configured] if configured else [
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/System/Library/Fonts/PingFang.ttc',
    ])
    for name in candidates:
        if Path(name).is_file():
            return name
    raise ValueError('所选中文字体未安装，请安装 Noto CJK 字体或选择默认字体')


def brand_font_options():
    options = []
    for value, label in [('default', '默认中文字体'), ('sans', '黑体（简洁现代）'), ('serif', '宋体（典雅人文）')]:
        try:
            brand_font_path(value)
            options.append({'value': value, 'label': label})
        except ValueError:
            pass
    return options


def wordmark_image(text, width, height, style=None):
    """Render text with Pillow so filter expressions never contain user input."""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(image)
    style = style or VideoBrandingSettings()
    font_path = brand_font_path(style.font)
    font_size = max(12, round(min(width * 0.062, height * 0.085) * style.font_size_percent / 6.2))
    padding = max(6, round(min(width, height) * 0.025))
    margin_x, margin_y = round(width * style.margin_x_percent / 100), round(height * style.margin_y_percent / 100)
    while True:
        # TTC files contain multiple faces: use regular Simplified Chinese,
        # avoiding Songti's Black face, which omits some traditional glyphs.
        face = 6 if Path(font_path).name == 'Songti.ttc' else 2 if Path(font_path).name.startswith('Noto') and 'CJK' in font_path else 0
        font = ImageFont.truetype(font_path, font_size, index=face)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        text_width, text_height = box[2] - box[0], box[3] - box[1]
        if text_width + padding * 2 <= width - 2 * margin_x and text_height + padding * 2 <= height - 2 * margin_y:
            break
        font_size -= 1
        if font_size < 10:
            raise ValueError('品牌名称过长，请缩短后重新制作视频')
    block_width, block_height = text_width + padding * 2, text_height + padding * 2
    vertical, horizontal = style.position.split('_')
    left = {'left': margin_x, 'center': round((width - block_width) / 2),
        'right': width - margin_x - block_width}[horizontal]
    top = {'top': margin_y, 'middle': round((height - block_height) / 2),
        'bottom': height - margin_y - block_height}[vertical]
    draw.rounded_rectangle((left, top, left + text_width + padding * 2, top + text_height + padding * 2),
        radius=padding, fill=(12, 22, 24, 155))
    draw.text((left + padding - box[0], top + padding - box[1]), text,
        font=font, fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(255, 255, 255, 255))
    return image


def add_opening_wordmark(content, text, duration_seconds=3, *, style=None):
    from app.services.media_processing import inspect_video
    if not text.strip() or not math.isfinite(duration_seconds) or not 1 <= duration_seconds <= 8:
        raise ValueError('视频片头需包含名称，展示时长为1至8秒')
    properties, _ = inspect_video(content)
    duration = properties['duration_seconds']
    visible = min(duration_seconds, duration)
    with tempfile.TemporaryDirectory(prefix='campfire-brand-') as directory:
        root = Path(directory)
        source, overlay, output = root / 'source.mp4', root / 'brand.png', root / 'output.mp4'
        source.write_bytes(content)
        wordmark_image(text, properties['width'], properties['height'], style).save(overlay)
        filters = (f'[1:v]format=rgba,fade=t=out:st={max(0, visible-0.35)}:d=0.35:alpha=1[brand];'
            f"[0:v][brand]overlay=0:0:enable='lt(t,{visible})':shortest=1,format=yuv420p[outv]")
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-filter_complex_threads', '1',
            '-i', str(source), '-loop', '1', '-framerate', '24', '-i', str(overlay),
            '-filter_complex', filters, '-map', '[outv]', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-threads', '2',
            '-c:a', 'copy', '-t', str(duration), '-movflags', '+faststart', str(output)],
            capture_output=True, check=True, timeout=max(240, duration * 10))
        return output.read_bytes()


def apply_opening_branding(db, project, content):
    company = db.query(Company).filter_by(id=project.company_id, is_deleted=False).first()
    config = VideoBrandingSettings.model_validate(
        (company.business_goals or {}).get('video_branding') or {}) if company else VideoBrandingSettings()
    if not config.enabled:
        return content, None
    result = add_opening_wordmark(content, config.text, config.duration_seconds, style=config)
    return result, {**config.model_dump(), 'version': 2}
