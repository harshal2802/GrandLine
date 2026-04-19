"""Helmsman Agent LangGraph — deploys a voyage artifact and (on failure) asks the
Dial System to diagnose the error. A successful deploy makes zero LLM calls;
the `diagnose` node only runs when the backend reports `status != "completed"`.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.crew.utils import strip_fences
from app.deployment.backend import (
    DeploymentArtifact,
    DeploymentBackend,
    DeploymentError,
)
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole
from app.schemas.deployment import DeploymentDiagnosisSpec
from app.schemas.dial_system import CompletionRequest

logger = logging.getLogger(__name__)

DIAGNOSIS_LOG_TAIL = 4000

HELMSMAN_SYSTEM_PROMPT = """\
You are a Helmsman — a DevOps agent responsible for diagnosing failed \
deployments. You will receive the tier, git ref/SHA, and the last portion of \
the backend's failure log. Produce a concise diagnosis that helps a human \
operator decide what to do next.

Respond with ONLY a JSON object:
{"summary": "...", "likely_cause": "...", "suggested_action": "..."}

- summary: one sentence describing what went wrong
- likely_cause: the most probable root cause, based on the log
- suggested_action: one concrete next step the operator can take

Do not include any other text, markdown formatting, or explanation."""


class HelmsmanState(TypedDict):
    voyage_id: uuid.UUID
    user_id: uuid.UUID
    tier: Literal["preview", "staging", "production"]
    git_ref: str
    git_sha: str | None
    # filled by deploy node:
    status: Literal["completed", "failed"]
    url: str | None
    backend_log: str
    error: str | None
    # filled by diagnose node (only on failure):
    diagnosis: dict[str, Any] | None


async def deploy_node(
    state: HelmsmanState,
    backend: DeploymentBackend,
) -> dict[str, Any]:
    artifact = DeploymentArtifact(
        voyage_id=state["voyage_id"],
        tier=state["tier"],
        git_ref=state["git_ref"],
        git_sha=state.get("git_sha"),
    )
    try:
        result = await backend.deploy(artifact)
    except DeploymentError as exc:
        return {
            "status": "failed",
            "url": None,
            "backend_log": str(exc),
            "error": exc.__class__.__name__,
            "diagnosis": None,
        }
    return {
        "status": result.status,
        "url": result.url,
        "backend_log": result.backend_log,
        "error": result.error,
        "diagnosis": None,
    }


def _build_diagnose_message(state: HelmsmanState) -> str:
    log_tail = (state.get("backend_log") or "")[-DIAGNOSIS_LOG_TAIL:]
    return (
        f"## Deployment\n"
        f"- tier: {state['tier']}\n"
        f"- git_ref: {state['git_ref']}\n"
        f"- git_sha: {state.get('git_sha')}\n"
        f"- error: {state.get('error')}\n\n"
        f"## Backend log (tail)\n```\n{log_tail}\n```"
    )


async def diagnose_node(
    state: HelmsmanState,
    dial_router: DialSystemRouter,
) -> dict[str, Any]:
    try:
        user_message = _build_diagnose_message(state)
        request = CompletionRequest(
            messages=[
                {"role": "system", "content": HELMSMAN_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            role=CrewRole.HELMSMAN,
            voyage_id=state["voyage_id"],
        )
        result = await dial_router.route(CrewRole.HELMSMAN, request)
        stripped = strip_fences(result.content)
        data = json.loads(stripped)
        spec = DeploymentDiagnosisSpec.model_validate(data)
        return {"diagnosis": spec.model_dump()}
    except Exception:
        logger.warning(
            "Helmsman diagnosis failed for voyage %s tier %s — persisting null",
            state["voyage_id"],
            state["tier"],
            exc_info=True,
        )
        return {"diagnosis": None}


def _route_after_deploy(state: HelmsmanState) -> str:
    return "diagnose" if state["status"] != "completed" else END


def build_helmsman_graph(
    dial_router: DialSystemRouter,
    deployment_backend: DeploymentBackend,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    graph = StateGraph(HelmsmanState)

    async def _deploy(state: HelmsmanState) -> dict[str, Any]:
        return await deploy_node(state, deployment_backend)

    async def _diagnose(state: HelmsmanState) -> dict[str, Any]:
        return await diagnose_node(state, dial_router)

    graph.add_node("deploy", _deploy)
    graph.add_node("diagnose", _diagnose)

    graph.set_entry_point("deploy")
    graph.add_conditional_edges(
        "deploy",
        _route_after_deploy,
        {"diagnose": "diagnose", END: END},
    )
    graph.add_edge("diagnose", END)

    return graph.compile()
