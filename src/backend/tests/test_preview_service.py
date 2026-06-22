"""Tests for PreviewService (Phase B0) — Null Cabin backend + mocked sessions.

Covers: start launches a real long-running service in the user's Cabin and returns
a real-shaped (localhost) URL; status/logs/stop; start replaces a prior preview;
reap_expired stops past-lifetime previews (now injected); secrets never appear in
PreviewInfo or the logs. No Docker, no Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cabin.null_backend import NullCabinBackend
from app.services.cabin_service import CabinService
from app.services.preview_service import PreviewError, PreviewService

USER_ID = uuid.uuid4()
OTHER_USER = uuid.uuid4()


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "cabin_idle_timeout_seconds": 1800,
        "cabin_max_lifetime_seconds": 3600,
        "cabin_network_allow": [],
        "execution_default_timeout": 30,
        "seachest_key": "test-key",
        "debug": True,
        "preview_default_command": "npm start",
        "preview_max_lifetime_seconds": 1800,
        "preview_idle_timeout_seconds": 900,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock()


def _voyage() -> MagicMock:
    v = MagicMock()
    v.user_id = USER_ID
    v.id = uuid.uuid4()
    return v


def _cabin_service(settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> CabinService:
    # No connected secrets — ensure just creates an empty Cabin.
    monkeypatch.setattr(
        "app.services.cabin_service.SeaChestService.reveal",
        AsyncMock(return_value=None),
        raising=True,
    )
    return CabinService(NullCabinBackend(), settings)


class TestStart:
    async def test_start_launches_service_and_returns_real_url(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)

        info = await svc.start(USER_ID, _voyage(), session)

        assert info.preview_id
        assert info.url.startswith("http://127.0.0.1:")
        assert info.status in ("starting", "running")

    async def test_start_uses_default_command_when_none(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings(preview_default_command="uvicorn app:app")
        backend = NullCabinBackend()
        monkeypatch.setattr(
            "app.services.cabin_service.SeaChestService.reveal",
            AsyncMock(return_value=None),
            raising=True,
        )
        cabin = CabinService(backend, settings)
        spy = AsyncMock(wraps=backend.start_service)
        backend.start_service = spy  # type: ignore[method-assign]
        svc = PreviewService(cabin, settings)

        await svc.start(USER_ID, _voyage(), session)

        _, kwargs = spy.call_args
        args = spy.call_args[0]
        # The default command was threaded through to the Cabin backend.
        assert "uvicorn app:app" in args

    async def test_start_replaces_prior_preview(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)

        first = await svc.start(USER_ID, _voyage(), session)
        second = await svc.start(USER_ID, _voyage(), session, command="npm run dev")

        assert first.preview_id != second.preview_id
        current = await svc.status(USER_ID)
        assert current is not None
        assert current.preview_id == second.preview_id


class TestStatusLogsStop:
    async def test_status_none_when_no_preview(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)
        assert await svc.status(OTHER_USER) is None

    async def test_logs_returns_tail(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)
        await svc.start(USER_ID, _voyage(), session)
        logs = await svc.logs(USER_ID, tail=50)
        assert isinstance(logs, str)
        assert logs.strip()

    async def test_logs_empty_when_no_preview(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)
        assert await svc.logs(OTHER_USER) == ""

    async def test_stop_removes_preview(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)
        await svc.start(USER_ID, _voyage(), session)
        await svc.stop(USER_ID)
        assert await svc.status(USER_ID) is None

    async def test_stop_is_noop_without_preview(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)
        await svc.stop(OTHER_USER)  # must not raise


class TestReapExpired:
    async def test_reaps_past_lifetime_keeps_fresh(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings(preview_max_lifetime_seconds=1800)
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)
        now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)

        old_voyage = _voyage()
        old_voyage.user_id = USER_ID
        fresh_voyage = _voyage()
        fresh_voyage.user_id = OTHER_USER

        await svc.start(USER_ID, old_voyage, session)
        await svc.start(OTHER_USER, fresh_voyage, session)

        # Backdate the first preview past the hard cap.
        svc._previews[USER_ID].started_at = now - timedelta(seconds=2000)
        svc._previews[OTHER_USER].started_at = now - timedelta(seconds=10)

        reaped = await svc.reap_expired(now=now)

        assert len(reaped) == 1
        assert await svc.status(USER_ID) is None
        assert await svc.status(OTHER_USER) is not None

    async def test_reap_empty_registry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)
        assert await svc.reap_expired(now=datetime.now(UTC)) == []


class TestSecretSafety:
    async def test_preview_info_carries_no_secret(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings()
        svc = PreviewService(_cabin_service(settings, monkeypatch), settings)
        info = await svc.start(USER_ID, _voyage(), session)
        dumped = info.model_dump_json()
        assert "secret" not in dumped.lower()
        assert "token" not in dumped.lower()


class TestErrors:
    async def test_start_wraps_cabin_failure(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = _settings()
        cabin = MagicMock()
        cabin.ensure = AsyncMock(side_effect=RuntimeError("boom"))
        svc = PreviewService(cabin, settings)
        with pytest.raises(PreviewError):
            await svc.start(USER_ID, _voyage(), session)
