"""CabinService — per-user persistent Cabin lifecycle + secret materialization.

The Cabin (Phase 0b) is the runtime half of the Phase 0 foundation: a persistent,
per-user, isolated container that holds the user's credentials (materialized from
the Sea Chest) and runs their workloads. This service is the persistent, reaping
evolution of ``ExecutionService``:

- It keeps a **process-local** per-user registry with ``created_at``/``last_active``
  timestamps. Multi-worker deployments are out of scope for v1 (single-worker
  fleet), exactly like ``app.state.pipeline_tasks``.
- ``ensure`` reveals the user's Sea Chest secrets (``SeaChestService.reveal``) for
  the kinds they have connected and hands them to the backend to materialize INSIDE
  the Cabin. The secret values never leave this method's call into the backend —
  they are never stored on the service, returned, or logged.
- ``reap_idle`` destroys Cabins idle past ``cabin_idle_timeout_seconds`` OR older
  than ``cabin_max_lifetime_seconds`` (hard max lifetime). ``now`` is injectable so
  the reaper is unit-testable without sleeping or a real clock.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.cabin.backend import (
    CabinBackend,
    CabinError,
    CabinRunResult,
    CabinStatus,
    ServiceHandle,
    ServiceStatus,
)
from app.core.config import Settings
from app.services.sea_chest_service import SeaChestService

logger = logging.getLogger(__name__)

# The Sea Chest kinds a Cabin materializes. Each is revealed (if connected) and
# injected by the backend under a kind-specific env var; an unconnected kind is
# simply skipped (no secret to inject).
_MATERIALIZED_KINDS: tuple[str, ...] = ("claude_code", "github")


@dataclass
class _CabinRecord:
    """Process-local bookkeeping for one user's Cabin (no secret value here)."""

    user_id: uuid.UUID
    created_at: datetime
    last_active: datetime


class CabinService:
    """Owns the per-user Cabin registry, reaping, and secret materialization."""

    def __init__(self, backend: CabinBackend, settings: Settings) -> None:
        self._backend = backend
        self._settings = settings
        # Process-local registry (v1 single-worker, like ``pipeline_tasks``).
        self._cabins: dict[uuid.UUID, _CabinRecord] = {}

    async def ensure(self, user_id: uuid.UUID, session: AsyncSession) -> CabinStatus:
        """Get-or-create the user's Cabin, materializing their Sea Chest secrets.

        Reveals each connected credential kind via ``SeaChestService.reveal`` and
        passes the plaintext secrets to the backend, which injects them INSIDE the
        Cabin. The secrets are never stored on the service, returned, or logged.
        """
        sea_chest = SeaChestService(session, self._settings)
        secrets: dict[str, str] = {}
        for kind in _MATERIALIZED_KINDS:
            secret = await sea_chest.reveal(user_id, kind)
            if secret is not None:
                secrets[kind] = secret

        await self._backend.ensure(
            user_id,
            secrets=secrets,
            network_allow=list(self._settings.cabin_network_allow),
        )
        self._touch(user_id)
        return await self._backend.status(user_id)

    async def run(
        self,
        user_id: uuid.UUID,
        session: AsyncSession,
        command: list[str] | str,
        *,
        timeout: int | None = None,
    ) -> CabinRunResult:
        """Ensure the user's Cabin exists, then run a one-shot command inside it."""
        await self.ensure(user_id, session)
        effective_timeout = (
            timeout if timeout is not None else self._settings.execution_default_timeout
        )
        result = await self._backend.run(user_id, command, timeout=effective_timeout)
        self._touch(user_id, refresh_only=True)
        return result

    async def status(self, user_id: uuid.UUID) -> CabinStatus:
        """Return the user's Cabin status (raises ``CabinError`` if none)."""
        if user_id not in self._cabins:
            raise CabinError("NOT_FOUND", "No cabin for user")
        return await self._backend.status(user_id)

    async def start_service(
        self,
        user_id: uuid.UUID,
        session: AsyncSession,
        command: list[str] | str,
        *,
        env: dict[str, str] | None = None,
        port: int | None = None,
    ) -> ServiceHandle:
        """Ensure the user's Cabin, then launch a long-running service inside it.

        Used by the Phase B0 preview path. ``env`` is materialized into the process
        INSIDE the Cabin by the backend and is never stored, returned, or logged.
        """
        await self.ensure(user_id, session)
        handle = await self._backend.start_service(user_id, command, env=env, port=port)
        self._touch(user_id, refresh_only=True)
        return handle

    async def service_logs(
        self,
        user_id: uuid.UUID,
        service_id: str,
        *,
        tail: int = 200,
    ) -> str:
        """Return the captured stdout/stderr tail of a long-running service."""
        return await self._backend.service_logs(user_id, service_id, tail=tail)

    async def service_status(self, user_id: uuid.UUID, service_id: str) -> ServiceStatus:
        """Return the lifecycle status of a long-running service."""
        return await self._backend.service_status(user_id, service_id)

    async def stop_service(self, user_id: uuid.UUID, service_id: str) -> None:
        """Stop a long-running service (idempotent)."""
        await self._backend.stop_service(user_id, service_id)

    async def destroy(self, user_id: uuid.UUID) -> None:
        """Destroy the user's Cabin (raises ``CabinError`` if none)."""
        if user_id not in self._cabins:
            raise CabinError("NOT_FOUND", "No cabin for user")
        self._cabins.pop(user_id, None)
        await self._backend.destroy(user_id)

    async def reap_idle(self, *, now: datetime | None = None) -> list[uuid.UUID]:
        """Destroy idle-past-timeout OR past-max-lifetime Cabins.

        Returns the reaped user_ids. ``now`` is injectable for deterministic tests.
        """
        current = now or datetime.now(UTC)
        idle_limit = self._settings.cabin_idle_timeout_seconds
        max_lifetime = self._settings.cabin_max_lifetime_seconds

        reaped: list[uuid.UUID] = []
        for user_id, record in list(self._cabins.items()):
            idle_for = (current - record.last_active).total_seconds()
            age = (current - record.created_at).total_seconds()
            if idle_for >= idle_limit or age >= max_lifetime:
                self._cabins.pop(user_id, None)
                try:
                    await self._backend.destroy(user_id)
                except Exception:
                    logger.warning("Failed to reap cabin for user %s", user_id)
                reaped.append(user_id)
        return reaped

    async def cleanup_all(self) -> None:
        """Destroy every tracked Cabin (called on shutdown)."""
        for user_id in list(self._cabins.keys()):
            try:
                await self._backend.destroy(user_id)
            except Exception:
                logger.warning("Failed to destroy cabin for user %s", user_id)
        self._cabins.clear()

    async def close(self) -> None:
        """Release the backend's resources."""
        await self._backend.close()

    def _touch(self, user_id: uuid.UUID, *, refresh_only: bool = False) -> None:
        """Stamp ``last_active`` (and ``created_at`` on first creation)."""
        now = datetime.now(UTC)
        record = self._cabins.get(user_id)
        if record is None:
            self._cabins[user_id] = _CabinRecord(user_id=user_id, created_at=now, last_active=now)
        else:
            record.last_active = now
