"""Shipwright Agent REST API endpoints."""

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
from app.api.v1.doctor import get_doctor_reader
from app.api.v1.navigator import get_navigator_reader
from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.router import DialSystemRouter
from app.models import get_db
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.build_artifact import BuildArtifactRead
from app.schemas.shipwright import (
    BuildArtifactListResponse,
    BuildResultResponse,
)
from app.services.doctor_service import DoctorService
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService
from app.services.navigator_service import NavigatorService
from app.services.shipwright_service import ShipwrightError, ShipwrightService

router = APIRouter(prefix="/voyages/{voyage_id}", tags=["shipwright"])


async def get_shipwright_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
    execution_service: ExecutionService = Depends(get_execution_service),
    git_service: GitService = Depends(get_git_service),
) -> ShipwrightService:
    return ShipwrightService(
        dial_router,
        mushi,
        session,
        execution_service=execution_service,
        git_service=git_service,
    )


async def get_shipwright_reader(
    session: AsyncSession = Depends(get_db),
) -> ShipwrightService:
    return ShipwrightService.reader(session)


@router.post(
    "/phases/{phase_number}/build",
    response_model=BuildResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def build_phase(
    voyage_id: uuid.UUID,
    phase_number: int,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    shipwright_service: ShipwrightService = Depends(get_shipwright_service),
    navigator_reader: NavigatorService = Depends(get_navigator_reader),
    doctor_reader: DoctorService = Depends(get_doctor_reader),
) -> BuildResultResponse:
    poneglyphs = await navigator_reader.get_poneglyphs(voyage_id)
    poneglyph = next((p for p in poneglyphs if p.phase_number == phase_number), None)
    if poneglyph is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "PONEGLYPH_NOT_FOUND",
                    "message": (f"No Poneglyph for voyage {voyage_id} phase {phase_number}"),
                }
            },
        )

    phase_health_checks = await doctor_reader.get_health_checks(voyage_id, phase_number)
    if not phase_health_checks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "HEALTH_CHECKS_NOT_FOUND",
                    "message": (f"No health checks for voyage {voyage_id} phase {phase_number}"),
                }
            },
        )

    try:
        return await shipwright_service.build_code(
            voyage, phase_number, poneglyph, phase_health_checks, user.id
        )
    except ShipwrightError as exc:
        status_code = (
            status.HTTP_409_CONFLICT
            if exc.code == "PHASE_NOT_BUILDABLE"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc


@router.get(
    "/phases/{phase_number}/build",
    response_model=BuildResultResponse,
)
async def get_phase_build(
    voyage_id: uuid.UUID,
    phase_number: int,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    shipwright_reader: ShipwrightService = Depends(get_shipwright_reader),
) -> BuildResultResponse:
    run = await shipwright_reader.get_latest_run(voyage_id, phase_number)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "BUILD_NOT_FOUND",
                    "message": (f"No build run for voyage {voyage_id} phase {phase_number}"),
                }
            },
        )

    artifacts = await shipwright_reader.get_build_artifacts(voyage_id, phase_number)
    summary = (run.output or "")[-500:]
    return BuildResultResponse(
        voyage_id=voyage_id,
        phase_number=phase_number,
        shipwright_run_id=run.id,
        status=run.status,
        iteration_count=run.iteration_count,
        passed_count=run.passed_count,
        failed_count=run.failed_count,
        total_count=run.total_count,
        file_count=len(artifacts),
        summary=summary,
    )


@router.get("/build-artifacts", response_model=BuildArtifactListResponse)
async def list_build_artifacts(
    voyage_id: uuid.UUID,
    phase_number: int | None = None,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    shipwright_reader: ShipwrightService = Depends(get_shipwright_reader),
) -> BuildArtifactListResponse:
    artifacts = await shipwright_reader.get_build_artifacts(voyage_id, phase_number)
    return BuildArtifactListResponse(
        voyage_id=voyage_id,
        phase_number=phase_number,
        artifacts=[BuildArtifactRead.model_validate(a) for a in artifacts],
    )
