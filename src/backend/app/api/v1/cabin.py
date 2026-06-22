"""Cabin REST API (Phase 0b) — the requesting user's own persistent Cabin.

Default-deny: every endpoint requires an authenticated user, and a user only ever
touches THEIR Cabin (there is no path to another user's Cabin — the registry is
keyed on ``user.id``). Responses are STATUS only (:class:`CabinStatus`) — never a
secret value. Secrets are materialized INSIDE the Cabin from the Sea Chest and are
never surfaced here.

- ``GET /api/v1/cabin`` — my Cabin's status (404 if none).
- ``POST /api/v1/cabin`` — ensure/wake my Cabin (materializes my Sea Chest secrets)
  and return its status.
- ``DELETE /api/v1/cabin`` — destroy my Cabin (204; 404 if none).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.cabin.backend import CabinError, CabinStatus
from app.models import get_db
from app.models.user import User
from app.services.cabin_service import CabinService

router = APIRouter(prefix="/cabin", tags=["cabin"])


def get_cabin_service(request: Request) -> CabinService:
    svc: CabinService = request.app.state.cabin_service
    return svc


@router.get("", response_model=CabinStatus)
async def get_cabin(
    user: User = Depends(get_current_user),
    service: CabinService = Depends(get_cabin_service),
) -> CabinStatus:
    """Return the requesting user's Cabin status (STATUS only — no secrets)."""
    try:
        return await service.status(user.id)
    except CabinError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )


@router.post("", response_model=CabinStatus)
async def ensure_cabin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    service: CabinService = Depends(get_cabin_service),
) -> CabinStatus:
    """Ensure/wake the requesting user's Cabin and return its status."""
    return await service.ensure(user.id, session)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def destroy_cabin(
    user: User = Depends(get_current_user),
    service: CabinService = Depends(get_cabin_service),
) -> Response:
    """Destroy the requesting user's Cabin."""
    try:
        await service.destroy(user.id)
    except CabinError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
