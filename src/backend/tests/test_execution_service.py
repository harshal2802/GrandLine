"""Tests for ExecutionService (mocked backend)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.execution.backend import ExecutionError
from app.schemas.execution import ExecutionRequest, ExecutionResult
from app.services.execution_service import ExecutionService


@pytest.fixture
def mock_backend() -> AsyncMock:
    backend = AsyncMock()
    backend.create = AsyncMock(return_value="sandbox-1")
    backend.execute = AsyncMock(
        return_value=ExecutionResult(
            exit_code=0,
            stdout="ok",
            stderr="",
            timed_out=False,
            duration_seconds=0.5,
            sandbox_id="sandbox-1",
        )
    )
    backend.destroy = AsyncMock()
    backend.status = AsyncMock()
    return backend


@pytest.fixture
def service(mock_backend: AsyncMock) -> ExecutionService:
    return ExecutionService(mock_backend)


USER_ID = uuid.uuid4()
OTHER_USER = uuid.uuid4()


class TestRun:
    @pytest.mark.asyncio
    async def test_run_creates_sandbox_and_executes(
        self, service: ExecutionService, mock_backend: AsyncMock
    ) -> None:
        request = ExecutionRequest(command="echo hello")
        result = await service.run(USER_ID, request)

        mock_backend.create.assert_awaited_once_with(USER_ID)
        mock_backend.execute.assert_awaited_once_with("sandbox-1", request)
        assert result.exit_code == 0
        assert result.stdout == "ok"

    @pytest.mark.asyncio
    async def test_run_reuses_existing_sandbox(
        self, service: ExecutionService, mock_backend: AsyncMock
    ) -> None:
        request = ExecutionRequest(command="echo 1")
        await service.run(USER_ID, request)
        await service.run(USER_ID, request)

        # create called only once — sandbox is reused
        mock_backend.create.assert_awaited_once()
        assert mock_backend.execute.await_count == 2


class TestGetOrCreateSandbox:
    @pytest.mark.asyncio
    async def test_detects_dead_sandbox(
        self, service: ExecutionService, mock_backend: AsyncMock
    ) -> None:
        # First call: create normally
        request = ExecutionRequest(command="echo 1")
        await service.run(USER_ID, request)

        # Simulate dead sandbox on status check
        mock_backend.status.side_effect = ExecutionError("Container gone")
        mock_backend.create.reset_mock()
        mock_backend.create.return_value = "sandbox-2"

        await service.run(USER_ID, request)

        # Should have created a new sandbox
        mock_backend.create.assert_awaited_once_with(USER_ID)


class TestDestroySandbox:
    @pytest.mark.asyncio
    async def test_destroy_sandbox_calls_backend(
        self, service: ExecutionService, mock_backend: AsyncMock
    ) -> None:
        # Create a sandbox first
        await service.run(USER_ID, ExecutionRequest(command="echo"))
        await service.destroy_sandbox(USER_ID)

        mock_backend.destroy.assert_awaited_once_with("sandbox-1")

    @pytest.mark.asyncio
    async def test_destroy_sandbox_not_found_raises(self, service: ExecutionService) -> None:
        with pytest.raises(ExecutionError, match="SANDBOX_NOT_FOUND"):
            await service.destroy_sandbox(OTHER_USER)


class TestCleanupAll:
    @pytest.mark.asyncio
    async def test_cleanup_all_destroys_all(
        self, service: ExecutionService, mock_backend: AsyncMock
    ) -> None:
        # Create sandboxes for two users
        mock_backend.create.side_effect = ["sandbox-1", "sandbox-2"]
        await service.run(USER_ID, ExecutionRequest(command="echo"))
        await service.run(OTHER_USER, ExecutionRequest(command="echo"))

        await service.cleanup_all()

        assert mock_backend.destroy.await_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_all_continues_on_error(
        self, service: ExecutionService, mock_backend: AsyncMock
    ) -> None:
        mock_backend.create.side_effect = ["sandbox-1", "sandbox-2"]
        await service.run(USER_ID, ExecutionRequest(command="echo"))
        await service.run(OTHER_USER, ExecutionRequest(command="echo"))

        # First destroy fails, second should still be called
        mock_backend.destroy.side_effect = [ExecutionError("fail"), None]

        await service.cleanup_all()

        assert mock_backend.destroy.await_count == 2
