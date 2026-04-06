from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import ProviderSwitchedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.adapters.base import ProviderAdapter
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
    ) -> None:
        self._role_mapping = role_mapping
        self._fallback_chains = fallback_chains
        self._mushi = mushi
        self._voyage_id = voyage_id

    async def route(self, role: CrewRole, request: CompletionRequest) -> CompletionResult:
        if role not in self._role_mapping:
            raise ValueError(f"No provider configured for role {role.value}")

        primary = self._role_mapping[role]

        # Try primary adapter
        if not primary.check_rate_limit().is_limited:
            try:
                return await primary.complete(request)
            except Exception as exc:
                logger.warning("Primary provider failed for %s: %s", role.value, exc)

        # Failover to fallback chain
        fallbacks = self._fallback_chains.get(role, [])
        for fallback in fallbacks:
            if fallback.check_rate_limit().is_limited:
                continue
            try:
                result = await fallback.complete(request)
                await self._publish_switch_event(role, result.provider)
                return result
            except Exception as exc:
                logger.warning("Fallback provider failed for %s: %s", role.value, exc)

        raise RuntimeError(f"All providers exhausted for role {role.value}")

    async def stream(self, role: CrewRole, request: CompletionRequest) -> AsyncIterator[str]:
        if role not in self._role_mapping:
            raise ValueError(f"No provider configured for role {role.value}")

        adapter = self._role_mapping[role]
        async for token in adapter.stream(request):
            yield token

    async def _publish_switch_event(self, role: CrewRole, new_provider: str) -> None:
        event = ProviderSwitchedEvent(
            voyage_id=self._voyage_id,
            source_role=role,
            payload={"new_provider": new_provider},
        )
        stream = stream_key(self._voyage_id)
        await self._mushi.publish(stream, event)
