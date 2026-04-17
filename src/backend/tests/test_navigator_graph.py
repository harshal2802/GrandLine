"""Tests for Navigator LangGraph graph (mocked LLM)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.crew.navigator_graph import build_navigator_graph, generate, validate
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionResult, TokenUsage

PLAN_PHASES = [
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

VALID_PONEGLYPHS_JSON = json.dumps(
    {
        "poneglyphs": [
            {
                "phase_number": 1,
                "title": "Design system architecture",
                "task_description": "Create architecture document",
                "technical_constraints": ["Must use PostgreSQL"],
                "expected_inputs": ["Requirements"],
                "expected_outputs": ["design.md"],
                "test_criteria": ["Document covers all modules"],
                "file_paths": ["docs/design.md"],
                "implementation_notes": "Use C4 model",
            },
            {
                "phase_number": 2,
                "title": "Implement core API",
                "task_description": "Write the REST API endpoints",
                "technical_constraints": ["FastAPI", "async"],
                "expected_inputs": ["design.md"],
                "expected_outputs": ["src/main.py"],
                "test_criteria": ["All endpoints return 200"],
                "file_paths": ["src/main.py"],
                "implementation_notes": "Follow RESTful conventions",
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
    async def test_sends_correct_role_and_stores_raw(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_PONEGLYPHS_JSON))

        state = {
            "plan_phases": PLAN_PHASES,
            "raw_poneglyphs": "",
            "poneglyphs": None,
            "error": None,
        }
        result = await generate(state, mock_router)

        mock_router.route.assert_awaited_once()
        call_args = mock_router.route.call_args
        assert call_args.args[0] == CrewRole.NAVIGATOR
        assert result["raw_poneglyphs"] == VALID_PONEGLYPHS_JSON

    @pytest.mark.asyncio
    async def test_includes_plan_phases_in_user_message(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_PONEGLYPHS_JSON))

        state = {
            "plan_phases": PLAN_PHASES,
            "raw_poneglyphs": "",
            "poneglyphs": None,
            "error": None,
        }
        await generate(state, mock_router)

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert "Design" in user_msg["content"]
        assert "Implement" in user_msg["content"]


class TestValidateNode:
    def test_parses_valid_json(self) -> None:
        state = {
            "plan_phases": PLAN_PHASES,
            "raw_poneglyphs": VALID_PONEGLYPHS_JSON,
            "poneglyphs": None,
            "error": None,
        }
        result = validate(state)

        assert result["poneglyphs"] is not None
        assert len(result["poneglyphs"]) == 2
        assert result["poneglyphs"][0].title == "Design system architecture"
        assert result["error"] is None

    def test_sets_error_on_invalid_json(self) -> None:
        state = {
            "plan_phases": PLAN_PHASES,
            "raw_poneglyphs": "not json",
            "poneglyphs": None,
            "error": None,
        }
        result = validate(state)

        assert result["poneglyphs"] is None
        assert result["error"] is not None

    def test_sets_error_on_invalid_schema(self) -> None:
        bad_output = json.dumps({"poneglyphs": []})
        state = {
            "plan_phases": PLAN_PHASES,
            "raw_poneglyphs": bad_output,
            "poneglyphs": None,
            "error": None,
        }
        result = validate(state)

        assert result["poneglyphs"] is None
        assert result["error"] is not None

    def test_strips_markdown_json_fences(self) -> None:
        fenced = f"```json\n{VALID_PONEGLYPHS_JSON}\n```"
        state = {
            "plan_phases": PLAN_PHASES,
            "raw_poneglyphs": fenced,
            "poneglyphs": None,
            "error": None,
        }
        result = validate(state)

        assert result["poneglyphs"] is not None
        assert len(result["poneglyphs"]) == 2
        assert result["error"] is None

    def test_strips_bare_fences(self) -> None:
        fenced = f"```\n{VALID_PONEGLYPHS_JSON}\n```"
        state = {
            "plan_phases": PLAN_PHASES,
            "raw_poneglyphs": fenced,
            "poneglyphs": None,
            "error": None,
        }
        result = validate(state)

        assert result["poneglyphs"] is not None
        assert result["error"] is None


class TestFullGraph:
    @pytest.mark.asyncio
    async def test_end_to_end_success(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_PONEGLYPHS_JSON))

        graph = build_navigator_graph(mock_router)
        result = await graph.ainvoke(
            {
                "plan_phases": PLAN_PHASES,
                "raw_poneglyphs": "",
                "poneglyphs": None,
                "error": None,
            }
        )

        assert result["poneglyphs"] is not None
        assert result["error"] is None
        assert len(result["poneglyphs"]) == 2

    @pytest.mark.asyncio
    async def test_end_to_end_invalid_llm_output(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result("I cannot generate poneglyphs"))

        graph = build_navigator_graph(mock_router)
        result = await graph.ainvoke(
            {
                "plan_phases": PLAN_PHASES,
                "raw_poneglyphs": "",
                "poneglyphs": None,
                "error": None,
            }
        )

        assert result["poneglyphs"] is None
        assert result["error"] is not None
