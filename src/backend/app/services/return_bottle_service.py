"""ReturnBottleService — close the loop when a voyage completes.

PandaOS's flagship demo ends by replying to the human who reported the bug.
GrandLine's pipeline ended at "Helmsman deploys" — nobody told the reporter.
The **Return Bottle** is the completion-time outreach that drifts word back home:

1. If the voyage was triggered by a **Message in a Bottle** (Phase 21) — i.e. it
   carries a ``github_issue`` ``origin`` — post a friendly voyage summary back as
   a comment on the originating GitHub issue.
2. If the voyage targets a repo, record a Log Book ``summary`` entry so future
   voyages recall what this one accomplished. This satisfies the Phase 19 Log Book
   deferral of "auto write-back from completed voyages" (explicitly punted to
   "Phase 22 Return Bottle territory").

Everything here is **best-effort**: a failed Return Bottle must never fail, roll
back, or change the status of a voyage that already completed successfully.

Security: the outbound GitHub host is the configured ``github_api_base_url``
(default ``https://api.github.com``) — **never** a host derived from the untrusted
``origin`` payload. The bearer token is the existing ``github_api_token`` setting,
read from settings and never logged.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.voyage import Voyage
from app.services.log_book_service import LogBookService

logger = logging.getLogger(__name__)

# Author recorded on the Log Book write-back (the crew that sailed the voyage).
_LOG_BOOK_AUTHOR = "return-bottle"
_LOG_BOOK_KIND = "summary"
_HTTP_TIMEOUT_SECONDS = 10.0


class ReturnBottleError(Exception):
    """Raised when a Return Bottle cannot be sent (rarely — outreach is best-effort)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ReturnBottleService:
    """Post a completion summary back to the originating channel and the Log Book."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def build_summary(
        self,
        voyage: Voyage,
        *,
        deployment_url: str | None,
        duration_seconds: float | None,
        phase_count: int | None = None,
    ) -> str:
        """Render a friendly, themed markdown summary of a completed voyage.

        PURE — no I/O — so it is trivially unit-testable. The deploy URL line is
        emitted only when a URL is present; everything else degrades cleanly when
        a value is missing.
        """
        title = voyage.title or "(untitled voyage)"
        lines = [
            "🍶 **The crew has returned!**",
            "",
            f"The voyage **{title}** has reached port.",
            "",
            f"- **Status**: {voyage.status}",
        ]
        if phase_count is not None:
            lines.append(f"- **Phases charted**: {phase_count}")
        if duration_seconds is not None:
            lines.append(f"- **Voyage duration**: {duration_seconds:.1f}s")
        if deployment_url:
            lines.append(f"- **Deployed to**: {deployment_url}")
        lines.extend(
            [
                "",
                "Fair winds — the Log Pose held, and the deed is done. ⚓",
            ]
        )
        return "\n".join(lines)

    async def post_to_github_issue(self, origin: dict[str, Any], body: str) -> bool:
        """Post ``body`` as a comment on the GitHub issue described by ``origin``.

        ``origin["repo"]`` is ``owner/name``; the comment is POSTed to
        ``{base}/repos/{owner}/{name}/issues/{number}/comments``. The host is
        ALWAYS ``settings.github_api_base_url`` — never derived from ``origin`` —
        so untrusted payload data can't redirect the bearer token at a host we
        don't control.

        Returns ``True`` on a 2xx response, ``False`` otherwise (including a
        non-2xx, an empty token, or a malformed ``origin``). An empty token skips
        the request entirely (logged at info).
        """
        token = self._settings.github_api_token
        if not token:
            logger.info("Return Bottle: github_api_token unset — skipping issue comment")
            return False

        repo = origin.get("repo")
        issue_number = origin.get("issue_number")
        if not repo or "/" not in str(repo) or issue_number is None:
            logger.info("Return Bottle: origin missing repo/issue_number — skipping")
            return False
        owner, _, name = str(repo).partition("/")

        base = self._settings.github_api_base_url.rstrip("/")
        url = f"{base}/repos/{owner}/{name}/issues/{issue_number}/comments"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json={"body": body})

        if 200 <= response.status_code < 300:
            return True
        logger.warning(
            "Return Bottle: GitHub comment failed (HTTP %s) for %s#%s",
            response.status_code,
            repo,
            issue_number,
        )
        return False

    async def report(
        self,
        voyage: Voyage,
        *,
        deployment_url: str | None = None,
        duration_seconds: float | None = None,
        phase_count: int | None = None,
        log_book: LogBookService | None = None,
    ) -> dict[str, bool]:
        """Orchestrate best-effort outreach for a completed voyage.

        Returns ``{"issue_commented": bool, "log_book_recorded": bool}``. Each leg
        is independent and best-effort: any exception is swallowed + logged so the
        completed voyage is never affected.
        """
        result = {"issue_commented": False, "log_book_recorded": False}

        summary = self.build_summary(
            voyage,
            deployment_url=deployment_url,
            duration_seconds=duration_seconds,
            phase_count=phase_count,
        )

        origin = voyage.origin
        if isinstance(origin, dict) and origin.get("type") == "github_issue":
            try:
                result["issue_commented"] = await self.post_to_github_issue(origin, summary)
            except Exception:
                logger.warning(
                    "Return Bottle: posting issue comment failed for voyage %s",
                    voyage.id,
                    exc_info=True,
                )

        if voyage.target_repo:
            book = log_book if log_book is not None else LogBookService(self._session)
            try:
                await book.record(
                    voyage.target_repo,
                    _LOG_BOOK_AUTHOR,
                    _LOG_BOOK_KIND,
                    summary,
                    details={
                        "voyage_status": voyage.status,
                        "deployment_url": deployment_url,
                        "phase_count": phase_count,
                    },
                    voyage_id=voyage.id,
                )
                result["log_book_recorded"] = True
            except Exception:
                logger.warning(
                    "Return Bottle: Log Book write-back failed for voyage %s",
                    voyage.id,
                    exc_info=True,
                )

        return result


__all__ = ["ReturnBottleError", "ReturnBottleService"]
