from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from app.schemas.execution import ExecutionRequest, ExecutionResult, SandboxStatus


class ExecutionError(Exception):
    """Raised when a sandbox operation fails."""


class ExecutionBackend(ABC):
    @abstractmethod
    async def create(self, user_id: uuid.UUID) -> str:
        """Provision a sandbox and return its ID."""
        ...

    @abstractmethod
    async def execute(self, sandbox_id: str, request: ExecutionRequest) -> ExecutionResult:
        """Run a command inside the sandbox."""
        ...

    @abstractmethod
    async def destroy(self, sandbox_id: str) -> None:
        """Tear down the sandbox."""
        ...

    @abstractmethod
    async def status(self, sandbox_id: str) -> SandboxStatus:
        """Query sandbox state."""
        ...

    async def close(self) -> None:
        """Release resources (e.g. Docker client session)."""
