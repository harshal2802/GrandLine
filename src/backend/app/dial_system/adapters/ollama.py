from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.dial_system.adapters.base import ProviderAdapter
from app.schemas.dial_system import (
    CompletionRequest,
    CompletionResult,
    RateLimitStatus,
    TokenUsage,
)


class OllamaAdapter(ProviderAdapter):
    def __init__(self, client: httpx.AsyncClient, model: str, base_url: str) -> None:
        self._client = client
        self._model = model
        self._base_url = base_url

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        response = await self._client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": request.messages,
                "stream": False,
                "options": {
                    "num_predict": request.max_tokens,
                    "temperature": request.temperature,
                },
            },
        )
        data = response.json()
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        return CompletionResult(
            content=data["message"]["content"],
            provider="ollama",
            model=data["model"],
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        async with self._client.stream(
            "POST",
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": request.messages,
                "stream": True,
                "options": {
                    "num_predict": request.max_tokens,
                    "temperature": request.temperature,
                },
            },
        ) as response:
            async for line in response.aiter_lines():
                chunk = json.loads(line)
                if chunk.get("done"):
                    break
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content

    def check_rate_limit(self) -> RateLimitStatus:
        return RateLimitStatus(is_limited=False)
