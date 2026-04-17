"""Tests for Shipwright LangGraph graph (mocked LLM + mocked executor)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.crew.shipwright_graph import build_shipwright_graph, generate, run_tests
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionResult, TokenUsage
from app.schemas.execution import ExecutionResult

PONEGLYPH = {
    "phase_number": 1,
    "title": "Implement auth module",
    "task_description": "Create a login() function returning a JWT",
    "test_criteria": ["login returns JWT", "invalid creds raise"],
    "file_paths": ["app/auth.py"],
}

HEALTH_CHECKS = [
    {
        "file_path": "tests/test_auth.py",
        "content": "def test_login(): from app.auth import login; assert login('u','p')",
        "framework": "pytest",
    },
]

VALID_OUTPUT_JSON = json.dumps(
    {
        "files": [
            {
                "file_path": "app/auth.py",
                "content": "def login(u, p): return 'jwt-token'",
                "language": "python",
            }
        ]
    }
)


def _base_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "voyage_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "phase_number": 1,
        "poneglyph": PONEGLYPH,
        "health_checks": HEALTH_CHECKS,
        "iteration": 1,
        "last_test_output": None,
        "raw_output": "",
        "generated_files": None,
        "exit_code": None,
        "stdout": "",
        "passed_count": 0,
        "failed_count": 0,
        "total_count": 0,
        "error": None,
    }
    state.update(overrides)
    return state


def _llm_result(content: str) -> CompletionResult:
    return CompletionResult(
        content=content,
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        usage=TokenUsage(),
    )


def _exec_result(exit_code: int, stdout: str) -> ExecutionResult:
    return ExecutionResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr="",
        timed_out=False,
        duration_seconds=1.0,
        sandbox_id="sbx-test",
    )


class TestGenerateNode:
    @pytest.mark.asyncio
    async def test_sends_shipwright_role(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        await generate(_base_state(), mock_router)  # type: ignore[arg-type]

        mock_router.route.assert_awaited_once()
        assert mock_router.route.call_args.args[0] == CrewRole.SHIPWRIGHT

    @pytest.mark.asyncio
    async def test_includes_poneglyph_in_user_message(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        await generate(_base_state(), mock_router)  # type: ignore[arg-type]

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert "Create a login() function" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_includes_health_check_content_verbatim(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        await generate(_base_state(), mock_router)  # type: ignore[arg-type]

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert HEALTH_CHECKS[0]["content"] in user_msg["content"]
        assert "tests/test_auth.py" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_includes_last_test_output_on_retry(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        await generate(
            _base_state(iteration=2, last_test_output="AssertionError: boom"),
            mock_router,  # type: ignore[arg-type]
        )

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert "Previous attempt" in user_msg["content"]
        assert "AssertionError: boom" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_omits_retry_block_on_first_iteration(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        await generate(_base_state(iteration=1), mock_router)  # type: ignore[arg-type]

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert "Previous attempt" not in user_msg["content"]

    @pytest.mark.asyncio
    async def test_valid_json_populates_generated_files(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        result = await generate(_base_state(), mock_router)  # type: ignore[arg-type]

        assert result["generated_files"] is not None
        assert len(result["generated_files"]) == 1
        assert result["generated_files"][0].file_path == "app/auth.py"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_malformed_json_sets_error(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result("not valid json"))

        result = await generate(_base_state(), mock_router)  # type: ignore[arg-type]

        assert result["generated_files"] is None
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self) -> None:
        mock_router = AsyncMock()
        fenced = f"```json\n{VALID_OUTPUT_JSON}\n```"
        mock_router.route = AsyncMock(return_value=_llm_result(fenced))

        result = await generate(_base_state(), mock_router)  # type: ignore[arg-type]

        assert result["generated_files"] is not None
        assert result["error"] is None


class TestRunTestsNode:
    @pytest.mark.asyncio
    async def test_skips_execution_when_no_generated_files(self) -> None:
        mock_exec = AsyncMock()
        mock_exec.run = AsyncMock()

        result = await run_tests(_base_state(generated_files=None), mock_exec)  # type: ignore[arg-type]

        mock_exec.run.assert_not_awaited()
        assert result["exit_code"] is None
        assert result["total_count"] == len(HEALTH_CHECKS)

    @pytest.mark.asyncio
    async def test_merges_generated_and_health_check_files(self) -> None:
        from app.schemas.shipwright import BuildArtifactSpec

        mock_exec = AsyncMock()
        mock_exec.run = AsyncMock(return_value=_exec_result(0, "1 passed"))

        generated = [
            BuildArtifactSpec(file_path="app/auth.py", content="def login(u,p): return 'x'")
        ]
        await run_tests(_base_state(generated_files=generated), mock_exec)  # type: ignore[arg-type]

        mock_exec.run.assert_awaited_once()
        sent_files = mock_exec.run.call_args.args[1].files
        assert "app/auth.py" in sent_files
        assert "tests/test_auth.py" in sent_files

    @pytest.mark.asyncio
    async def test_parses_exit_zero_as_pass(self) -> None:
        from app.schemas.shipwright import BuildArtifactSpec

        mock_exec = AsyncMock()
        mock_exec.run = AsyncMock(return_value=_exec_result(0, "========= 3 passed ========="))

        generated = [BuildArtifactSpec(file_path="app/a.py", content="x")]
        result = await run_tests(_base_state(generated_files=generated), mock_exec)  # type: ignore[arg-type]

        assert result["exit_code"] == 0
        assert result["failed_count"] == 0
        assert result["passed_count"] >= 1

    @pytest.mark.asyncio
    async def test_parses_exit_nonzero_as_fail(self) -> None:
        from app.schemas.shipwright import BuildArtifactSpec

        mock_exec = AsyncMock()
        mock_exec.run = AsyncMock(return_value=_exec_result(1, "test_auth.py::test_login FAILED"))

        generated = [BuildArtifactSpec(file_path="app/a.py", content="x")]
        result = await run_tests(_base_state(generated_files=generated), mock_exec)  # type: ignore[arg-type]

        assert result["exit_code"] == 1
        assert result["failed_count"] >= 1


class TestFullGraph:
    @pytest.mark.asyncio
    async def test_end_to_end_success(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))
        mock_exec = AsyncMock()
        mock_exec.run = AsyncMock(return_value=_exec_result(0, "1 passed"))

        graph = build_shipwright_graph(mock_router, mock_exec)
        result = await graph.ainvoke(_base_state())

        assert result["generated_files"] is not None
        assert result["exit_code"] == 0
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_end_to_end_malformed_output_skips_tests(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result("not json"))
        mock_exec = AsyncMock()
        mock_exec.run = AsyncMock()

        graph = build_shipwright_graph(mock_router, mock_exec)
        result = await graph.ainvoke(_base_state())

        assert result["generated_files"] is None
        assert result["error"] is not None
        assert result["exit_code"] is None
        mock_exec.run.assert_not_awaited()
