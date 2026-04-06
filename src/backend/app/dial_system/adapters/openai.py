from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from openai import APIError, AsyncOpenAI, RateLimitError

from app.dial_system.adapters.base import ProviderAdapter, ProviderError
from app.schemas.dial_system import (
    CompletionRequest,
    CompletionResult,
    RateLimitStatus,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class OpenAIAdapter(ProviderAdapter):
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model
        self._rate_limited = False

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=cast(Any, request.messages),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except RateLimitError as exc:
            self._rate_limited = True
            raise ProviderError(f"OpenAI rate limited: {exc}") from exc
        except APIError as exc:
            raise ProviderError(f"OpenAI API error: {exc}") from exc

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
        try:
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
        except RateLimitError as exc:
            self._rate_limited = True
            raise ProviderError(f"OpenAI rate limited: {exc}") from exc
        except APIError as exc:
            raise ProviderError(f"OpenAI API error: {exc}") from exc

    def check_rate_limit(self) -> RateLimitStatus:
        return RateLimitStatus(is_limited=self._rate_limited)
