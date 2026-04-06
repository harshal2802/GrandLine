"""Tests for DialSystemRouter — role-based routing, failover, and Den Den Mushi events."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.adapters.base import ProviderAdapter, ProviderError
from app.dial_system.rate_limiter import RateLimiter
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
        messages=[{"role": "user", "content": "Plan the voyage"}],
        role=CrewRole.CAPTAIN,
        max_tokens=200,
    )


def _make_result(
    provider: str = "anthropic", model: str = "claude-sonnet-4-20250514"
) -> CompletionResult:
    return CompletionResult(
        content="Aye aye, captain!",
        provider=provider,
        model=model,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _make_adapter(result: CompletionResult | None = None, limited: bool = False) -> ProviderAdapter:
    adapter = AsyncMock(spec=ProviderAdapter)
    adapter.complete.return_value = result or _make_result()
    adapter.check_rate_limit.return_value = RateLimitStatus(is_limited=limited)
    return adapter


class TestRouting:
    @pytest.mark.asyncio
    async def test_routes_to_correct_provider_for_role(self) -> None:
        adapter = _make_adapter()
        role_mapping = {CrewRole.CAPTAIN: adapter}

        router = DialSystemRouter(
            role_mapping=role_mapping,
            fallback_chains={},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
        )

        result = await router.route(CrewRole.CAPTAIN, _make_request())

        assert result.content == "Aye aye, captain!"
        adapter.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_for_unmapped_role(self) -> None:
        router = DialSystemRouter(
            role_mapping={},
            fallback_chains={},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
        )

        with pytest.raises(ValueError, match="No provider configured"):
            await router.route(CrewRole.CAPTAIN, _make_request())

    @pytest.mark.asyncio
    async def test_stream_routes_to_correct_provider(self) -> None:
        adapter = AsyncMock(spec=ProviderAdapter)
        adapter.check_rate_limit.return_value = RateLimitStatus(is_limited=False)

        async def mock_stream(req):
            yield "Hello"
            yield " captain"

        adapter.stream = mock_stream

        role_mapping = {CrewRole.CAPTAIN: adapter}
        router = DialSystemRouter(
            role_mapping=role_mapping,
            fallback_chains={},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
        )

        tokens = [t async for t in router.stream(CrewRole.CAPTAIN, _make_request())]

        assert tokens == ["Hello", " captain"]


class TestFailover:
    @pytest.mark.asyncio
    async def test_failover_to_fallback_on_rate_limit(self) -> None:
        primary = _make_adapter(limited=True)
        fallback = _make_adapter(result=_make_result(provider="openai", model="gpt-4o"))

        role_mapping = {CrewRole.CAPTAIN: primary}
        fallback_chains = {CrewRole.CAPTAIN: [fallback]}

        mushi = AsyncMock(spec=DenDenMushi)

        router = DialSystemRouter(
            role_mapping=role_mapping,
            fallback_chains=fallback_chains,
            mushi=mushi,
            voyage_id=VOYAGE_ID,
        )

        result = await router.route(CrewRole.CAPTAIN, _make_request())

        assert result.provider == "openai"
        primary.complete.assert_not_awaited()
        fallback.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failover_to_fallback_on_provider_error(self) -> None:
        primary = _make_adapter()
        primary.check_rate_limit.return_value = RateLimitStatus(is_limited=False)
        primary.complete.side_effect = ProviderError("Provider down")

        fallback = _make_adapter(result=_make_result(provider="openai", model="gpt-4o"))

        role_mapping = {CrewRole.CAPTAIN: primary}
        fallback_chains = {CrewRole.CAPTAIN: [fallback]}

        mushi = AsyncMock(spec=DenDenMushi)

        router = DialSystemRouter(
            role_mapping=role_mapping,
            fallback_chains=fallback_chains,
            mushi=mushi,
            voyage_id=VOYAGE_ID,
        )

        result = await router.route(CrewRole.CAPTAIN, _make_request())

        assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_raises_when_all_providers_exhausted(self) -> None:
        primary = _make_adapter(limited=True)
        fallback = _make_adapter(limited=True)

        role_mapping = {CrewRole.CAPTAIN: primary}
        fallback_chains = {CrewRole.CAPTAIN: [fallback]}

        router = DialSystemRouter(
            role_mapping=role_mapping,
            fallback_chains=fallback_chains,
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
        )

        with pytest.raises(RuntimeError, match="All providers exhausted"):
            await router.route(CrewRole.CAPTAIN, _make_request())

    @pytest.mark.asyncio
    async def test_publishes_provider_switched_event_on_failover(self) -> None:
        primary = _make_adapter(limited=True)
        fallback = _make_adapter(result=_make_result(provider="openai", model="gpt-4o"))

        role_mapping = {CrewRole.CAPTAIN: primary}
        fallback_chains = {CrewRole.CAPTAIN: [fallback]}

        mushi = AsyncMock(spec=DenDenMushi)

        router = DialSystemRouter(
            role_mapping=role_mapping,
            fallback_chains=fallback_chains,
            mushi=mushi,
            voyage_id=VOYAGE_ID,
        )

        await router.route(CrewRole.CAPTAIN, _make_request())

        mushi.publish.assert_awaited_once()
        event = mushi.publish.call_args[0][1]
        assert event.event_type == "provider_switched"
        assert event.voyage_id == VOYAGE_ID
        assert event.source_role == CrewRole.CAPTAIN

    @pytest.mark.asyncio
    async def test_no_event_when_primary_succeeds(self) -> None:
        primary = _make_adapter()

        role_mapping = {CrewRole.CAPTAIN: primary}

        mushi = AsyncMock(spec=DenDenMushi)

        router = DialSystemRouter(
            role_mapping=role_mapping,
            fallback_chains={},
            mushi=mushi,
            voyage_id=VOYAGE_ID,
        )

        await router.route(CrewRole.CAPTAIN, _make_request())

        mushi.publish.assert_not_awaited()


class TestStreamFailover:
    @pytest.mark.asyncio
    async def test_stream_fails_over_on_provider_error(self) -> None:
        primary = AsyncMock(spec=ProviderAdapter)
        primary.check_rate_limit.return_value = RateLimitStatus(is_limited=False)

        async def failing_stream(req):
            raise ProviderError("Stream failed")
            yield  # make it an async generator  # noqa: E501

        primary.stream = failing_stream

        fallback = AsyncMock(spec=ProviderAdapter)
        fallback.check_rate_limit.return_value = RateLimitStatus(is_limited=False)

        async def fallback_stream(req):
            yield "fallback"
            yield " response"

        fallback.stream = fallback_stream

        mushi = AsyncMock(spec=DenDenMushi)

        router = DialSystemRouter(
            role_mapping={CrewRole.CAPTAIN: primary},
            fallback_chains={CrewRole.CAPTAIN: [fallback]},
            mushi=mushi,
            voyage_id=VOYAGE_ID,
        )

        tokens = [t async for t in router.stream(CrewRole.CAPTAIN, _make_request())]

        assert tokens == ["fallback", " response"]
        mushi.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_skips_rate_limited_primary(self) -> None:
        primary = AsyncMock(spec=ProviderAdapter)
        primary.check_rate_limit.return_value = RateLimitStatus(is_limited=True)

        fallback = AsyncMock(spec=ProviderAdapter)
        fallback.check_rate_limit.return_value = RateLimitStatus(is_limited=False)

        async def fallback_stream(req):
            yield "ok"

        fallback.stream = fallback_stream

        mushi = AsyncMock(spec=DenDenMushi)

        router = DialSystemRouter(
            role_mapping={CrewRole.CAPTAIN: primary},
            fallback_chains={CrewRole.CAPTAIN: [fallback]},
            mushi=mushi,
            voyage_id=VOYAGE_ID,
        )

        tokens = [t async for t in router.stream(CrewRole.CAPTAIN, _make_request())]

        assert tokens == ["ok"]


class TestRateLimiterIntegration:
    @pytest.mark.asyncio
    async def test_records_usage_after_successful_completion(self) -> None:
        adapter = _make_adapter()
        rate_limiter = AsyncMock(spec=RateLimiter)

        router = DialSystemRouter(
            role_mapping={CrewRole.CAPTAIN: adapter},
            fallback_chains={},
            mushi=AsyncMock(spec=DenDenMushi),
            voyage_id=VOYAGE_ID,
            rate_limiter=rate_limiter,
        )

        await router.route(CrewRole.CAPTAIN, _make_request())

        rate_limiter.record_usage.assert_awaited_once_with("anthropic", 15)
