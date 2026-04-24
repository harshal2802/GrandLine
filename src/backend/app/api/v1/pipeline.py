"""Pipeline REST + SSE API endpoints.

Thin HTTP surface over `PipelineService`. `POST /start` spawns the graph
via `asyncio.create_task` and records the task in
`app.state.pipeline_tasks: dict[uuid.UUID, asyncio.Task]`. The task's
done-callback removes itself from the registry on completion — success,
failure, or cancellation.

Note: `app.state.pipeline_tasks` is process-local; multi-worker deployments
are out of scope for v1.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_authorized_voyage,
    get_current_user,
    get_den_den_mushi,
    get_pipeline_service,
    get_pipeline_service_reader,
)
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.mushi import DenDenMushi
from app.models import get_db
from app.models.enums import VoyageStatus
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.pipeline import (
    PipelineEventEnvelope,
    PipelineStatusSnapshot,
    StartVoyageRequest,
    StartVoyageResponse,
)
from app.services.pipeline_guards import PipelineError
from app.services.pipeline_service import PipelineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voyages/{voyage_id}", tags=["pipeline"])


_PIPELINE_ERROR_STATUS: dict[str, int] = {
    "VOYAGE_NOT_PLANNABLE": status.HTTP_409_CONFLICT,
    "PIPELINE_ALREADY_RUNNING": status.HTTP_409_CONFLICT,
    "INVALID_CONCURRENCY": status.HTTP_400_BAD_REQUEST,
}

_TERMINAL_STATUSES = frozenset(
    {
        VoyageStatus.COMPLETED.value,
        VoyageStatus.FAILED.value,
        VoyageStatus.CANCELLED.value,
    }
)

_SSE_BLOCK_MS = 1000


def _pipeline_http_exception(exc: PipelineError) -> HTTPException:
    code = _PIPELINE_ERROR_STATUS.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY)
    return HTTPException(
        status_code=code,
        detail={"error": {"code": exc.code, "message": exc.message}},
    )


def _already_running(request: Request, voyage_id: uuid.UUID) -> bool:
    registry: dict[uuid.UUID, asyncio.Task[None]] = getattr(request.app.state, "pipeline_tasks", {})
    existing = registry.get(voyage_id)
    return existing is not None and not existing.done()


@router.post(
    "/start",
    response_model=StartVoyageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_voyage(
    voyage_id: uuid.UUID,
    body: StartVoyageRequest,
    request: Request,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> StartVoyageResponse:
    registry: dict[uuid.UUID, asyncio.Task[None]] = request.app.state.pipeline_tasks

    if _already_running(request, voyage_id):
        raise _pipeline_http_exception(
            PipelineError(
                "PIPELINE_ALREADY_RUNNING",
                f"Pipeline for voyage {voyage_id} is already running",
            )
        )

    # Additional 409 guard: completed voyages cannot be re-run. Re-run workflow
    # is cancel + restart — out of scope for v1.
    if voyage.status == VoyageStatus.COMPLETED.value:
        raise _pipeline_http_exception(
            PipelineError(
                "VOYAGE_NOT_PLANNABLE",
                f"Voyage status is {voyage.status}; cannot re-run a completed voyage",
            )
        )

    task = asyncio.create_task(
        pipeline_service.start(
            voyage,
            user.id,
            body.task,
            body.deploy_tier,
            body.max_parallel_shipwrights,
        )
    )
    registry[voyage_id] = task

    def _cleanup(_t: asyncio.Task[None]) -> None:
        registry.pop(voyage_id, None)

    task.add_done_callback(_cleanup)

    return StartVoyageResponse(voyage_id=voyage_id, status=voyage.status)


@router.post("/pause", status_code=status.HTTP_200_OK)
async def pause_voyage(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> dict[str, object]:
    try:
        await pipeline_service.pause(voyage)
    except PipelineError as exc:
        raise _pipeline_http_exception(exc) from exc
    return {"voyage_id": str(voyage_id), "status": voyage.status}


@router.post("/cancel", status_code=status.HTTP_200_OK)
async def cancel_voyage(
    voyage_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> dict[str, object]:
    try:
        await pipeline_service.cancel(voyage)
    except PipelineError as exc:
        raise _pipeline_http_exception(exc) from exc

    registry: dict[uuid.UUID, asyncio.Task[None]] = getattr(request.app.state, "pipeline_tasks", {})
    task = registry.get(voyage_id)
    if task is not None and not task.done():
        task.cancel()

    return {"voyage_id": str(voyage_id), "status": voyage.status}


@router.get(
    "/status",
    response_model=PipelineStatusSnapshot,
)
async def get_pipeline_status(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    pipeline_reader: PipelineService = Depends(get_pipeline_service_reader),
) -> PipelineStatusSnapshot:
    return await pipeline_reader.get_status(voyage)


@router.get("/stream")
async def stream_events(
    voyage_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Server-Sent Events stream of pipeline events for a voyage.

    One fresh ephemeral consumer group per connection (replay-from-start).
    Terminates on voyage terminal status (COMPLETED | FAILED | CANCELLED)
    or client disconnect. No `last-event-id` resume in v1.
    """
    stream = stream_key(voyage_id)
    group = f"sse-{uuid.uuid4().hex}"
    consumer = f"sse-{uuid.uuid4().hex[:8]}"

    async def event_generator() -> AsyncGenerator[bytes, None]:
        await mushi.ensure_group(stream, group)
        try:
            while True:
                if await request.is_disconnected():
                    break

                batch = await mushi.read(
                    stream=stream,
                    group=group,
                    consumer=consumer,
                    count=10,
                    block_ms=_SSE_BLOCK_MS,
                )
                for msg_id, event in batch:
                    envelope = PipelineEventEnvelope(
                        msg_id=msg_id,
                        event=event.model_dump(mode="json"),
                    )
                    yield f"data: {envelope.model_dump_json()}\n\n".encode()
                    await mushi.ack(stream, group, msg_id)

                # Re-fetch voyage status; close on terminal.
                refreshed = await session.get(Voyage, voyage.id)
                if refreshed is not None and refreshed.status in _TERMINAL_STATUSES:
                    break
        finally:
            # Best-effort: destroy the ephemeral group so Redis doesn't
            # accumulate per-connection groups.
            try:
                await mushi._redis.xgroup_destroy(stream, group)  # noqa: SLF001
            except Exception:  # pragma: no cover - best effort cleanup
                logger.warning(
                    "Failed to destroy SSE consumer group %s on stream %s",
                    group,
                    stream,
                    exc_info=True,
                )

    return StreamingResponse(event_generator(), media_type="text/event-stream")
