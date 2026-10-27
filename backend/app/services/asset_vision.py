"""Vision metadata for uploaded hotel images using the configured LLM relay."""
import asyncio
import base64
import io
import json
from datetime import datetime, timezone

from PIL import Image
from app.config import settings
from app.providers.llm.openai_provider import OpenAIProvider

CATEGORIES = ('exterior','lobby','guest_room','bathroom','restaurant','breakfast','amenities','pool','meeting_room','staff','landscape','other')


def analyze_image(content: bytes, mime_type: str) -> dict:
    if not all((settings.LLM_BASE_URL,settings.LLM_MODEL,settings.LLM_API_KEY)):
        return {'status':'skipped','detail':'未配置完整的视觉模型参数，已保留原素材'}
    image=Image.open(io.BytesIO(content)).convert('RGB')
    image.thumbnail((1024,1024))
    buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=82,optimize=True)
    data='data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')
    messages=[
        {'role':'system','content':'你是酒店素材库视觉标注员。只描述画面可见事实，不推测酒店名称、星级、价格、服务承诺或版权。将图片归入预设类别之一，中文输出严格 JSON：{"category":"...","tags":["..."],"caption":"...","visual_description":"...","people_visible":false}. tags 为 3 至 8 个简洁中文主题词。category 必须是这些值之一：'+','.join(CATEGORIES)},
        {'role':'user','content':[{'type':'text','text':'识别这张酒店运营素材，供按主题检索和视频选材。'},
                                  {'type':'image_url','image_url':{'url':data,'detail':'low'}}]},
    ]
    response=asyncio.run(OpenAIProvider().complete(messages,max_tokens=500,temperature=0.1))
    raw=response['content'].strip()
    if raw.startswith('```'):
        raw=raw.split('\n',1)[-1].strip()
        if raw.endswith('```'):raw=raw[:-3].strip()
    result=json.loads(raw)
    category=result.get('category')
    if category not in CATEGORIES:category='other'
    tags=[]
    for tag in result.get('tags',[]):
        value=str(tag).strip()[:40]
        if value and value not in tags:tags.append(value)
    if not tags:tags=['待补充标签']
    return {'status':'completed','category':category,'tags':tags[:8],
            'caption':str(result.get('caption',''))[:500],
            'visual_description':str(result.get('visual_description',''))[:2000],
            'people_visible':bool(result.get('people_visible',False)),
            'model':response.get('model'),'analyzed_at':datetime.now(timezone.utc).isoformat(),
            'input_tokens':response.get('input_tokens',0),'output_tokens':response.get('output_tokens',0)}

