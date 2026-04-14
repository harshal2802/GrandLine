"""Captain Agent REST API endpoints."""

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
from app.schemas.captain import (
    ChartCourseRequest,
    ChartCourseResponse,
    PhaseSpec,
    VoyagePlanResponse,
)
from app.services.captain_service import CaptainService

router = APIRouter(prefix="/voyages/{voyage_id}", tags=["captain"])


async def get_captain_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
) -> CaptainService:
    return CaptainService(dial_router, mushi, session)


@router.post(
    "/plan",
    response_model=ChartCourseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def chart_course(
    voyage_id: uuid.UUID,
    body: ChartCourseRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    captain_service: CaptainService = Depends(get_captain_service),
) -> ChartCourseResponse:
    if voyage.status != VoyageStatus.CHARTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "VOYAGE_NOT_CHARTABLE",
                    "message": (f"Voyage status is {voyage.status}, " "expected CHARTED"),
                }
            },
        )

    plan_model, spec = await captain_service.chart_course(voyage, body.task)

    return ChartCourseResponse(
        voyage_id=voyage_id,
        plan_id=plan_model.id,
        plan=spec,
        version=plan_model.version,
    )


@router.get("/plan", response_model=VoyagePlanResponse)
async def get_plan(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    captain_service: CaptainService = Depends(get_captain_service),
) -> VoyagePlanResponse:
    plan = await captain_service.get_plan(voyage_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "PLAN_NOT_FOUND",
                    "message": "No voyage plan exists for this voyage",
                }
            },
        )

    phases_data = plan.phases.get("phases", [])
    phases = [PhaseSpec.model_validate(p) for p in phases_data]

    return VoyagePlanResponse(
        plan_id=plan.id,
        voyage_id=plan.voyage_id,
        phases=phases,
        version=plan.version,
        created_by=plan.created_by,
        created_at=plan.created_at,
    )
