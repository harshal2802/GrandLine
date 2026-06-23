"""CabinBackend ABC — the swappable seam for the per-user Cabin (Phase 0b).

Mirrors ``ExecutionBackend`` / ``DeploymentBackend`` / ``BrowserCheckBackend``: a
clean async ABC behind a factory so a real container runtime can be swapped in
without the service layer ever importing ``aiodocker``. The v1 default
(:class:`NullCabinBackend`) needs no container at all, keeping CI and the test
suite Docker-free.

Security note: a Cabin materializes the user's secrets INSIDE the container only.
None of the value types below carry a secret value — ``CabinStatus`` exposes
provenance + lifecycle (``state``, timestamps, the egress allow-list, and the
KINDS of secret materialized), never the secrets themselves.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CabinState = Literal["running", "idle", "destroyed"]

# A long-running service (Phase B0 preview) launched inside the Cabin.
ServiceStatus = Literal["starting", "running", "stopped", "failed"]


class CabinError(Exception):
    """Raised when a Cabin operation fails (e.g. backend unavailable, not found)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class CabinInfo(BaseModel):
    """The handle returned by ``ensure`` — identifies the user's persistent Cabin.

    ``materialized_kinds`` records WHICH kinds of secret were injected into the
    container (e.g. ``["claude_code", "github"]``) — never their values.
    """

    model_config = ConfigDict(from_attributes=True)

    cabin_id: str
    user_id: uuid.UUID
    state: CabinState = "running"
    materialized_kinds: list[str] = Field(default_factory=list)
    network_allow: list[str] = Field(default_factory=list)


class CabinStatus(BaseModel):
    """A Cabin's STATUS as returned by the API — never carries a secret value."""

    model_config = ConfigDict(from_attributes=True)

    cabin_id: str
    user_id: uuid.UUID
    state: CabinState
    created_at: datetime
    last_active: datetime
    materialized_kinds: list[str] = Field(default_factory=list)
    network_allow: list[str] = Field(default_factory=list)


class CabinRunResult(BaseModel):
    """The outcome of a one-shot ``run`` inside the Cabin."""

    cabin_id: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float


class ServiceHandle(BaseModel):
    """A long-running service launched inside the Cabin (Phase B0 preview).

    ``url`` is the reachable preview URL (a real localhost/allow-listed address,
    never a synthetic stub). Carries NO secret value — the command/env that started
    the service is never surfaced here.
    """

    model_config = ConfigDict(from_attributes=True)

    service_id: str
    url: str
    port: int
    status: ServiceStatus = "starting"


class CabinTerminal(ABC):
    """An interactive PTY session bound to a user's Cabin (Phase B3).

    A small async handle bridged over the bidirectional terminal WS. It carries NO
    secret value — only the raw PTY byte stream (stdin/stdout) flows through it, and
    those bytes are never logged. ``read`` yields PTY output (blocking until there is
    some), ``write`` feeds stdin, ``resize`` adjusts the window, ``close`` tears the
    session down (idempotent).
    """

    @abstractmethod
    async def read(self) -> bytes:
        """Return the next chunk of PTY output. Returns ``b""`` when the PTY is closed."""
        ...

    @abstractmethod
    async def write(self, data: bytes) -> None:
        """Write ``data`` to the PTY's stdin."""
        ...

    @abstractmethod
    async def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY window (best-effort)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Tear down the PTY session (idempotent)."""
        ...


class CabinBackend(ABC):
    @abstractmethod
    async def ensure(
        self,
        user_id: uuid.UUID,
        *,
        secrets: dict[str, str],
        network_allow: list[str],
    ) -> CabinInfo:
        """Get-or-create the user's persistent Cabin.

        ``secrets`` maps kind -> plaintext secret (e.g. ``{"claude_code": "...",
        "github": "..."}``); the backend materializes them INSIDE the container
        (env/files) by kind and never logs/returns the values. ``network_allow`` is
        the deny-by-default egress allow-list applied to the Cabin.
        """
        ...

    @abstractmethod
    async def run(
        self,
        user_id: uuid.UUID,
        command: list[str] | str,
        *,
        timeout: int,
    ) -> CabinRunResult:
        """Run a one-shot command inside the user's Cabin."""
        ...

    @abstractmethod
    async def status(self, user_id: uuid.UUID) -> CabinStatus:
        """Query the user's Cabin state (raises ``CabinError`` if none)."""
        ...

    @abstractmethod
    async def destroy(self, user_id: uuid.UUID) -> None:
        """Tear down the user's Cabin (idempotent)."""
        ...

    @abstractmethod
    async def start_service(
        self,
        user_id: uuid.UUID,
        command: list[str] | str,
        *,
        env: dict[str, str] | None = None,
        port: int | None = None,
    ) -> ServiceHandle:
        """Launch a long-running process inside the user's Cabin (Phase B0 preview).

        Binds a port and returns a :class:`ServiceHandle` whose ``url`` is the
        reachable preview URL. ``env`` is materialized into the process environment
        INSIDE the Cabin and is NEVER logged or returned. Raises ``CabinError`` if
        the user has no Cabin.
        """
        ...

    @abstractmethod
    async def service_logs(
        self,
        user_id: uuid.UUID,
        service_id: str,
        *,
        tail: int = 200,
    ) -> str:
        """Return the captured stdout/stderr tail of a long-running service.

        Phase B0 is tail-only; Phase B1 will stream. Returns app output only —
        never a secret.
        """
        ...

    @abstractmethod
    async def service_status(self, user_id: uuid.UUID, service_id: str) -> ServiceStatus:
        """Return the lifecycle status of a long-running service."""
        ...

    @abstractmethod
    async def stop_service(self, user_id: uuid.UUID, service_id: str) -> None:
        """Stop a long-running service (idempotent)."""
        ...

    @abstractmethod
    async def open_terminal(
        self,
        user_id: uuid.UUID,
        *,
        cols: int = 80,
        rows: int = 24,
    ) -> CabinTerminal:
        """Open an interactive PTY session inside the user's Cabin (Phase B3).

        Returns a :class:`CabinTerminal` bridged over the bidirectional terminal WS.
        Arbitrary commands run, but ONLY inside the isolated gVisor Cabin (kernel
        filtered syscalls, deny-by-default egress, bounded by the Cabin's hard max
        lifetime + reaper) — there is no host access. Raises ``CabinError`` if the
        user has no Cabin. No secret value flows through the handle's metadata.
        """
        ...

    async def close(self) -> None:
        """Release resources (e.g. the Docker client session)."""
