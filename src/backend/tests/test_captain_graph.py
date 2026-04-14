"""Tests for Captain LangGraph graph (mocked LLM)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.crew.captain_graph import build_captain_graph, decompose, validate
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionResult, TokenUsage

VALID_PLAN_JSON = json.dumps(
    {
        "phases": [
            {
                "phase_number": 1,
                "name": "Design",
                "description": "Architecture",
                "assigned_to": "navigator",
                "depends_on": [],
                "artifacts": [],
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


class TestDecomposeNode:
    @pytest.mark.asyncio
    async def test_sends_correct_role_and_stores_raw_plan(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_PLAN_JSON))

        state = {"task": "Build an API", "raw_plan": "", "plan": None, "error": None}
        result = await decompose(state, mock_router)

        mock_router.route.assert_awaited_once()
        call_args = mock_router.route.call_args
        assert call_args.args[0] == CrewRole.CAPTAIN
        assert result["raw_plan"] == VALID_PLAN_JSON

    @pytest.mark.asyncio
    async def test_includes_task_in_user_message(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_PLAN_JSON))

        state = {"task": "Build an API", "raw_plan": "", "plan": None, "error": None}
        await decompose(state, mock_router)

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert "Build an API" in user_msg["content"]


class TestValidateNode:
    def test_parses_valid_json(self) -> None:
        state = {
            "task": "Build an API",
            "raw_plan": VALID_PLAN_JSON,
            "plan": None,
            "error": None,
        }
        result = validate(state)

        assert result["plan"] is not None
        assert result["plan"].phases[0].name == "Design"
        assert result["error"] is None

    def test_sets_error_on_invalid_json(self) -> None:
        state = {
            "task": "Build an API",
            "raw_plan": "not json",
            "plan": None,
            "error": None,
        }
        result = validate(state)

        assert result["plan"] is None
        assert result["error"] is not None

    def test_sets_error_on_invalid_schema(self) -> None:
        bad_plan = json.dumps({"phases": []})
        state = {
            "task": "Build an API",
            "raw_plan": bad_plan,
            "plan": None,
            "error": None,
        }
        result = validate(state)

        assert result["plan"] is None
        assert result["error"] is not None

    def test_strips_markdown_fences(self) -> None:
        fenced = f"```json\n{VALID_PLAN_JSON}\n```"
        state = {
            "task": "Build an API",
            "raw_plan": fenced,
            "plan": None,
            "error": None,
        }
        result = validate(state)

        assert result["plan"] is not None
        assert result["plan"].phases[0].name == "Design"
        assert result["error"] is None

    def test_strips_bare_fences(self) -> None:
        fenced = f"```\n{VALID_PLAN_JSON}\n```"
        state = {
            "task": "Build an API",
            "raw_plan": fenced,
            "plan": None,
            "error": None,
        }
        result = validate(state)

        assert result["plan"] is not None
        assert result["error"] is None


class TestFullGraph:
    @pytest.mark.asyncio
    async def test_end_to_end_success(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_PLAN_JSON))

        graph = build_captain_graph(mock_router)
        result = await graph.ainvoke(
            {"task": "Build an API", "raw_plan": "", "plan": None, "error": None}
        )

        assert result["plan"] is not None
        assert result["error"] is None
        assert len(result["plan"].phases) == 1

    @pytest.mark.asyncio
    async def test_end_to_end_invalid_llm_output(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result("I cannot do that"))

        graph = build_captain_graph(mock_router)
        result = await graph.ainvoke(
            {"task": "Build an API", "raw_plan": "", "plan": None, "error": None}
        )

        assert result["plan"] is None
        assert result["error"] is not None
