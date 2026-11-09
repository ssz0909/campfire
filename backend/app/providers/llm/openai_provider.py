from __future__ import annotations

from typing import Any

import httpx
from app.config import settings

from app.services.model_settings import get_llm_settings
from app.providers.llm.base import LLMProvider

# Cost per 1M tokens in cents (approximate as of mid-2024)
_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 250, "output": 1000},
    "gpt-4o-mini": {"input": 15, "output": 60},
    "gpt-4-turbo": {"input": 1000, "output": 3000},
    "gpt-3.5-turbo": {"input": 50, "output": 150},
}


class OpenAIProvider(LLMProvider):
    """OpenAI chat completion provider via httpx."""

    def __init__(self, api_key: str | None = None, *, config: dict[str, str] | None = None) -> None:
        config = get_llm_settings() if config is None else config
        self._api_key = api_key or config["api_key"]
        if not self._api_key:
            raise ValueError("LLM_API_KEY is not configured")
        self._base_url = config["base_url"].strip().rstrip("/")
        self._model = config["model"].strip()
        if not self._base_url:
            raise ValueError("LLM_BASE_URL is not configured")

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> dict[str, Any]:
        model = model or self._model
        if not model:
            raise ValueError("LLM_MODEL is not configured")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS, connect=20)) as client:
            try:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise ValueError(f'大模型请求超时（等待上限{settings.LLM_TIMEOUT_SECONDS:g}秒），未取得本次交付结果；请核对中转服务后重新执行任务。') from exc
            except httpx.RequestError as exc:
                raise ValueError('大模型服务连接异常，未取得交付结果；请检查中转服务后重新执行任务') from exc
            if response.is_error:
                code = response.status_code
                if code in (408, 504, 524):
                    raise ValueError(f'大模型中转或上游响应超时（HTTP {code}），未取得本次交付结果；不代表模型 KEY 错误。请核对中转请求记录后再重新执行，避免重复计费。')
                if code in (401, 403):
                    raise ValueError(f'大模型鉴权或权限校验失败（HTTP {code}），请检查当前生效的模型 KEY、模型访问权限及中转配置')
                if code == 429:
                    raise ValueError('大模型接口限流或额度不足（HTTP 429），请核对中转额度与并发限制后重试')
                if code >= 500:
                    raise ValueError(f'大模型中转或上游服务异常（HTTP {code}），未取得本次交付结果；请检查中转服务状态')
                raise ValueError(f'大模型接口 HTTP {code}，请检查请求参数、模型名称及中转接口地址')
            data = response.json()

        choice = data["choices"][0]
        if not isinstance(choice.get('message', {}).get('content'), str):
            raise ValueError('大模型未返回文本交付，请检查模型能力及接口响应')
        usage = data.get("usage", {})
        return {
            "content": choice["message"]["content"],
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "model": data.get("model", model),
            "finish_reason": choice.get("finish_reason"),
        }

    def estimate_cost_cents(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> int:
        pricing = _PRICING.get(model, _PRICING["gpt-4o-mini"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return int(input_cost + output_cost)
