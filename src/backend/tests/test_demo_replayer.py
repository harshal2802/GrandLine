"""Tests for the demo replayer's pacing + intervention gating (#56)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.demo.replayer import DemoReplayer
from app.demo.script import DEMO_SCRIPT

VOYAGE_ID = uuid.uuid4()


class _Voyage:
    def __init__(self, status: str = "CHARTED") -> None:
        self.status = status
        self.phase_status: dict[str, str] = {}


class _Session:
    def __init__(self, voyage: _Voyage) -> None:
        self._voyage = voyage

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def get(self, _model: object, _vid: uuid.UUID) -> _Voyage:
        return self._voyage

    def add(self, _obj: object) -> None:
        pass

    async def commit(self) -> None:
        pass


def _factory(voyage: _Voyage):
    return lambda: _Session(voyage)


@pytest.mark.asyncio
async def test_replays_all_events_in_order_and_completes() -> None:
    voyage = _Voyage("CHARTED")
    mushi = AsyncMock()
    mushi.publish = AsyncMock(return_value="1-0")

    replayer = DemoReplayer(mushi, _factory(voyage), VOYAGE_ID, speed=1000, sleep=AsyncMock())
    result = await replayer.run()

    assert result == "completed"
    # Two events per step (crew_action_recorded + typed).
    assert mushi.publish.await_count == len(DEMO_SCRIPT) * 2
    first_event = mushi.publish.await_args_list[0].args[1]
    assert first_event.event_type == "crew_action_recorded"
    # Status + phase progression were applied.
    assert voyage.status == "COMPLETED"
    assert voyage.phase_status == {"1": "BUILT", "2": "BUILT", "3": "BUILT", "4": "BUILT"}


@pytest.mark.asyncio
async def test_cancel_stops_the_replay() -> None:
    voyage = _Voyage("CANCELLED")
    mushi = AsyncMock()
    mushi.publish = AsyncMock()

    replayer = DemoReplayer(mushi, _factory(voyage), VOYAGE_ID, speed=1000, sleep=AsyncMock())
    result = await replayer.run()

    assert result == "cancelled"
    mushi.publish.assert_not_awaited()  # stopped before publishing the first step


@pytest.mark.asyncio
async def test_pause_blocks_until_resumed() -> None:
    voyage = _Voyage("PAUSED")
    mushi = AsyncMock()
    mushi.publish = AsyncMock()

    pause_polls = 0

    async def sleep(secs: float) -> None:
        nonlocal pause_polls
        # The pause poll uses pause_poll_seconds (0.5); flip to running after one
        # poll so the replay proceeds. Step delays are tiny (speed=1000).
        if abs(secs - 0.5) < 1e-9:
            pause_polls += 1
            voyage.status = "BUILDING"

    replayer = DemoReplayer(
        mushi,
        _factory(voyage),
        VOYAGE_ID,
        speed=1000,
        sleep=sleep,
        pause_poll_seconds=0.5,
    )
    result = await replayer.run()

    assert result == "completed"
    assert pause_polls >= 1  # it actually waited on the pause at least once
    assert mushi.publish.await_count == len(DEMO_SCRIPT) * 2


@pytest.mark.asyncio
async def test_apply_changes_does_not_clobber_a_concurrent_pause() -> None:
    # If a Pause lands mid-step, the status update must not overwrite PAUSED.
    voyage = _Voyage("PAUSED")
    mushi = AsyncMock()
    mushi.publish = AsyncMock()

    replayer = DemoReplayer(mushi, _factory(voyage), VOYAGE_ID, sleep=AsyncMock())
    # Directly exercise _apply_changes with a stage-changing step.
    stage_step = next(s for s in DEMO_SCRIPT if s.stage == "PDD")
    await replayer._apply_changes(stage_step)

    assert voyage.status == "PAUSED"  # not flipped to PDD
