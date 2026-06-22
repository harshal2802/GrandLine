"""Tests for the Return Bottle REST API (direct endpoint calls)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.enums import VoyageStatus

VOYAGE_ID = uuid.uuid4()


def _voyage(status: str = VoyageStatus.COMPLETED.value) -> MagicMock:
    v = MagicMock()
    v.id = VOYAGE_ID
    v.status = status
    return v


class TestSendReturnBottle:
    @pytest.mark.asyncio
    async def test_completed_voyage_returns_result_dict(self) -> None:
        from app.api.v1.return_bottle import send_return_bottle

        svc = AsyncMock()
        svc.report = AsyncMock(
            return_value={"issue_commented": True, "log_book_recorded": True}
        )

        result = await send_return_bottle(_voyage(), svc)

        assert result == {"issue_commented": True, "log_book_recorded": True}
        svc.report.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_completed_voyage_returns_409(self) -> None:
        from app.api.v1.return_bottle import send_return_bottle

        svc = AsyncMock()
        voyage = _voyage(status=VoyageStatus.BUILDING.value)

        with pytest.raises(HTTPException) as exc:
            await send_return_bottle(voyage, svc)

        assert exc.value.status_code == 409
        assert exc.value.detail["error"]["code"] == "VOYAGE_NOT_COMPLETED"
        svc.report.assert_not_called()


class TestOwnerScoping:
    @pytest.mark.asyncio
    async def test_missing_or_unowned_voyage_is_404_via_dependency(self) -> None:
        # The endpoint relies on `get_authorized_voyage`, which 404s a missing or
        # foreign voyage before the handler runs. Verify that dependency directly.
        from app.api.v1.dependencies import get_authorized_voyage

        session = AsyncMock()
        empty = MagicMock()
        empty.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=empty)
        user = MagicMock()
        user.id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc:
            await get_authorized_voyage(VOYAGE_ID, session, user)

        assert exc.value.status_code == 404
