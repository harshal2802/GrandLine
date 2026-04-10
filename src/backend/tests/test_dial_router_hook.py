"""Tests for DialSystemRouter on_provider_switch hook."""

from __future__ import annotations

import logging
import uuid
from unittest.mock import AsyncMock

import pytest

from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.adapters.base import ProviderAdapter, ProviderError
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole
from app.schemas.dial_system import (
    CompletionRequest,
    CompletionResult,
    RateLimitStatus,
    TokenUsage,
)

VOYAGE_ID = uuid.uuid4()


def _make_request() -> CompletionRequest:
    return CompletionRequest(
        messages=[{"role": "user", "content": "Checkpoint test"}],
        role=CrewRole.CAPTAIN,
        max_tokens=100,
    )


def _make_result(provider: str = "anthropic") -> CompletionResult:
    return CompletionResult(
        content="Result",
        provider=provider,
        model="test-model",
        usage=TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
    )


def _make_adapter(
    result: CompletionResult | None = None,
    limited: bool = False,
    fail: bool = False,
) -> ProviderAdapter:
    adapter = AsyncMock(spec=ProviderAdapter)
    if fail:
        adapter.complete.side_effect = ProviderError("Provider failed")
        adapter.stream.side_effect = ProviderError("Provider failed")
    else:
        adapter.complete.return_value = result or _make_result()

        async def _stream(req: CompletionRequest) -> None:
            yield "token1"
            yield "token2"

        adapter.stream = _stream
    adapter.check_rate_limit.return_value = RateLimitStatus(is_limited=limited)
    return adapter


class TestOnProviderSwitchHook:
    @pytest.mark.asyncio
    async def test_hook_called_on_failover(self) -> None:
        primary = _make_adapter(fail=True)
        fallback = _make_adapter(result=_make_result("openai"))
        hook = AsyncMock()

        router = DialSystemRouter(
            role_mapping={CrewRole.CAPTAIN: primary},
            fallback_chains={CrewRole.CAPTAIN: [fallback]},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
            on_provider_switch=hook,
        )

        await router.route(CrewRole.CAPTAIN, _make_request())

        hook.assert_awaited_once()
        call_args = hook.call_args[0]
        assert call_args[0] == CrewRole.CAPTAIN

    @pytest.mark.asyncio
    async def test_hook_called_on_stream_failover(self) -> None:
        primary = _make_adapter(fail=True)

        fallback = AsyncMock(spec=ProviderAdapter)
        fallback.check_rate_limit.return_value = RateLimitStatus(is_limited=False)

        async def _fallback_stream(req: CompletionRequest):
            yield "token1"

        fallback.stream = _fallback_stream
        hook = AsyncMock()

        router = DialSystemRouter(
            role_mapping={CrewRole.CAPTAIN: primary},
            fallback_chains={CrewRole.CAPTAIN: [fallback]},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
            on_provider_switch=hook,
        )

        tokens = []
        async for token in router.stream(CrewRole.CAPTAIN, _make_request()):
            tokens.append(token)

        hook.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hook_not_called_when_primary_succeeds(self) -> None:
        primary = _make_adapter()
        hook = AsyncMock()

        router = DialSystemRouter(
            role_mapping={CrewRole.CAPTAIN: primary},
            fallback_chains={},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
            on_provider_switch=hook,
        )

        await router.route(CrewRole.CAPTAIN, _make_request())

        hook.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_hook_none_is_safe(self) -> None:
        primary = _make_adapter(fail=True)
        fallback = _make_adapter(result=_make_result("openai"))

        router = DialSystemRouter(
            role_mapping={CrewRole.CAPTAIN: primary},
            fallback_chains={CrewRole.CAPTAIN: [fallback]},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
            # no on_provider_switch — should default to None
        )

        # Should not crash
        result = await router.route(CrewRole.CAPTAIN, _make_request())
        assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_hook_error_does_not_block_failover(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        primary = _make_adapter(fail=True)
        fallback = _make_adapter(result=_make_result("openai"))
        hook = AsyncMock(side_effect=RuntimeError("Hook blew up"))

        router = DialSystemRouter(
            role_mapping={CrewRole.CAPTAIN: primary},
            fallback_chains={CrewRole.CAPTAIN: [fallback]},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
            on_provider_switch=hook,
        )

        with caplog.at_level(logging.WARNING):
            result = await router.route(CrewRole.CAPTAIN, _make_request())

        # Failover still succeeded despite hook error
        assert result.provider == "openai"
        hook.assert_awaited_once()
