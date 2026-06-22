"""Tests for StandingOrderService (mocked AsyncSession — no database)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.dial_config import DialConfig
from app.models.enums import VoyageStatus
from app.models.standing_order import StandingOrder
from app.models.voyage import Voyage
from app.services.standing_order_service import StandingOrderError, StandingOrderService

USER_ID = uuid.uuid4()


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
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


def _order(**overrides: object) -> StandingOrder:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": USER_ID,
        "name": "bugfix voyage",
        "description": None,
        "target_repo": "github.com/acme/widgets",
        "dial_config": None,
        "plan_skeleton": None,
        "injected_context": None,
    }
    defaults.update(overrides)
    return StandingOrder(**defaults)


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_adds_flushes_commits_refreshes(self) -> None:
        session = _mock_session()
        service = StandingOrderService(session)

        order = await service.create(USER_ID, name="bugfix voyage")

        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        assert isinstance(added, StandingOrder)
        assert added.user_id == USER_ID
        assert added.name == "bugfix voyage"
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(order)


class TestGet:
    @pytest.mark.asyncio
    async def test_get_returns_owned_order(self) -> None:
        order = _order()
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(order))
        service = StandingOrderService(session)

        result = await service.get(order.id, USER_ID)

        assert result is order

    @pytest.mark.asyncio
    async def test_get_missing_or_foreign_raises_not_found(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        service = StandingOrderService(session)

        with pytest.raises(StandingOrderError) as exc:
            await service.get(uuid.uuid4(), USER_ID)

        assert exc.value.code == "NOT_FOUND"


class TestListForUser:
    @pytest.mark.asyncio
    async def test_lists_user_orders(self) -> None:
        orders = [_order(), _order()]
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalars_all(orders))
        service = StandingOrderService(session)

        result = await service.list_for_user(USER_ID)

        assert result == orders


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_applies_only_given_fields(self) -> None:
        order = _order(description="old")
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(order))
        service = StandingOrderService(session)

        result = await service.update(order.id, USER_ID, fields={"description": "new"})

        assert result.description == "new"
        assert result.name == "bugfix voyage"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_foreign_raises_not_found(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        service = StandingOrderService(session)

        with pytest.raises(StandingOrderError):
            await service.update(uuid.uuid4(), USER_ID, fields={"name": "x"})


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_owned(self) -> None:
        order = _order()
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(order))
        service = StandingOrderService(session)

        await service.delete(order.id, USER_ID)

        session.delete.assert_awaited_once_with(order)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_foreign_raises_not_found(self) -> None:
        session = _mock_session()
        session.execute = AsyncMock(return_value=_scalar_one_or_none(None))
        service = StandingOrderService(session)

        with pytest.raises(StandingOrderError):
            await service.delete(uuid.uuid4(), USER_ID)


class TestChart:
    @pytest.mark.asyncio
    async def test_chart_creates_charted_voyage_with_default_dial_config(self) -> None:
        order = _order(dial_config=None, target_repo="github.com/acme/widgets")
        session = _mock_session()
        service = StandingOrderService(session)

        voyage = await service.chart(order, task="Fix the flaky login test now")

        assert isinstance(voyage, Voyage)
        assert voyage.status == VoyageStatus.CHARTED.value
        assert voyage.user_id == USER_ID
        assert voyage.title == "bugfix voyage"
        assert voyage.target_repo == "github.com/acme/widgets"

        added = [c.args[0] for c in session.add.call_args_list]
        assert any(isinstance(a, Voyage) for a in added)
        dial = next(a for a in added if isinstance(a, DialConfig))
        # Default seeds every crew role with the deployment default provider.
        assert "captain" in dial.role_mapping
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chart_applies_preset_dial_config(self) -> None:
        order = _order(
            dial_config={
                "role_mapping": {"captain": {"provider": "anthropic", "model": "preset-model"}},
                "fallback_chain": {"captain": ["openai"]},
            }
        )
        session = _mock_session()
        service = StandingOrderService(session)

        await service.chart(order, task="Fix the flaky login test now")

        added = [c.args[0] for c in session.add.call_args_list]
        dial = next(a for a in added if isinstance(a, DialConfig))
        assert dial.role_mapping == {"captain": {"provider": "anthropic", "model": "preset-model"}}
        assert dial.fallback_chain == {"captain": ["openai"]}

    @pytest.mark.asyncio
    async def test_chart_prepends_injected_context_to_description(self) -> None:
        order = _order(injected_context="Honor conventions.md")
        session = _mock_session()
        service = StandingOrderService(session)

        voyage = await service.chart(order, task="Fix the flaky login test now")

        assert voyage.description == "Honor conventions.md\n\n---\n\nFix the flaky login test now"

    @pytest.mark.asyncio
    async def test_chart_without_injected_context_uses_task_alone(self) -> None:
        order = _order(injected_context=None)
        session = _mock_session()
        service = StandingOrderService(session)

        voyage = await service.chart(order, task="Fix the flaky login test now")

        assert voyage.description == "Fix the flaky login test now"

    @pytest.mark.asyncio
    async def test_chart_overrides_win(self) -> None:
        order = _order(name="bugfix voyage", target_repo="github.com/acme/widgets")
        session = _mock_session()
        service = StandingOrderService(session)

        voyage = await service.chart(
            order,
            task="Fix the flaky login test now",
            title="Custom title",
            target_repo="github.com/acme/other",
        )

        assert voyage.title == "Custom title"
        assert voyage.target_repo == "github.com/acme/other"


class TestReader:
    def test_reader_returns_instance(self) -> None:
        assert isinstance(StandingOrderService.reader(_mock_session()), StandingOrderService)
