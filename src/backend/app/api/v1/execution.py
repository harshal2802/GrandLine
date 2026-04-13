"""Execution Service REST API endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.v1.dependencies import get_authorized_voyage, get_current_user, get_execution_service
from app.execution.backend import ExecutionError
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.execution import ExecutionRequest, ExecutionResult, SandboxStatus
from app.services.execution_service import ExecutionService

router = APIRouter(tags=["execution"])


@router.post(
    "/voyages/{voyage_id}/execute",
    response_model=ExecutionResult,
)
async def execute_code(
    voyage_id: uuid.UUID,
    body: ExecutionRequest,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionResult:
    try:
        return await execution_service.run(user.id, body)
    except ExecutionError as exc:
        msg = str(exc)
        if "Invalid file path" in msg or "File too large" in msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "INVALID_REQUEST", "message": msg}},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "EXECUTION_ERROR", "message": msg}},
        ) from exc


@router.get(
    "/sandbox/status",
    response_model=SandboxStatus,
)
async def get_sandbox_status(
    user: User = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> SandboxStatus:
    try:
        return await execution_service.get_sandbox_status(user.id)
    except ExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SANDBOX_NOT_FOUND", "message": str(exc)}},
        ) from exc


@router.delete(
    "/sandbox",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def destroy_sandbox(
    user: User = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> Response:
    try:
        await execution_service.destroy_sandbox(user.id)
    except ExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SANDBOX_NOT_FOUND", "message": str(exc)}},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
