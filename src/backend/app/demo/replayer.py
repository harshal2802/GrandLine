"""Demo voyage replayer (#56).

Publishes the recorded `DEMO_SCRIPT` to `grandline:events:{voyage_id}` with
realistic pacing, updating the voyage's status/phase_status so the Sea Chart
poll and badges keep up. Honors live interventions by re-reading the voyage row
between steps: a **Pause** (status PAUSED) halts the replay until resumed; a
**Cancel** (status CANCELLED) stops it. No LLM provider is involved.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.demo.script import DEMO_SCRIPT, DemoStep, build_events
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.mushi import DenDenMushi
from app.models.enums import VoyageStatus
from app.models.voyage import Voyage

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]
Sleeper = Callable[[float], Awaitable[None]]


class DemoReplayer:
    def __init__(
        self,
        mushi: DenDenMushi,
        session_factory: SessionFactory,
        voyage_id: uuid.UUID,
        *,
        speed: float = 1.0,
        sleep: Sleeper = asyncio.sleep,
        pause_poll_seconds: float = 1.0,
    ) -> None:
        self._mushi = mushi
        self._session_factory = session_factory
        self._voyage_id = voyage_id
        self._speed = speed if speed > 0 else 1.0
        self._sleep = sleep
        self._pause_poll = pause_poll_seconds

    async def run(self) -> str:
        """Replay the script. Returns the terminal reason: 'completed' or
        'cancelled'."""
        stream = stream_key(self._voyage_id)
        for step in DEMO_SCRIPT:
            await self._sleep(step.delay / self._speed)

            gate = await self._await_runnable()
            if gate == "cancelled":
                logger.info("Demo voyage %s cancelled — stopping replay", self._voyage_id)
                return "cancelled"

            for event in build_events(step, self._voyage_id):
                await self._mushi.publish(stream, event)

            await self._apply_changes(step)

        logger.info("Demo voyage %s replay complete", self._voyage_id)
        return "completed"

    async def _await_runnable(self) -> str:
        """Block while the voyage is PAUSED; return 'cancelled' if it is, else
        'running' once it is not paused."""
        while True:
            status = await self._current_status()
            if status == VoyageStatus.CANCELLED.value:
                return "cancelled"
            if status != VoyageStatus.PAUSED.value:
                return "running"
            await self._sleep(self._pause_poll)

    async def _current_status(self) -> str | None:
        async with self._session_factory() as session:
            voyage = await session.get(Voyage, self._voyage_id)
            return voyage.status if voyage is not None else None

    async def _apply_changes(self, step: DemoStep) -> None:
        if step.stage is None and step.phase_status is None:
            return
        async with self._session_factory() as session:
            voyage = await session.get(Voyage, self._voyage_id)
            if voyage is None:
                return
            # Don't clobber a Pause/Cancel that landed during this step.
            if voyage.status in (VoyageStatus.PAUSED.value, VoyageStatus.CANCELLED.value):
                if step.phase_status is None:
                    return
            elif step.stage is not None:
                voyage.status = step.stage
            if step.phase_status is not None:
                voyage.phase_status = {**(voyage.phase_status or {}), **step.phase_status}
            session.add(voyage)
            await session.commit()


# Sentinel marking a seeded demo voyage (no is_demo column / migration needed).
DEMO_TARGET_REPO = "grandline/demo"
