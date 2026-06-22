"""BedsideBrowserService — the Doctor's browser-in-the-loop verification (Phase 23).

PandaOS verifies a fix by testing it in a real browser. GrandLine's Doctor only
validated via tests; the **Bedside Browser** adds the second half — drive a
headless browser against a running app, assert the page renders, and surface a
screenshot in the Ship's Log: "tests pass AND the page renders".

Real browser execution sits behind a swappable ``BrowserCheckBackend`` (the
Null default for CI; Playwright opt-in), so this service is fully testable
without a browser. It persists a ``BrowserCheck`` row and records a
``BROWSER_CHECK_RUN`` CrewAction carrying the ``screenshot_ref`` so the Ship's
Log surfaces the screenshot, mirroring the Doctor's commit/refresh/publish
ordering.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.browser.backend import BrowserCheckBackend
from app.den_den_mushi.mushi import DenDenMushi
from app.models.browser_check import BrowserCheck
from app.models.crew_action import CrewAction
from app.models.enums import CrewRole
from app.models.voyage import Voyage
from app.schemas.browser_check import BrowserCheckSpec
from app.services.crew_action_helper import (
    CrewActionType,
    publish_crew_action_recorded,
    record_action,
)

logger = logging.getLogger(__name__)


class BedsideBrowserError(Exception):
    """Raised when Bedside Browser operations fail."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class BedsideBrowserService:
    def __init__(
        self,
        session: AsyncSession,
        mushi: DenDenMushi | None = None,
    ) -> None:
        self._session = session
        self._mushi = mushi

    async def run_browser_check(
        self,
        voyage: Voyage,
        phase_number: int | None,
        spec: BrowserCheckSpec,
        backend: BrowserCheckBackend,
    ) -> BrowserCheck:
        """Run the spec through the injected backend, persist a ``BrowserCheck``
        row, and record a ``BROWSER_CHECK_RUN`` CrewAction whose ``details`` carry
        ``screenshot_ref`` + ``passed`` so the Ship's Log surfaces the screenshot.

        Commits atomically (the row + the CrewAction in the same transaction);
        publishes the crew-action event best-effort after the commit.
        """
        result = await backend.run(spec)
        screenshot_ref = result.screenshots[0] if result.screenshots else None

        check = BrowserCheck(
            voyage_id=voyage.id,
            phase_number=phase_number,
            url=spec.url,
            passed=result.passed,
            screenshot_ref=screenshot_ref,
            console_errors=list(result.console_errors),
            failed_assertions=list(result.failed_assertions),
        )
        self._session.add(check)
        await self._session.flush()

        status_word = "rendered" if result.passed else "failed to render"
        crew_action = record_action(
            self._session,
            voyage.id,
            CrewRole.DOCTOR,
            CrewActionType.BROWSER_CHECK_RUN,
            f"Bedside Browser: {spec.name} {status_word}"[:200],
            details={
                "browser_check_id": str(check.id),
                "phase_number": phase_number,
                "url": spec.url,
                "passed": result.passed,
                "screenshot_ref": screenshot_ref,
                "duration_ms": result.duration_ms,
            },
        )

        await self._session.commit()
        await self._session.refresh(check)
        await self._session.refresh(crew_action)

        if self._mushi is not None:
            await self._publish_best_effort(voyage_id=voyage.id, crew_action=crew_action)

        return check

    async def _publish_best_effort(
        self,
        *,
        voyage_id: uuid.UUID,
        crew_action: CrewAction,
    ) -> None:
        if self._mushi is None:
            return
        try:
            await publish_crew_action_recorded(self._mushi, voyage_id, crew_action)
        except Exception:
            logger.warning(
                "Failed to publish browser_check_run crew action for voyage %s",
                voyage_id,
                exc_info=True,
            )

    async def list_browser_checks(self, voyage_id: uuid.UUID) -> list[BrowserCheck]:
        """List a voyage's browser checks, newest first."""
        result = await self._session.execute(
            select(BrowserCheck)
            .where(BrowserCheck.voyage_id == voyage_id)
            .order_by(BrowserCheck.created_at.desc())
        )
        return list(result.scalars().all())
