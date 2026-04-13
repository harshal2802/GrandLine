"""Execution Service — manages per-user sandbox lifecycle."""

from __future__ import annotations

import logging
import uuid

from app.execution.backend import ExecutionBackend, ExecutionError
from app.schemas.execution import ExecutionRequest, ExecutionResult, SandboxStatus

logger = logging.getLogger(__name__)


class ExecutionService:
    def __init__(self, backend: ExecutionBackend) -> None:
        self._backend = backend
        self._sandboxes: dict[uuid.UUID, str] = {}

    async def run(self, user_id: uuid.UUID, request: ExecutionRequest) -> ExecutionResult:
        sandbox_id = await self.get_or_create_sandbox(user_id)
        return await self._backend.execute(sandbox_id, request)

    async def get_or_create_sandbox(self, user_id: uuid.UUID) -> str:
        if user_id in self._sandboxes:
            sandbox_id = self._sandboxes[user_id]
            try:
                await self._backend.status(sandbox_id)
                return sandbox_id
            except ExecutionError:
                logger.info("Sandbox %s for user %s is dead, recreating", sandbox_id, user_id)
                del self._sandboxes[user_id]

        sandbox_id = await self._backend.create(user_id)
        self._sandboxes[user_id] = sandbox_id
        return sandbox_id

    async def get_sandbox_status(self, user_id: uuid.UUID) -> SandboxStatus:
        if user_id not in self._sandboxes:
            raise ExecutionError("SANDBOX_NOT_FOUND")
        return await self._backend.status(self._sandboxes[user_id])

    async def destroy_sandbox(self, user_id: uuid.UUID) -> None:
        if user_id not in self._sandboxes:
            raise ExecutionError("SANDBOX_NOT_FOUND")
        sandbox_id = self._sandboxes.pop(user_id)
        await self._backend.destroy(sandbox_id)

    async def cleanup_all(self) -> None:
        for user_id, sandbox_id in list(self._sandboxes.items()):
            try:
                await self._backend.destroy(sandbox_id)
            except Exception:
                logger.warning("Failed to destroy sandbox %s for user %s", sandbox_id, user_id)
        self._sandboxes.clear()
