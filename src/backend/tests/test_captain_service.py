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


def _mock_voyage(
    status: str = VoyageStatus.CHARTED.value,
    target_repo: str | None = None,
) -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.status = status
    # Default to None so the Log Book recall hook is a no-op unless a test
    # explicitly exercises it.
    voyage.target_repo = target_repo
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
    async def test_restores_charted_status_after_success(
        self, service: CaptainService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.chart_course(voyage, "Build a REST API with authentication")

        assert voyage.status == VoyageStatus.CHARTED.value

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

        # Captain publishes voyage_plan_created and (Phase 16.0) crew_action_recorded.
        published = [c.args[1] for c in mock_mushi.publish.await_args_list]
        plan_events = [e for e in published if e.event_type == "voyage_plan_created"]
        assert len(plan_events) == 1
        assert plan_events[0].source_role == CrewRole.CAPTAIN

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
    async def test_succeeds_when_publish_fails(
        self,
        service: CaptainService,
        mock_mushi: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_mushi.publish.side_effect = ConnectionError("Redis unavailable")
        voyage = _mock_voyage()

        plan_model, spec = await service.chart_course(
            voyage, "Build a REST API with authentication"
        )

        assert spec is not None
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


class TestLogBookRecall:
    @pytest.mark.asyncio
    async def test_prepends_recalled_context_when_target_repo_set(
        self, service: CaptainService, mock_dial_router: AsyncMock
    ) -> None:
        voyage = _mock_voyage(target_repo="github.com/acme/widgets")
        recalled = (
            "## Log Book — prior knowledge for github.com/acme/widgets"
            "\n\n- (layout) src/ holds it"
        )
        service._log_book.render_context = AsyncMock(  # type: ignore[method-assign]
            return_value=recalled
        )

        await service.chart_course(voyage, "Build a REST API with authentication")

        service._log_book.render_context.assert_awaited_once_with("github.com/acme/widgets")
        sent_task = mock_dial_router.route.call_args.args[1].messages[-1]["content"]
        assert "Log Book — prior knowledge" in sent_task
        assert "Build a REST API with authentication" in sent_task
        assert "\n\n---\n\n" in sent_task

    @pytest.mark.asyncio
    async def test_does_not_prepend_when_target_repo_none(
        self, service: CaptainService, mock_dial_router: AsyncMock
    ) -> None:
        voyage = _mock_voyage(target_repo=None)
        service._log_book.render_context = AsyncMock(return_value="")  # type: ignore[method-assign]

        await service.chart_course(voyage, "Build a REST API with authentication")

        service._log_book.render_context.assert_not_awaited()
        sent_task = mock_dial_router.route.call_args.args[1].messages[-1]["content"]
        assert "Log Book" not in sent_task

    @pytest.mark.asyncio
    async def test_does_not_prepend_when_log_book_empty(
        self, service: CaptainService, mock_dial_router: AsyncMock
    ) -> None:
        voyage = _mock_voyage(target_repo="github.com/acme/widgets")
        service._log_book.render_context = AsyncMock(return_value="")  # type: ignore[method-assign]

        await service.chart_course(voyage, "Build a REST API with authentication")

        service._log_book.render_context.assert_awaited_once()
        sent_task = mock_dial_router.route.call_args.args[1].messages[-1]["content"]
        assert "Log Book" not in sent_task

    @pytest.mark.asyncio
    async def test_recall_failure_is_best_effort(
        self, service: CaptainService, mock_dial_router: AsyncMock
    ) -> None:
        voyage = _mock_voyage(target_repo="github.com/acme/widgets")
        service._log_book.render_context = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("DB hiccup")
        )

        plan_model, spec = await service.chart_course(
            voyage, "Build a REST API with authentication"
        )

        assert spec is not None
        sent_task = mock_dial_router.route.call_args.args[1].messages[-1]["content"]
        assert sent_task == "Build a REST API with authentication"


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

    @pytest.mark.asyncio
    async def test_reader_instance_can_get_plan(self) -> None:
        session = AsyncMock()
        plan = MagicMock()
        plan.version = 3
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = plan
        session.execute = AsyncMock(return_value=result_mock)

        reader = CaptainService.reader(session)
        result = await reader.get_plan(VOYAGE_ID)

        assert result is not None
        assert result.version == 3
