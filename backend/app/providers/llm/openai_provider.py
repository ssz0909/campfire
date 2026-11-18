from __future__ import annotations

from typing import Any
import asyncio

import httpx
from app.config import settings

from app.services.model_settings import get_llm_settings
from app.providers.llm.base import LLMProvider


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
        company_id = kwargs.pop('billing_company_id', None)
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
        from app.services import llm_metering
        billing_key = llm_metering.begin(company_id, messages, max_tokens) if company_id else None
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS, connect=20)) as client:
            try:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                llm_metering.unknown(billing_key)
                raise ValueError(f'大模型请求超时（等待上限{settings.LLM_TIMEOUT_SECONDS:g}秒），未取得本次交付结果；请核对中转服务后重新执行任务。') from exc
            except asyncio.CancelledError:
                llm_metering.unknown(billing_key)
                raise
            except httpx.RequestError as exc:
                llm_metering.unknown(billing_key)
                raise ValueError('大模型服务连接异常，未取得交付结果；请检查中转服务后重新执行任务') from exc
            if response.is_error:
                code = response.status_code
                (llm_metering.release if code in (400,401,403,404,405,413,415,422,429) else llm_metering.unknown)(billing_key)
                if code in (408, 504, 524):
                    raise ValueError(f'大模型中转或上游响应超时（HTTP {code}），未取得本次交付结果；不代表模型 KEY 错误。请核对中转请求记录后再重新执行，避免重复计费。')
                if code in (401, 403):
                    raise ValueError(f'大模型鉴权或权限校验失败（HTTP {code}），请检查当前生效的模型 KEY、模型访问权限及中转配置')
                if code == 429:
                    raise ValueError('大模型接口限流或额度不足（HTTP 429），请核对中转额度与并发限制后重试')
                if code >= 500:
                    raise ValueError(f'大模型中转或上游服务异常（HTTP {code}），未取得本次交付结果；请检查中转服务状态')
                raise ValueError(f'大模型接口 HTTP {code}，请检查请求参数、模型名称及中转接口地址')
            try:
                data = response.json()
            except ValueError:
                llm_metering.unknown(billing_key)
                raise ValueError('大模型响应无效，本次用量待核对') from None
            llm_metering.settle(billing_key, data.get('usage'))

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
        from math import ceil
        from app.services.model_settings import SessionLocal
        from app.services.billing_catalog import get_catalog
        with SessionLocal() as db:
            rates = get_catalog(db)
        return ceil((input_tokens * rates['llm_input_cost_fen_per_million'] +
                     output_tokens * rates['llm_output_cost_fen_per_million']) / 1_000_000)
