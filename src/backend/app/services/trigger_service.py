"""TriggerService — Message in a Bottle: chart a course from an external signal.

PandaOS's flagship demo starts work from an external signal (an email / a GitHub
issue) rather than a human typing a task. GrandLine adapts this as an inbound,
**HMAC-verified** GitHub issue webhook that charts a course and records **origin**
metadata on the voyage — the canonical provenance record Phase 22 ("Return
Bottle") reads to reply back to the originating issue.

The webhook carries no GrandLine identity, so the owning user is resolved from
configuration (``trigger_default_user_email``). Signature verification is a
module-level function so it is unit-testable in isolation, and the comparison is
constant-time — an unverified payload is never accepted.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.voyages import _default_dial_config
from app.core.config import settings
from app.models.enums import VoyageStatus
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.trigger import GithubIssueWebhook

# Actions on a GitHub issue that may chart a course (others are ignored).
_TRIGGER_ACTIONS = {"opened", "labeled"}


def verify_github_signature(
    raw_body: bytes,
    signature_header: str | None,
    secret: str | None,
) -> bool:
    """Verify a GitHub ``X-Hub-Signature-256`` header against the raw body.

    GitHub signs each delivery with HMAC-SHA256 over the exact request bytes and
    sends the digest as ``sha256=<hex>``. We recompute it and compare
    **constant-time** (``hmac.compare_digest``) to avoid leaking via timing.

    ``secret is None`` (webhook unconfigured) -> ``False``: we never accept an
    unverified payload. A missing or malformed header is likewise rejected.
    """
    if secret is None:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = signature_header[len("sha256=") :]
    computed = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected)


class TriggerError(Exception):
    """Raised when an inbound trigger cannot be charted (e.g. user unresolved)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class TriggerService:
    """Verify, gate, and ingest external triggers into CHARTED voyages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @classmethod
    def reader(cls, session: AsyncSession) -> TriggerService:
        """Create a session-only instance (mirrors other services' ``reader``)."""
        return cls(session)

    @staticmethod
    def verify_github_signature(
        raw_body: bytes,
        signature_header: str | None,
        secret: str | None,
    ) -> bool:
        """Static-method handle on the module-level signature verifier."""
        return verify_github_signature(raw_body, signature_header, secret)

    @staticmethod
    def should_trigger(payload: GithubIssueWebhook) -> bool:
        """Gate an inbound issue event.

        A course is charted only when the action is ``opened``/``labeled`` AND the
        configured ``trigger_label`` is present on the issue. Every other event is
        ignored (returns ``False``) — the webhook stays quiet for unrelated issues.
        """
        if payload.action not in _TRIGGER_ACTIONS:
            return False
        label_names = {label.name for label in payload.issue.labels}
        return settings.trigger_label in label_names

    async def resolve_trigger_user(self) -> User:
        """Resolve the configured owning user of a triggered voyage.

        The webhook carries no GrandLine identity, so the owner comes from
        ``settings.trigger_default_user_email``. Unset -> ``TRIGGER_USER_UNCONFIGURED``;
        no such user -> ``TRIGGER_USER_NOT_FOUND``.
        """
        email = settings.trigger_default_user_email
        if not email:
            raise TriggerError(
                "TRIGGER_USER_UNCONFIGURED",
                "No trigger_default_user_email configured for external triggers",
            )
        result = await self._session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            raise TriggerError(
                "TRIGGER_USER_NOT_FOUND",
                f"No user found for configured trigger email {email!r}",
            )
        return user

    async def ingest_github_issue(
        self,
        payload: GithubIssueWebhook,
        user: User,
    ) -> Voyage:
        """Chart a CHARTED voyage from a GitHub issue, recording its origin.

        Mirrors ``voyages.create_voyage``: creates the voyage and seeds a default
        ``DialConfig`` in one atomic commit, so a triggered voyage is configured
        identically to a manual one (``_default_dial_config`` is the single source
        of truth). The ``origin`` dict is the canonical provenance record Phase 22
        reads to reply back to the issue.
        """
        issue = payload.issue
        repo = payload.repository
        origin = {
            "type": "github_issue",
            "repo": repo.full_name,
            "issue_number": issue.number,
            "issue_url": issue.html_url,
            "issue_title": issue.title,
            "sender": payload.sender.login,
            "received_at": datetime.now(UTC).isoformat(),
        }

        voyage = Voyage(
            id=uuid.uuid4(),
            user_id=user.id,
            title=issue.title[:255],
            description=issue.body,
            target_repo=repo.clone_url or repo.full_name,
            status=VoyageStatus.CHARTED.value,
            phase_status={},
            origin=origin,
        )
        self._session.add(voyage)
        await self._session.flush()

        self._session.add(_default_dial_config(voyage.id))

        await self._session.commit()
        await self._session.refresh(voyage)
        return voyage
