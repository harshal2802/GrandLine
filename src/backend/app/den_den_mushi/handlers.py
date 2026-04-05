from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.den_den_mushi.constants import BLOCK_MS, MAX_RETRIES, group_name
from app.den_den_mushi.events import DenDenMushiEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.models.enums import CrewRole

logger = logging.getLogger(__name__)

EventHandler = Callable[[DenDenMushiEvent], Awaitable[None]]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def on(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def handlers_for(self, event_type: str) -> list[EventHandler]:
        return self._handlers.get(event_type, [])


async def consume_loop(
    mushi: DenDenMushi,
    stream: str,
    role: CrewRole,
    consumer_id: str,
    registry: HandlerRegistry,
    *,
    max_retries: int = MAX_RETRIES,
    block_ms: int = BLOCK_MS,
) -> None:
    group = group_name(role)
    await mushi.ensure_group(stream, group)

    while True:
        # Recover stale pending messages before reading new ones
        stale = await mushi.claim_stale(stream, group, consumer_id)
        messages = await mushi.read(stream, group, consumer_id, block_ms=block_ms)

        for msg_id, event in stale + messages:
            handlers = registry.handlers_for(event.event_type)

            if not handlers:
                await mushi.ack(stream, group, msg_id)
                continue

            last_error: str | None = None
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as exc:
                    last_error = str(exc)
                    logger.error(
                        "Handler failed for %s (msg %s): %s",
                        event.event_type,
                        msg_id,
                        exc,
                    )
                    break

            if last_error is not None:
                pending_info = await mushi._redis.xpending_range(
                    stream, group, min=msg_id, max=msg_id, count=1
                )
                times_delivered = 0
                if pending_info:
                    times_delivered = pending_info[0].get("times_delivered", 0)

                if times_delivered >= max_retries:
                    event_data = event.model_dump(mode="json")
                    await mushi.send_to_dead_letter(
                        original_stream=stream,
                        msg_id=msg_id,
                        event_data=event_data,
                        error=last_error,
                        retry_count=times_delivered,
                    )
                    await mushi.ack(stream, group, msg_id)
                    logger.warning(
                        "Dead-lettered message %s after %d retries",
                        msg_id,
                        times_delivered,
                    )
            else:
                await mushi.ack(stream, group, msg_id)
