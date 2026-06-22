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

    async def close(self) -> None:
        """Release resources (e.g. the Docker client session)."""
