"""GVisorCabinBackend — the opt-in REAL per-user Cabin backend (Phase 0b).

Selected only by config (``GRANDLINE_CABIN_BACKEND=gvisor``); the default stays
:class:`NullCabinBackend`. ``aiodocker`` is **lazily imported inside the methods**
so that importing this module — and therefore app startup and the whole test
suite — never requires ``aiodocker`` or a running Docker daemon. If ``aiodocker``
is unavailable, the methods raise a clear :class:`CabinError` (never an opaque
``ImportError``).

This reuses the gVisor isolation from ``app/execution/gvisor_backend.py`` (runsc
runtime, managed labels, readonly rootfs, tmpfs, mem/cpu limits) but with two
differences that make it a CABIN rather than a one-shot sandbox:

- **Persistent + per-user.** One long-lived container per user, reused across
  voyages (tracked by the ``grandline.cabin`` + ``grandline.user_id`` labels).
- **Deny-by-default egress allow-list.** Instead of ``NetworkMode: none``, the
  Cabin attaches to a bridge only when ``network_allow`` is non-empty; an empty
  allow-list keeps egress fully denied.

Security: the user's secrets are injected as environment variables INSIDE the
container at spawn and are NEVER logged or returned. ``CabinStatus`` carries only
provenance (state, timestamps, the egress allow-list, and the KINDS materialized).
"""

from __future__ import annotations

import logging
import uuid
from asyncio import wait_for
from datetime import UTC, datetime
from typing import Any

from app.cabin.backend import (
    CabinBackend,
    CabinError,
    CabinInfo,
    CabinRunResult,
    CabinStatus,
    CabinTerminal,
    ServiceHandle,
    ServiceStatus,
)

logger = logging.getLogger(__name__)

# Maps a Sea Chest credential kind to the environment variable the Cabin exposes it
# under. The values are materialized INSIDE the container only — never logged.
_KIND_ENV = {
    "claude_code": "CLAUDE_CODE_OAUTH_TOKEN",
    "github": "GITHUB_TOKEN",
}


def _sh_quote(value: str) -> str:
    """Single-quote a value for a POSIX shell (defense against injection)."""
    import shlex

    return shlex.quote(value)


def _parse_memory(value: str) -> int:
    """Parse a memory limit string to bytes (supports 'm'/'g' suffixes)."""
    value = value.strip().lower()
    if not value:
        raise ValueError("Empty memory limit")
    suffix = value[-1]
    if suffix in ("m", "g"):
        numeric = value[:-1]
        if not numeric:
            raise ValueError(f"Invalid memory limit: {value!r}")
        n = int(numeric)
        return n * 1024 * 1024 * (1024 if suffix == "g" else 1)
    if not value.isdigit():
        raise ValueError(f"Invalid memory limit suffix: {value!r}")
    return int(value)


def _secret_env(secrets: dict[str, str]) -> dict[str, str]:
    """Map known secret kinds to their container env vars (values, never logged)."""
    env: dict[str, str] = {}
    for kind, value in secrets.items():
        var = _KIND_ENV.get(kind)
        if var is not None:
            env[var] = value
    return env


class _GVisorCabinTerminal(CabinTerminal):
    """A real PTY (Phase B3) wrapping an ``aiodocker`` exec with ``Tty=True`` + stdin.

    The exec runs inside the persistent per-user Cabin, so arbitrary commands are
    kernel-filtered by runsc, bounded by deny-by-default egress + CPU/mem quotas and the
    Cabin's hard max lifetime + reaper — there is no host access. The raw PTY byte
    stream flows through ``read``/``write`` verbatim and is NEVER logged.
    """

    def __init__(self, exec_obj: Any, stream: Any) -> None:
        self._exec = exec_obj
        self._stream = stream
        self._closed = False

    async def read(self) -> bytes:
        if self._closed:
            return b""
        try:
            msg = await self._stream.read_out()
        except Exception:  # pragma: no cover - stream closed underfoot
            return b""
        if msg is None:
            return b""
        # In a TTY exec stdout + stderr are merged onto the same stream; pass bytes
        # through verbatim (never logged).
        return bytes(msg.data)

    async def write(self, data: bytes) -> None:
        if self._closed:
            return
        await self._stream.write_in(data)

    async def resize(self, cols: int, rows: int) -> None:
        if self._closed:
            return
        # Best-effort PTY resize; aiodocker exposes resize on the exec handle.
        try:
            await self._exec.resize(w=cols, h=rows)
        except Exception:  # pragma: no cover - resize is advisory
            logger.debug("Terminal resize to %sx%s failed", cols, rows)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._stream.close()
        except Exception:  # pragma: no cover - best effort
            logger.debug("Terminal stream already closed")


class GVisorCabinBackend(CabinBackend):
    """Real persistent-per-user gVisor container (opt-in)."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._docker: Any = None
        # Process-local map of user_id -> container id for the running Cabin.
        self._cabins: dict[uuid.UUID, str] = {}
        # Process-local map of (user_id, service_id) -> bound port for long-running
        # services (Phase B0 preview). The log file path is derived from service_id.
        self._services: dict[tuple[uuid.UUID, str], int] = {}

    def _client(self) -> Any:
        """Lazily construct the aiodocker client (kept out of module import time)."""
        if self._docker is None:
            try:
                import aiodocker
            except ImportError as exc:  # pragma: no cover - exercised via patched import
                raise CabinError(
                    "BACKEND_UNAVAILABLE",
                    "aiodocker is not available. The 'gvisor' cabin backend requires "
                    "aiodocker and a running Docker daemon with the gVisor (runsc) "
                    "runtime; use the default 'null' backend if Docker is unavailable.",
                ) from exc
            self._docker = aiodocker.Docker()
        return self._docker

    def _network_mode(self, network_allow: list[str]) -> str:
        # Deny-by-default: no allow-list -> no egress. A non-empty allow-list
        # attaches to the bridge (host-level firewalling enforces the allow-list).
        return "bridge" if network_allow else "none"

    async def ensure(
        self,
        user_id: uuid.UUID,
        *,
        secrets: dict[str, str],
        network_allow: list[str],
    ) -> CabinInfo:
        client = self._client()
        from aiodocker.exceptions import DockerError  # lazy

        materialized_kinds = sorted(secrets.keys())
        env = _secret_env(secrets)

        existing = self._cabins.get(user_id)
        if existing is not None:
            try:
                container = client.containers.container(existing)
                await container.show()
                return CabinInfo(
                    cabin_id=existing,
                    user_id=user_id,
                    state="running",
                    materialized_kinds=materialized_kinds,
                    network_allow=list(network_allow),
                )
            except DockerError:
                logger.info("Cabin %s for user %s is gone, recreating", existing, user_id)
                self._cabins.pop(user_id, None)

        config = {
            "Image": self._settings.execution_image,
            "Cmd": ["tail", "-f", "/dev/null"],
            "Env": [f"{k}={v}" for k, v in env.items()],
            "Labels": {
                "grandline.user_id": str(user_id),
                "grandline.cabin": "true",
                "grandline.managed": "true",
            },
            "HostConfig": {
                "Runtime": self._settings.execution_gvisor_runtime,
                "Memory": _parse_memory(self._settings.execution_memory_limit),
                "CpuQuota": self._settings.execution_cpu_quota,
                "CpuPeriod": self._settings.execution_cpu_period,
                "NetworkMode": self._network_mode(network_allow),
                "ReadonlyRootfs": True,
                "Tmpfs": {
                    "/workspace": "rw,size=256m",
                    "/tmp": "rw,size=64m",
                    "/home": "rw,size=64m",
                },
            },
        }
        try:
            container = await client.containers.create_or_replace(
                name=f"grandline-cabin-{user_id}",
                config=config,
            )
            await container.start()
        except DockerError as exc:
            raise CabinError("ENSURE_FAILED", f"Failed to ensure cabin: {exc}") from exc

        self._cabins[user_id] = container.id
        return CabinInfo(
            cabin_id=container.id,
            user_id=user_id,
            state="running",
            materialized_kinds=materialized_kinds,
            network_allow=list(network_allow),
        )

    async def run(
        self,
        user_id: uuid.UUID,
        command: list[str] | str,
        *,
        timeout: int,
    ) -> CabinRunResult:
        client = self._client()
        from aiodocker.exceptions import DockerError  # lazy

        cabin_id = self._cabins.get(user_id)
        if cabin_id is None:
            raise CabinError("NOT_FOUND", "No cabin for user")

        cmd = ["sh", "-c", command] if isinstance(command, str) else command
        try:
            container = client.containers.container(cabin_id)
            exec_obj = await container.exec(cmd=cmd, tty=False)
            stream = exec_obj.start(detach=False)
            stdout_buf = b""
            stderr_buf = b""
            timed_out = False

            async def _read() -> None:
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
                await wait_for(_read(), timeout=timeout)
            except TimeoutError:
                timed_out = True
                await stream.close()

            inspect_data = await exec_obj.inspect()
            exit_code = inspect_data.get("ExitCode")
            if exit_code is None:
                exit_code = -1
        except DockerError as exc:
            raise CabinError("RUN_FAILED", f"Cabin run failed: {exc}") from exc

        return CabinRunResult(
            cabin_id=cabin_id,
            exit_code=exit_code,
            stdout=stdout_buf.decode(errors="replace"),
            stderr=stderr_buf.decode(errors="replace"),
            timed_out=timed_out,
            duration_seconds=0.0,
        )

    async def status(self, user_id: uuid.UUID) -> CabinStatus:
        client = self._client()
        from aiodocker.exceptions import DockerError  # lazy

        cabin_id = self._cabins.get(user_id)
        if cabin_id is None:
            raise CabinError("NOT_FOUND", "No cabin for user")
        try:
            container = client.containers.container(cabin_id)
            info = await container.show()
        except DockerError as exc:
            raise CabinError("NOT_FOUND", f"Cabin not found: {cabin_id}") from exc

        docker_state = info["State"]["Status"]
        state = "running" if docker_state == "running" else "idle"
        created_str = info["Created"]
        created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        return CabinStatus(
            cabin_id=cabin_id,
            user_id=user_id,
            state=state,
            created_at=created_at,
            last_active=datetime.now(UTC),
            materialized_kinds=[],
            network_allow=[],
        )

    async def destroy(self, user_id: uuid.UUID) -> None:
        cabin_id = self._cabins.pop(user_id, None)
        if cabin_id is None:
            return
        client = self._client()
        from aiodocker.exceptions import DockerError  # lazy

        try:
            container = client.containers.container(cabin_id)
            await container.kill()
            await container.delete(force=True)
        except DockerError:
            logger.debug("Cabin %s already removed", cabin_id)

    @staticmethod
    def _log_path(service_id: str) -> str:
        # Per-service log sink inside the Cabin's writable tmpfs (/tmp is rw).
        return f"/tmp/grandline-preview-{service_id}.log"

    async def start_service(
        self,
        user_id: uuid.UUID,
        command: list[str] | str,
        *,
        env: dict[str, str] | None = None,
        port: int | None = None,
    ) -> ServiceHandle:
        client = self._client()
        from aiodocker.exceptions import DockerError  # lazy

        cabin_id = self._cabins.get(user_id)
        if cabin_id is None:
            raise CabinError("NOT_FOUND", "No cabin for user")

        bound_port = port if port is not None else 3000
        service_id = f"preview-{uuid.uuid4().hex[:8]}"
        log_path = self._log_path(service_id)

        # Build the shell command: export env (values never logged), launch the app
        # detached, tee stdout+stderr to the per-service log sink. PORT is exported so
        # a generic dev server binds the requested localhost port.
        cmd_str = " ".join(command) if isinstance(command, list) else command
        env_assigns = {**(env or {}), "PORT": str(bound_port)}
        exports = " ".join(f"export {k}={_sh_quote(v)};" for k, v in env_assigns.items())
        launch = f"{exports} nohup sh -c {_sh_quote(cmd_str)} > {log_path} 2>&1 &"

        try:
            container = client.containers.container(cabin_id)
            exec_obj = await container.exec(cmd=["sh", "-c", launch], tty=False)
            await exec_obj.start(detach=True)
        except DockerError as exc:
            # The exception is generic — the command/env (which may carry a secret)
            # is never placed in the message.
            raise CabinError("START_FAILED", "Failed to start preview service") from exc

        self._services[(user_id, service_id)] = bound_port
        return ServiceHandle(
            service_id=service_id,
            url=f"http://127.0.0.1:{bound_port}",
            port=bound_port,
            status="running",
        )

    async def service_logs(
        self,
        user_id: uuid.UUID,
        service_id: str,
        *,
        tail: int = 200,
    ) -> str:
        client = self._client()
        from aiodocker.exceptions import DockerError  # lazy

        cabin_id = self._cabins.get(user_id)
        if cabin_id is None or (user_id, service_id) not in self._services:
            raise CabinError("NOT_FOUND", "No service for user")

        log_path = self._log_path(service_id)
        try:
            container = client.containers.container(cabin_id)
            exec_obj = await container.exec(
                cmd=["sh", "-c", f"tail -n {int(tail)} {log_path} 2>/dev/null || true"],
                tty=False,
            )
            stream = exec_obj.start(detach=False)
            out = b""
            while True:
                msg = await stream.read_out()
                if msg is None:
                    break
                if msg.stream in (1, 2):
                    out += msg.data
        except DockerError as exc:
            raise CabinError("LOGS_FAILED", "Failed to read preview logs") from exc
        return out.decode(errors="replace")

    async def service_status(self, user_id: uuid.UUID, service_id: str) -> ServiceStatus:
        if (user_id, service_id) not in self._services:
            raise CabinError("NOT_FOUND", "No service for user")
        # B0 tracks lifecycle at the registry level; a richer probe (process alive)
        # is a B1 refinement. A registered service is considered running.
        return "running"

    async def stop_service(self, user_id: uuid.UUID, service_id: str) -> None:
        port = self._services.pop((user_id, service_id), None)
        if port is None:
            return
        cabin_id = self._cabins.get(user_id)
        if cabin_id is None:
            return
        client = self._client()
        from aiodocker.exceptions import DockerError  # lazy

        try:
            container = client.containers.container(cabin_id)
            # Kill any process bound to the preview port (best-effort; idempotent).
            exec_obj = await container.exec(
                cmd=["sh", "-c", f"pkill -f 'PORT={port}' 2>/dev/null || true"],
                tty=False,
            )
            await exec_obj.start(detach=True)
        except DockerError:
            logger.debug("Preview service %s already stopped", service_id)

    async def open_terminal(
        self,
        user_id: uuid.UUID,
        *,
        cols: int = 80,
        rows: int = 24,
    ) -> CabinTerminal:
        client = self._client()
        from aiodocker.exceptions import DockerError  # lazy

        cabin_id = self._cabins.get(user_id)
        if cabin_id is None:
            raise CabinError("NOT_FOUND", "No cabin for user")

        try:
            container = client.containers.container(cabin_id)
            # Interactive login shell with a PTY + stdin attached. The shell runs
            # INSIDE the gVisor Cabin — kernel-filtered, deny-by-default egress,
            # bounded by the Cabin's lifetime. No host access.
            exec_obj = await container.exec(
                cmd=["/bin/sh", "-i"],
                tty=True,
                stdin=True,
                stdout=True,
                stderr=True,
            )
            stream = exec_obj.start(detach=False)
            await stream._init()  # noqa: SLF001 - open the multiplexed exec stream
        except DockerError as exc:
            # Generic message — the command/env (which may carry a secret) is never
            # placed in the error.
            raise CabinError("TERMINAL_FAILED", "Failed to open cabin terminal") from exc

        terminal = _GVisorCabinTerminal(exec_obj, stream)
        await terminal.resize(cols, rows)
        return terminal

    async def close(self) -> None:
        if self._docker is not None:
            await self._docker.close()
            self._docker = None
