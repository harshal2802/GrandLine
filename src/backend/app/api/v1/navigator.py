"""Navigator Agent REST API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_authorized_voyage,
    get_current_user,
    get_den_den_mushi,
    get_dial_router,
)
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.router import DialSystemRouter
from app.models import get_db
from app.models.enums import VoyageStatus
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.navigator import (
    DraftPoneglyphsResponse,
    PoneglyphListResponse,
)
from app.schemas.poneglyph import PoneglyphRead
from app.services.captain_service import CaptainService
from app.services.navigator_service import NavigatorError, NavigatorService

router = APIRouter(prefix="/voyages/{voyage_id}", tags=["navigator"])


async def get_navigator_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
) -> NavigatorService:
    return NavigatorService(dial_router, mushi, session)


async def get_navigator_reader(
    session: AsyncSession = Depends(get_db),
) -> NavigatorService:
    """Lightweight dependency for read-only navigator operations."""
    return NavigatorService.reader(session)


async def get_captain_reader(
    session: AsyncSession = Depends(get_db),
) -> CaptainService:
    return CaptainService.reader(session)


@router.post(
    "/poneglyphs",
    response_model=DraftPoneglyphsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def draft_poneglyphs(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    navigator_service: NavigatorService = Depends(get_navigator_service),
    captain_reader: CaptainService = Depends(get_captain_reader),
) -> DraftPoneglyphsResponse:
    if voyage.status != VoyageStatus.CHARTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "VOYAGE_NOT_CHARTABLE",
                    "message": (f"Voyage status is {voyage.status}, expected CHARTED"),
                }
            },
        )

    plan = await captain_reader.get_plan(voyage_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "PLAN_NOT_FOUND",
                    "message": "No voyage plan exists — run Captain first",
                }
            },
        )

    try:
        poneglyphs = await navigator_service.draft_poneglyphs(voyage, plan)
    except NavigatorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc

    return DraftPoneglyphsResponse(
        voyage_id=voyage_id,
        poneglyph_ids=[p.id for p in poneglyphs],
        count=len(poneglyphs),
    )


@router.get("/poneglyphs", response_model=PoneglyphListResponse)
async def get_poneglyphs(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    navigator_service: NavigatorService = Depends(get_navigator_reader),
) -> PoneglyphListResponse:
    poneglyphs = await navigator_service.get_poneglyphs(voyage_id)
    return PoneglyphListResponse(
        voyage_id=voyage_id,
        poneglyphs=[PoneglyphRead.model_validate(p) for p in poneglyphs],
    )
