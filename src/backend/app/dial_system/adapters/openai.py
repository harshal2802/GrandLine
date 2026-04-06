from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI

from app.dial_system.adapters.base import ProviderAdapter
from app.schemas.dial_system import (
    CompletionRequest,
    CompletionResult,
    RateLimitStatus,
    TokenUsage,
)


class OpenAIAdapter(ProviderAdapter):
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=cast(Any, request.messages),
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return CompletionResult(
            content=content,
            provider="openai",
            model=response.model,
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=cast(Any, request.messages),
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content is not None:
                yield delta.content

    def check_rate_limit(self) -> RateLimitStatus:
        return RateLimitStatus(is_limited=False)
