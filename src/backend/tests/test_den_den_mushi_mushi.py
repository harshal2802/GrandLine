"""Tests for DenDenMushi class (Redis Streams wrapper) with mocked Redis."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ResponseError

from app.den_den_mushi.constants import DEAD_LETTER_STREAM
from app.den_den_mushi.events import VoyagePlanCreatedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.models.enums import CrewRole

VOYAGE_ID = uuid.uuid4()
STREAM = f"grandline:events:{VOYAGE_ID}"
GROUP = "crew:captain"
CONSUMER = "captain-1"


def _make_event() -> VoyagePlanCreatedEvent:
    return VoyagePlanCreatedEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"plan_id": str(uuid.uuid4()), "phase_count": 3},
    )


def _make_stream_entry(event: VoyagePlanCreatedEvent) -> list[list]:
    """Simulate the shape returned by xreadgroup: [[stream, [(msg_id, fields)]]]."""
    return [[STREAM, [("1234567890-0", {"data": event.model_dump_json()})]]]


class TestPublish:
    @pytest.mark.asyncio
    async def test_publish_calls_xadd(self) -> None:
        redis = AsyncMock()
        redis.xadd.return_value = "1234567890-0"
        mushi = DenDenMushi(redis)
        event = _make_event()

        msg_id = await mushi.publish(STREAM, event)

        redis.xadd.assert_awaited_once()
        call_args = redis.xadd.call_args
        assert call_args[0][0] == STREAM
        fields = call_args[0][1]
        assert "data" in fields
        parsed = json.loads(fields["data"])
        assert parsed["event_type"] == "voyage_plan_created"
        assert msg_id == "1234567890-0"

    @pytest.mark.asyncio
    async def test_publish_returns_message_id(self) -> None:
        redis = AsyncMock()
        redis.xadd.return_value = "9999999999-5"
        mushi = DenDenMushi(redis)

        msg_id = await mushi.publish(STREAM, _make_event())

        assert msg_id == "9999999999-5"


class TestEnsureGroup:
    @pytest.mark.asyncio
    async def test_ensure_group_creates_group(self) -> None:
        redis = AsyncMock()
        mushi = DenDenMushi(redis)

        await mushi.ensure_group(STREAM, GROUP)

        redis.xgroup_create.assert_awaited_once_with(STREAM, GROUP, id="0", mkstream=True)

    @pytest.mark.asyncio
    async def test_ensure_group_ignores_busygroup(self) -> None:
        redis = AsyncMock()
        redis.xgroup_create.side_effect = ResponseError(
            "BUSYGROUP Consumer Group name already exists"
        )
        mushi = DenDenMushi(redis)

        # Should not raise
        await mushi.ensure_group(STREAM, GROUP)

    @pytest.mark.asyncio
    async def test_ensure_group_raises_other_errors(self) -> None:
        redis = AsyncMock()
        redis.xgroup_create.side_effect = ResponseError("WRONGTYPE Operation")
        mushi = DenDenMushi(redis)

        with pytest.raises(ResponseError, match="WRONGTYPE"):
            await mushi.ensure_group(STREAM, GROUP)


class TestRead:
    @pytest.mark.asyncio
    async def test_read_calls_xreadgroup(self) -> None:
        event = _make_event()
        redis = AsyncMock()
        redis.xreadgroup.return_value = _make_stream_entry(event)
        mushi = DenDenMushi(redis)

        results = await mushi.read(STREAM, GROUP, CONSUMER, count=10, block_ms=1000)

        redis.xreadgroup.assert_awaited_once_with(
            GROUP, CONSUMER, {STREAM: ">"}, count=10, block=1000
        )
        assert len(results) == 1
        msg_id, parsed_event = results[0]
        assert msg_id == "1234567890-0"
        assert isinstance(parsed_event, VoyagePlanCreatedEvent)
        assert parsed_event.voyage_id == event.voyage_id

    @pytest.mark.asyncio
    async def test_read_returns_empty_on_no_messages(self) -> None:
        redis = AsyncMock()
        redis.xreadgroup.return_value = None
        mushi = DenDenMushi(redis)

        results = await mushi.read(STREAM, GROUP, CONSUMER)

        assert results == []

    @pytest.mark.asyncio
    async def test_read_returns_empty_on_empty_list(self) -> None:
        redis = AsyncMock()
        redis.xreadgroup.return_value = []
        mushi = DenDenMushi(redis)

        results = await mushi.read(STREAM, GROUP, CONSUMER)

        assert results == []

    @pytest.mark.asyncio
    async def test_read_dead_letters_and_acks_malformed_messages(self) -> None:
        redis = AsyncMock()
        redis.xreadgroup.return_value = [[STREAM, [("bad-id", {"data": "not valid json {{"})]]]
        redis.xadd.return_value = "dl-1-0"
        redis.xack.return_value = 1
        mushi = DenDenMushi(redis)

        with patch("app.den_den_mushi.mushi.logger") as mock_logger:
            results = await mushi.read(STREAM, GROUP, CONSUMER)

        assert results == []
        mock_logger.warning.assert_called_once()
        # Malformed message is dead-lettered and ACKed
        redis.xadd.assert_awaited_once()
        redis.xack.assert_awaited_once_with(STREAM, GROUP, "bad-id")

    @pytest.mark.asyncio
    async def test_read_dead_letters_and_acks_invalid_event_data(self) -> None:
        redis = AsyncMock()
        redis.xreadgroup.return_value = [
            [STREAM, [("bad-id", {"data": json.dumps({"event_type": "unknown"})})]]
        ]
        redis.xadd.return_value = "dl-1-0"
        redis.xack.return_value = 1
        mushi = DenDenMushi(redis)

        with patch("app.den_den_mushi.mushi.logger") as mock_logger:
            results = await mushi.read(STREAM, GROUP, CONSUMER)

        assert results == []
        mock_logger.warning.assert_called_once()
        redis.xadd.assert_awaited_once()
        redis.xack.assert_awaited_once_with(STREAM, GROUP, "bad-id")


class TestAck:
    @pytest.mark.asyncio
    async def test_ack_calls_xack(self) -> None:
        redis = AsyncMock()
        redis.xack.return_value = 1
        mushi = DenDenMushi(redis)

        count = await mushi.ack(STREAM, GROUP, "1234567890-0")

        redis.xack.assert_awaited_once_with(STREAM, GROUP, "1234567890-0")
        assert count == 1

    @pytest.mark.asyncio
    async def test_ack_multiple_ids(self) -> None:
        redis = AsyncMock()
        redis.xack.return_value = 3
        mushi = DenDenMushi(redis)

        count = await mushi.ack(STREAM, GROUP, "1-0", "2-0", "3-0")

        redis.xack.assert_awaited_once_with(STREAM, GROUP, "1-0", "2-0", "3-0")
        assert count == 3


class TestSendToDeadLetter:
    @pytest.mark.asyncio
    async def test_send_to_dead_letter_calls_xadd(self) -> None:
        redis = AsyncMock()
        redis.xadd.return_value = "dl-1234-0"
        mushi = DenDenMushi(redis)

        event_data = {"event_type": "voyage_plan_created", "voyage_id": str(VOYAGE_ID)}
        msg_id = await mushi.send_to_dead_letter(
            original_stream=STREAM,
            msg_id="1234567890-0",
            event_data=event_data,
            error="ValueError: bad data",
            retry_count=3,
        )

        redis.xadd.assert_awaited_once()
        call_args = redis.xadd.call_args
        assert call_args[0][0] == DEAD_LETTER_STREAM
        fields = call_args[0][1]
        assert fields["original_stream"] == STREAM
        assert fields["original_msg_id"] == "1234567890-0"
        assert fields["error"] == "ValueError: bad data"
        assert fields["retry_count"] == "3"
        assert "data" in fields
        assert "dead_lettered_at" in fields
        assert msg_id == "dl-1234-0"


class TestClaimStale:
    @pytest.mark.asyncio
    async def test_claim_stale_calls_xautoclaim(self) -> None:
        event = _make_event()
        redis = AsyncMock()
        # xautoclaim returns (next_start_id, [(msg_id, fields), ...], [deleted_ids])
        redis.xautoclaim.return_value = (
            "0-0",
            [("stale-1-0", {"data": event.model_dump_json()})],
            [],
        )
        mushi = DenDenMushi(redis)

        results = await mushi.claim_stale(STREAM, GROUP, CONSUMER, min_idle_ms=30000, count=5)

        redis.xautoclaim.assert_awaited_once_with(
            STREAM, GROUP, CONSUMER, min_idle_time=30000, start_id="0-0", count=5
        )
        assert len(results) == 1
        msg_id, parsed = results[0]
        assert msg_id == "stale-1-0"
        assert isinstance(parsed, VoyagePlanCreatedEvent)

    @pytest.mark.asyncio
    async def test_claim_stale_returns_empty_when_none(self) -> None:
        redis = AsyncMock()
        redis.xautoclaim.return_value = ("0-0", [], [])
        mushi = DenDenMushi(redis)

        results = await mushi.claim_stale(STREAM, GROUP, CONSUMER)

        assert results == []


class TestReplay:
    @pytest.mark.asyncio
    async def test_replay_calls_xrange(self) -> None:
        event = _make_event()
        redis = AsyncMock()
        redis.xrange.return_value = [
            ("1-0", {"data": event.model_dump_json()}),
        ]
        mushi = DenDenMushi(redis)

        results = await mushi.replay(STREAM, start_id="0-0", count=50)

        redis.xrange.assert_awaited_once_with(STREAM, min="0-0", count=50)
        assert len(results) == 1
        msg_id, parsed = results[0]
        assert msg_id == "1-0"
        assert isinstance(parsed, VoyagePlanCreatedEvent)

    @pytest.mark.asyncio
    async def test_replay_returns_empty(self) -> None:
        redis = AsyncMock()
        redis.xrange.return_value = []
        mushi = DenDenMushi(redis)

        results = await mushi.replay(STREAM)

        assert results == []


class TestTrim:
    @pytest.mark.asyncio
    async def test_trim_calls_xtrim(self) -> None:
        redis = AsyncMock()
        redis.xtrim.return_value = 5
        mushi = DenDenMushi(redis)

        trimmed = await mushi.trim(STREAM, maxlen=1000, approximate=True)

        redis.xtrim.assert_awaited_once_with(STREAM, maxlen=1000, approximate=True)
        assert trimmed == 5

    @pytest.mark.asyncio
    async def test_trim_exact(self) -> None:
        redis = AsyncMock()
        redis.xtrim.return_value = 10
        mushi = DenDenMushi(redis)

        trimmed = await mushi.trim(STREAM, maxlen=500, approximate=False)

        redis.xtrim.assert_awaited_once_with(STREAM, maxlen=500, approximate=False)
        assert trimmed == 10


class TestGetPendingCount:
    @pytest.mark.asyncio
    async def test_get_pending_count(self) -> None:
        redis = AsyncMock()
        redis.xpending.return_value = {"pending": 7}
        mushi = DenDenMushi(redis)

        count = await mushi.get_pending_count(STREAM, GROUP)

        redis.xpending.assert_awaited_once_with(STREAM, GROUP)
        assert count == 7

    @pytest.mark.asyncio
    async def test_get_pending_count_zero(self) -> None:
        redis = AsyncMock()
        redis.xpending.return_value = {"pending": 0}
        mushi = DenDenMushi(redis)

        count = await mushi.get_pending_count(STREAM, GROUP)

        assert count == 0
