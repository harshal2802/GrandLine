"""Tests for Doctor LangGraph graph (mocked LLM)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.crew.doctor_graph import build_doctor_graph, generate, validate
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionResult, TokenUsage

PONEGLYPHS = [
    {
        "phase_number": 1,
        "title": "Design auth module",
        "task_description": "Create JWT-based auth",
        "test_criteria": ["login returns JWT", "expired tokens reject"],
        "file_paths": ["src/auth.py"],
    },
    {
        "phase_number": 2,
        "title": "Build API endpoints",
        "task_description": "FastAPI routes",
        "test_criteria": ["POST /login returns 200", "GET /me requires auth"],
        "file_paths": ["src/api.py"],
    },
]

VALID_OUTPUT_JSON = json.dumps(
    {
        "health_checks": [
            {
                "phase_number": 1,
                "file_path": "tests/test_auth.py",
                "content": "def test_jwt(): from src.auth import login; assert login()",
                "framework": "pytest",
            },
            {
                "phase_number": 2,
                "file_path": "tests/test_api.py",
                "content": "def test_login(): assert False  # TDD failing",
                "framework": "pytest",
            },
        ]
    }
)


def _llm_result(content: str) -> CompletionResult:
    return CompletionResult(
        content=content,
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        usage=TokenUsage(),
    )


class TestGenerateNode:
    @pytest.mark.asyncio
    async def test_sends_doctor_role_and_stores_raw(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        state = {
            "poneglyphs": PONEGLYPHS,
            "raw_output": "",
            "health_checks": None,
            "error": None,
        }
        result = await generate(state, mock_router)

        mock_router.route.assert_awaited_once()
        assert mock_router.route.call_args.args[0] == CrewRole.DOCTOR
        assert result["raw_output"] == VALID_OUTPUT_JSON

    @pytest.mark.asyncio
    async def test_includes_poneglyph_content_in_user_message(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        state = {
            "poneglyphs": PONEGLYPHS,
            "raw_output": "",
            "health_checks": None,
            "error": None,
        }
        await generate(state, mock_router)

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert "Design auth module" in user_msg["content"]
        assert "login returns JWT" in user_msg["content"]


class TestValidateNode:
    def test_parses_valid_json(self) -> None:
        state = {
            "poneglyphs": PONEGLYPHS,
            "raw_output": VALID_OUTPUT_JSON,
            "health_checks": None,
            "error": None,
        }
        result = validate(state)

        assert result["health_checks"] is not None
        assert len(result["health_checks"]) == 2
        assert result["health_checks"][0].file_path == "tests/test_auth.py"
        assert result["error"] is None

    def test_sets_error_on_invalid_json(self) -> None:
        state = {
            "poneglyphs": PONEGLYPHS,
            "raw_output": "definitely not json",
            "health_checks": None,
            "error": None,
        }
        result = validate(state)

        assert result["health_checks"] is None
        assert result["error"] is not None

    def test_sets_error_on_empty_health_checks(self) -> None:
        state = {
            "poneglyphs": PONEGLYPHS,
            "raw_output": json.dumps({"health_checks": []}),
            "health_checks": None,
            "error": None,
        }
        result = validate(state)

        assert result["health_checks"] is None
        assert result["error"] is not None

    def test_strips_markdown_json_fences(self) -> None:
        fenced = f"```json\n{VALID_OUTPUT_JSON}\n```"
        state = {
            "poneglyphs": PONEGLYPHS,
            "raw_output": fenced,
            "health_checks": None,
            "error": None,
        }
        result = validate(state)

        assert result["health_checks"] is not None
        assert result["error"] is None

    def test_strips_bare_fences(self) -> None:
        fenced = f"```\n{VALID_OUTPUT_JSON}\n```"
        state = {
            "poneglyphs": PONEGLYPHS,
            "raw_output": fenced,
            "health_checks": None,
            "error": None,
        }
        result = validate(state)

        assert result["health_checks"] is not None
        assert result["error"] is None


class TestFullGraph:
    @pytest.mark.asyncio
    async def test_end_to_end_success(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_OUTPUT_JSON))

        graph = build_doctor_graph(mock_router)
        result = await graph.ainvoke(
            {
                "poneglyphs": PONEGLYPHS,
                "raw_output": "",
                "health_checks": None,
                "error": None,
            }
        )

        assert result["health_checks"] is not None
        assert result["error"] is None
        assert len(result["health_checks"]) == 2

    @pytest.mark.asyncio
    async def test_end_to_end_invalid_output(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result("I cannot comply"))

        graph = build_doctor_graph(mock_router)
        result = await graph.ainvoke(
            {
                "poneglyphs": PONEGLYPHS,
                "raw_output": "",
                "health_checks": None,
                "error": None,
            }
        )

        assert result["health_checks"] is None
        assert result["error"] is not None
