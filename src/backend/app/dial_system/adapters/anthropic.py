from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from anthropic import APIError, AsyncAnthropic, RateLimitError

from app.dial_system.adapters.base import ProviderAdapter, ProviderError
from app.schemas.dial_system import (
    CompletionRequest,
    CompletionResult,
    RateLimitStatus,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class AnthropicAdapter(ProviderAdapter):
    def __init__(self, client: AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model
        self._rate_limited = False

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            response = await self._client.messages.create(
                model=self._model,
                messages=cast(Any, request.messages),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except RateLimitError as exc:
            self._rate_limited = True
            raise ProviderError(f"Anthropic rate limited: {exc}") from exc
        except APIError as exc:
            raise ProviderError(f"Anthropic API error: {exc}") from exc

        text_block = response.content[0]
        content: str = text_block.text  # type: ignore[union-attr]
        usage = response.usage
        return CompletionResult(
            content=content,
            provider="anthropic",
            model=response.model,
            usage=TokenUsage(
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
            ),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        try:
            async with self._client.messages.stream(
                model=self._model,
                messages=cast(Any, request.messages),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ) as s:
                async for event in s:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield event.delta.text
        except RateLimitError as exc:
            self._rate_limited = True
            raise ProviderError(f"Anthropic rate limited: {exc}") from exc
        except APIError as exc:
            raise ProviderError(f"Anthropic API error: {exc}") from exc

    def check_rate_limit(self) -> RateLimitStatus:
        return RateLimitStatus(is_limited=self._rate_limited)
