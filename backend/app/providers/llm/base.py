from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Send a chat completion request.
        Returns dict with keys: content, input_tokens, output_tokens, model.
        """
        ...

    @abstractmethod
    def estimate_cost_cents(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> int:
        """Estimate cost in cents for a completion."""
        ...
