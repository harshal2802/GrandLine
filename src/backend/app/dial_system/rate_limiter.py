from __future__ import annotations

import time

from redis.asyncio import Redis

from app.schemas.dial_system import RateLimitStatus

WINDOW_SECONDS = 60
KEY_PREFIX = "grandline:ratelimit"


class RateLimiter:
    def __init__(
        self,
        redis: Redis,
        max_tokens_per_minute: int = 100_000,
        max_requests_per_minute: int = 100,
    ) -> None:
        self._redis = redis
        self._max_tokens = max_tokens_per_minute
        self._max_requests = max_requests_per_minute

    def _key(self, provider: str) -> str:
        return f"{KEY_PREFIX}:{provider}"

    async def record_usage(self, provider: str, tokens: int) -> None:
        key = self._key(provider)
        now = time.time()
        member = f"{now}:{tokens}"
        await self._redis.zadd(key, {member: now})
        await self._redis.expire(key, WINDOW_SECONDS * 2)

    async def check(self, provider: str) -> RateLimitStatus:
        key = self._key(provider)
        now = time.time()
        window_start = now - WINDOW_SECONDS

        # Get entries within the sliding window
        entries = await self._redis.zrangebyscore(key, window_start, now, withscores=True)
        request_count = await self._redis.zcount(key, window_start, now)

        # Sum tokens from member names (format: "timestamp:tokens")
        total_tokens = 0
        for member, _score in entries:
            parts = member.split(":")
            if len(parts) >= 2:
                try:
                    total_tokens += int(parts[-1])
                except ValueError:
                    pass

        tokens_limited = total_tokens >= self._max_tokens
        requests_limited = request_count >= self._max_requests

        return RateLimitStatus(
            is_limited=tokens_limited or requests_limited,
            remaining_tokens=max(0, self._max_tokens - total_tokens),
            remaining_requests=max(0, self._max_requests - request_count),
        )

    async def cleanup(self, provider: str) -> int:
        key = self._key(provider)
        now = time.time()
        window_start = now - WINDOW_SECONDS
        removed: int = await self._redis.zremrangebyscore(key, 0, window_start)
        return removed
