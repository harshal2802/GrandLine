"""Tests for Dial System rate limiter with mocked Redis."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.dial_system.rate_limiter import RateLimiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_record_usage_stores_in_redis(self) -> None:
        redis = AsyncMock()
        redis.zadd.return_value = 1
        redis.expire.return_value = True
        limiter = RateLimiter(redis)

        await limiter.record_usage("anthropic", tokens=100)

        redis.zadd.assert_awaited()
        redis.expire.assert_awaited()

    @pytest.mark.asyncio
    async def test_check_returns_not_limited_under_threshold(self) -> None:
        redis = AsyncMock()
        redis.zrangebyscore.return_value = []
        redis.zcount.return_value = 0
        limiter = RateLimiter(redis, max_tokens_per_minute=100_000, max_requests_per_minute=100)

        status = await limiter.check("anthropic")

        assert status.is_limited is False

    @pytest.mark.asyncio
    async def test_check_returns_limited_when_tokens_exceeded(self) -> None:
        redis = AsyncMock()
        # Member format is "timestamp:tokens" — sum of tokens exceeds limit
        redis.zrangebyscore.return_value = [("1234.5:60000", 1234.5), ("1234.6:50000", 1234.6)]
        redis.zcount.return_value = 2
        limiter = RateLimiter(redis, max_tokens_per_minute=100_000, max_requests_per_minute=100)

        status = await limiter.check("anthropic")

        assert status.is_limited is True

    @pytest.mark.asyncio
    async def test_check_returns_limited_when_requests_exceeded(self) -> None:
        redis = AsyncMock()
        redis.zrangebyscore.return_value = []
        redis.zcount.return_value = 150
        limiter = RateLimiter(redis, max_tokens_per_minute=100_000, max_requests_per_minute=100)

        status = await limiter.check("anthropic")

        assert status.is_limited is True

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_entries(self) -> None:
        redis = AsyncMock()
        redis.zremrangebyscore.return_value = 5
        limiter = RateLimiter(redis)

        removed = await limiter.cleanup("anthropic")

        assert removed == 5
        redis.zremrangebyscore.assert_awaited_once()
