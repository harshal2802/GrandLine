from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.den_den_mushi.constants import BLOCK_MS, CLAIM_MIN_IDLE_MS, DEAD_LETTER_STREAM
from app.den_den_mushi.events import DenDenMushiEvent, parse_event

logger = logging.getLogger(__name__)


class DenDenMushi:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, stream: str, event: DenDenMushiEvent) -> str:
        msg_id: str = await self._redis.xadd(stream, {"data": event.model_dump_json()})
        return msg_id

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def read(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = BLOCK_MS,
    ) -> list[tuple[str, DenDenMushiEvent]]:
        raw = await self._redis.xreadgroup(
            group, consumer, {stream: ">"}, count=count, block=block_ms
        )
        if not raw:
            return []

        results: list[tuple[str, DenDenMushiEvent]] = []
        for _stream_name, messages in raw:
            for msg_id, fields in messages:
                try:
                    data = json.loads(fields["data"])
                    event = parse_event(data)
                    results.append((msg_id, event))
                except Exception as exc:
                    logger.warning(
                        "Skipping malformed message %s on %s: %s",
                        msg_id,
                        stream,
                        exc,
                    )
                    await self.send_to_dead_letter(
                        original_stream=stream,
                        msg_id=msg_id,
                        event_data={"raw_fields": {k: v for k, v in fields.items()}},
                        error=str(exc),
                        retry_count=0,
                    )
                    await self.ack(stream, group, msg_id)
        return results

    async def ack(self, stream: str, group: str, *msg_ids: str) -> int:
        count: int = await self._redis.xack(stream, group, *msg_ids)
        return count

    async def send_to_dead_letter(
        self,
        original_stream: str,
        msg_id: str,
        event_data: dict[str, Any],
        error: str,
        retry_count: int,
    ) -> str:
        dl_id: str = await self._redis.xadd(
            DEAD_LETTER_STREAM,
            {
                "data": json.dumps(event_data),
                "original_stream": original_stream,
                "original_msg_id": msg_id,
                "error": error,
                "retry_count": str(retry_count),
                "dead_lettered_at": datetime.now(UTC).isoformat(),
            },
        )
        return dl_id

    async def claim_stale(
        self,
        stream: str,
        group: str,
        consumer: str,
        min_idle_ms: int = CLAIM_MIN_IDLE_MS,
        count: int = 10,
    ) -> list[tuple[str, DenDenMushiEvent]]:
        _next_id, claimed, _deleted = await self._redis.xautoclaim(
            stream, group, consumer, min_idle_time=min_idle_ms, start_id="0-0", count=count
        )

        results: list[tuple[str, DenDenMushiEvent]] = []
        for msg_id, fields in claimed:
            try:
                data = json.loads(fields["data"])
                event = parse_event(data)
                results.append((msg_id, event))
            except Exception as exc:
                logger.warning(
                    "Skipping malformed claimed message %s on %s: %s",
                    msg_id,
                    stream,
                    exc,
                )
                await self.send_to_dead_letter(
                    original_stream=stream,
                    msg_id=msg_id,
                    event_data={"raw_fields": {k: v for k, v in fields.items()}},
                    error=str(exc),
                    retry_count=0,
                )
                await self.ack(stream, group, msg_id)
        return results

    async def replay(
        self,
        stream: str,
        start_id: str = "0-0",
        count: int = 100,
    ) -> list[tuple[str, DenDenMushiEvent]]:
        raw = await self._redis.xrange(stream, min=start_id, count=count)

        results: list[tuple[str, DenDenMushiEvent]] = []
        for msg_id, fields in raw:
            try:
                data = json.loads(fields["data"])
                event = parse_event(data)
                results.append((msg_id, event))
            except Exception as exc:
                logger.warning(
                    "Skipping malformed message %s during replay on %s: %s",
                    msg_id,
                    stream,
                    exc,
                )
        return results

    async def trim(self, stream: str, maxlen: int, approximate: bool = True) -> int:
        trimmed: int = await self._redis.xtrim(stream, maxlen=maxlen, approximate=approximate)
        return trimmed

    async def get_pending_count(self, stream: str, group: str) -> int:
        info = await self._redis.xpending(stream, group)
        count: int = info["pending"]
        return count
