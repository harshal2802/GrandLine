"""Per-user integrations REST API — GitHub device-code OAuth (Phase A3) + Claude
Code device-login in the Cabin (Phase C0).

Default-deny: every endpoint requires an authenticated user, and each flow is
per-user — the token resolved on a successful poll is stored in the requesting
user's Sea Chest only. SECURITY: NO endpoint returns the access token. The GitHub
``start`` returns the transient device/user codes; ``poll`` returns
``DeviceFlowStatus`` (status + login only). The Claude ``login/start`` returns the
verification URL + an opaque ``login_id``; ``login/poll`` returns
``ClaudeLoginStatus`` (status + label only) — the ``CLAUDE_CODE_OAUTH_TOKEN`` never
leaves the Sea Chest.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.core.config import settings
from app.models import get_db
from app.models.user import User
from app.schemas.integrations import (
    ClaudeLoginPollRequest,
    ClaudeLoginStart,
    ClaudeLoginStatus,
    DeviceFlowPollRequest,
    DeviceFlowStart,
    DeviceFlowStatus,
)
from app.services.claude_auth_service import ClaudeAuthError, ClaudeAuthService
from app.services.github_auth_service import GithubAuthError, GithubAuthService

router = APIRouter(prefix="/integrations", tags=["integrations"])


async def get_github_auth_service(
    session: AsyncSession = Depends(get_db),
) -> GithubAuthService:
    return GithubAuthService(session, settings)


def get_claude_auth_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ClaudeAuthService:
    # The Cabin runner lives on app.state (single-worker v1, like the other
    # backends); the login command runs inside the requesting user's Cabin.
    cabin_service = request.app.state.cabin_service
    return ClaudeAuthService(session, settings, cabin_service=cabin_service)


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


def _handle_claude_auth_error(exc: ClaudeAuthError) -> HTTPException:
    if exc.code == "CABIN_UNAVAILABLE":
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"error": {"code": exc.code, "message": exc.message}},
    )


@router.post("/claude/login/start", response_model=ClaudeLoginStart)
async def start_claude_login(
    user: User = Depends(get_current_user),
    service: ClaudeAuthService = Depends(get_claude_auth_service),
) -> ClaudeLoginStart:
    """Begin the Claude Code device-login in the user's Cabin — returns the URL + login_id."""
    try:
        return await service.start_login(user.id)
    except ClaudeAuthError as exc:
        raise _handle_claude_auth_error(exc) from exc


@router.post("/claude/login/poll", response_model=ClaudeLoginStatus)
async def poll_claude_login(
    body: ClaudeLoginPollRequest,
    user: User = Depends(get_current_user),
    service: ClaudeAuthService = Depends(get_claude_auth_service),
) -> ClaudeLoginStatus:
    """Poll for approval; on success vault the token and report status (no token)."""
    try:
        return await service.poll_login(user.id, body.login_id)
    except ClaudeAuthError as exc:
        raise _handle_claude_auth_error(exc) from exc
