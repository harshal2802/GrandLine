"""Return Bottle REST API — manually (re)send a voyage's completion outreach.

``POST /api/v1/voyages/{voyage_id}/return-bottle`` re-runs the Phase 22 Return
Bottle for a COMPLETED voyage: posts a summary back to the originating GitHub
issue (Phase 21 ``origin``) and records a Log Book summary for the repo. Useful
when the automatic completion-time outreach failed (e.g. GitHub was down) and the
fleet admiral wants to close the loop by hand.

Default-deny: requires an authenticated user, and the voyage is owner-scoped (a
missing or foreign voyage is 404). A non-COMPLETED voyage is 409.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_authorized_voyage
from app.core.config import settings
from app.models import get_db
from app.models.enums import VoyageStatus
from app.models.voyage import Voyage
from app.services.return_bottle_service import ReturnBottleService

router = APIRouter(prefix="/voyages", tags=["return-bottle"])


async def get_return_bottle_service(
    session: AsyncSession = Depends(get_db),
) -> ReturnBottleService:
    return ReturnBottleService(session, settings)


@router.post("/{voyage_id}/return-bottle")
async def send_return_bottle(
    voyage: Voyage = Depends(get_authorized_voyage),
    service: ReturnBottleService = Depends(get_return_bottle_service),
) -> dict[str, bool]:
    """Manually (re)send the Return Bottle for a COMPLETED voyage.

    Returns ``{"issue_commented": bool, "log_book_recorded": bool}`` — the same
    best-effort result the completion hook produces. 409 if the voyage has not
    completed (the loop can only be closed once the voyage has reached port).
    """
    if voyage.status != VoyageStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "VOYAGE_NOT_COMPLETED",
                    "message": (
                        f"Voyage status is {voyage.status}; a Return Bottle can only "
                        "be sent for a COMPLETED voyage"
                    ),
                }
            },
        )
    return await service.report(voyage)
