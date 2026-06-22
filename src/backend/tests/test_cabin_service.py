"""Tests for CabinService (Null backend + mocked Sea Chest reveal).

Covers: ensure creates + reuses one Cabin per user; ensure reveals the user's Sea
Chest secrets and passes them to backend.ensure (no secret leaks into status);
reap_idle destroys idle-past-timeout AND past-max-lifetime cabins while keeping
fresh ones (now injected); status/destroy. No Docker, no Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cabin.backend import CabinError
from app.cabin.null_backend import NullCabinBackend
from app.services.cabin_service import CabinService

USER_ID = uuid.uuid4()
OTHER_USER = uuid.uuid4()


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "cabin_idle_timeout_seconds": 1800,
        "cabin_max_lifetime_seconds": 3600,
        "cabin_reap_interval_seconds": 300,
        "cabin_network_allow": [],
        "execution_default_timeout": 30,
        "seachest_key": "test-key",
        "debug": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock()


class TestEnsure:
    async def test_ensure_creates_and_reuses_one_cabin(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reveal = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "app.services.cabin_service.SeaChestService.reveal", reveal, raising=True
        )
        service = CabinService(NullCabinBackend(), _settings())

        s1 = await service.ensure(USER_ID, session)
        s2 = await service.ensure(USER_ID, session)

        assert s1.cabin_id == s2.cabin_id
        # One record per user in the registry.
        assert list(service._cabins.keys()) == [USER_ID]

    async def test_ensure_reveals_secrets_and_passes_to_backend(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _reveal(self: object, user_id: uuid.UUID, kind: str) -> str | None:
            return {"claude_code": "oauth-secret", "github": "gh-secret"}.get(kind)

        monkeypatch.setattr(
            "app.services.cabin_service.SeaChestService.reveal", _reveal, raising=True
        )
        backend = MagicMock()
        backend.ensure = AsyncMock()
        backend.status = AsyncMock(
            return_value=SimpleNamespace(cabin_id="c", user_id=USER_ID, state="running")
        )
        service = CabinService(backend, _settings(cabin_network_allow=["api.github.com"]))

        await service.ensure(USER_ID, session)

        backend.ensure.assert_awaited_once()
        _, kwargs = backend.ensure.call_args
        assert kwargs["secrets"] == {
            "claude_code": "oauth-secret",
            "github": "gh-secret",
        }
        assert kwargs["network_allow"] == ["api.github.com"]

    async def test_status_carries_no_secret(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _reveal(self: object, user_id: uuid.UUID, kind: str) -> str | None:
            return "TOP-SECRET-VALUE" if kind == "github" else None

        monkeypatch.setattr(
            "app.services.cabin_service.SeaChestService.reveal", _reveal, raising=True
        )
        service = CabinService(NullCabinBackend(), _settings())

        status = await service.ensure(USER_ID, session)

        assert "TOP-SECRET-VALUE" not in status.model_dump_json()
        # Only the KIND is observable.
        assert status.materialized_kinds == ["github"]

    async def test_ensure_skips_unconnected_kinds(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reveal = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "app.services.cabin_service.SeaChestService.reveal", reveal, raising=True
        )
        backend = MagicMock()
        backend.ensure = AsyncMock()
        backend.status = AsyncMock(
            return_value=SimpleNamespace(cabin_id="c", user_id=USER_ID, state="running")
        )
        service = CabinService(backend, _settings())

        await service.ensure(USER_ID, session)

        _, kwargs = backend.ensure.call_args
        assert kwargs["secrets"] == {}


class TestStatusDestroy:
    async def test_status_without_cabin_raises(self) -> None:
        service = CabinService(NullCabinBackend(), _settings())
        with pytest.raises(CabinError):
            await service.status(OTHER_USER)

    async def test_destroy_removes_cabin(
        self, session: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.cabin_service.SeaChestService.reveal",
            AsyncMock(return_value=None),
            raising=True,
        )
        service = CabinService(NullCabinBackend(), _settings())
        await service.ensure(USER_ID, session)
        await service.destroy(USER_ID)
        with pytest.raises(CabinError):
            await service.status(USER_ID)

    async def test_destroy_without_cabin_raises(self) -> None:
        service = CabinService(NullCabinBackend(), _settings())
        with pytest.raises(CabinError):
            await service.destroy(OTHER_USER)


class TestReapIdle:
    async def test_reaps_idle_and_lifetime_keeps_fresh(self) -> None:
        backend = MagicMock()
        backend.destroy = AsyncMock()
        service = CabinService(
            backend,
            _settings(cabin_idle_timeout_seconds=1800, cabin_max_lifetime_seconds=3600),
        )
        now = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)

        # idle_user: created recently but idle for > 30 min -> reaped (idle).
        idle_user = uuid.uuid4()
        # old_user: recently active but older than 60 min -> reaped (max lifetime).
        old_user = uuid.uuid4()
        # fresh_user: created + active recently -> kept.
        fresh_user = uuid.uuid4()

        from app.services.cabin_service import _CabinRecord

        service._cabins[idle_user] = _CabinRecord(
            user_id=idle_user,
            created_at=now - timedelta(minutes=40),
            last_active=now - timedelta(minutes=31),
        )
        service._cabins[old_user] = _CabinRecord(
            user_id=old_user,
            created_at=now - timedelta(minutes=61),
            last_active=now - timedelta(seconds=10),
        )
        service._cabins[fresh_user] = _CabinRecord(
            user_id=fresh_user,
            created_at=now - timedelta(minutes=5),
            last_active=now - timedelta(seconds=10),
        )

        reaped = await service.reap_idle(now=now)

        assert set(reaped) == {idle_user, old_user}
        assert list(service._cabins.keys()) == [fresh_user]
        assert backend.destroy.await_count == 2

    async def test_reap_empty_registry(self) -> None:
        service = CabinService(NullCabinBackend(), _settings())
        assert await service.reap_idle(now=datetime.now(UTC)) == []
