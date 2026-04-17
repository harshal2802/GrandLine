"""Tests for Navigator Agent REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.enums import VoyageStatus
from app.services.navigator_service import NavigatorError

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
PONEGLYPH_ID_1 = uuid.uuid4()
PONEGLYPH_ID_2 = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _mock_voyage(status: str = VoyageStatus.CHARTED.value) -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.status = status
    return voyage


def _mock_plan() -> MagicMock:
    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.voyage_id = VOYAGE_ID
    plan.version = 1
    return plan


def _mock_poneglyph(poneglyph_id: uuid.UUID, phase_number: int) -> MagicMock:
    p = MagicMock()
    p.id = poneglyph_id
    p.voyage_id = VOYAGE_ID
    p.phase_number = phase_number
    p.content = '{"title": "Test"}'
    p.metadata_ = {"phase_name": "Test"}
    p.created_by = "navigator"
    p.created_at = datetime(2026, 4, 14, tzinfo=UTC)
    return p


def _mock_navigator_service() -> AsyncMock:
    svc = AsyncMock()
    svc.draft_poneglyphs = AsyncMock(
        return_value=[
            _mock_poneglyph(PONEGLYPH_ID_1, 1),
            _mock_poneglyph(PONEGLYPH_ID_2, 2),
        ]
    )
    svc.get_poneglyphs = AsyncMock(
        return_value=[
            _mock_poneglyph(PONEGLYPH_ID_1, 1),
            _mock_poneglyph(PONEGLYPH_ID_2, 2),
        ]
    )
    return svc


def _mock_captain_reader() -> AsyncMock:
    svc = AsyncMock()
    svc.get_plan = AsyncMock(return_value=_mock_plan())
    return svc


class TestDraftPoneglyphsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_201_with_poneglyph_ids(self) -> None:
        from app.api.v1.navigator import draft_poneglyphs

        nav_svc = _mock_navigator_service()
        cap_reader = _mock_captain_reader()

        result = await draft_poneglyphs(
            VOYAGE_ID, _mock_user(), _mock_voyage(), nav_svc, cap_reader
        )

        assert result.voyage_id == VOYAGE_ID
        assert result.count == 2
        assert PONEGLYPH_ID_1 in result.poneglyph_ids
        nav_svc.draft_poneglyphs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_409_if_not_charted(self) -> None:
        from app.api.v1.navigator import draft_poneglyphs

        nav_svc = _mock_navigator_service()
        cap_reader = _mock_captain_reader()
        voyage = _mock_voyage(status=VoyageStatus.PLANNING.value)

        with pytest.raises(HTTPException) as exc_info:
            await draft_poneglyphs(VOYAGE_ID, _mock_user(), voyage, nav_svc, cap_reader)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_returns_404_if_no_plan(self) -> None:
        from app.api.v1.navigator import draft_poneglyphs

        nav_svc = _mock_navigator_service()
        cap_reader = _mock_captain_reader()
        cap_reader.get_plan.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await draft_poneglyphs(VOYAGE_ID, _mock_user(), _mock_voyage(), nav_svc, cap_reader)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_422_on_navigator_error(self) -> None:
        from app.api.v1.navigator import draft_poneglyphs

        nav_svc = _mock_navigator_service()
        nav_svc.draft_poneglyphs.side_effect = NavigatorError(
            "PONEGLYPH_PARSE_FAILED", "Bad LLM output"
        )
        cap_reader = _mock_captain_reader()

        with pytest.raises(HTTPException) as exc_info:
            await draft_poneglyphs(VOYAGE_ID, _mock_user(), _mock_voyage(), nav_svc, cap_reader)

        assert exc_info.value.status_code == 422


class TestGetPoneglyphsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_poneglyphs(self) -> None:
        from app.api.v1.navigator import get_poneglyphs

        nav_svc = _mock_navigator_service()

        result = await get_poneglyphs(VOYAGE_ID, _mock_user(), _mock_voyage(), nav_svc)

        assert result.voyage_id == VOYAGE_ID
        assert len(result.poneglyphs) == 2

    @pytest.mark.asyncio
    async def test_returns_200_with_empty_list(self) -> None:
        from app.api.v1.navigator import get_poneglyphs

        nav_svc = _mock_navigator_service()
        nav_svc.get_poneglyphs.return_value = []

        result = await get_poneglyphs(VOYAGE_ID, _mock_user(), _mock_voyage(), nav_svc)

        assert result.voyage_id == VOYAGE_ID
        assert result.poneglyphs == []
