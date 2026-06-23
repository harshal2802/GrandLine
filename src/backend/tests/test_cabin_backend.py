"""Tests for the Cabin backends (Phase 0b).

Mirrors test_browser_backend / test_execution_backend: Null backend determinism +
secret-free status, factory selection + unknown -> ValueError, and the gVisor
backend raising a clean CabinError when aiodocker is patched absent (no Docker, no
real gVisor required).
"""

from __future__ import annotations

import builtins
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.cabin.backend import CabinError
from app.cabin.factory import create_cabin_backend
from app.cabin.gvisor_backend import GVisorCabinBackend
from app.cabin.null_backend import NullCabinBackend

USER_ID = uuid.uuid4()
OTHER_USER = uuid.uuid4()


class TestNullBackendDeterminism:
    async def test_ensure_creates_and_reuses_one_cabin(self) -> None:
        backend = NullCabinBackend()
        info1 = await backend.ensure(USER_ID, secrets={}, network_allow=[])
        info2 = await backend.ensure(USER_ID, secrets={}, network_allow=[])
        assert info1.cabin_id == info2.cabin_id
        assert info1.user_id == USER_ID

    async def test_run_returns_canned_success(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        result = await backend.run(USER_ID, "echo hi", timeout=30)
        assert result.exit_code == 0
        assert result.timed_out is False

    async def test_run_without_cabin_raises(self) -> None:
        backend = NullCabinBackend()
        with pytest.raises(CabinError):
            await backend.run(OTHER_USER, "echo", timeout=5)

    async def test_status_records_kinds_not_secret_values(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(
            USER_ID,
            secrets={"claude_code": "super-secret-token", "github": "ghp_secret"},
            network_allow=["api.github.com"],
        )
        status = await backend.status(USER_ID)
        # The KINDS are observable; the secret VALUES are not present anywhere.
        assert status.materialized_kinds == ["claude_code", "github"]
        assert status.network_allow == ["api.github.com"]
        dumped = status.model_dump_json()
        assert "super-secret-token" not in dumped
        assert "ghp_secret" not in dumped

    async def test_status_without_cabin_raises(self) -> None:
        backend = NullCabinBackend()
        with pytest.raises(CabinError):
            await backend.status(OTHER_USER)

    async def test_destroy_is_idempotent(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        await backend.destroy(USER_ID)
        await backend.destroy(USER_ID)  # must not raise
        with pytest.raises(CabinError):
            await backend.status(USER_ID)

    async def test_close_is_noop(self) -> None:
        backend = NullCabinBackend()
        await backend.close()  # must not raise


class TestFactorySelection:
    def test_default_is_null(self) -> None:
        backend = create_cabin_backend(SimpleNamespace())
        assert isinstance(backend, NullCabinBackend)

    def test_explicit_null(self) -> None:
        backend = create_cabin_backend(SimpleNamespace(cabin_backend="null"))
        assert isinstance(backend, NullCabinBackend)

    def test_gvisor_selected(self) -> None:
        backend = create_cabin_backend(SimpleNamespace(cabin_backend="gvisor"))
        assert isinstance(backend, GVisorCabinBackend)

    def test_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown cabin backend"):
            create_cabin_backend(SimpleNamespace(cabin_backend="podman"))


class TestGVisorBackendMissingLib:
    async def test_ensure_raises_clean_error_when_aiodocker_absent(self) -> None:
        backend = GVisorCabinBackend(SimpleNamespace())

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "aiodocker" or name.startswith("aiodocker."):
                raise ImportError("No module named 'aiodocker'")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _fake_import):
            with pytest.raises(CabinError) as exc:
                await backend.ensure(USER_ID, secrets={}, network_allow=[])
        assert exc.value.code == "BACKEND_UNAVAILABLE"


class TestNullBackendServiceLifecycle:
    """B0: long-running service support (start / logs / status / stop)."""

    async def test_start_service_returns_reachable_url(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        handle = await backend.start_service(USER_ID, "npm start", port=3000)
        assert handle.service_id
        assert handle.port == 3000
        # A real-shaped, reachable localhost URL — never a synthetic *.local stub.
        assert handle.url == "http://127.0.0.1:3000"
        assert handle.status in ("starting", "running")

    async def test_start_service_allocates_port_when_none(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        handle = await backend.start_service(USER_ID, "uvicorn app:app")
        assert handle.port > 0
        assert handle.url == f"http://127.0.0.1:{handle.port}"

    async def test_start_service_without_cabin_raises(self) -> None:
        backend = NullCabinBackend()
        with pytest.raises(CabinError):
            await backend.start_service(OTHER_USER, "npm start")

    async def test_service_logs_returns_canned_lines(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        handle = await backend.start_service(USER_ID, "npm start", port=8080)
        logs = await backend.service_logs(USER_ID, handle.service_id, tail=200)
        assert isinstance(logs, str)
        assert logs.strip()  # non-empty, deterministic

    async def test_service_status_transitions(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        handle = await backend.start_service(USER_ID, "npm start", port=8080)
        assert await backend.service_status(USER_ID, handle.service_id) == "running"
        await backend.stop_service(USER_ID, handle.service_id)
        assert await backend.service_status(USER_ID, handle.service_id) == "stopped"

    async def test_stop_service_is_idempotent(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        handle = await backend.start_service(USER_ID, "npm start", port=8080)
        await backend.stop_service(USER_ID, handle.service_id)
        await backend.stop_service(USER_ID, handle.service_id)  # must not raise

    async def test_service_handle_carries_no_secret(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={"github": "ghp_supersecret"}, network_allow=[])
        handle = await backend.start_service(
            USER_ID, "npm start", env={"TOKEN": "ghp_supersecret"}, port=8080
        )
        dumped = handle.model_dump_json()
        assert "ghp_supersecret" not in dumped
        assert "TOKEN" not in dumped


class TestGVisorServiceMissingLib:
    async def test_start_service_raises_clean_error_when_aiodocker_absent(self) -> None:
        backend = GVisorCabinBackend(SimpleNamespace())

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "aiodocker" or name.startswith("aiodocker."):
                raise ImportError("No module named 'aiodocker'")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _fake_import):
            with pytest.raises(CabinError) as exc:
                await backend.start_service(USER_ID, "npm start", port=3000)
        assert exc.value.code == "BACKEND_UNAVAILABLE"


class TestNullBackendTerminal:
    """B3: interactive PTY support — deterministic in-memory echo terminal."""

    async def test_open_terminal_emits_canned_prompt(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        terminal = await backend.open_terminal(USER_ID, cols=120, rows=40)
        # The first read yields the canned shell prompt so the client sees a shell.
        prompt = await terminal.read()
        assert isinstance(prompt, bytes)
        assert prompt  # non-empty, deterministic
        await terminal.close()

    async def test_open_terminal_echoes_input(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        terminal = await backend.open_terminal(USER_ID)
        await terminal.read()  # drain the prompt
        await terminal.write(b"ls -la\n")
        echoed = await terminal.read()
        assert echoed == b"ls -la\n"
        await terminal.close()

    async def test_resize_is_accepted(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        terminal = await backend.open_terminal(USER_ID)
        await terminal.resize(200, 50)  # must not raise
        await terminal.close()

    async def test_read_after_close_returns_empty(self) -> None:
        backend = NullCabinBackend()
        await backend.ensure(USER_ID, secrets={}, network_allow=[])
        terminal = await backend.open_terminal(USER_ID)
        await terminal.read()  # drain the prompt
        await terminal.close()
        assert await terminal.read() == b""

    async def test_open_terminal_without_cabin_raises(self) -> None:
        backend = NullCabinBackend()
        with pytest.raises(CabinError):
            await backend.open_terminal(OTHER_USER)


class TestGVisorTerminalMissingLib:
    async def test_open_terminal_raises_clean_error_when_aiodocker_absent(self) -> None:
        backend = GVisorCabinBackend(SimpleNamespace())

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "aiodocker" or name.startswith("aiodocker."):
                raise ImportError("No module named 'aiodocker'")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _fake_import):
            with pytest.raises(CabinError) as exc:
                await backend.open_terminal(USER_ID)
        assert exc.value.code == "BACKEND_UNAVAILABLE"
