"""Tests for Execution Service REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.execution.backend import ExecutionError
from app.schemas.execution import ExecutionRequest, ExecutionResult, SandboxStatus

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _mock_voyage() -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    return voyage


def _mock_exec_service() -> AsyncMock:
    svc = AsyncMock()
    svc.run = AsyncMock(
        return_value=ExecutionResult(
            exit_code=0,
            stdout="ok",
            stderr="",
            timed_out=False,
            duration_seconds=0.5,
            sandbox_id="sandbox-1",
        )
    )
    svc.get_sandbox_status = AsyncMock(
        return_value=SandboxStatus(
            sandbox_id="sandbox-1",
            state="running",
            user_id=USER_ID,
            created_at=datetime.now(UTC),
        )
    )
    svc.destroy_sandbox = AsyncMock()
    return svc


class TestExecuteEndpoint:
    @pytest.mark.asyncio
    async def test_execute_returns_result(self) -> None:
        from app.api.v1.execution import execute_code

        svc = _mock_exec_service()
        body = ExecutionRequest(command="echo hello")
        result = await execute_code(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert result.exit_code == 0
        assert result.stdout == "ok"
        svc.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_sets_user_from_auth(self) -> None:
        from app.api.v1.execution import execute_code

        svc = _mock_exec_service()
        body = ExecutionRequest(command="echo hello")
        user = _mock_user()

        await execute_code(VOYAGE_ID, body, user, _mock_voyage(), svc)

        # user_id passed to service.run comes from auth, not request body
        call_args = svc.run.call_args
        assert call_args[0][0] == USER_ID

    @pytest.mark.asyncio
    async def test_execute_error_raises_http_500(self) -> None:
        from app.api.v1.execution import execute_code

        svc = _mock_exec_service()
        svc.run.side_effect = ExecutionError("Container failed")
        body = ExecutionRequest(command="echo hello")

        with pytest.raises(HTTPException) as exc_info:
            await execute_code(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_execute_invalid_path_returns_400(self) -> None:
        from app.api.v1.execution import execute_code

        svc = _mock_exec_service()
        svc.run.side_effect = ExecutionError("Invalid file path: path traversal detected")
        body = ExecutionRequest(command="echo hello")

        with pytest.raises(HTTPException) as exc_info:
            await execute_code(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_execute_file_too_large_returns_400(self) -> None:
        from app.api.v1.execution import execute_code

        svc = _mock_exec_service()
        svc.run.side_effect = ExecutionError("File too large: big.txt")
        body = ExecutionRequest(command="echo hello")

        with pytest.raises(HTTPException) as exc_info:
            await execute_code(VOYAGE_ID, body, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 400


class TestSandboxStatusEndpoint:
    @pytest.mark.asyncio
    async def test_sandbox_status_returns_status(self) -> None:
        from app.api.v1.execution import get_sandbox_status

        svc = _mock_exec_service()
        result = await get_sandbox_status(_mock_user(), svc)

        assert result.state == "running"
        assert result.sandbox_id == "sandbox-1"

    @pytest.mark.asyncio
    async def test_sandbox_status_not_found(self) -> None:
        from app.api.v1.execution import get_sandbox_status

        svc = _mock_exec_service()
        svc.get_sandbox_status.side_effect = ExecutionError("SANDBOX_NOT_FOUND")

        with pytest.raises(HTTPException) as exc_info:
            await get_sandbox_status(_mock_user(), svc)

        assert exc_info.value.status_code == 404


class TestDestroySandboxEndpoint:
    @pytest.mark.asyncio
    async def test_destroy_sandbox_204(self) -> None:
        from app.api.v1.execution import destroy_sandbox

        svc = _mock_exec_service()
        await destroy_sandbox(_mock_user(), svc)

        svc.destroy_sandbox.assert_awaited_once_with(USER_ID)

    @pytest.mark.asyncio
    async def test_destroy_sandbox_not_found(self) -> None:
        from app.api.v1.execution import destroy_sandbox

        svc = _mock_exec_service()
        svc.destroy_sandbox.side_effect = ExecutionError("SANDBOX_NOT_FOUND")

        with pytest.raises(HTTPException) as exc_info:
            await destroy_sandbox(_mock_user(), svc)

        assert exc_info.value.status_code == 404


class TestAuthRequired:
    @pytest.mark.asyncio
    async def test_execute_unauthorized_401(self) -> None:
        """get_current_user raises 401 when no credentials are provided."""
        from app.api.v1.dependencies import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None, session=AsyncMock())

        assert exc_info.value.status_code == 401
