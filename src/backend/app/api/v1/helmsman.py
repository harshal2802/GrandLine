"""Helmsman Agent REST API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    get_authorized_voyage,
    get_current_user,
    get_den_den_mushi,
    get_deployment_backend,
    get_dial_router,
    get_git_service,
)
from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.backend import DeploymentBackend
from app.dial_system.router import DialSystemRouter
from app.models import get_db
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.deployment import (
    DeploymentListResponse,
    DeploymentRead,
    DeploymentResponse,
    DeploymentTier,
    DeployRequest,
    RollbackRequest,
)
from app.services.git_service import GitService
from app.services.helmsman_service import HelmsmanError, HelmsmanService

router = APIRouter(prefix="/voyages/{voyage_id}", tags=["helmsman"])


_HELMSMAN_ERROR_STATUS: dict[str, int] = {
    "APPROVAL_REQUIRED": status.HTTP_403_FORBIDDEN,
    "VOYAGE_NOT_DEPLOYABLE": status.HTTP_409_CONFLICT,
    "NO_PREVIOUS_DEPLOYMENT": status.HTTP_404_NOT_FOUND,
}


def _helmsman_http_exception(exc: HelmsmanError) -> HTTPException:
    code = _HELMSMAN_ERROR_STATUS.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY)
    return HTTPException(
        status_code=code,
        detail={"error": {"code": exc.code, "message": exc.message}},
    )


async def get_helmsman_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
    deployment_backend: DeploymentBackend = Depends(get_deployment_backend),
    git_service: GitService = Depends(get_git_service),
) -> HelmsmanService:
    return HelmsmanService(
        dial_router,
        mushi,
        session,
        deployment_backend=deployment_backend,
        git_service=git_service,
    )


async def get_helmsman_reader(
    session: AsyncSession = Depends(get_db),
) -> HelmsmanService:
    return HelmsmanService.reader(session)


@router.post(
    "/deploy",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def deploy_voyage(
    voyage_id: uuid.UUID,
    body: DeployRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    helmsman_service: HelmsmanService = Depends(get_helmsman_service),
) -> DeploymentResponse:
    try:
        return await helmsman_service.deploy(
            voyage=voyage,
            tier=body.tier,
            user_id=user.id,
            git_ref=body.git_ref,
            approved_by=body.approved_by,
        )
    except HelmsmanError as exc:
        raise _helmsman_http_exception(exc) from exc


@router.post(
    "/rollback",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rollback_voyage(
    voyage_id: uuid.UUID,
    body: RollbackRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    helmsman_service: HelmsmanService = Depends(get_helmsman_service),
) -> DeploymentResponse:
    try:
        return await helmsman_service.rollback(
            voyage=voyage,
            tier=body.tier,
            user_id=user.id,
        )
    except HelmsmanError as exc:
        raise _helmsman_http_exception(exc) from exc


@router.get("/deployments", response_model=DeploymentListResponse)
async def list_deployments(
    voyage_id: uuid.UUID,
    tier: DeploymentTier | None = None,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    helmsman_reader: HelmsmanService = Depends(get_helmsman_reader),
) -> DeploymentListResponse:
    rows = await helmsman_reader.get_deployments(voyage_id, tier)
    return DeploymentListResponse(
        voyage_id=voyage_id,
        tier=tier,
        deployments=[DeploymentRead.model_validate(r) for r in rows],
    )
