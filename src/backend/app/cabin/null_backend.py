"""NullCabinBackend — the deterministic, container-free v1 default for the Cabin.

The analogue of ``InProcessDeploymentBackend`` / ``NullBrowserBackend``: no real
container, fully deterministic, CI-safe. It tracks Cabins in an in-memory dict and
returns a canned success from ``run``.

Security: ``ensure`` records only the KINDS of secret materialized (the dict keys),
NEVER the secret values — the values are dropped on the floor here exactly as the
gVisor backend injects them inside the container and forgets them. Nothing in this
module stores, echoes, or logs a secret value.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.cabin.backend import (
    CabinBackend,
    CabinError,
    CabinInfo,
    CabinRunResult,
    CabinStatus,
)


class _NullCabin:
    """In-memory record of a Cabin — provenance only, never a secret value."""

    def __init__(
        self,
        cabin_id: str,
        user_id: uuid.UUID,
        materialized_kinds: list[str],
        network_allow: list[str],
    ) -> None:
        self.cabin_id = cabin_id
        self.user_id = user_id
        self.materialized_kinds = materialized_kinds
        self.network_allow = network_allow
        now = datetime.now(UTC)
        self.created_at = now
        self.last_active = now


class NullCabinBackend(CabinBackend):
    """Deterministic, container-free backend used for v1 and tests."""

    def __init__(self) -> None:
        self._cabins: dict[uuid.UUID, _NullCabin] = {}

    async def ensure(
        self,
        user_id: uuid.UUID,
        *,
        secrets: dict[str, str],
        network_allow: list[str],
    ) -> CabinInfo:
        # Record ONLY the kinds materialized — never the secret values.
        materialized_kinds = sorted(secrets.keys())
        cabin = self._cabins.get(user_id)
        if cabin is None:
            cabin = _NullCabin(
                cabin_id=f"null-cabin-{user_id}",
                user_id=user_id,
                materialized_kinds=materialized_kinds,
                network_allow=list(network_allow),
            )
            self._cabins[user_id] = cabin
        else:
            # Re-materialize: refresh the recorded provenance + egress allow-list.
            cabin.materialized_kinds = materialized_kinds
            cabin.network_allow = list(network_allow)
            cabin.last_active = datetime.now(UTC)
        return CabinInfo(
            cabin_id=cabin.cabin_id,
            user_id=user_id,
            state="running",
            materialized_kinds=cabin.materialized_kinds,
            network_allow=cabin.network_allow,
        )

    async def run(
        self,
        user_id: uuid.UUID,
        command: list[str] | str,
        *,
        timeout: int,
    ) -> CabinRunResult:
        cabin = self._cabins.get(user_id)
        if cabin is None:
            raise CabinError("NOT_FOUND", "No cabin for user")
        cabin.last_active = datetime.now(UTC)
        return CabinRunResult(
            cabin_id=cabin.cabin_id,
            exit_code=0,
            stdout="",
            stderr="",
            timed_out=False,
            duration_seconds=0.0,
        )

    async def status(self, user_id: uuid.UUID) -> CabinStatus:
        cabin = self._cabins.get(user_id)
        if cabin is None:
            raise CabinError("NOT_FOUND", "No cabin for user")
        return CabinStatus(
            cabin_id=cabin.cabin_id,
            user_id=user_id,
            state="running",
            created_at=cabin.created_at,
            last_active=cabin.last_active,
            materialized_kinds=cabin.materialized_kinds,
            network_allow=cabin.network_allow,
        )

    async def destroy(self, user_id: uuid.UUID) -> None:
        self._cabins.pop(user_id, None)
