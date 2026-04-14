"""Tests for NavigatorService (mocked dependencies)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import CrewRole, VoyageStatus
from app.models.poneglyph import Poneglyph
from app.models.vivre_card import VivreCard
from app.schemas.dial_system import CompletionResult, TokenUsage
from app.services.navigator_service import NavigatorError, NavigatorService

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

VALID_PONEGLYPHS_JSON = json.dumps(
    {
        "poneglyphs": [
            {
                "phase_number": 1,
                "title": "Design architecture",
                "task_description": "Create system architecture document",
                "technical_constraints": ["PostgreSQL"],
                "expected_inputs": ["Requirements"],
                "expected_outputs": ["design.md"],
                "test_criteria": ["Covers all modules"],
                "file_paths": ["docs/design.md"],
                "implementation_notes": "Use C4 model",
            },
            {
                "phase_number": 2,
                "title": "Implement API",
                "task_description": "Build REST endpoints",
                "technical_constraints": ["FastAPI"],
                "expected_inputs": ["design.md"],
                "expected_outputs": ["src/main.py"],
                "test_criteria": ["Endpoints return 200"],
                "file_paths": ["src/main.py"],
                "implementation_notes": "RESTful",
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


def _mock_plan() -> MagicMock:
    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.voyage_id = VOYAGE_ID
    plan.phases = {
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
    plan.version = 1
    return plan


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
    router.route = AsyncMock(return_value=_llm_result(VALID_PONEGLYPHS_JSON))
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
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.fixture
def service(
    mock_dial_router: AsyncMock,
    mock_mushi: AsyncMock,
    mock_session: AsyncMock,
) -> NavigatorService:
    return NavigatorService(mock_dial_router, mock_mushi, mock_session)


class TestDraftPoneglyphs:
    @pytest.mark.asyncio
    async def test_restores_charted_status_after_success(
        self, service: NavigatorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.draft_poneglyphs(voyage, _mock_plan())

        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_invokes_dial_router_with_navigator_role(
        self, service: NavigatorService, mock_dial_router: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.draft_poneglyphs(voyage, _mock_plan())

        mock_dial_router.route.assert_awaited_once()
        call_args = mock_dial_router.route.call_args
        assert call_args.args[0] == CrewRole.NAVIGATOR

    @pytest.mark.asyncio
    async def test_persists_one_poneglyph_per_phase(
        self, service: NavigatorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        result = await service.draft_poneglyphs(voyage, _mock_plan())

        assert len(result) == 2
        added = [call.args[0] for call in mock_session.add.call_args_list]
        poneglyph_adds = [o for o in added if isinstance(o, Poneglyph)]
        assert len(poneglyph_adds) == 2

    @pytest.mark.asyncio
    async def test_stores_content_as_serialized_spec(
        self, service: NavigatorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        result = await service.draft_poneglyphs(voyage, _mock_plan())

        content = json.loads(result[0].content)
        assert content["title"] == "Design architecture"
        assert content["phase_number"] == 1

    @pytest.mark.asyncio
    async def test_stores_metadata_summary(
        self, service: NavigatorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        result = await service.draft_poneglyphs(voyage, _mock_plan())

        meta = result[0].metadata_
        assert meta["phase_name"] == "Design architecture"
        assert meta["test_criteria_count"] == 1
        assert meta["file_count"] == 1

    @pytest.mark.asyncio
    async def test_creates_vivre_card_checkpoint(
        self, service: NavigatorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.draft_poneglyphs(voyage, _mock_plan())

        added = [call.args[0] for call in mock_session.add.call_args_list]
        vivre_cards = [o for o in added if isinstance(o, VivreCard)]
        assert len(vivre_cards) == 1
        assert vivre_cards[0].crew_member == "navigator"
        assert vivre_cards[0].voyage_id == VOYAGE_ID

    @pytest.mark.asyncio
    async def test_commits_all_writes_atomically(
        self, service: NavigatorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.draft_poneglyphs(voyage, _mock_plan())

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publishes_event_per_poneglyph(
        self, service: NavigatorService, mock_mushi: AsyncMock
    ) -> None:
        voyage = _mock_voyage()

        await service.draft_poneglyphs(voyage, _mock_plan())

        assert mock_mushi.publish.await_count == 2
        events = [call.args[1] for call in mock_mushi.publish.call_args_list]
        assert all(e.event_type == "poneglyph_drafted" for e in events)
        assert all(e.source_role == CrewRole.NAVIGATOR for e in events)

    @pytest.mark.asyncio
    async def test_succeeds_when_publish_fails(
        self,
        service: NavigatorService,
        mock_mushi: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_mushi.publish.side_effect = ConnectionError("Redis unavailable")
        voyage = _mock_voyage()

        result = await service.draft_poneglyphs(voyage, _mock_plan())

        assert len(result) == 2
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_navigator_error_on_invalid_llm_output(
        self,
        service: NavigatorService,
        mock_dial_router: AsyncMock,
    ) -> None:
        mock_dial_router.route.return_value = _llm_result("not valid json")
        voyage = _mock_voyage()

        with pytest.raises(NavigatorError, match="Failed to parse"):
            await service.draft_poneglyphs(voyage, _mock_plan())

    @pytest.mark.asyncio
    async def test_resets_status_on_parse_failure(
        self,
        service: NavigatorService,
        mock_dial_router: AsyncMock,
    ) -> None:
        mock_dial_router.route.return_value = _llm_result("garbage")
        voyage = _mock_voyage()

        with pytest.raises(NavigatorError):
            await service.draft_poneglyphs(voyage, _mock_plan())

        assert voyage.status == VoyageStatus.CHARTED.value


class TestGetPoneglyphs:
    @pytest.mark.asyncio
    async def test_returns_poneglyphs_ordered(
        self, service: NavigatorService, mock_session: AsyncMock
    ) -> None:
        p1, p2 = MagicMock(), MagicMock()
        p1.phase_number, p2.phase_number = 1, 2
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [p1, p2]
        mock_session.execute.return_value = result_mock

        result = await service.get_poneglyphs(VOYAGE_ID)

        assert len(result) == 2
        assert result[0].phase_number == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(
        self, service: NavigatorService, mock_session: AsyncMock
    ) -> None:
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        result = await service.get_poneglyphs(VOYAGE_ID)

        assert result == []

    @pytest.mark.asyncio
    async def test_reader_instance_can_get_poneglyphs(self) -> None:
        session = AsyncMock()
        p1 = MagicMock()
        p1.phase_number = 1
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [p1]
        session.execute = AsyncMock(return_value=result_mock)

        reader = NavigatorService.reader(session)
        result = await reader.get_poneglyphs(VOYAGE_ID)

        assert len(result) == 1
