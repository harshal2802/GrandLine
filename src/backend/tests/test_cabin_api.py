"""Tests for the Cabin REST API (direct endpoint calls, owner-scoped).

GET/POST/DELETE all operate on the requesting user's OWN Cabin (keyed on
``user.id``); the status response carries no secret.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.cabin.backend import CabinError, CabinStatus

USER_ID = uuid.uuid4()


def _user() -> MagicMock:
    u = MagicMock()
    u.id = USER_ID
    return u


def _status() -> CabinStatus:
    now = datetime.now(UTC)
    return CabinStatus(
        cabin_id="null-cabin",
        user_id=USER_ID,
        state="running",
        created_at=now,
        last_active=now,
        materialized_kinds=["github"],
        network_allow=["api.github.com"],
    )


class TestGetCabin:
    async def test_returns_status(self) -> None:
        from app.api.v1.cabin import get_cabin

        service = AsyncMock()
        service.status = AsyncMock(return_value=_status())

        result = await get_cabin(user=_user(), service=service)

        assert result.cabin_id == "null-cabin"
        service.status.assert_awaited_once_with(USER_ID)

    async def test_404_when_no_cabin(self) -> None:
        from app.api.v1.cabin import get_cabin

        service = AsyncMock()
        service.status = AsyncMock(side_effect=CabinError("NOT_FOUND", "No cabin for user"))

        with pytest.raises(HTTPException) as exc:
            await get_cabin(user=_user(), service=service)
        assert exc.value.status_code == 404

    async def test_status_response_has_no_secret(self) -> None:
        from app.api.v1.cabin import get_cabin

        service = AsyncMock()
        service.status = AsyncMock(return_value=_status())

        result = await get_cabin(user=_user(), service=service)
        dumped = result.model_dump_json()
        # Only kinds + allow-list provenance — no secret value field exists at all.
        assert "secret" not in dumped.lower()
        assert "token" not in dumped.lower()


class TestEnsureCabin:
    async def test_ensures_and_returns_status(self) -> None:
        from app.api.v1.cabin import ensure_cabin

        service = AsyncMock()
        service.ensure = AsyncMock(return_value=_status())
        session = AsyncMock()

        result = await ensure_cabin(user=_user(), session=session, service=service)

        assert result.state == "running"
        service.ensure.assert_awaited_once_with(USER_ID, session)


class TestDestroyCabin:
    async def test_returns_204(self) -> None:
        from app.api.v1.cabin import destroy_cabin

        service = AsyncMock()
        service.destroy = AsyncMock()

        result = await destroy_cabin(user=_user(), service=service)

        assert result.status_code == 204
        service.destroy.assert_awaited_once_with(USER_ID)

    async def test_404_when_no_cabin(self) -> None:
        from app.api.v1.cabin import destroy_cabin

        service = AsyncMock()
        service.destroy = AsyncMock(side_effect=CabinError("NOT_FOUND", "No cabin for user"))

        with pytest.raises(HTTPException) as exc:
            await destroy_cabin(user=_user(), service=service)
        assert exc.value.status_code == 404
