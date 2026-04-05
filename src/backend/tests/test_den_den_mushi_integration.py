"""Integration tests for Den Den Mushi with real Redis.

These tests require a running Redis instance on localhost:6379.
They use DB index 1 to avoid interfering with development data.
Skipped automatically if Redis is not available.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.den_den_mushi.constants import (
    DEAD_LETTER_STREAM,
    group_name,
    stream_key,
)
from app.den_den_mushi.events import (
    CodeGeneratedEvent,
    VoyagePlanCreatedEvent,
)
from app.den_den_mushi.handlers import HandlerRegistry, consume_loop
from app.den_den_mushi.mushi import DenDenMushi
from app.models.enums import CrewRole


async def _redis_available() -> bool:
    try:
        client = Redis.from_url("redis://localhost:6379/1", decode_responses=True)
        await client.ping()
        await client.aclose()
        return True
    except (RedisConnectionError, OSError):
        return False


pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client():
    client = Redis.from_url("redis://localhost:6379/1", decode_responses=True)
    try:
        await client.ping()
    except (RedisConnectionError, OSError):
        pytest.skip("Redis not available on localhost:6379")
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def mushi(redis_client: Redis) -> DenDenMushi:
    return DenDenMushi(redis_client)


VOYAGE_ID = uuid.uuid4()


class TestPublishAndRead:
    @pytest.mark.asyncio
    async def test_publish_and_read_round_trip(self, mushi: DenDenMushi) -> None:
        stream = stream_key(VOYAGE_ID)
        group = group_name(CrewRole.NAVIGATOR)

        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={"plan_id": str(uuid.uuid4()), "phase_count": 5},
        )

        await mushi.ensure_group(stream, group)
        msg_id = await mushi.publish(stream, event)
        assert msg_id

        results = await mushi.read(stream, group, "nav-1", count=10, block_ms=100)
        assert len(results) == 1
        read_id, read_event = results[0]
        assert read_id == msg_id
        assert isinstance(read_event, VoyagePlanCreatedEvent)
        assert read_event.event_id == event.event_id
        assert read_event.voyage_id == event.voyage_id

    @pytest.mark.asyncio
    async def test_two_consumer_groups_both_receive(self, mushi: DenDenMushi) -> None:
        stream = stream_key(VOYAGE_ID)
        group_nav = group_name(CrewRole.NAVIGATOR)
        group_doc = group_name(CrewRole.DOCTOR)

        await mushi.ensure_group(stream, group_nav)
        await mushi.ensure_group(stream, group_doc)

        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={},
        )
        await mushi.publish(stream, event)

        results_nav = await mushi.read(stream, group_nav, "nav-1", block_ms=100)
        results_doc = await mushi.read(stream, group_doc, "doc-1", block_ms=100)

        assert len(results_nav) == 1
        assert len(results_doc) == 1
        assert results_nav[0][1].event_id == results_doc[0][1].event_id


class TestAck:
    @pytest.mark.asyncio
    async def test_ack_removes_from_pending(self, mushi: DenDenMushi) -> None:
        stream = stream_key(VOYAGE_ID)
        group = group_name(CrewRole.NAVIGATOR)

        await mushi.ensure_group(stream, group)
        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={},
        )
        await mushi.publish(stream, event)

        results = await mushi.read(stream, group, "nav-1", block_ms=100)
        assert len(results) == 1
        msg_id = results[0][0]

        pending_before = await mushi.get_pending_count(stream, group)
        assert pending_before == 1

        await mushi.ack(stream, group, msg_id)

        pending_after = await mushi.get_pending_count(stream, group)
        assert pending_after == 0


class TestReplay:
    @pytest.mark.asyncio
    async def test_replay_from_offset(self, mushi: DenDenMushi) -> None:
        stream = stream_key(VOYAGE_ID)

        msg_ids = []
        for i in range(5):
            event = VoyagePlanCreatedEvent(
                voyage_id=VOYAGE_ID,
                source_role=CrewRole.CAPTAIN,
                payload={"phase_count": i},
            )
            mid = await mushi.publish(stream, event)
            msg_ids.append(mid)

        # Replay from the 3rd message
        results = await mushi.replay(stream, start_id=msg_ids[2], count=100)
        assert len(results) == 3  # messages 2, 3, 4
        assert results[0][0] == msg_ids[2]

    @pytest.mark.asyncio
    async def test_replay_all(self, mushi: DenDenMushi) -> None:
        stream = stream_key(VOYAGE_ID)

        for i in range(3):
            event = CodeGeneratedEvent(
                voyage_id=VOYAGE_ID,
                source_role=CrewRole.SHIPWRIGHT,
                payload={"files": [f"file{i}.py"], "phase_number": i},
            )
            await mushi.publish(stream, event)

        results = await mushi.replay(stream)
        assert len(results) == 3
        assert all(isinstance(r[1], CodeGeneratedEvent) for r in results)


class TestDeadLetter:
    @pytest.mark.asyncio
    async def test_dead_letter_stores_metadata(self, mushi: DenDenMushi) -> None:
        event_data = {"event_type": "voyage_plan_created", "voyage_id": str(VOYAGE_ID)}
        dl_id = await mushi.send_to_dead_letter(
            original_stream="test:stream",
            msg_id="1234-0",
            event_data=event_data,
            error="ValueError: bad",
            retry_count=3,
        )
        assert dl_id

        raw = await mushi._redis.xrange(DEAD_LETTER_STREAM)
        assert len(raw) == 1
        _id, fields = raw[0]
        assert fields["original_stream"] == "test:stream"
        assert fields["original_msg_id"] == "1234-0"
        assert fields["error"] == "ValueError: bad"
        assert fields["retry_count"] == "3"
        assert json.loads(fields["data"]) == event_data


class TestEnsureGroup:
    @pytest.mark.asyncio
    async def test_ensure_group_idempotent(self, mushi: DenDenMushi) -> None:
        stream = stream_key(VOYAGE_ID)
        group = group_name(CrewRole.CAPTAIN)

        await mushi.ensure_group(stream, group)
        await mushi.ensure_group(stream, group)  # should not raise


class TestMalformedData:
    @pytest.mark.asyncio
    async def test_malformed_data_skipped(self, mushi: DenDenMushi, redis_client: Redis) -> None:
        stream = stream_key(VOYAGE_ID)
        group = group_name(CrewRole.NAVIGATOR)

        await mushi.ensure_group(stream, group)

        # Inject a malformed message directly
        await redis_client.xadd(stream, {"data": "not valid json"})
        # Also inject a valid one
        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={},
        )
        await mushi.publish(stream, event)

        results = await mushi.read(stream, group, "nav-1", count=10, block_ms=100)
        # Only the valid message should be returned
        assert len(results) == 1
        assert isinstance(results[0][1], VoyagePlanCreatedEvent)


class TestConsumeLoopIntegration:
    @pytest.mark.asyncio
    async def test_consume_loop_processes_events(self, mushi: DenDenMushi) -> None:
        stream = stream_key(VOYAGE_ID)
        received: list = []

        async def on_plan_created(event: VoyagePlanCreatedEvent) -> None:
            received.append(event)

        registry = HandlerRegistry()
        registry.on("voyage_plan_created", on_plan_created)

        # Publish event before starting consumer
        event = VoyagePlanCreatedEvent(
            voyage_id=VOYAGE_ID,
            source_role=CrewRole.CAPTAIN,
            payload={"plan_id": str(uuid.uuid4()), "phase_count": 3},
        )
        await mushi.ensure_group(stream, group_name(CrewRole.NAVIGATOR))
        await mushi.publish(stream, event)

        # Run consume_loop as a task with short block time
        task = asyncio.create_task(
            consume_loop(
                mushi,
                stream,
                CrewRole.NAVIGATOR,
                "nav-test",
                registry,
                block_ms=100,
            )
        )

        # Give it time to process
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(received) == 1
        assert received[0].event_id == event.event_id


class TestTrim:
    @pytest.mark.asyncio
    async def test_trim_reduces_stream(self, mushi: DenDenMushi) -> None:
        stream = stream_key(VOYAGE_ID)

        for i in range(10):
            event = VoyagePlanCreatedEvent(
                voyage_id=VOYAGE_ID,
                source_role=CrewRole.CAPTAIN,
                payload={"phase_count": i},
            )
            await mushi.publish(stream, event)

        # Trim to ~5 (approximate)
        await mushi.trim(stream, maxlen=5)

        remaining = await mushi.replay(stream)
        assert len(remaining) <= 6  # approximate allows slight overshoot
