"""Docker + gVisor execution backend."""

from __future__ import annotations

import io
import logging
import tarfile
import time
import uuid
from asyncio import wait_for
from datetime import datetime
from typing import Any

import aiodocker
from aiodocker.exceptions import DockerError

from app.execution.backend import ExecutionBackend, ExecutionError
from app.schemas.execution import ExecutionRequest, ExecutionResult, SandboxStatus

logger = logging.getLogger(__name__)


def _parse_memory(value: str) -> int:
    """Parse memory limit string to bytes. Supports 'm' (MiB) and 'g' (GiB)."""
    value = value.strip().lower()
    if value.endswith("m"):
        return int(value[:-1]) * 1024 * 1024
    if value.endswith("g"):
        return int(value[:-1]) * 1024 * 1024 * 1024
    return int(value)


def _build_tar(files: dict[str, str]) -> bytes:
    """Create an in-memory tar archive from a path→content dict."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    return buf.read()


class GVisorContainerBackend(ExecutionBackend):
    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._docker = aiodocker.Docker()

    async def create(self, user_id: uuid.UUID) -> str:
        config = {
            "Image": self._settings.execution_image,
            "Cmd": ["tail", "-f", "/dev/null"],
            "Labels": {
                "grandline.user_id": str(user_id),
                "grandline.managed": "true",
            },
            "HostConfig": {
                "Runtime": self._settings.execution_gvisor_runtime,
                "Memory": _parse_memory(self._settings.execution_memory_limit),
                "CpuQuota": self._settings.execution_cpu_quota,
                "CpuPeriod": self._settings.execution_cpu_period,
                "NetworkMode": "none" if not self._settings.execution_network_enabled else "bridge",
                "ReadonlyRootfs": True,
                "Tmpfs": {
                    "/workspace": "rw,size=64m",
                    "/tmp": "rw,size=32m",
                },
            },
        }
        try:
            container = await self._docker.containers.create_or_replace(
                name=f"grandline-{user_id}-{uuid.uuid4().hex[:8]}",
                config=config,
            )
            await container.start()
            return container.id
        except DockerError as exc:
            raise ExecutionError(f"Failed to create sandbox: {exc}") from exc

    async def execute(self, sandbox_id: str, request: ExecutionRequest) -> ExecutionResult:
        try:
            container = self._docker.containers.container(sandbox_id)

            if request.files:
                tar_data = _build_tar(request.files)
                await container.put_archive("/workspace", tar_data)  # type: ignore[no-untyped-call]

            exec_obj = await container.exec(
                cmd=["sh", "-c", request.command],
                workdir=request.working_dir,
                environment=[f"{k}={v}" for k, v in request.environment.items()],
                tty=False,
            )

            stream = exec_obj.start(detach=False)
            timed_out = False
            stdout_buf = b""
            stderr_buf = b""
            start = time.monotonic()

            async def _read_stream() -> None:
                nonlocal stdout_buf, stderr_buf
                while True:
                    msg = await stream.read_out()
                    if msg is None:
                        break
                    if msg.stream == 1:
                        stdout_buf += msg.data
                    elif msg.stream == 2:
                        stderr_buf += msg.data

            try:
                await wait_for(_read_stream(), timeout=request.timeout_seconds)
            except TimeoutError:
                timed_out = True
                await stream.close()

            duration = time.monotonic() - start

            inspect_data = await exec_obj.inspect()
            exit_code = inspect_data.get("ExitCode", -1)
            if exit_code is None:
                exit_code = -1

            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout_buf.decode(errors="replace"),
                stderr=stderr_buf.decode(errors="replace"),
                timed_out=timed_out,
                duration_seconds=round(duration, 3),
                sandbox_id=sandbox_id,
            )
        except ExecutionError:
            raise
        except DockerError as exc:
            raise ExecutionError(f"Execution failed: {exc}") from exc

    async def destroy(self, sandbox_id: str) -> None:
        try:
            container = self._docker.containers.container(sandbox_id)
            await container.kill()
            await container.delete(force=True)
        except DockerError:
            logger.debug("Container %s already removed", sandbox_id)

    async def status(self, sandbox_id: str) -> SandboxStatus:
        try:
            container = self._docker.containers.container(sandbox_id)
            info = await container.show()
        except DockerError as exc:
            raise ExecutionError(f"Container not found: {sandbox_id}") from exc

        docker_state = info["State"]["Status"]
        if docker_state == "running":
            state = "running"
        elif docker_state in ("created", "paused"):
            state = "idle"
        else:
            state = "destroyed"

        user_id_str = info["Config"]["Labels"].get("grandline.user_id", "")
        created_str = info["Created"]

        return SandboxStatus(
            sandbox_id=sandbox_id,
            state=state,
            user_id=uuid.UUID(user_id_str),
            created_at=datetime.fromisoformat(created_str.replace("Z", "+00:00")),
        )

    async def close(self) -> None:
        await self._docker.close()
