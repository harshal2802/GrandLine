"""Tests for GVisorContainerBackend (mocked aiodocker)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.execution.backend import ExecutionError
from app.execution.gvisor_backend import GVisorContainerBackend
from app.schemas.execution import ExecutionRequest


@dataclass
class _FakeMessage:
    stream: int  # 1=stdout, 2=stderr
    data: bytes


def _mock_stream(stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
    """Create a mock Stream that yields messages then returns None."""
    messages: list[_FakeMessage | None] = []
    if stdout:
        messages.append(_FakeMessage(stream=1, data=stdout))
    if stderr:
        messages.append(_FakeMessage(stream=2, data=stderr))
    messages.append(None)  # EOF
    it = iter(messages)
    stream = MagicMock()
    stream.read_out = AsyncMock(side_effect=lambda: next(it))
    stream.close = AsyncMock()
    return stream


def _timeout_stream() -> MagicMock:
    """Create a mock Stream whose read_out hangs forever (for timeout tests)."""
    stream = MagicMock()

    async def _hang() -> None:
        await asyncio.sleep(3600)

    stream.read_out = AsyncMock(side_effect=_hang)
    stream.close = AsyncMock()
    return stream


@pytest.fixture
def settings() -> MagicMock:
    s = MagicMock()
    s.execution_image = "python:3.13-slim"
    s.execution_gvisor_runtime = "runsc"
    s.execution_memory_limit = "256m"
    s.execution_cpu_quota = 50000
    s.execution_cpu_period = 100000
    s.execution_network_enabled = False
    s.execution_default_timeout = 30
    return s


@pytest.fixture
def mock_docker() -> MagicMock:
    docker = MagicMock()
    docker.containers = MagicMock()
    docker.containers.create_or_replace = AsyncMock()
    # containers.container() is synchronous in aiodocker — returns a DockerContainer
    docker.containers.container = MagicMock()
    return docker


@pytest.fixture
def backend(settings: MagicMock, mock_docker: MagicMock) -> GVisorContainerBackend:
    with patch("app.execution.gvisor_backend.aiodocker.Docker"):
        b = GVisorContainerBackend(settings)
    b._docker = mock_docker
    return b


USER_ID = uuid.uuid4()


def _container_mock(container_id: str = "abc123") -> AsyncMock:
    container = AsyncMock()
    container.id = container_id
    container.start = AsyncMock()
    container.kill = AsyncMock()
    container.delete = AsyncMock()
    container.show = AsyncMock(
        return_value={
            "Id": container_id,
            "State": {"Status": "running"},
            "Config": {"Labels": {"grandline.user_id": str(USER_ID)}},
            "Created": datetime.now(UTC).isoformat(),
        }
    )
    return container


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_sets_gvisor_runtime(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.create_or_replace = AsyncMock(return_value=container)

        await backend.create(USER_ID)

        config = mock_docker.containers.create_or_replace.call_args[1]["config"]
        assert config["HostConfig"]["Runtime"] == "runsc"

    @pytest.mark.asyncio
    async def test_create_sets_resource_limits(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.create_or_replace = AsyncMock(return_value=container)

        await backend.create(USER_ID)

        config = mock_docker.containers.create_or_replace.call_args[1]["config"]
        host = config["HostConfig"]
        assert host["Memory"] == 268435456  # 256m in bytes
        assert host["CpuQuota"] == 50000
        assert host["CpuPeriod"] == 100000

    @pytest.mark.asyncio
    async def test_create_disables_network(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.create_or_replace = AsyncMock(return_value=container)

        await backend.create(USER_ID)

        config = mock_docker.containers.create_or_replace.call_args[1]["config"]
        assert config["HostConfig"]["NetworkMode"] == "none"

    @pytest.mark.asyncio
    async def test_create_sets_readonly_rootfs(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.create_or_replace = AsyncMock(return_value=container)

        await backend.create(USER_ID)

        config = mock_docker.containers.create_or_replace.call_args[1]["config"]
        host = config["HostConfig"]
        assert host["ReadonlyRootfs"] is True
        assert "/workspace" in host["Tmpfs"]
        assert "/tmp" in host["Tmpfs"]

    @pytest.mark.asyncio
    async def test_create_labels_include_user_id(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.create_or_replace = AsyncMock(return_value=container)

        await backend.create(USER_ID)

        config = mock_docker.containers.create_or_replace.call_args[1]["config"]
        labels = config["Labels"]
        assert labels["grandline.user_id"] == str(USER_ID)
        assert labels["grandline.managed"] == "true"

    @pytest.mark.asyncio
    async def test_create_starts_container(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.create_or_replace = AsyncMock(return_value=container)

        sandbox_id = await backend.create(USER_ID)

        container.start.assert_awaited_once()
        assert sandbox_id == "abc123"


class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_captures_output(
        self, backend: GVisorContainerBackend, mock_docker: MagicMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.container.return_value = container

        exec_obj = AsyncMock()
        exec_obj.start = MagicMock(return_value=_mock_stream(stdout=b"hello\n"))
        exec_obj.inspect = AsyncMock(return_value={"ExitCode": 0})
        container.exec = AsyncMock(return_value=exec_obj)

        request = ExecutionRequest(command="echo hello")
        result = await backend.execute("abc123", request)

        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_captures_exit_code(
        self, backend: GVisorContainerBackend, mock_docker: MagicMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.container.return_value = container

        exec_obj = AsyncMock()
        exec_obj.start = MagicMock(return_value=_mock_stream(stderr=b"error\n"))
        exec_obj.inspect = AsyncMock(return_value={"ExitCode": 1})
        container.exec = AsyncMock(return_value=exec_obj)

        request = ExecutionRequest(command="false")
        result = await backend.execute("abc123", request)

        assert result.exit_code == 1
        assert result.stderr == "error\n"

    @pytest.mark.asyncio
    async def test_execute_respects_timeout(
        self, backend: GVisorContainerBackend, mock_docker: MagicMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.container.return_value = container

        exec_obj = AsyncMock()
        exec_obj.start = MagicMock(return_value=_timeout_stream())
        exec_obj.inspect = AsyncMock(return_value={"ExitCode": -1})
        container.exec = AsyncMock(return_value=exec_obj)

        request = ExecutionRequest(command="sleep 999", timeout_seconds=1)
        result = await backend.execute("abc123", request)

        assert result.timed_out is True

    @pytest.mark.asyncio
    async def test_execute_writes_files(
        self, backend: GVisorContainerBackend, mock_docker: MagicMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.container.return_value = container
        container.put_archive = AsyncMock()

        exec_obj = AsyncMock()
        exec_obj.start = MagicMock(return_value=_mock_stream(stdout=b"ok"))
        exec_obj.inspect = AsyncMock(return_value={"ExitCode": 0})
        container.exec = AsyncMock(return_value=exec_obj)

        request = ExecutionRequest(
            command="python main.py",
            files={"main.py": "print('ok')"},
        )
        result = await backend.execute("abc123", request)

        container.put_archive.assert_awaited_once()
        assert result.stdout == "ok"

    @pytest.mark.asyncio
    async def test_execute_sets_environment(
        self, backend: GVisorContainerBackend, mock_docker: MagicMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.container.return_value = container

        exec_obj = AsyncMock()
        exec_obj.start = MagicMock(return_value=_mock_stream(stdout=b"1"))
        exec_obj.inspect = AsyncMock(return_value={"ExitCode": 0})
        container.exec = AsyncMock(return_value=exec_obj)

        request = ExecutionRequest(
            command="echo $DEBUG",
            environment={"DEBUG": "1"},
        )
        await backend.execute("abc123", request)

        exec_call = container.exec.call_args
        env = exec_call[1].get("environment") or exec_call[1].get("env")
        assert "DEBUG=1" in env

    @pytest.mark.asyncio
    async def test_execute_tracks_duration(
        self, backend: GVisorContainerBackend, mock_docker: MagicMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.container.return_value = container

        exec_obj = AsyncMock()
        exec_obj.start = MagicMock(return_value=_mock_stream())
        exec_obj.inspect = AsyncMock(return_value={"ExitCode": 0})
        container.exec = AsyncMock(return_value=exec_obj)

        request = ExecutionRequest(command="true")
        result = await backend.execute("abc123", request)

        assert result.duration_seconds >= 0


class TestDestroy:
    @pytest.mark.asyncio
    async def test_destroy_removes_container(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        mock_docker.containers.container.return_value = container

        await backend.destroy("abc123")

        container.kill.assert_awaited_once()
        container.delete.assert_awaited_once_with(force=True)

    @pytest.mark.asyncio
    async def test_destroy_handles_already_removed(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        from aiodocker.exceptions import DockerError

        container = _container_mock()
        container.kill = AsyncMock(side_effect=DockerError(404, {"message": "not found"}))
        mock_docker.containers.container.return_value = container

        # Should not raise
        await backend.destroy("abc123")


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_maps_running(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        container.show = AsyncMock(
            return_value={
                "Id": "abc123",
                "State": {"Status": "running"},
                "Config": {"Labels": {"grandline.user_id": str(USER_ID)}},
                "Created": datetime.now(UTC).isoformat(),
            }
        )
        mock_docker.containers.container.return_value = container

        status = await backend.status("abc123")

        assert status.state == "running"

    @pytest.mark.asyncio
    async def test_status_maps_created_to_idle(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        container = _container_mock()
        container.show = AsyncMock(
            return_value={
                "Id": "abc123",
                "State": {"Status": "created"},
                "Config": {"Labels": {"grandline.user_id": str(USER_ID)}},
                "Created": datetime.now(UTC).isoformat(),
            }
        )
        mock_docker.containers.container.return_value = container

        status = await backend.status("abc123")

        assert status.state == "idle"

    @pytest.mark.asyncio
    async def test_status_not_found_raises(
        self, backend: GVisorContainerBackend, mock_docker: AsyncMock
    ) -> None:
        from aiodocker.exceptions import DockerError

        mock_docker.containers.container.return_value = AsyncMock(
            show=AsyncMock(side_effect=DockerError(404, {"message": "not found"}))
        )

        with pytest.raises(ExecutionError):
            await backend.status("nonexistent")


class TestParseMemory:
    def test_parse_memory_megabytes(self) -> None:
        from app.execution.gvisor_backend import _parse_memory

        assert _parse_memory("256m") == 268435456

    def test_parse_memory_gigabytes(self) -> None:
        from app.execution.gvisor_backend import _parse_memory

        assert _parse_memory("1g") == 1073741824
