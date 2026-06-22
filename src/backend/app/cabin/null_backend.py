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
    ServiceHandle,
    ServiceStatus,
)

# Deterministic base port for Null-allocated service ports (no real bind happens).
_NULL_BASE_PORT = 8000


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
        # Long-running services (Phase B0 preview) launched in this Cabin.
        self.services: dict[str, _NullService] = {}


class _NullService:
    """In-memory record of a long-running service — no secret value stored."""

    def __init__(self, service_id: str, port: int) -> None:
        self.service_id = service_id
        self.port = port
        self.status: ServiceStatus = "running"


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

    async def start_service(
        self,
        user_id: uuid.UUID,
        command: list[str] | str,
        *,
        env: dict[str, str] | None = None,
        port: int | None = None,
    ) -> ServiceHandle:
        cabin = self._cabins.get(user_id)
        if cabin is None:
            raise CabinError("NOT_FOUND", "No cabin for user")
        cabin.last_active = datetime.now(UTC)
        # Deterministic port allocation when none is requested (no real bind).
        bound_port = port if port is not None else _NULL_BASE_PORT + len(cabin.services)
        service_id = f"null-svc-{uuid.uuid4().hex[:8]}"
        # The command/env are intentionally NOT stored — secrets in env never persist.
        cabin.services[service_id] = _NullService(service_id, bound_port)
        return ServiceHandle(
            service_id=service_id,
            url=f"http://127.0.0.1:{bound_port}",
            port=bound_port,
            status="running",
        )

    async def service_logs(
        self,
        user_id: uuid.UUID,
        service_id: str,
        *,
        tail: int = 200,
    ) -> str:
        cabin = self._cabins.get(user_id)
        if cabin is None or service_id not in cabin.services:
            raise CabinError("NOT_FOUND", "No service for user")
        # Canned, deterministic log lines (app output only — never a secret).
        lines = [
            f"[null-cabin] service {service_id} starting",
            f"[null-cabin] listening on {cabin.services[service_id].port}",
            "[null-cabin] ready",
        ]
        return "\n".join(lines[-tail:]) + "\n"

    async def service_status(self, user_id: uuid.UUID, service_id: str) -> ServiceStatus:
        cabin = self._cabins.get(user_id)
        if cabin is None or service_id not in cabin.services:
            raise CabinError("NOT_FOUND", "No service for user")
        return cabin.services[service_id].status

    async def stop_service(self, user_id: uuid.UUID, service_id: str) -> None:
        cabin = self._cabins.get(user_id)
        if cabin is None:
            return
        service = cabin.services.get(service_id)
        if service is not None:
            service.status = "stopped"
