"""Dev FastAPI server with PipelineService.start mocked out.

The real PipelineService.start invokes Captain → Navigator → Doctor →
Shipwrights → Doctor → Helmsman, all of which call real LLM providers
and execute generated code in Docker sandboxes. For Phase 15.4 API
smoke-testing we don't want any of that — we only want to exercise the
HTTP surface and the SSE event framing.

This script monkey-patches `PipelineService.start` with a fast stub that
emits the same five pipeline events to the Redis stream via the injected
DenDenMushi, flips voyage.status through PLANNING → COMPLETED, and
returns. That lets the SSE endpoint replay a realistic event sequence
and the status/pause/cancel endpoints observe lifelike state.

Run via: `make api-mocked` (or `python -m scripts.dev_api_mocked`).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Literal

import uvicorn

from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import (
    PipelineCompletedEvent,
    PipelineStageCompletedEvent,
    PipelineStageEnteredEvent,
    PipelineStartedEvent,
)
from app.models.enums import CrewRole, VoyageStatus
from app.services.pipeline_service import PipelineService

logger = logging.getLogger(__name__)

_STAGES: list[str] = ["PLANNING", "PDD", "TDD", "BUILDING", "REVIEWING", "DEPLOYING"]


async def _mocked_start(
    self: PipelineService,
    voyage: Any,
    user_id: uuid.UUID,
    task: str,
    deploy_tier: Literal["preview"] = "preview",
    max_parallel_shipwrights: int | None = None,
) -> None:
    """Emit synthetic pipeline events for smoke testing — no LLM calls."""
    stream = stream_key(voyage.id)
    logger.info("MOCK pipeline start for voyage=%s task=%r", voyage.id, task)

    async def _publish(event: Any) -> None:
        try:
            await self._mushi.publish(stream, event)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("MOCK publish failed")

    await _publish(
        PipelineStartedEvent(
            voyage_id=voyage.id,
            source_role=CrewRole.CAPTAIN,
            payload={
                "task": task,
                "deploy_tier": deploy_tier,
                "max_parallel_shipwrights": max_parallel_shipwrights or 1,
            },
        )
    )

    voyage.status = VoyageStatus.PLANNING.value
    try:
        self._session.add(voyage)  # type: ignore[attr-defined]
        await self._session.commit()  # type: ignore[attr-defined]
    except Exception:
        logger.exception("MOCK status update failed (PLANNING)")

    for stage in _STAGES:
        await _publish(
            PipelineStageEnteredEvent(
                voyage_id=voyage.id,
                source_role=CrewRole.CAPTAIN,
                payload={"stage": stage, "voyage_status": voyage.status},
            )
        )
        await asyncio.sleep(0.3)
        await _publish(
            PipelineStageCompletedEvent(
                voyage_id=voyage.id,
                source_role=CrewRole.CAPTAIN,
                payload={"stage": stage, "duration_seconds": 0.3, "skipped": False},
            )
        )

    voyage.status = VoyageStatus.COMPLETED.value
    try:
        self._session.add(voyage)
        await self._session.commit()
    except Exception:
        logger.exception("MOCK status update failed (COMPLETED)")

    await _publish(
        PipelineCompletedEvent(
            voyage_id=voyage.id,
            source_role=CrewRole.CAPTAIN,
            payload={
                "duration_seconds": len(_STAGES) * 0.3,
                "deployment_url": "http://preview.voyage.local",
            },
        )
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # Patch before the app is imported into uvicorn's workers.
    PipelineService.start = _mocked_start  # type: ignore[method-assign]
    logger.info("PipelineService.start replaced with synthetic-event stub")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
