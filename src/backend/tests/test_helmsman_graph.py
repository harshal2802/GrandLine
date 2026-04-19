"""Tests for Helmsman LangGraph graph (mocked backend + mocked LLM)."""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.crew.helmsman_graph import (
    DIAGNOSIS_LOG_TAIL,
    build_helmsman_graph,
    deploy_node,
    diagnose_node,
)
from app.deployment.backend import DeploymentError, DeploymentResult
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionResult, TokenUsage


def _base_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "voyage_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "tier": "preview",
        "git_ref": "agent/shipwright/deadbeef",
        "git_sha": "deadbeef",
        "status": "failed",
        "url": None,
        "backend_log": "",
        "error": None,
        "diagnosis": None,
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


VALID_DIAGNOSIS = json.dumps(
    {
        "summary": "Build failed during test stage",
        "likely_cause": "Missing APP_URL env var",
        "suggested_action": "Set APP_URL before redeploying",
    }
)


class TestDeployNode:
    @pytest.mark.asyncio
    async def test_maps_completed_result(self) -> None:
        mock_backend = AsyncMock()
        mock_backend.deploy = AsyncMock(
            return_value=DeploymentResult(
                status="completed",
                url="http://preview.voyage-abc.local",
                backend_log="ok",
                error=None,
            )
        )

        result = await deploy_node(_base_state(), mock_backend)  # type: ignore[arg-type]

        assert result["status"] == "completed"
        assert result["url"] == "http://preview.voyage-abc.local"
        assert result["backend_log"] == "ok"
        assert result["error"] is None
        assert result["diagnosis"] is None

    @pytest.mark.asyncio
    async def test_maps_failed_result(self) -> None:
        mock_backend = AsyncMock()
        mock_backend.deploy = AsyncMock(
            return_value=DeploymentResult(
                status="failed",
                url=None,
                backend_log="build error",
                error="BuildFail",
            )
        )

        result = await deploy_node(_base_state(), mock_backend)  # type: ignore[arg-type]

        assert result["status"] == "failed"
        assert result["url"] is None
        assert result["backend_log"] == "build error"
        assert result["error"] == "BuildFail"

    @pytest.mark.asyncio
    async def test_converts_deployment_error_to_failed(self) -> None:
        mock_backend = AsyncMock()
        mock_backend.deploy = AsyncMock(side_effect=DeploymentError("connection refused"))

        result = await deploy_node(_base_state(), mock_backend)  # type: ignore[arg-type]

        assert result["status"] == "failed"
        assert result["url"] is None
        assert "connection refused" in result["backend_log"]
        assert result["error"] == "DeploymentError"

    @pytest.mark.asyncio
    async def test_builds_artifact_from_state(self) -> None:
        mock_backend = AsyncMock()
        mock_backend.deploy = AsyncMock(
            return_value=DeploymentResult(status="completed", url="http://x", backend_log="")
        )
        state = _base_state(tier="staging", git_ref="staging", git_sha="abc123")

        await deploy_node(state, mock_backend)  # type: ignore[arg-type]

        artifact = mock_backend.deploy.call_args.args[0]
        assert artifact.tier == "staging"
        assert artifact.git_ref == "staging"
        assert artifact.git_sha == "abc123"


class TestDiagnoseNode:
    @pytest.mark.asyncio
    async def test_uses_helmsman_role(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_DIAGNOSIS))

        await diagnose_node(_base_state(backend_log="err"), mock_router)  # type: ignore[arg-type]

        mock_router.route.assert_awaited_once()
        assert mock_router.route.call_args.args[0] == CrewRole.HELMSMAN

    @pytest.mark.asyncio
    async def test_valid_json_populates_diagnosis(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_DIAGNOSIS))

        result = await diagnose_node(_base_state(backend_log="err"), mock_router)  # type: ignore[arg-type]

        assert result["diagnosis"] is not None
        assert result["diagnosis"]["summary"] == "Build failed during test stage"
        assert result["diagnosis"]["likely_cause"] == "Missing APP_URL env var"

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self) -> None:
        mock_router = AsyncMock()
        fenced = f"```json\n{VALID_DIAGNOSIS}\n```"
        mock_router.route = AsyncMock(return_value=_llm_result(fenced))

        result = await diagnose_node(_base_state(backend_log="err"), mock_router)  # type: ignore[arg-type]

        assert result["diagnosis"] is not None

    @pytest.mark.asyncio
    async def test_malformed_json_returns_none_diagnosis(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result("not valid json"))

        result = await diagnose_node(_base_state(backend_log="err"), mock_router)  # type: ignore[arg-type]

        assert result["diagnosis"] is None

    @pytest.mark.asyncio
    async def test_schema_violation_returns_none_diagnosis(self) -> None:
        mock_router = AsyncMock()
        empty = json.dumps({"summary": "", "likely_cause": "", "suggested_action": ""})
        mock_router.route = AsyncMock(return_value=_llm_result(empty))

        result = await diagnose_node(_base_state(backend_log="err"), mock_router)  # type: ignore[arg-type]

        assert result["diagnosis"] is None

    @pytest.mark.asyncio
    async def test_dial_router_exception_returns_none_diagnosis(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(side_effect=RuntimeError("rate limited"))

        result = await diagnose_node(_base_state(backend_log="err"), mock_router)  # type: ignore[arg-type]

        assert result["diagnosis"] is None

    @pytest.mark.asyncio
    async def test_user_message_contains_log_tail(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_DIAGNOSIS))

        long_log = "X" * (DIAGNOSIS_LOG_TAIL + 500) + "END_MARKER"
        await diagnose_node(_base_state(backend_log=long_log), mock_router)  # type: ignore[arg-type]

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert "END_MARKER" in user_msg["content"]
        assert len(user_msg["content"]) < len(long_log) + 500

    @pytest.mark.asyncio
    async def test_user_message_includes_tier_and_ref(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_DIAGNOSIS))

        state = _base_state(tier="production", git_ref="main", backend_log="err")
        await diagnose_node(state, mock_router)  # type: ignore[arg-type]

        request = mock_router.route.call_args.args[1]
        user_msg = next(m for m in request.messages if m["role"] == "user")
        assert "production" in user_msg["content"]
        assert "main" in user_msg["content"]


class TestFullGraph:
    @pytest.mark.asyncio
    async def test_successful_deploy_skips_diagnose(self) -> None:
        mock_router = AsyncMock()
        mock_backend = AsyncMock()
        mock_backend.deploy = AsyncMock(
            return_value=DeploymentResult(
                status="completed", url="http://x.local", backend_log="ok"
            )
        )

        graph = build_helmsman_graph(mock_router, mock_backend)  # type: ignore[arg-type]
        final = await graph.ainvoke(_base_state())

        assert final["status"] == "completed"
        assert final["diagnosis"] is None
        mock_router.route.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_deploy_runs_diagnose(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_DIAGNOSIS))
        mock_backend = AsyncMock()
        mock_backend.deploy = AsyncMock(
            return_value=DeploymentResult(
                status="failed", url=None, backend_log="broken", error="Oops"
            )
        )

        graph = build_helmsman_graph(mock_router, mock_backend)  # type: ignore[arg-type]
        final = await graph.ainvoke(_base_state())

        assert final["status"] == "failed"
        assert final["diagnosis"] is not None
        assert final["diagnosis"]["summary"] == "Build failed during test stage"
        mock_router.route.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deployment_error_routes_to_diagnose(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(return_value=_llm_result(VALID_DIAGNOSIS))
        mock_backend = AsyncMock()
        mock_backend.deploy = AsyncMock(side_effect=DeploymentError("boom"))

        graph = build_helmsman_graph(mock_router, mock_backend)  # type: ignore[arg-type]
        final = await graph.ainvoke(_base_state())

        assert final["status"] == "failed"
        assert final["diagnosis"] is not None
        assert "boom" in final["backend_log"]

    @pytest.mark.asyncio
    async def test_diagnose_failure_does_not_mask_deploy_failure(self) -> None:
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(side_effect=RuntimeError("llm down"))
        mock_backend = AsyncMock()
        mock_backend.deploy = AsyncMock(
            return_value=DeploymentResult(
                status="failed", url=None, backend_log="broken", error="Oops"
            )
        )

        graph = build_helmsman_graph(mock_router, mock_backend)  # type: ignore[arg-type]
        final = await graph.ainvoke(_base_state())

        assert final["status"] == "failed"
        assert final["diagnosis"] is None
        assert final["backend_log"] == "broken"
