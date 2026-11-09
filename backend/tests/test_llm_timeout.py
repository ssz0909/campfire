import httpx
import pytest
from app.config import settings
from app.providers.llm.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_llm_timeout_is_configurable_and_error_is_useful(monkeypatch):
    captured=[]
    class Client:
        def __init__(self, **kwargs): captured.append(kwargs['timeout'])
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):raise httpx.ReadTimeout('')
    monkeypatch.setattr(settings,'LLM_TIMEOUT_SECONDS',300)
    monkeypatch.setattr(httpx,'AsyncClient',Client)
    provider=OpenAIProvider(config={'base_url':'https://example.test/v1','model':'test','api_key':'test-secret'})
    with pytest.raises(ValueError,match='大模型请求超时') as error:
        await provider.complete([{'role':'user','content':'script'}])
    assert '300秒' in str(error.value) and 'test-secret' not in str(error.value)
    assert captured[0].read==300 and captured[0].connect==20


@pytest.mark.asyncio
@pytest.mark.parametrize('code,expected', [(524,'响应超时'), (504,'响应超时'),
    (401,'鉴权或权限'), (403,'鉴权或权限'), (429,'限流或额度'), (503,'上游服务异常')])
async def test_http_errors_are_classified_without_retry_or_secret_leak(monkeypatch, code, expected):
    calls=[]
    class Client:
        def __init__(self, **kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):
            calls.append(args)
            return httpx.Response(code, text='private upstream details test-secret')
    monkeypatch.setattr(httpx,'AsyncClient',Client)
    provider=OpenAIProvider(config={'base_url':'https://example.test/v1','model':'test','api_key':'test-secret'})
    with pytest.raises(ValueError,match=expected) as error:
        await provider.complete([{'role':'user','content':'script'}])
    assert 'test-secret' not in str(error.value)
    assert 'private upstream' not in str(error.value)
    assert len(calls)==1
    if code==524:
        assert '避免重复计费' in str(error.value)
