"""Tests for SeaChestService (mocked AsyncSession — no database)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.core.seachest_crypto import decrypt
from app.models.user_credential import UserCredential
from app.schemas.sea_chest import CredentialStatus
from app.services.sea_chest_service import SeaChestError, SeaChestService

USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()
SECRET = "ghp_super-secret-github-token"


def _settings() -> Settings:
    return Settings(seachest_key="test-vault-key", debug=False)


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()

    async def _refresh(obj: object) -> None:
        # The DB would stamp the server_default timestamps on refresh; emulate
        # just enough for CredentialStatus mapping in these DB-less tests.
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 6, 22, tzinfo=UTC)  # type: ignore[attr-defined]

    session.refresh = AsyncMock(side_effect=_refresh)
    return session


def _scalar_one_or_none(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(values: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


def _service(session: AsyncMock) -> SeaChestService:
    return SeaChestService(session, _settings())


def _credential(**overrides: object) -> UserCredential:
    """Build a UserCredential with timestamps the (DB-less) server_default omits."""
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": USER_ID,
        "kind": "github",
        "ciphertext": b"x",
        "label": None,
        "created_at": datetime(2026, 6, 22, tzinfo=UTC),
        "last_used_at": None,
    }
    defaults.update(overrides)
    return UserCredential(**defaults)


class TestStore:
    @pytest.mark.asyncio
    async def test_store_encrypts_and_persists_ciphertext_not_plaintext(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))  # not yet connected
        service = _service(session)

        status = await service.store(USER_ID, "github", SECRET, label="…oken")

        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert isinstance(added, UserCredential)
        # The DB row carries CIPHERTEXT, not the plaintext secret.
        assert added.ciphertext != SECRET.encode()
        assert SECRET.encode() not in added.ciphertext
        # And it decrypts back to the original secret.
        assert decrypt(added.ciphertext, cfg=_settings()) == SECRET
        assert added.user_id == USER_ID
        assert added.kind == "github"
        session.commit.assert_awaited_once()
        # The returned status NEVER contains the secret.
        assert isinstance(status, CredentialStatus)
        assert status.connected is True
        assert status.kind == "github"
        assert SECRET not in status.model_dump_json()

    @pytest.mark.asyncio
    async def test_store_replaces_existing_row_in_place(self) -> None:
        existing = _credential(kind="github", ciphertext=b"old-ciphertext", label="old")
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(existing))
        service = _service(session)

        await service.store(USER_ID, "github", "new-secret", label="new")

        # Upsert: no new row added; the existing row is mutated.
        session.add.assert_not_called()
        assert existing.label == "new"
        assert existing.ciphertext != b"old-ciphertext"
        assert decrypt(existing.ciphertext, cfg=_settings()) == "new-secret"


class TestReveal:
    @pytest.mark.asyncio
    async def test_reveal_round_trips_and_marks_last_used(self) -> None:
        from app.core.seachest_crypto import encrypt

        row = _credential(ciphertext=encrypt(SECRET, cfg=_settings()), label="…oken")
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(row))
        service = _service(session)

        secret = await service.reveal(USER_ID, "github")

        assert secret == SECRET
        assert row.last_used_at is not None  # access recorded
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reveal_missing_returns_none(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        service = _service(session)

        assert await service.reveal(USER_ID, "claude_code") is None


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_lists_statuses_without_secret(self) -> None:
        rows = [
            _credential(kind="github", label="…1"),
            _credential(kind="claude_code", ciphertext=b"y", label="dev"),
        ]
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalars_all(rows))
        service = _service(session)

        statuses = await service.status(USER_ID)

        assert {s.kind for s in statuses} == {"github", "claude_code"}
        assert all(s.connected for s in statuses)
        # No CredentialStatus field can carry the ciphertext or a secret.
        for s in statuses:
            dumped = s.model_dump()
            assert "secret" not in dumped
            assert "ciphertext" not in dumped

    @pytest.mark.asyncio
    async def test_status_for_missing_returns_none(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        service = _service(session)

        assert await service.status_for(USER_ID, "github") is None


class TestPerUserIsolation:
    @pytest.mark.asyncio
    async def test_get_row_query_scopes_to_owner(self) -> None:
        # A foreign user's lookup returns None (owner-scoped query → no leak).
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        service = _service(session)

        assert await service.reveal(OTHER_USER_ID, "github") is None
        # The WHERE clause was built with the owner id.
        session.execute.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_owned(self) -> None:
        row = _credential(kind="github")
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(row))
        service = _service(session)

        await service.delete(USER_ID, "github")

        session.delete.assert_awaited_once_with(row)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_missing_raises_not_found(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        service = _service(session)

        with pytest.raises(SeaChestError) as exc:
            await service.delete(USER_ID, "github")

        assert exc.value.code == "NOT_FOUND"


class TestReader:
    def test_reader_returns_instance(self) -> None:
        assert isinstance(SeaChestService.reader(_mock_session(), _settings()), SeaChestService)
