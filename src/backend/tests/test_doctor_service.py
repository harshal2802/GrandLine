"""Tests for DoctorService (mocked dependencies)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import CrewRole, VoyageStatus
from app.models.health_check import HealthCheck
from app.models.vivre_card import VivreCard
from app.schemas.dial_system import CompletionResult, TokenUsage
from app.schemas.execution import ExecutionResult
from app.services.doctor_service import DoctorError, DoctorService

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
PONEGLYPH_ID_1 = uuid.uuid4()
PONEGLYPH_ID_2 = uuid.uuid4()

VALID_DOCTOR_OUTPUT = json.dumps(
    {
        "health_checks": [
            {
                "phase_number": 1,
                "file_path": "tests/test_auth.py",
                "content": "def test_auth(): assert False  # TDD",
                "framework": "pytest",
            },
            {
                "phase_number": 2,
                "file_path": "tests/test_api.py",
                "content": "def test_api(): assert False  # TDD",
                "framework": "pytest",
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
    voyage.target_repo = target_repo
    return voyage


def _mock_poneglyph(poneglyph_id: uuid.UUID, phase_number: int) -> MagicMock:
    p = MagicMock()
    p.id = poneglyph_id
    p.voyage_id = VOYAGE_ID
    p.phase_number = phase_number
    p.content = json.dumps(
        {
            "phase_number": phase_number,
            "title": f"Phase {phase_number}",
            "task_description": "desc",
            "technical_constraints": [],
            "expected_inputs": [],
            "expected_outputs": [],
            "test_criteria": ["must work"],
            "file_paths": [f"src/phase{phase_number}.py"],
            "implementation_notes": "",
        }
    )
    return p


def _poneglyphs() -> list[MagicMock]:
    return [_mock_poneglyph(PONEGLYPH_ID_1, 1), _mock_poneglyph(PONEGLYPH_ID_2, 2)]


def _llm_result(content: str) -> CompletionResult:
    return CompletionResult(
        content=content,
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=200, total_tokens=300),
    )


def _exec_result(exit_code: int, stdout: str = "") -> ExecutionResult:
    return ExecutionResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr="",
        timed_out=False,
        duration_seconds=1.0,
        sandbox_id="sb-1",
    )


@pytest.fixture
def mock_dial_router() -> AsyncMock:
    router = AsyncMock()
    router.route = AsyncMock(return_value=_llm_result(VALID_DOCTOR_OUTPUT))
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
def mock_execution() -> AsyncMock:
    svc = AsyncMock()
    svc.run = AsyncMock(return_value=_exec_result(0, "2 passed"))
    return svc


@pytest.fixture
def mock_git() -> AsyncMock:
    git = AsyncMock()
    git.create_branch = AsyncMock()
    git.commit = AsyncMock()
    git.push = AsyncMock()
    return git


@pytest.fixture
def service(
    mock_dial_router: AsyncMock,
    mock_mushi: AsyncMock,
    mock_session: AsyncMock,
    mock_execution: AsyncMock,
    mock_git: AsyncMock,
) -> DoctorService:
    return DoctorService(mock_dial_router, mock_mushi, mock_session, mock_execution, mock_git)


class TestWriteHealthChecks:
    @pytest.mark.asyncio
    async def test_restores_charted_status_after_success(self, service: DoctorService) -> None:
        voyage = _mock_voyage()
        await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_invokes_dial_router_with_doctor_role(
        self, service: DoctorService, mock_dial_router: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        mock_dial_router.route.assert_awaited_once()
        assert mock_dial_router.route.call_args.args[0] == CrewRole.DOCTOR

    @pytest.mark.asyncio
    async def test_persists_one_health_check_per_spec(
        self, service: DoctorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        result = await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        assert len(result) == 2
        added = [call.args[0] for call in mock_session.add.call_args_list]
        hc_adds = [o for o in added if isinstance(o, HealthCheck)]
        assert len(hc_adds) == 2

    @pytest.mark.asyncio
    async def test_links_poneglyph_by_phase_number(self, service: DoctorService) -> None:
        voyage = _mock_voyage()
        result = await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        by_phase = {hc.phase_number: hc.poneglyph_id for hc in result}
        assert by_phase[1] == PONEGLYPH_ID_1
        assert by_phase[2] == PONEGLYPH_ID_2

    @pytest.mark.asyncio
    async def test_stores_content_and_file_path_verbatim(self, service: DoctorService) -> None:
        voyage = _mock_voyage()
        result = await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        by_phase = {hc.phase_number: hc for hc in result}
        assert by_phase[1].file_path == "tests/test_auth.py"
        assert "def test_auth" in by_phase[1].content

    @pytest.mark.asyncio
    async def test_creates_vivre_card_checkpoint(
        self, service: DoctorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        added = [call.args[0] for call in mock_session.add.call_args_list]
        cards = [o for o in added if isinstance(o, VivreCard)]
        assert len(cards) == 1
        assert cards[0].crew_member == "doctor"

    @pytest.mark.asyncio
    async def test_commits_atomically(
        self, service: DoctorService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publishes_health_check_written_event_per_row(
        self, service: DoctorService, mock_mushi: AsyncMock
    ) -> None:
        voyage = _mock_voyage()
        await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        assert mock_mushi.publish.await_count == 2
        events = [call.args[1] for call in mock_mushi.publish.call_args_list]
        assert all(e.event_type == "health_check_written" for e in events)
        assert all(e.source_role == CrewRole.DOCTOR for e in events)

    @pytest.mark.asyncio
    async def test_succeeds_when_publish_fails(
        self,
        service: DoctorService,
        mock_mushi: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        mock_mushi.publish.side_effect = ConnectionError("Redis down")
        voyage = _mock_voyage()
        result = await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        assert len(result) == 2
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deletes_existing_health_checks_before_insert(
        self, service: DoctorService, mock_session: AsyncMock
    ) -> None:
        from sqlalchemy.sql.dml import Delete

        voyage = _mock_voyage()
        await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        executed = [call.args[0] for call in mock_session.execute.call_args_list]
        deletes = [s for s in executed if isinstance(s, Delete)]
        assert len(deletes) == 1

    @pytest.mark.asyncio
    async def test_raises_on_invalid_llm_output(
        self, service: DoctorService, mock_dial_router: AsyncMock
    ) -> None:
        mock_dial_router.route.return_value = _llm_result("not json")
        voyage = _mock_voyage()
        with pytest.raises(DoctorError) as exc_info:
            await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        assert exc_info.value.code == "HEALTH_CHECK_PARSE_FAILED"
        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_raises_on_phase_mismatch(
        self, service: DoctorService, mock_dial_router: AsyncMock
    ) -> None:
        bad = json.dumps(
            {
                "health_checks": [
                    {
                        "phase_number": 1,
                        "file_path": "tests/a.py",
                        "content": "x",
                        "framework": "pytest",
                    },
                    {
                        "phase_number": 99,
                        "file_path": "tests/b.py",
                        "content": "y",
                        "framework": "pytest",
                    },
                ]
            }
        )
        mock_dial_router.route.return_value = _llm_result(bad)
        voyage = _mock_voyage()
        with pytest.raises(DoctorError) as exc_info:
            await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        assert exc_info.value.code == "HEALTH_CHECK_PHASE_MISMATCH"
        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_commits_to_git_when_target_repo_set(
        self, service: DoctorService, mock_git: AsyncMock
    ) -> None:
        voyage = _mock_voyage(target_repo="https://github.com/org/repo.git")
        await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        mock_git.create_branch.assert_awaited_once()
        mock_git.commit.assert_awaited_once()
        mock_git.push.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_git_when_no_target_repo(
        self, service: DoctorService, mock_git: AsyncMock
    ) -> None:
        voyage = _mock_voyage(target_repo=None)
        await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        mock_git.create_branch.assert_not_called()
        mock_git.commit.assert_not_called()
        mock_git.push.assert_not_called()

    @pytest.mark.asyncio
    async def test_succeeds_when_git_commit_fails(
        self, service: DoctorService, mock_git: AsyncMock
    ) -> None:
        mock_git.commit.side_effect = RuntimeError("git boom")
        voyage = _mock_voyage(target_repo="https://github.com/org/repo.git")
        result = await service.write_health_checks(voyage, _poneglyphs(), USER_ID)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_no_git_service_skips_git_path(
        self,
        mock_dial_router: AsyncMock,
        mock_mushi: AsyncMock,
        mock_session: AsyncMock,
        mock_execution: AsyncMock,
    ) -> None:
        svc = DoctorService(
            mock_dial_router, mock_mushi, mock_session, mock_execution, git_service=None
        )
        voyage = _mock_voyage(target_repo="https://github.com/org/repo.git")
        result = await svc.write_health_checks(voyage, _poneglyphs(), USER_ID)
        assert len(result) == 2


class TestValidateCode:
    @pytest.mark.asyncio
    async def test_passes_when_pytest_exits_zero(
        self,
        service: DoctorService,
        mock_session: AsyncMock,
        mock_execution: AsyncMock,
    ) -> None:
        mock_execution.run.return_value = _exec_result(0, "===== 2 passed in 0.01s =====")
        hc1 = HealthCheck(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            phase_number=1,
            file_path="tests/a.py",
            content="x",
            framework="pytest",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [hc1]
        mock_session.execute.return_value = result_mock

        voyage = _mock_voyage()
        resp = await service.validate_code(voyage, USER_ID, {"src/a.py": "pass"})

        assert resp.status == "passed"
        assert resp.passed_count == 2
        assert hc1.last_run_status == "passed"

    @pytest.mark.asyncio
    async def test_fails_when_pytest_exits_nonzero(
        self,
        service: DoctorService,
        mock_session: AsyncMock,
        mock_execution: AsyncMock,
    ) -> None:
        mock_execution.run.return_value = _exec_result(1, "1 failed, 1 passed")
        hc1 = HealthCheck(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            phase_number=1,
            file_path="tests/a.py",
            content="x",
            framework="pytest",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [hc1]
        mock_session.execute.return_value = result_mock

        voyage = _mock_voyage()
        resp = await service.validate_code(voyage, USER_ID, {"src/a.py": "pass"})

        assert resp.status == "failed"
        assert resp.failed_count == 1
        assert hc1.last_run_status == "failed"

    @pytest.mark.asyncio
    async def test_layers_shipwright_and_healthcheck_files(
        self,
        service: DoctorService,
        mock_session: AsyncMock,
        mock_execution: AsyncMock,
    ) -> None:
        hc = HealthCheck(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            phase_number=1,
            file_path="tests/test_a.py",
            content="test_content",
            framework="pytest",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [hc]
        mock_session.execute.return_value = result_mock

        voyage = _mock_voyage()
        await service.validate_code(voyage, USER_ID, {"src/a.py": "shipwright"})

        exec_request = mock_execution.run.call_args.args[1]
        assert "src/a.py" in exec_request.files
        assert "tests/test_a.py" in exec_request.files
        assert exec_request.files["tests/test_a.py"] == "test_content"

    @pytest.mark.asyncio
    async def test_restores_charted_status_after_success(
        self,
        service: DoctorService,
        mock_session: AsyncMock,
    ) -> None:
        hc = HealthCheck(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            phase_number=1,
            file_path="tests/a.py",
            content="x",
            framework="pytest",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [hc]
        mock_session.execute.return_value = result_mock

        voyage = _mock_voyage()
        await service.validate_code(voyage, USER_ID, {"src/a.py": "pass"})
        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_publishes_passed_event_on_pass(
        self,
        service: DoctorService,
        mock_session: AsyncMock,
        mock_mushi: AsyncMock,
    ) -> None:
        hc = HealthCheck(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            phase_number=1,
            file_path="tests/a.py",
            content="x",
            framework="pytest",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [hc]
        mock_session.execute.return_value = result_mock

        voyage = _mock_voyage()
        await service.validate_code(voyage, USER_ID, {"src/a.py": "pass"})

        event = mock_mushi.publish.call_args.args[1]
        assert event.event_type == "validation_passed"

    @pytest.mark.asyncio
    async def test_publishes_failed_event_on_fail(
        self,
        service: DoctorService,
        mock_session: AsyncMock,
        mock_mushi: AsyncMock,
        mock_execution: AsyncMock,
    ) -> None:
        mock_execution.run.return_value = _exec_result(1, "1 failed")
        hc = HealthCheck(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            phase_number=1,
            file_path="tests/a.py",
            content="x",
            framework="pytest",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [hc]
        mock_session.execute.return_value = result_mock

        voyage = _mock_voyage()
        await service.validate_code(voyage, USER_ID, {"src/a.py": "pass"})

        event = mock_mushi.publish.call_args.args[1]
        assert event.event_type == "validation_failed"

    @pytest.mark.asyncio
    async def test_raises_when_no_health_checks(
        self,
        service: DoctorService,
        mock_session: AsyncMock,
    ) -> None:
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        voyage = _mock_voyage()
        with pytest.raises(DoctorError) as exc_info:
            await service.validate_code(voyage, USER_ID, {"src/a.py": "pass"})
        assert exc_info.value.code == "NO_HEALTH_CHECKS"
        assert voyage.status == VoyageStatus.CHARTED.value


class TestGetHealthChecks:
    @pytest.mark.asyncio
    async def test_returns_ordered_rows(
        self, service: DoctorService, mock_session: AsyncMock
    ) -> None:
        hc1, hc2 = MagicMock(), MagicMock()
        hc1.phase_number, hc2.phase_number = 1, 2
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [hc1, hc2]
        mock_session.execute.return_value = result_mock

        result = await service.get_health_checks(VOYAGE_ID)
        assert len(result) == 2
        assert result[0].phase_number == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, service: DoctorService, mock_session: AsyncMock
    ) -> None:
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        result = await service.get_health_checks(VOYAGE_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_reader_instance_works(self) -> None:
        session = AsyncMock()
        hc = MagicMock()
        hc.phase_number = 1
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [hc]
        session.execute = AsyncMock(return_value=result_mock)

        reader = DoctorService.reader(session)
        result = await reader.get_health_checks(VOYAGE_ID)
        assert len(result) == 1
