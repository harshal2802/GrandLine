"""Stub backends for integration tests.

`StubExecutionBackend` returns canned pytest "all passed" results regardless
of input. `StubGitBackend` is a no-op git host used to build a real
`GitService` without touching a sandbox or a remote.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.execution.backend import ExecutionBackend
from app.schemas.execution import ExecutionRequest, ExecutionResult, SandboxStatus


class StubExecutionBackend(ExecutionBackend):
    """Returns canned pytest passed results. No real execution."""

    def __init__(self) -> None:
        self._sandboxes: dict[str, uuid.UUID] = {}
        self._created_at = datetime.now(UTC)

    async def create(self, user_id: uuid.UUID) -> str:
        sid = f"stub-{uuid.uuid4().hex[:8]}"
        self._sandboxes[sid] = user_id
        return sid

    async def execute(self, sandbox_id: str, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            exit_code=0,
            stdout="3 passed in 0.12s",
            stderr="",
            timed_out=False,
            duration_seconds=0.1,
            sandbox_id=sandbox_id,
        )

    async def destroy(self, sandbox_id: str) -> None:
        self._sandboxes.pop(sandbox_id, None)

    async def status(self, sandbox_id: str) -> SandboxStatus:
        user_id = self._sandboxes.get(sandbox_id, uuid.uuid4())
        return SandboxStatus(
            sandbox_id=sandbox_id,
            state="running",
            user_id=user_id,
            created_at=self._created_at,
        )
