"""Preview REST API (Phase B0) — run the crew's built app inside the user's Cabin.

Default-deny + owner-scoped: every endpoint resolves the voyage via
``get_authorized_voyage`` (the voyage must belong to the requesting user), and the
preview is keyed on the voyage OWNER's id — there is no path to another user's
preview. Responses are STATUS/logs only (:class:`PreviewInfo` + app stdout/stderr) —
never a secret. The app runs as a long-running process INSIDE the user's gVisor
Cabin; secrets are materialized there and never surfaced here.

- ``POST   /api/v1/voyages/{id}/preview``           — start the preview -> ``PreviewInfo``.
- ``GET    /api/v1/voyages/{id}/preview``           — status (404 if none).
- ``GET    /api/v1/voyages/{id}/preview/logs``      — captured stdout/stderr tail.
- ``GET    /api/v1/voyages/{id}/preview/logs/stream`` — live SSE of NEW log lines (B1).
- ``DELETE /api/v1/voyages/{id}/preview``           — stop (204).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_authorized_voyage
from app.models import get_db
from app.models.voyage import Voyage
from app.services.preview_service import PreviewError, PreviewInfo, PreviewService

router = APIRouter(prefix="/voyages/{voyage_id}/preview", tags=["preview"])

# Poll the captured log tail on a short interval and emit only the delta. Keep the
# loop bounded so a forgotten browser tab cannot pin a generator forever — the
# preview's own hard max-lifetime cap (reaper) is the ultimate backstop, but the
# stream also self-terminates when the preview is stopped/absent or the client drops.
_LOG_POLL_INTERVAL_S = 1.0
_LOG_STREAM_TAIL = 500
_LOG_STREAM_MAX_ITERATIONS = 86_400  # ~24h at 1s — a hard cap on the loop.


def get_preview_service(request: Request) -> PreviewService:
    svc: PreviewService = request.app.state.preview_service
    return svc


def _handle_preview_error(exc: PreviewError) -> HTTPException:
    if exc.code == "CABIN_UNAVAILABLE":
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"error": {"code": exc.code, "message": exc.message}},
    )


@router.post("", response_model=PreviewInfo)
async def start_preview(
    voyage: Voyage = Depends(get_authorized_voyage),
    session: AsyncSession = Depends(get_db),
    service: PreviewService = Depends(get_preview_service),
) -> PreviewInfo:
    """Launch the crew's app as a long-running process in the owner's Cabin."""
    try:
        return await service.start(voyage.user_id, voyage, session, command=None)
    except PreviewError as exc:
        raise _handle_preview_error(exc) from exc


@router.get("", response_model=PreviewInfo)
async def get_preview(
    voyage: Voyage = Depends(get_authorized_voyage),
    service: PreviewService = Depends(get_preview_service),
) -> PreviewInfo:
    """Return the owner's current preview status (404 if none)."""
    info = await service.status(voyage.user_id)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "No preview running"}},
        )
    return info


@router.get("/logs")
async def get_preview_logs(
    tail: int = Query(200, ge=1, le=2000),
    voyage: Voyage = Depends(get_authorized_voyage),
    service: PreviewService = Depends(get_preview_service),
) -> dict[str, str]:
    """Return the captured stdout/stderr tail (app output only — never a secret)."""
    logs = await service.logs(voyage.user_id, tail=tail)
    return {"logs": logs}


@router.get("/logs/stream")
async def stream_preview_logs(
    request: Request,
    voyage: Voyage = Depends(get_authorized_voyage),
    service: PreviewService = Depends(get_preview_service),
) -> StreamingResponse:
    """Stream NEW preview log content over Server-Sent Events (Phase B1).

    Owner-scoped (via ``get_authorized_voyage``, keyed on the voyage OWNER's id).
    Polls ``PreviewService.logs`` on a short interval and emits only the bytes that
    appeared since the last poll as ``data: <line>\\n\\n`` frames (mirrors the
    pipeline SSE shape). Terminates on client disconnect, when the preview is
    stopped/absent, or at the hard iteration cap — so no generator orphans. App
    stdout/stderr only; never a secret (``PreviewInfo``/logs carry none).
    """
    user_id = voyage.user_id

    async def log_generator() -> AsyncGenerator[bytes, None]:
        # Track what we have already sent so each frame is only the NEW delta. The
        # captured tail is a rolling window, so anchor on the longest common prefix
        # rather than a byte offset (a rotated/truncated buffer just re-syncs).
        emitted = ""
        for _ in range(_LOG_STREAM_MAX_ITERATIONS):
            if await request.is_disconnected():
                break

            # No preview (never started or stopped) → close the stream cleanly.
            info = await service.status(user_id)
            if info is None:
                break

            logs = await service.logs(user_id, tail=_LOG_STREAM_TAIL)
            if logs.startswith(emitted):
                delta = logs[len(emitted) :]
            else:
                # Buffer rotated/truncated — re-sync to the current window.
                delta = logs
            emitted = logs

            if delta:
                # Emit per line so the client renders incrementally; keep blank
                # lines out of the SSE framing (a bare ``data:\n\n`` is a no-op).
                for line in delta.splitlines():
                    yield f"data: {line}\n\n".encode()

            await asyncio.sleep(_LOG_POLL_INTERVAL_S)

    return StreamingResponse(log_generator(), media_type="text/event-stream")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def stop_preview(
    voyage: Voyage = Depends(get_authorized_voyage),
    service: PreviewService = Depends(get_preview_service),
) -> Response:
    """Stop the owner's preview (idempotent)."""
    await service.stop(voyage.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
