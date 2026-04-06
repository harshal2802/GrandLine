from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import ProviderSwitchedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.adapters.base import ProviderAdapter, ProviderError
from app.dial_system.rate_limiter import RateLimiter
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionRequest, CompletionResult

logger = logging.getLogger(__name__)


class DialSystemRouter:
    def __init__(
        self,
        role_mapping: dict[CrewRole, ProviderAdapter],
        fallback_chains: dict[CrewRole, list[ProviderAdapter]],
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._role_mapping = role_mapping
        self._fallback_chains = fallback_chains
        self._mushi = mushi
        self._voyage_id = voyage_id
        self._rate_limiter = rate_limiter

    async def _is_rate_limited(self, adapter: ProviderAdapter) -> bool:
        """Check both adapter-level and Redis-level rate limits."""
        if adapter.check_rate_limit().is_limited:
            return True
        if self._rate_limiter:
            provider_name = self._get_provider_name(adapter)
            redis_status = await self._rate_limiter.check(provider_name)
            if redis_status.is_limited:
                return True
        return False

    def _get_provider_name(self, adapter: ProviderAdapter) -> str:
        """Extract provider name from adapter class."""
        cls_name = type(adapter).__name__.lower()
        if "anthropic" in cls_name:
            return "anthropic"
        if "openai" in cls_name:
            return "openai"
        if "ollama" in cls_name:
            return "ollama"
        return "unknown"

    async def route(self, role: CrewRole, request: CompletionRequest) -> CompletionResult:
        if role not in self._role_mapping:
            raise ValueError(f"No provider configured for role {role.value}")

        primary = self._role_mapping[role]

        # Try primary adapter
        if not await self._is_rate_limited(primary):
            try:
                result = await primary.complete(request)
                if self._rate_limiter:
                    await self._rate_limiter.record_usage(
                        result.provider, result.usage.total_tokens
                    )
                return result
            except ProviderError as exc:
                logger.warning("Primary provider failed for %s: %s", role.value, exc)

        # Failover to fallback chain
        fallbacks = self._fallback_chains.get(role, [])
        for fallback in fallbacks:
            if await self._is_rate_limited(fallback):
                continue
            try:
                result = await fallback.complete(request)
                if self._rate_limiter:
                    await self._rate_limiter.record_usage(
                        result.provider, result.usage.total_tokens
                    )
                await self._publish_switch_event(role, result.provider)
                return result
            except ProviderError as exc:
                logger.warning("Fallback provider failed for %s: %s", role.value, exc)

        raise RuntimeError(f"All providers exhausted for role {role.value}")

    async def stream(self, role: CrewRole, request: CompletionRequest) -> AsyncIterator[str]:
        if role not in self._role_mapping:
            raise ValueError(f"No provider configured for role {role.value}")

        primary = self._role_mapping[role]

        # Try primary adapter
        if not await self._is_rate_limited(primary):
            try:
                async for token in primary.stream(request):
                    yield token
                return
            except ProviderError as exc:
                logger.warning("Primary stream failed for %s: %s", role.value, exc)

        # Failover to fallback chain
        fallbacks = self._fallback_chains.get(role, [])
        for fallback in fallbacks:
            if await self._is_rate_limited(fallback):
                continue
            try:
                await self._publish_switch_event(role, "fallback")
                async for token in fallback.stream(request):
                    yield token
                return
            except ProviderError as exc:
                logger.warning("Fallback stream failed for %s: %s", role.value, exc)

        raise RuntimeError(f"All providers exhausted for role {role.value}")

    async def close(self) -> None:
        """Close all adapter clients to prevent resource leaks."""
        adapters = list(self._role_mapping.values())
        for chain in self._fallback_chains.values():
            adapters.extend(chain)
        for adapter in adapters:
            client = getattr(adapter, "_client", None)
            if client is not None and hasattr(client, "close"):
                await client.close()
            elif client is not None and hasattr(client, "aclose"):
                await client.aclose()

    async def _publish_switch_event(self, role: CrewRole, new_provider: str) -> None:
        event = ProviderSwitchedEvent(
            voyage_id=self._voyage_id,
            source_role=role,
            payload={"new_provider": new_provider},
        )
        stream = stream_key(self._voyage_id)
        await self._mushi.publish(stream, event)
