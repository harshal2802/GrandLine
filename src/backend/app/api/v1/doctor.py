"""Doctor Agent REST API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_authorized_voyage,
    get_current_user,
    get_den_den_mushi,
    get_dial_router,
    get_execution_service,
    get_git_service,
)
from app.api.v1.navigator import get_navigator_reader
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.router import DialSystemRouter
from app.models import get_db
from app.models.enums import VoyageStatus
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.doctor import (
    HealthCheckListResponse,
    ValidateCodeRequest,
    ValidationResultResponse,
    WriteHealthChecksResponse,
)
from app.schemas.health_check import HealthCheckRead
from app.services.doctor_service import DoctorError, DoctorService
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService
from app.services.navigator_service import NavigatorService

router = APIRouter(prefix="/voyages/{voyage_id}", tags=["doctor"])


async def get_doctor_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
    execution_service: ExecutionService = Depends(get_execution_service),
    git_service: GitService = Depends(get_git_service),
) -> DoctorService:
    return DoctorService(
        dial_router,
        mushi,
        session,
        execution_service=execution_service,
        git_service=git_service,
    )


async def get_doctor_reader(
    session: AsyncSession = Depends(get_db),
) -> DoctorService:
    """Lightweight dependency for read-only doctor operations."""
    return DoctorService.reader(session)


@router.post(
    "/health-checks",
    response_model=WriteHealthChecksResponse,
    status_code=status.HTTP_201_CREATED,
)
async def write_health_checks(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    doctor_service: DoctorService = Depends(get_doctor_service),
    navigator_reader: NavigatorService = Depends(get_navigator_reader),
) -> WriteHealthChecksResponse:
    if voyage.status != VoyageStatus.CHARTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "VOYAGE_NOT_CHARTABLE",
                    "message": f"Voyage status is {voyage.status}, expected CHARTED",
                }
            },
        )

    poneglyphs = await navigator_reader.get_poneglyphs(voyage_id)
    if not poneglyphs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "PONEGLYPHS_NOT_FOUND",
                    "message": "No Poneglyphs exist — run Navigator first",
                }
            },
        )

    try:
        health_checks = await doctor_service.write_health_checks(voyage, poneglyphs, user.id)
    except DoctorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc

    return WriteHealthChecksResponse(
        voyage_id=voyage_id,
        health_check_ids=[hc.id for hc in health_checks],
        count=len(health_checks),
    )


@router.get("/health-checks", response_model=HealthCheckListResponse)
async def get_health_checks(
    voyage_id: uuid.UUID,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    doctor_service: DoctorService = Depends(get_doctor_reader),
) -> HealthCheckListResponse:
    health_checks = await doctor_service.get_health_checks(voyage_id)
    return HealthCheckListResponse(
        voyage_id=voyage_id,
        health_checks=[HealthCheckRead.model_validate(hc) for hc in health_checks],
    )


@router.post(
    "/validation",
    response_model=ValidationResultResponse,
    status_code=status.HTTP_200_OK,
)
async def run_validation(
    voyage_id: uuid.UUID,
    body: ValidateCodeRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    doctor_service: DoctorService = Depends(get_doctor_service),
) -> ValidationResultResponse:
    if voyage.status != VoyageStatus.CHARTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "VOYAGE_NOT_CHARTABLE",
                    "message": f"Voyage status is {voyage.status}, expected CHARTED",
                }
            },
        )

    try:
        return await doctor_service.validate_code(voyage, user.id, body.files)
    except DoctorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
