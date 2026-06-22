"""Sea Chest REST API — connect, inspect, and disconnect per-user credentials.

Default-deny: every endpoint requires an authenticated user, and every operation
is scoped to the requesting user's own credentials (owner isolation). The API
exposes STATUS only — it NEVER returns the secret or the ciphertext. Decryption
is an internal service concern (``SeaChestService.reveal``) for the Cabin/adapters
in later phases.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.core.config import settings
from app.models import get_db
from app.models.user import User
from app.schemas.sea_chest import CredentialKind, CredentialStatus, SeaChestConnectRequest
from app.services.sea_chest_service import SeaChestError, SeaChestService

router = APIRouter(prefix="/sea-chest", tags=["sea-chest"])

# The kinds the path parameter accepts, kept in lock-step with ``CredentialKind``.
_ALLOWED_KINDS = frozenset(("claude_code", "github"))


async def get_sea_chest_service(
    session: AsyncSession = Depends(get_db),
) -> SeaChestService:
    return SeaChestService(session, settings)


def _validate_kind(kind: str) -> None:
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_KIND",
                    "message": "Unknown credential kind",
                }
            },
        )


@router.get("", response_model=list[CredentialStatus])
async def list_credentials(
    user: User = Depends(get_current_user),
    service: SeaChestService = Depends(get_sea_chest_service),
) -> list[CredentialStatus]:
    """List the requesting user's connected credentials (STATUS only — no secrets)."""
    return await service.status(user.id)


@router.put("/{kind}", response_model=CredentialStatus)
async def connect_credential(
    kind: CredentialKind,
    body: SeaChestConnectRequest,
    user: User = Depends(get_current_user),
    service: SeaChestService = Depends(get_sea_chest_service),
) -> CredentialStatus:
    """Store or replace the credential for ``kind`` (returns STATUS, never the secret)."""
    _validate_kind(kind)
    if body.kind != kind:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "KIND_MISMATCH",
                    "message": "Body kind does not match the path kind",
                }
            },
        )
    return await service.store(user.id, kind, body.secret, label=body.label)


@router.delete(
    "/{kind}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def disconnect_credential(
    kind: CredentialKind,
    user: User = Depends(get_current_user),
    service: SeaChestService = Depends(get_sea_chest_service),
) -> Response:
    """Disconnect (delete) the requesting user's credential for ``kind``."""
    _validate_kind(kind)
    try:
        await service.delete(user.id, kind)
    except SeaChestError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
