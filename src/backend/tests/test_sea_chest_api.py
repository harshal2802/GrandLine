"""Tests for the Sea Chest REST API (direct endpoint calls)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.sea_chest import CredentialStatus, SeaChestConnectRequest
from app.services.sea_chest_service import SeaChestError

USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()
SECRET = "ghp_super-secret-github-token"


def _user(user_id: uuid.UUID = USER_ID) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _status(kind: str = "github", label: str | None = "…oken") -> CredentialStatus:
    return CredentialStatus(
        kind=kind,
        connected=True,
        label=label,
        created_at=datetime(2026, 6, 22, tzinfo=UTC),
        last_used_at=None,
    )


class TestListEndpoint:
    @pytest.mark.asyncio
    async def test_lists_statuses_without_secrets(self) -> None:
        from app.api.v1.sea_chest import list_credentials

        svc = AsyncMock()
        svc.status = AsyncMock(return_value=[_status("github"), _status("claude_code", "dev")])

        result = await list_credentials(_user(), svc)

        assert {s.kind for s in result} == {"github", "claude_code"}
        svc.status.assert_awaited_once_with(USER_ID)
        # No status carries the secret.
        for s in result:
            assert SECRET not in s.model_dump_json()


class TestConnectEndpoint:
    @pytest.mark.asyncio
    async def test_put_stores_and_returns_status_no_secret(self) -> None:
        from app.api.v1.sea_chest import connect_credential

        svc = AsyncMock()
        svc.store = AsyncMock(return_value=_status("github"))
        body = SeaChestConnectRequest(kind="github", secret=SECRET, label="…oken")

        result = await connect_credential("github", body, _user(), svc)

        assert result.kind == "github"
        assert result.connected is True
        svc.store.assert_awaited_once_with(USER_ID, "github", SECRET, label="…oken")
        # The response body never contains the secret.
        assert SECRET not in result.model_dump_json()

    @pytest.mark.asyncio
    async def test_put_rejects_body_path_kind_mismatch(self) -> None:
        from app.api.v1.sea_chest import connect_credential

        svc = AsyncMock()
        body = SeaChestConnectRequest(kind="claude_code", secret=SECRET, label=None)

        with pytest.raises(HTTPException) as exc:
            await connect_credential("github", body, _user(), svc)

        assert exc.value.status_code == 422
        svc.store.assert_not_called()


class TestDeleteEndpoint:
    @pytest.mark.asyncio
    async def test_delete_returns_204(self) -> None:
        from app.api.v1.sea_chest import disconnect_credential

        svc = AsyncMock()
        svc.delete = AsyncMock(return_value=None)

        result = await disconnect_credential("github", _user(), svc)

        assert result.status_code == 204
        svc.delete.assert_awaited_once_with(USER_ID, "github")

    @pytest.mark.asyncio
    async def test_delete_404_when_not_connected(self) -> None:
        from app.api.v1.sea_chest import disconnect_credential

        svc = AsyncMock()
        svc.delete = AsyncMock(side_effect=SeaChestError("NOT_FOUND", "nope"))

        with pytest.raises(HTTPException) as exc:
            await disconnect_credential("github", _user(), svc)

        assert exc.value.status_code == 404


class TestOwnerScoping:
    @pytest.mark.asyncio
    async def test_foreign_user_only_sees_own_credentials(self) -> None:
        # The endpoint always passes the AUTHENTICATED user's id to the service —
        # a foreign user can never address another user's credentials.
        from app.api.v1.sea_chest import disconnect_credential, list_credentials

        svc = AsyncMock()
        svc.status = AsyncMock(return_value=[])
        svc.delete = AsyncMock(side_effect=SeaChestError("NOT_FOUND", "nope"))

        await list_credentials(_user(OTHER_USER_ID), svc)
        svc.status.assert_awaited_once_with(OTHER_USER_ID)

        with pytest.raises(HTTPException) as exc:
            await disconnect_credential("github", _user(OTHER_USER_ID), svc)
        assert exc.value.status_code == 404
        svc.delete.assert_awaited_once_with(OTHER_USER_ID, "github")
