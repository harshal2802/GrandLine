"""PreviewService — run the crew's built app as a long-running process in the Cabin.

Phase B0 (the Live App workstream's linchpin). Today the deployment layer
(``InProcessDeploymentBackend``) is a STUB: it records a synthetic
``http://preview.voyage-xxxx.local`` URL and runs NOTHING. This service makes
"preview" real: it launches the crew's app as a **long-running process inside the
user's Cabin** (Phase 0b), captures a **real reachable URL + logs**, and **reaps it
on a hard lifetime cap**.

It is a STANDALONE service over ``CabinService`` (NOT a change to the pipeline's
``InProcessDeploymentBackend``) so the deploy pipeline stays byte-identical. Scope is
**start / status / logs(tail) / stop** — log STREAMING is B1, the embedded iframe is
B2, the interactive PTY terminal is B3 (later phases).

Security:
- The app always runs INSIDE the gVisor Cabin (via ``CabinService.start_service``) —
  never as a host process. The Cabin's egress stays deny-by-default + allow-list.
- A **process-local** per-user registry (v1 single-worker, like ``pipeline_tasks``)
  stamps each preview with a ``started_at`` + a hard max lifetime; ``reap_expired``
  stops previews past the cap so no long-running, credential-bearing process orphans.
- ``PreviewInfo`` carries NO secret — only ``preview_id`` / ``url`` / ``status``. The
  start command / env is never logged or returned; ``logs`` is app output only.
- ONE preview per user: starting again replaces (and stops) the prior one.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.cabin.backend import CabinError, ServiceStatus
from app.core.config import Settings
from app.services.cabin_service import CabinService

logger = logging.getLogger(__name__)


class PreviewError(Exception):
    """Raised when a preview operation fails (e.g. the Cabin is unavailable)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class PreviewInfo(BaseModel):
    """The preview's public handle — carries NO secret value."""

    model_config = ConfigDict(from_attributes=True)

    preview_id: str
    url: str
    status: ServiceStatus


@dataclass
class _PreviewRecord:
    """Process-local bookkeeping for one user's preview (no secret value here)."""

    preview_id: str
    service_id: str
    url: str
    status: ServiceStatus
    started_at: datetime


class PreviewService:
    """Owns the per-user preview registry, lifetime cap, and reaping."""

    def __init__(self, cabin_service: CabinService, settings: Settings) -> None:
        self._cabin = cabin_service
        self._settings = settings
        # Process-local registry (v1 single-worker, like ``pipeline_tasks``).
        self._previews: dict[uuid.UUID, _PreviewRecord] = {}

    async def start(
        self,
        user_id: uuid.UUID,
        voyage: object,
        session: AsyncSession,
        *,
        command: str | None = None,
    ) -> PreviewInfo:
        """Launch the crew's app as a long-running process in the user's Cabin.

        Resolves the start command (explicit arg › ``preview_default_command``),
        ensures the Cabin, starts the service, and stamps the started-at for the hard
        max-lifetime cap. Starting again replaces (and stops) the prior preview.
        """
        # ONE preview per user: stop the prior one before replacing it.
        await self.stop(user_id)

        resolved = command or self._settings.preview_default_command
        try:
            # Ensure the Cabin (materializes the user's secrets INSIDE the container),
            # then launch the long-running service. The command/env never leave here.
            await self._cabin.ensure(user_id, session)
            handle = await self._cabin.start_service(user_id, session, resolved)
        except CabinError as exc:
            raise PreviewError("CABIN_UNAVAILABLE", exc.message) from exc
        except Exception as exc:  # noqa: BLE001 - surface as a clean PreviewError
            raise PreviewError("START_FAILED", "Failed to start preview") from exc

        preview_id = f"preview-{uuid.uuid4().hex[:12]}"
        self._previews[user_id] = _PreviewRecord(
            preview_id=preview_id,
            service_id=handle.service_id,
            url=handle.url,
            status=handle.status,
            started_at=datetime.now(UTC),
        )
        return PreviewInfo(preview_id=preview_id, url=handle.url, status=handle.status)

    async def status(self, user_id: uuid.UUID) -> PreviewInfo | None:
        """Return the user's current preview, or ``None`` if there is none."""
        record = self._previews.get(user_id)
        if record is None:
            return None
        return PreviewInfo(
            preview_id=record.preview_id,
            url=record.url,
            status=record.status,
        )

    async def logs(self, user_id: uuid.UUID, *, tail: int = 200) -> str:
        """Return the preview's captured stdout/stderr tail (empty if no preview)."""
        record = self._previews.get(user_id)
        if record is None:
            return ""
        try:
            return await self._cabin.service_logs(user_id, record.service_id, tail=tail)
        except CabinError:
            return ""

    async def stop(self, user_id: uuid.UUID) -> None:
        """Stop the user's preview (idempotent — a no-op if there is none)."""
        record = self._previews.pop(user_id, None)
        if record is None:
            return
        try:
            await self._cabin.stop_service(user_id, record.service_id)
        except Exception:
            logger.warning("Failed to stop preview for user %s", user_id)

    async def reap_expired(self, *, now: datetime | None = None) -> list[str]:
        """Stop previews older than ``preview_max_lifetime_seconds``.

        Returns the reaped preview ids. ``now`` is injectable for deterministic tests.
        """
        current = now or datetime.now(UTC)
        max_lifetime = self._settings.preview_max_lifetime_seconds
        reaped: list[str] = []
        for user_id, record in list(self._previews.items()):
            age = (current - record.started_at).total_seconds()
            if age >= max_lifetime:
                reaped.append(record.preview_id)
                await self.stop(user_id)
        return reaped

    async def stop_all(self) -> None:
        """Stop every tracked preview (called on shutdown — no orphan processes)."""
        for user_id in list(self._previews.keys()):
            await self.stop(user_id)
