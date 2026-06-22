"""Per-user integrations REST API — GitHub device-code OAuth (Phase A3).

Default-deny: every endpoint requires an authenticated user, and the device flow
is per-user — the token resolved on a successful poll is stored in the requesting
user's Sea Chest only. SECURITY: NO endpoint returns the access token. ``start``
returns the transient device/user codes for the client round-trip; ``poll`` returns
``DeviceFlowStatus`` (status + login only) — the token never leaves the vault.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.core.config import settings
from app.models import get_db
from app.models.user import User
from app.schemas.integrations import (
    DeviceFlowPollRequest,
    DeviceFlowStart,
    DeviceFlowStatus,
)
from app.services.github_auth_service import GithubAuthError, GithubAuthService

router = APIRouter(prefix="/integrations", tags=["integrations"])


async def get_github_auth_service(
    session: AsyncSession = Depends(get_db),
) -> GithubAuthService:
    return GithubAuthService(session, settings)


def _handle_github_auth_error(exc: GithubAuthError) -> HTTPException:
    if exc.code == "OAUTH_NOT_CONFIGURED":
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"error": {"code": exc.code, "message": exc.message}},
    )


@router.post("/github/device/start", response_model=DeviceFlowStart)
async def start_github_device_flow(
    user: User = Depends(get_current_user),
    service: GithubAuthService = Depends(get_github_auth_service),
) -> DeviceFlowStart:
    """Begin the GitHub device flow — returns the user_code + verification_uri."""
    try:
        return await service.start_device_flow()
    except GithubAuthError as exc:
        raise _handle_github_auth_error(exc) from exc


@router.post("/github/device/poll", response_model=DeviceFlowStatus)
async def poll_github_device_flow(
    body: DeviceFlowPollRequest,
    user: User = Depends(get_current_user),
    service: GithubAuthService = Depends(get_github_auth_service),
) -> DeviceFlowStatus:
    """Poll for approval; on success vault the token and report the login (no token)."""
    try:
        return await service.poll_device_flow(user.id, body.device_code)
    except GithubAuthError as exc:
        raise _handle_github_auth_error(exc) from exc
