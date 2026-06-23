"""Preview REST API (Phase B0) — run the crew's built app inside the user's Cabin.

Default-deny + owner-scoped: every endpoint resolves the voyage via
``get_authorized_voyage`` (the voyage must belong to the requesting user), and the
preview is keyed on the voyage OWNER's id — there is no path to another user's
preview. Responses are STATUS/logs only (:class:`PreviewInfo` + app stdout/stderr) —
never a secret. The app runs as a long-running process INSIDE the user's gVisor
Cabin; secrets are materialized there and never surfaced here.

- ``POST   /api/v1/voyages/{id}/preview``      — start the preview -> ``PreviewInfo``.
- ``GET    /api/v1/voyages/{id}/preview``      — status (404 if none).
- ``GET    /api/v1/voyages/{id}/preview/logs`` — captured stdout/stderr tail.
- ``DELETE /api/v1/voyages/{id}/preview``      — stop (204).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_authorized_voyage
from app.models import get_db
from app.models.voyage import Voyage
from app.services.preview_service import PreviewError, PreviewInfo, PreviewService

router = APIRouter(prefix="/voyages/{voyage_id}/preview", tags=["preview"])


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


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def stop_preview(
    voyage: Voyage = Depends(get_authorized_voyage),
    service: PreviewService = Depends(get_preview_service),
) -> Response:
    """Stop the owner's preview (idempotent)."""
    await service.stop(voyage.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
