from urllib.parse import quote
import re
import httpx
from app.config import settings
from app.services.model_settings import get_video_settings
from app.providers.video.base import VideoProvider, VideoGenerationResult

class RelayVideoRequestError(ValueError):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code

class RelayVideoProvider(VideoProvider):
    def __init__(self):
        config = get_video_settings()
        self.url = config['base_url'].strip().rstrip('/')
        self.model = config['model'].strip()
        self.key = config['api_key'].strip()
        self.status_url = settings.VIDEO_STATUS_URL.strip()
        if not all((self.url, self.model, self.key)):
            raise ValueError('请在管理后台配置视频模型，或设置 VIDEO_BASE_URL、VIDEO_MODEL、VIDEO_API_KEY')
        if not self.url.endswith('/video/generations'):
            self.url += '/video/generations'

    @staticmethod
    def parse(data, fallback=None):
        item = data.get('data', data)
        if isinstance(item, list): item = item[0] if item else {}
        if not isinstance(item, dict): raise ValueError('视频响应格式不支持')
        error = item.get('error') or item.get('fail_reason')
        if isinstance(error, dict): error = error.get('message') or '视频服务错误'
        output = item.get('video_url') or item.get('output_url') or item.get('result_url') or item.get('url')
        nested = item.get('data') if isinstance(item.get('data'), dict) else {}
        nested_output = nested.get('output') if isinstance(nested.get('output'), dict) else {}
        output = output or nested_output.get('video_url') or nested_output.get('url')
        if isinstance(item.get('output'), dict):
            output = output or item['output'].get('video_url') or item['output'].get('url')
        raw = str(item.get('status') or item.get('state') or nested_output.get('task_status') or '').lower()
        status = {'succeeded':'completed','success':'completed','done':'completed','successfully':'completed','error':'failed',
                  'cancelled':'failed','canceled':'failed','queued':'processing','pending':'processing',
                  'running':'processing','in_progress':'processing','submitted':'processing',
                  'not_start':'processing','not_started':'processing','waiting':'processing',
                  'failure':'failed'}.get(raw, raw)
        status = status or ('failed' if error else ('completed' if output else 'processing'))
        # Relay's numeric database ID and nested provider ID are not polling IDs.
        task_id = item.get('task_id') or item.get('taskId') or fallback or item.get('id')
        if not task_id and status != 'completed': raise ValueError('视频接口未返回任务 ID')
        if status not in {'completed','processing','failed'}: raise ValueError('未知视频任务状态')
        if status == 'completed' and not output: raise ValueError('视频已完成但没有结果地址')
        metadata = item.get('metadata') if isinstance(item.get('metadata'),dict) else {}
        return VideoGenerationResult(provider_task_id=str(task_id or 'direct'),status=status,output_url=output,
            error=error, duration_seconds=metadata.get('duration'), cost_cents=item.get('cost_cents'))

    async def request(self, method, url, **kwargs):
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.request(method,url,headers={'Authorization':f'Bearer {self.key}'},**kwargs)
        if response.is_error:
            detail = ''
            try:
                data = response.json()
                if isinstance(data, dict):
                    error = data.get('error') or data
                    if isinstance(error, dict):
                        detail = error.get('message') or error.get('detail') or ''
                    elif isinstance(error, str):
                        detail = error
            except ValueError:
                pass
            if isinstance(detail, str) and detail:
                detail = detail.replace(self.key, '[已隐藏密钥]')
                detail = re.sub(r'https?://\S+', '[已隐藏链接]', detail)
                detail = re.sub(r'(?i)(?:bearer\s+|sk-)[\w.\-]+', '[已隐藏密钥]', detail)
                detail = '：' + ' '.join(detail.split())[:400]
            else:
                detail = '，服务未返回可识别的错误详情'
            raise RelayVideoRequestError(f'视频接口 HTTP {response.status_code}{detail}', response.status_code)
        return response.json()

    async def submit_generation(self, request):
        prompt = request.prompt
        if request.style:
            prompt += f'\n风格：{request.style}'
        prompt += f'\n画面比例：{request.aspect_ratio}'
        duration = request.duration_seconds
        if float(duration).is_integer():
            duration = int(duration)
        metadata = {'parameters': {'resolution': request.resolution,
                                  'duration': duration, 'audio': request.audio}}
        if request.reference_image_url:
            metadata['input'] = {'media': [{'type': 'first_frame', 'url': request.reference_image_url}]}
        return self.parse(await self.request('POST', self.url, json={
            'model': self.model, 'prompt': prompt, 'metadata': metadata,
        }))

    async def get_task_status(self, provider_task_id):
        template = self.status_url or self.url + '/{task_id}'
        return self.parse(await self.request('GET',template.replace('{task_id}',quote(provider_task_id,safe=''))),provider_task_id)

    async def cancel_task(self, provider_task_id):
        return False
