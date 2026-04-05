"""Tests for handler registry and consume_loop."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from app.den_den_mushi.constants import MAX_RETRIES
from app.den_den_mushi.events import VoyagePlanCreatedEvent
from app.den_den_mushi.handlers import HandlerRegistry, consume_loop
from app.den_den_mushi.mushi import DenDenMushi
from app.models.enums import CrewRole

VOYAGE_ID = uuid.uuid4()
STREAM = f"grandline:events:{VOYAGE_ID}"
GROUP = "crew:navigator"
CONSUMER = "navigator-1"


def _make_event() -> VoyagePlanCreatedEvent:
    return VoyagePlanCreatedEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"plan_id": str(uuid.uuid4()), "phase_count": 3},
    )


class TestHandlerRegistry:
    def test_register_handler(self) -> None:
        registry = HandlerRegistry()
        handler = AsyncMock()
        registry.on("voyage_plan_created", handler)

        handlers = registry.handlers_for("voyage_plan_created")
        assert handlers == [handler]

    def test_multiple_handlers_for_same_event(self) -> None:
        registry = HandlerRegistry()
        h1 = AsyncMock()
        h2 = AsyncMock()
        registry.on("voyage_plan_created", h1)
        registry.on("voyage_plan_created", h2)

        handlers = registry.handlers_for("voyage_plan_created")
        assert handlers == [h1, h2]

    def test_handlers_for_unregistered_type(self) -> None:
        registry = HandlerRegistry()
        handlers = registry.handlers_for("nonexistent")
        assert handlers == []

    def test_different_event_types_are_isolated(self) -> None:
        registry = HandlerRegistry()
        h1 = AsyncMock()
        h2 = AsyncMock()
        registry.on("voyage_plan_created", h1)
        registry.on("code_generated", h2)

        assert registry.handlers_for("voyage_plan_created") == [h1]
        assert registry.handlers_for("code_generated") == [h2]


class TestConsumeLoop:
    @pytest.mark.asyncio
    async def test_dispatches_to_correct_handler_and_acks(self) -> None:
        event = _make_event()
        handler = AsyncMock()

        registry = HandlerRegistry()
        registry.on("voyage_plan_created", handler)

        mushi = AsyncMock(spec=DenDenMushi)
        mushi.claim_stale.return_value = []
        # First call returns an event, second raises CancelledError to stop the loop
        mushi.read.side_effect = [
            [("msg-1", event)],
            asyncio.CancelledError(),
        ]

        with pytest.raises(asyncio.CancelledError):
            await consume_loop(mushi, STREAM, CrewRole.NAVIGATOR, CONSUMER, registry)

        handler.assert_awaited_once_with(event)
        mushi.ack.assert_awaited_once_with(STREAM, GROUP, "msg-1")

    @pytest.mark.asyncio
    async def test_does_not_ack_on_handler_failure(self) -> None:
        event = _make_event()
        handler = AsyncMock(side_effect=ValueError("handler failed"))

        registry = HandlerRegistry()
        registry.on("voyage_plan_created", handler)

        mushi = AsyncMock(spec=DenDenMushi)
        mushi.claim_stale.return_value = []
        # Return event, then pending info showing retry count < MAX_RETRIES
        mushi.read.side_effect = [
            [("msg-1", event)],
            asyncio.CancelledError(),
        ]
        # xpending_range returns delivery count per message
        mushi._redis = AsyncMock()
        mushi._redis.xpending_range.return_value = [{"message_id": "msg-1", "times_delivered": 1}]

        with pytest.raises(asyncio.CancelledError):
            await consume_loop(mushi, STREAM, CrewRole.NAVIGATOR, CONSUMER, registry)

        handler.assert_awaited_once_with(event)
        mushi.ack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dead_letters_after_max_retries(self) -> None:
        event = _make_event()
        handler = AsyncMock(side_effect=ValueError("persistent failure"))

        registry = HandlerRegistry()
        registry.on("voyage_plan_created", handler)

        mushi = AsyncMock(spec=DenDenMushi)
        mushi.claim_stale.return_value = []
        mushi.read.side_effect = [
            [("msg-1", event)],
            asyncio.CancelledError(),
        ]
        # Simulate that message has been delivered MAX_RETRIES times
        mushi._redis = AsyncMock()
        mushi._redis.xpending_range.return_value = [
            {"message_id": "msg-1", "times_delivered": MAX_RETRIES}
        ]

        with pytest.raises(asyncio.CancelledError):
            await consume_loop(mushi, STREAM, CrewRole.NAVIGATOR, CONSUMER, registry)

        mushi.send_to_dead_letter.assert_awaited_once()
        call_kwargs = mushi.send_to_dead_letter.call_args
        assert call_kwargs[1]["original_stream"] == STREAM
        assert call_kwargs[1]["msg_id"] == "msg-1"
        assert call_kwargs[1]["retry_count"] == MAX_RETRIES
        # After dead-lettering, the message is acked from original stream
        mushi.ack.assert_awaited_once_with(STREAM, GROUP, "msg-1")

    @pytest.mark.asyncio
    async def test_ensures_consumer_group_on_start(self) -> None:
        mushi = AsyncMock(spec=DenDenMushi)
        mushi.claim_stale.return_value = []
        mushi.read.side_effect = asyncio.CancelledError()
        mushi._redis = AsyncMock()

        registry = HandlerRegistry()

        with pytest.raises(asyncio.CancelledError):
            await consume_loop(mushi, STREAM, CrewRole.NAVIGATOR, CONSUMER, registry)

        mushi.ensure_group.assert_awaited_once_with(STREAM, GROUP)

    @pytest.mark.asyncio
    async def test_continues_on_empty_read(self) -> None:
        event = _make_event()
        handler = AsyncMock()

        registry = HandlerRegistry()
        registry.on("voyage_plan_created", handler)

        mushi = AsyncMock(spec=DenDenMushi)
        mushi.claim_stale.return_value = []
        mushi.read.side_effect = [
            [],  # empty read
            [("msg-1", event)],  # event arrives
            asyncio.CancelledError(),
        ]

        with pytest.raises(asyncio.CancelledError):
            await consume_loop(mushi, STREAM, CrewRole.NAVIGATOR, CONSUMER, registry)

        handler.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_no_handlers_still_acks(self) -> None:
        """Messages with no registered handlers are acked (no-op dispatch)."""
        event = _make_event()
        registry = HandlerRegistry()  # no handlers registered

        mushi = AsyncMock(spec=DenDenMushi)
        mushi.claim_stale.return_value = []
        mushi.read.side_effect = [
            [("msg-1", event)],
            asyncio.CancelledError(),
        ]

        with pytest.raises(asyncio.CancelledError):
            await consume_loop(mushi, STREAM, CrewRole.NAVIGATOR, CONSUMER, registry)

        # Should still ack even with no handlers
        mushi.ack.assert_awaited_once_with(STREAM, GROUP, "msg-1")

    @pytest.mark.asyncio
    async def test_processes_stale_pending_messages(self) -> None:
        """claim_stale recovers pending messages and routes them through handlers."""
        event = _make_event()
        handler = AsyncMock()

        registry = HandlerRegistry()
        registry.on("voyage_plan_created", handler)

        mushi = AsyncMock(spec=DenDenMushi)
        mushi.claim_stale.side_effect = [
            [("stale-1", event)],
            asyncio.CancelledError(),
        ]
        mushi.read.return_value = []

        with pytest.raises(asyncio.CancelledError):
            await consume_loop(mushi, STREAM, CrewRole.NAVIGATOR, CONSUMER, registry)

        handler.assert_awaited_once_with(event)
        mushi.ack.assert_awaited_once_with(STREAM, GROUP, "stale-1")
