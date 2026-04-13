"""Tests for Execution Service schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.execution import ExecutionRequest, ExecutionResult, SandboxStatus


class TestExecutionRequestDefaults:
    def test_defaults(self) -> None:
        req = ExecutionRequest(command="echo hello")
        assert req.command == "echo hello"
        assert req.working_dir == "/workspace"
        assert req.timeout_seconds == 30
        assert req.environment == {}
        assert req.files == {}


class TestExecutionRequestCustom:
    def test_custom_values(self) -> None:
        req = ExecutionRequest(
            command="python main.py",
            working_dir="/app",
            timeout_seconds=120,
            environment={"DEBUG": "1"},
            files={"main.py": "print('hi')"},
        )
        assert req.command == "python main.py"
        assert req.working_dir == "/app"
        assert req.timeout_seconds == 120
        assert req.environment == {"DEBUG": "1"}
        assert req.files == {"main.py": "print('hi')"}


class TestExecutionRequestTimeoutRange:
    def test_timeout_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRequest(command="echo", timeout_seconds=0)

    def test_timeout_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionRequest(command="echo", timeout_seconds=301)

    def test_timeout_at_boundaries_accepted(self) -> None:
        req_min = ExecutionRequest(command="echo", timeout_seconds=1)
        assert req_min.timeout_seconds == 1
        req_max = ExecutionRequest(command="echo", timeout_seconds=300)
        assert req_max.timeout_seconds == 300


class TestExecutionResultFields:
    def test_all_fields(self) -> None:
        result = ExecutionResult(
            exit_code=0,
            stdout="hello\n",
            stderr="",
            timed_out=False,
            duration_seconds=1.23,
            sandbox_id="abc123",
        )
        assert result.exit_code == 0
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.timed_out is False
        assert result.duration_seconds == 1.23
        assert result.sandbox_id == "abc123"

    def test_timed_out_default_false(self) -> None:
        result = ExecutionResult(
            exit_code=1,
            stdout="",
            stderr="err",
            duration_seconds=0.5,
            sandbox_id="x",
        )
        assert result.timed_out is False


class TestSandboxStatusFields:
    def test_all_fields(self) -> None:
        uid = uuid.uuid4()
        now = datetime.now(UTC)
        status = SandboxStatus(
            sandbox_id="container-1",
            state="running",
            user_id=uid,
            created_at=now,
        )
        assert status.sandbox_id == "container-1"
        assert status.state == "running"
        assert status.user_id == uid
        assert status.created_at == now

    def test_state_accepts_valid_values(self) -> None:
        uid = uuid.uuid4()
        now = datetime.now(UTC)
        for valid_state in ("running", "idle", "destroyed"):
            s = SandboxStatus(sandbox_id="c1", state=valid_state, user_id=uid, created_at=now)
            assert s.state == valid_state

    def test_state_rejects_invalid_value(self) -> None:
        uid = uuid.uuid4()
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            SandboxStatus(sandbox_id="c1", state="unknown", user_id=uid, created_at=now)
