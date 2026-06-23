"""ClaudeAuthService — per-user Claude Code via a device-login run in the Cabin (Phase C0).

Today the ``claude_code`` dial adapter runs the Claude CLI with the HOST's
credentials (a single ``claude`` login / ``CLAUDE_CODE_OAUTH_TOKEN`` / API key). C0
lets each user connect THEIR OWN Claude Code account: a device-login flow is run
INSIDE the user's **Cabin** (Phase 0b), the captured ``CLAUDE_CODE_OAUTH_TOKEN`` is
vaulted in the **Sea Chest** (Phase 0a, ``kind="claude_code"``), and the adapter then
sets ``CLAUDE_CODE_OAUTH_TOKEN`` from that per-user credential so the CLI runs AS THE
USER. Absent a connected credential, the host behavior is unchanged (additive,
fallback-safe).

The flow is two caller-driven steps:

1. ``start_login`` — ensure the user's Cabin and run the configurable Claude login
   command (``settings.claude_code_login_command``, default ``claude setup-token``)
   inside it via :meth:`CabinService.run`; parse the verification URL (and optional
   short user code) the CLI prints, mint an opaque ``login_id``, and remember the
   run so :meth:`poll_login` can capture its result. Return
   ``{verification_uri, user_code?, login_id}``.
2. ``poll_login`` — check whether the login completed (the token is captured from the
   original Cabin run's output, or a follow-up Cabin command); on success
   ``SeaChestService.store(user_id, "claude_code", token, label="claude-login")`` →
   ``connected``; otherwise ``pending`` / ``error``.

HONEST CAVEAT: the EXACT Claude CLI device-flow mechanics (the precise login command,
the URL it prints, and where the token surfaces) need the real CLI to pin down. This
service is structured around that flow and is FULLY unit-tested with the Cabin run
MOCKED — the parsing/store/status contract is exercised without a real CLI or
container. The login command is a setting so a deployment can pin the real invocation.

SECURITY (NON-NEGOTIABLE): the captured ``CLAUDE_CODE_OAUTH_TOKEN`` is NEVER returned
by any endpoint or logged. ``ClaudeLoginStatus`` carries only a ``connected``/``pending``
/``error`` status and a non-secret ``label`` — the token lives solely in the Sea Chest.
The login registry below holds the captured token process-locally between start and
poll (single-worker v1, like the Cabin registry) and is wiped the moment it is vaulted.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.cabin.backend import CabinRunResult
from app.core.config import Settings
from app.schemas.integrations import ClaudeLoginStart, ClaudeLoginStatus
from app.services.cabin_service import CabinService
from app.services.sea_chest_service import SeaChestService

logger = logging.getLogger(__name__)

_CLAUDE_CODE_KIND = "claude_code"
_CREDENTIAL_LABEL = "claude-login"

# A verification URL the Claude CLI prints for the user to approve out-of-band.
# Fixed, anchored host set — never derived from untrusted input.
_VERIFICATION_URI_RE = re.compile(
    r"https://(?:claude\.ai|console\.anthropic\.com|[\w.-]*anthropic\.com)/[^\s\"'<>]*"
)
# A short approval code the CLI may print (e.g. "ABCD-1234"). Best-effort; optional.
_USER_CODE_RE = re.compile(r"\b([A-Z0-9]{4,8}-[A-Z0-9]{4,8})\b")
# The captured token the CLI emits on success. Best-effort capture from output —
# the value is stored, never logged. (Anthropic OAuth tokens are sk-ant-oat…-style.)
_TOKEN_RE = re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{10,})\b")


class ClaudeAuthError(Exception):
    """Raised when the Claude Code device-login cannot proceed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class _LoginRecord:
    """Process-local bookkeeping for one in-flight login (single-worker v1).

    Holds the captured token ONLY transiently, between start and the poll that
    vaults it; it never leaves this module and is wiped on store. No token is ever
    logged.
    """

    user_id: uuid.UUID
    verification_uri: str
    captured_token: str | None = None
    user_code: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


# Process-local registry of in-flight logins, keyed by the opaque login_id. This is
# the C0 analogue of the Cabin's process-local registry (single-worker v1); a
# multi-worker deployment would back this with Redis (noted, not solved now).
_LOGINS: dict[str, _LoginRecord] = {}


class ClaudeAuthService:
    """Drive the Claude Code device-login inside the user's Cabin → Sea Chest."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        cabin_service: CabinService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        # The Cabin runner is injected by the API dependency (app.state). It is
        # optional only so the service is trivially constructible; ``start_login``
        # fails closed without it.
        self._cabin_service = cabin_service

    async def start_login(self, user_id: uuid.UUID) -> ClaudeLoginStart:
        """Begin the device-login: run the Claude login command in the user's Cabin.

        Runs ``settings.claude_code_login_command`` inside the user's Cabin (creating
        it if needed) and parses the verification URL (and optional short user code)
        from the output. Returns the URL + an opaque ``login_id`` the client polls
        with. Raises ``CABIN_UNAVAILABLE`` if no Cabin runner is wired and
        ``LOGIN_FAILED`` if no verification URL can be parsed.
        """
        if self._cabin_service is None:
            raise ClaudeAuthError(
                "CABIN_UNAVAILABLE",
                "Cabin runtime is not available to start the Claude login",
            )

        command = self._settings.claude_code_login_command
        result = await self._cabin_service.run(user_id, self._session, command)

        output = self._combined_output(result)
        verification_uri = self._parse_verification_uri(output)
        if verification_uri is None:
            # Never include the raw CLI output (could carry a token) in the error.
            raise ClaudeAuthError(
                "LOGIN_FAILED",
                "Could not parse a verification URL from the Claude login output",
            )

        user_code_match = _USER_CODE_RE.search(output)
        user_code = user_code_match.group(1) if user_code_match else None

        # If the CLI captured the token in this same run, remember it transiently so
        # the poll can vault it without a second Cabin command.
        token = self._parse_token(output)

        login_id = uuid.uuid4().hex
        _LOGINS[login_id] = _LoginRecord(
            user_id=user_id,
            verification_uri=verification_uri,
            captured_token=token,
            user_code=user_code,
        )

        return ClaudeLoginStart(
            verification_uri=verification_uri,
            user_code=user_code,
            login_id=login_id,
        )

    async def poll_login(self, user_id: uuid.UUID, login_id: str) -> ClaudeLoginStatus:
        """Check whether the login completed; on success vault the token (no token out).

        - Unknown / foreign ``login_id`` → status ``error`` (``unknown_login``). The
          record is owner-scoped to the caller so one user can't poll another's login.
        - Token already captured (from the start run or a prior poll) → ``store`` it
          under ``kind="claude_code"`` (label ``claude-login``), drop the record, and
          report ``connected`` (label only — NEVER the token).
        - Otherwise → re-run the login command in the Cabin to see if the token has
          since been captured; ``connected`` if so, else ``pending``.
        The token is never logged or returned.
        """
        record = _LOGINS.get(login_id)
        if record is None or record.user_id != user_id:
            # Indistinguishable foreign/missing — no existence leak, no token.
            return ClaudeLoginStatus(status="error", error="unknown_login")

        token = record.captured_token
        if token is None:
            token = await self._recheck_token(user_id, record)

        if token is None:
            return ClaudeLoginStatus(status="pending")

        sea_chest = SeaChestService(self._session, self._settings)
        await sea_chest.store(user_id, _CLAUDE_CODE_KIND, token, label=_CREDENTIAL_LABEL)

        # Wipe the transient token from the registry the moment it is vaulted.
        _LOGINS.pop(login_id, None)

        return ClaudeLoginStatus(status="connected", label=_CREDENTIAL_LABEL)

    async def _recheck_token(self, user_id: uuid.UUID, record: _LoginRecord) -> str | None:
        """Re-run the login command in the Cabin to capture the token post-approval.

        The Claude login command is expected to be idempotent: once the user has
        approved out-of-band, re-running it surfaces the captured token. Returns the
        token (cached onto the record) or ``None`` while still pending.
        """
        if self._cabin_service is None:
            return None
        result = await self._cabin_service.run(
            user_id, self._session, self._settings.claude_code_login_command
        )
        token = self._parse_token(self._combined_output(result))
        if token is not None:
            record.captured_token = token
        return token

    @staticmethod
    def _combined_output(result: CabinRunResult) -> str:
        return f"{result.stdout}\n{result.stderr}"

    @staticmethod
    def _parse_verification_uri(output: str) -> str | None:
        match = _VERIFICATION_URI_RE.search(output)
        return match.group(0) if match else None

    @staticmethod
    def _parse_token(output: str) -> str | None:
        match = _TOKEN_RE.search(output)
        return match.group(1) if match else None


__all__ = ["ClaudeAuthError", "ClaudeAuthService"]
