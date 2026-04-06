from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.schemas.dial_system import CompletionRequest, CompletionResult, RateLimitStatus


class ProviderAdapter(ABC):
    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    @abstractmethod
    def stream(self, request: CompletionRequest) -> AsyncIterator[str]: ...

    @abstractmethod
    def check_rate_limit(self) -> RateLimitStatus: ...
