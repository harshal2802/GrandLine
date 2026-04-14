"""Tests for CaptainService (mocked dependencies)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import CrewRole, VoyageStatus
from app.models.vivre_card import VivreCard
from app.schemas.dial_system import CompletionResult, TokenUsage
from app.services.captain_service import CaptainError, CaptainService

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

VALID_PLAN_JSON = json.dumps(
    {
        "phases": [
            {
                "phase_number": 1,
                "name": "Design",
                "description": "Architecture doc",
                "assigned_to": "navigator",
                "depends_on": [],
                "artifacts": ["design.md"],
            },
            {
                "phase_number": 2,
                "name": "Implement",
                "description": "Write code",
                "assigned_to": "shipwright",
                "depends_on": [1],
                "artifacts": ["src/main.py"],
            },
        ]
    }
)


def _mock_voyage(status: str = VoyageStatus.CHARTED.value) -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.status = status
    return voyage


def _llm_result(content: str) -> CompletionResult:
    return CompletionResult(
        content=content,
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=200, total_tokens=300),
    )


@pytest.fixture
def mock_dial_router() -> AsyncMock:
    router = AsyncMock()
    router.route = AsyncMock(return_value=_llm_result(VALID_PLAN_JSON))
    return router


@pytest.fixture
def mock_mushi() -> AsyncMock:
    mushi = AsyncMock()
    mushi.publish = AsyncMock(return_value="msg-1")
    return mushi


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    # Default: no existing plan (scalar_one_or_none returns None)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.fixture
def service(
    mock_dial_router: AsyncMock,
    mock_mushi: AsyncMock,
    mock_session: AsyncMock,
) -> CaptainService:
    return CaptainService(mock_dial_router, mock_mushi, mock_session)


class TestChartCourse:
    @pytest.mark.asyncio
    async def test_sets_voyage_status_to_planning(
        self, service: CaptainService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.chart_course(voyage, "Build a REST API with authentication")

        assert voyage.status == VoyageStatus.PLANNING.value

    @pytest.mark.asyncio
    async def test_invokes_dial_router_with_captain_role(
        self, service: CaptainService, mock_dial_router: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.chart_course(voyage, "Build a REST API with authentication")

        mock_dial_router.route.assert_awaited_once()
        call_args = mock_dial_router.route.call_args
        assert call_args.args[0] == CrewRole.CAPTAIN

    @pytest.mark.asyncio
    async def test_persists_voyage_plan(
        self, service: CaptainService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        plan_model, spec = await service.chart_course(
            voyage, "Build a REST API with authentication"
        )

        mock_session.add.assert_called()
        assert len(spec.phases) == 2
        assert spec.phases[0].name == "Design"
        assert spec.phases[1].assigned_to == CrewRole.SHIPWRIGHT

    @pytest.mark.asyncio
    async def test_increments_plan_version(
        self, service: CaptainService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        # Simulate existing plan with version 2
        existing_plan = MagicMock()
        existing_plan.version = 2
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing_plan
        mock_session.execute.return_value = result_mock

        plan_model, _ = await service.chart_course(voyage, "Build a REST API with authentication")

        assert plan_model.version == 3

    @pytest.mark.asyncio
    async def test_publishes_voyage_plan_created_event(
        self, service: CaptainService, mock_mushi: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.chart_course(voyage, "Build a REST API with authentication")

        mock_mushi.publish.assert_awaited_once()
        call_args = mock_mushi.publish.call_args
        event = call_args.args[1]
        assert event.event_type == "voyage_plan_created"
        assert event.source_role == CrewRole.CAPTAIN

    @pytest.mark.asyncio
    async def test_creates_vivre_card_checkpoint(
        self, service: CaptainService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.chart_course(voyage, "Build a REST API with authentication")

        # session.add called twice: once for plan, once for VivreCard
        added_objects = [call.args[0] for call in mock_session.add.call_args_list]
        vivre_cards = [o for o in added_objects if isinstance(o, VivreCard)]
        assert len(vivre_cards) == 1
        assert vivre_cards[0].crew_member == "captain"
        assert vivre_cards[0].voyage_id == VOYAGE_ID

    @pytest.mark.asyncio
    async def test_commits_plan_and_checkpoint_together(
        self, service: CaptainService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.chart_course(voyage, "Build a REST API with authentication")

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_captain_error_on_invalid_llm_output(
        self,
        service: CaptainService,
        mock_dial_router: AsyncMock,
    ) -> None:
        mock_dial_router.route.return_value = _llm_result("not valid json at all")
        voyage = _mock_voyage()

        with pytest.raises(CaptainError, match="Failed to parse"):
            await service.chart_course(voyage, "Build a REST API with authentication")

    @pytest.mark.asyncio
    async def test_resets_status_on_parse_failure(
        self,
        service: CaptainService,
        mock_dial_router: AsyncMock,
    ) -> None:
        mock_dial_router.route.return_value = _llm_result("garbage output")
        voyage = _mock_voyage()

        with pytest.raises(CaptainError):
            await service.chart_course(voyage, "Build a REST API with authentication")

        assert voyage.status == VoyageStatus.CHARTED.value


class TestGetPlan:
    @pytest.mark.asyncio
    async def test_returns_latest_plan(
        self, service: CaptainService, mock_session: AsyncMock
    ) -> None:
        plan = MagicMock()
        plan.version = 2
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = plan
        mock_session.execute.return_value = result_mock

        result = await service.get_plan(VOYAGE_ID)

        assert result is not None
        assert result.version == 2

    @pytest.mark.asyncio
    async def test_returns_none_when_no_plan(
        self, service: CaptainService, mock_session: AsyncMock
    ) -> None:
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await service.get_plan(VOYAGE_ID)

        assert result is None
