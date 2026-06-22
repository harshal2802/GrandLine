"""Message in a Bottle — external triggers REST API.

``POST /api/v1/triggers/github`` ingests a signed GitHub ``issues`` webhook and
charts a course from the issue. This endpoint is the single deliberate relaxation
of the default-deny posture: it carries NO Bearer token and is instead
**HMAC-verified** (allowlisted by exact path in ``PUBLIC_PATHS``). An unconfigured
or invalid signature is rejected — an unverified payload is never accepted.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import get_db
from app.schemas.trigger import GithubIssueWebhook, TriggerResult
from app.services.trigger_service import TriggerError, TriggerService

router = APIRouter(prefix="/triggers", tags=["triggers"])

# Map a TriggerError code to the HTTP status the API surfaces.
_TRIGGER_ERROR_STATUS: dict[str, int] = {
    "TRIGGER_USER_UNCONFIGURED": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "TRIGGER_USER_NOT_FOUND": status.HTTP_503_SERVICE_UNAVAILABLE,
}


async def get_trigger_service(
    session: AsyncSession = Depends(get_db),
) -> TriggerService:
    return TriggerService(session)


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


@router.post("/github", response_model=TriggerResult)
async def github_trigger(
    request: Request,
    response: Response,
    service: TriggerService = Depends(get_trigger_service),
) -> TriggerResult:
    """Ingest a signed GitHub ``issues`` webhook and chart a course from the issue.

    The raw body is read BEFORE JSON parsing so the signature is verified over the
    exact bytes GitHub signed. Flow: verify signature (401 on failure or unconfigured
    secret) -> parse -> gate via ``should_trigger`` (200 ``ignored`` if not a
    trigger) -> resolve the configured owning user -> chart a CHARTED voyage (201).
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not service.verify_github_signature(
        raw_body, signature, settings.github_webhook_secret
    ):
        raise _error(
            "INVALID_SIGNATURE",
            "Webhook signature verification failed",
            status.HTTP_401_UNAUTHORIZED,
        )

    payload = GithubIssueWebhook.model_validate_json(raw_body)

    if not service.should_trigger(payload):
        return TriggerResult(
            status="ignored",
            reason=f"action {payload.action!r} or missing label {settings.trigger_label!r}",
        )

    try:
        user = await service.resolve_trigger_user()
    except TriggerError as exc:
        raise _error(
            exc.code,
            exc.message,
            _TRIGGER_ERROR_STATUS.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        )

    voyage = await service.ingest_github_issue(payload, user)
    response.status_code = status.HTTP_201_CREATED
    return TriggerResult(status="charted", voyage_id=voyage.id)
