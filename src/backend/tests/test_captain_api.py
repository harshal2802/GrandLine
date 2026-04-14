"""Tests for Captain Agent REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.enums import CrewRole, VoyageStatus
from app.schemas.captain import PhaseSpec, VoyagePlanSpec

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
PLAN_ID = uuid.uuid4()


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


def _mock_plan_model() -> MagicMock:
    plan = MagicMock()
    plan.id = PLAN_ID
    plan.voyage_id = VOYAGE_ID
    plan.phases = {
        "phases": [
            {
                "phase_number": 1,
                "name": "Design",
                "description": "Architecture",
                "assigned_to": "navigator",
                "depends_on": [],
                "artifacts": [],
            }
        ]
    }
    plan.version = 1
    plan.created_by = "captain"
    plan.created_at = datetime(2026, 4, 13, tzinfo=UTC)
    return plan


def _valid_spec() -> VoyagePlanSpec:
    return VoyagePlanSpec(
        phases=[
            PhaseSpec(
                phase_number=1,
                name="Design",
                description="Architecture",
                assigned_to=CrewRole.NAVIGATOR,
            )
        ]
    )


def _mock_captain_service() -> AsyncMock:
    svc = AsyncMock()
    svc.chart_course = AsyncMock(return_value=(_mock_plan_model(), _valid_spec()))
    svc.get_plan = AsyncMock(return_value=_mock_plan_model())
    return svc


class TestChartCourseEndpoint:
    @pytest.mark.asyncio
    async def test_returns_201_with_plan(self) -> None:
        from app.api.v1.captain import chart_course
        from app.schemas.captain import ChartCourseRequest

        svc = _mock_captain_service()
        body = ChartCourseRequest(task="Build a REST API with authentication and JWT tokens")
        voyage = _mock_voyage()

        result = await chart_course(VOYAGE_ID, body, _mock_user(), voyage, svc)

        assert result.voyage_id == VOYAGE_ID
        assert result.plan_id == PLAN_ID
        assert result.version == 1
        svc.chart_course.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_409_if_not_charted(self) -> None:
        from app.api.v1.captain import chart_course
        from app.schemas.captain import ChartCourseRequest

        svc = _mock_captain_service()
        body = ChartCourseRequest(task="Build a REST API with authentication and JWT tokens")
        voyage = _mock_voyage(status=VoyageStatus.PLANNING.value)

        with pytest.raises(HTTPException) as exc_info:
            await chart_course(VOYAGE_ID, body, _mock_user(), voyage, svc)

        assert exc_info.value.status_code == 409


class TestGetPlanEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_with_plan(self) -> None:
        from app.api.v1.captain import get_plan

        svc = _mock_captain_service()

        result = await get_plan(VOYAGE_ID, _mock_user(), _mock_voyage(), svc)

        assert result.plan_id == PLAN_ID
        assert result.version == 1

    @pytest.mark.asyncio
    async def test_returns_404_when_no_plan(self) -> None:
        from app.api.v1.captain import get_plan

        svc = _mock_captain_service()
        svc.get_plan.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_plan(VOYAGE_ID, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 404
