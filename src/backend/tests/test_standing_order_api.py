"""Tests for the Standing Orders REST API (direct endpoint calls)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.enums import VoyageStatus
from app.schemas.standing_order import (
    ChartFromStandingOrderRequest,
    StandingOrderCreate,
    StandingOrderUpdate,
)
from app.services.standing_order_service import StandingOrderError

USER_ID = uuid.uuid4()
ORDER_ID = uuid.uuid4()
VOYAGE_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _order_row(**overrides: object) -> MagicMock:
    row = MagicMock()
    row.id = ORDER_ID
    row.user_id = USER_ID
    row.name = "bugfix voyage"
    row.description = None
    row.target_repo = "github.com/acme/widgets"
    row.dial_config = None
    row.plan_skeleton = None
    row.injected_context = None
    row.created_at = datetime(2026, 6, 22, tzinfo=UTC)
    row.updated_at = datetime(2026, 6, 22, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _voyage_row() -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.title = "bugfix voyage"
    voyage.description = "Fix the flaky login test now"
    voyage.status = VoyageStatus.CHARTED.value
    voyage.target_repo = "github.com/acme/widgets"
    voyage.created_at = datetime(2026, 6, 22, tzinfo=UTC)
    voyage.updated_at = datetime(2026, 6, 22, tzinfo=UTC)
    return voyage


class TestListEndpoint:
    @pytest.mark.asyncio
    async def test_lists_orders(self) -> None:
        from app.api.v1.standing_orders import list_standing_orders

        svc = AsyncMock()
        svc.list_for_user = AsyncMock(return_value=[_order_row(), _order_row()])

        result = await list_standing_orders(_mock_user(), svc)

        assert len(result) == 2
        svc.list_for_user.assert_awaited_once_with(USER_ID)


class TestCreateEndpoint:
    @pytest.mark.asyncio
    async def test_creates_order(self) -> None:
        from app.api.v1.standing_orders import create_standing_order

        svc = AsyncMock()
        svc.create = AsyncMock(return_value=_order_row())
        body = StandingOrderCreate(name="bugfix voyage")

        result = await create_standing_order(body, _mock_user(), svc)

        assert result.name == "bugfix voyage"
        svc.create.assert_awaited_once()
        assert svc.create.call_args.args[0] == USER_ID


class TestGetEndpoint:
    @pytest.mark.asyncio
    async def test_returns_order(self) -> None:
        from app.api.v1.standing_orders import get_standing_order

        svc = AsyncMock()
        svc.get = AsyncMock(return_value=_order_row())

        result = await get_standing_order(ORDER_ID, _mock_user(), svc)

        assert result.id == ORDER_ID

    @pytest.mark.asyncio
    async def test_404_when_not_found(self) -> None:
        from app.api.v1.standing_orders import get_standing_order

        svc = AsyncMock()
        svc.get = AsyncMock(side_effect=StandingOrderError("NOT_FOUND", "nope"))

        with pytest.raises(HTTPException) as exc:
            await get_standing_order(ORDER_ID, _mock_user(), svc)

        assert exc.value.status_code == 404


class TestUpdateEndpoint:
    @pytest.mark.asyncio
    async def test_updates_with_only_set_fields(self) -> None:
        from app.api.v1.standing_orders import update_standing_order

        svc = AsyncMock()
        svc.update = AsyncMock(return_value=_order_row(description="new"))
        body = StandingOrderUpdate(description="new")

        result = await update_standing_order(ORDER_ID, body, _mock_user(), svc)

        assert result.description == "new"
        svc.update.assert_awaited_once_with(ORDER_ID, USER_ID, fields={"description": "new"})

    @pytest.mark.asyncio
    async def test_404_when_not_found(self) -> None:
        from app.api.v1.standing_orders import update_standing_order

        svc = AsyncMock()
        svc.update = AsyncMock(side_effect=StandingOrderError("NOT_FOUND", "nope"))

        with pytest.raises(HTTPException) as exc:
            await update_standing_order(ORDER_ID, StandingOrderUpdate(name="x"), _mock_user(), svc)

        assert exc.value.status_code == 404


class TestDeleteEndpoint:
    @pytest.mark.asyncio
    async def test_deletes(self) -> None:
        from app.api.v1.standing_orders import delete_standing_order

        svc = AsyncMock()
        svc.delete = AsyncMock(return_value=None)

        result = await delete_standing_order(ORDER_ID, _mock_user(), svc)

        assert result.status_code == 204
        svc.delete.assert_awaited_once_with(ORDER_ID, USER_ID)

    @pytest.mark.asyncio
    async def test_404_when_not_found(self) -> None:
        from app.api.v1.standing_orders import delete_standing_order

        svc = AsyncMock()
        svc.delete = AsyncMock(side_effect=StandingOrderError("NOT_FOUND", "nope"))

        with pytest.raises(HTTPException) as exc:
            await delete_standing_order(ORDER_ID, _mock_user(), svc)

        assert exc.value.status_code == 404


class TestChartEndpoint:
    @pytest.mark.asyncio
    async def test_charts_voyage_from_order(self) -> None:
        from app.api.v1.standing_orders import chart_from_standing_order

        order = _order_row()
        svc = AsyncMock()
        svc.get = AsyncMock(return_value=order)
        svc.chart = AsyncMock(return_value=_voyage_row())
        body = ChartFromStandingOrderRequest(task="Fix the flaky login test now")

        result = await chart_from_standing_order(ORDER_ID, body, _mock_user(), svc)

        assert result.id == VOYAGE_ID
        assert result.status == VoyageStatus.CHARTED
        svc.get.assert_awaited_once_with(ORDER_ID, USER_ID)
        svc.chart.assert_awaited_once_with(
            order,
            task="Fix the flaky login test now",
            title=None,
            target_repo=None,
        )

    @pytest.mark.asyncio
    async def test_404_when_order_not_found(self) -> None:
        from app.api.v1.standing_orders import chart_from_standing_order

        svc = AsyncMock()
        svc.get = AsyncMock(side_effect=StandingOrderError("NOT_FOUND", "nope"))
        body = ChartFromStandingOrderRequest(task="Fix the flaky login test now")

        with pytest.raises(HTTPException) as exc:
            await chart_from_standing_order(ORDER_ID, body, _mock_user(), svc)

        assert exc.value.status_code == 404
        svc.chart.assert_not_called()
