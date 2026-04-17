"""Doctor Agent LangGraph — generates failing health-check tests from Poneglyphs."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.crew.utils import strip_fences
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionRequest
from app.schemas.doctor import DoctorOutputSpec, HealthCheckSpec

DOCTOR_SYSTEM_PROMPT = """\
You are the Doctor of a software engineering crew. Your job is to write failing \
health-check tests (TDD) for each phase of the voyage — BEFORE any implementation \
code exists. Your tests should import and reference the modules, classes, and \
functions that the Shipwrights will build from the Poneglyphs; those symbols do \
not exist yet, and that is intentional. A well-written failing test is the \
specification for the implementation.

For each Poneglyph, produce ONE test file. Decide the framework:
- pytest if the phase's file_paths include .py files (or default when unclear)
- vitest if the phase's file_paths are .ts/.tsx/.js/.jsx

Each health check must include:
- phase_number (must match the Poneglyph's phase_number)
- file_path (where to write the test, e.g., "tests/test_auth.py")
- content (the complete test source code)
- framework ("pytest" or "vitest")

Respond with ONLY a JSON object: {"health_checks": [...]}
Do not include any other text, markdown formatting, or explanation."""


class DoctorState(TypedDict):
    poneglyphs: list[dict[str, Any]]
    raw_output: str
    health_checks: list[HealthCheckSpec] | None
    error: str | None


async def generate(
    state: DoctorState,
    dial_router: DialSystemRouter,
) -> dict[str, Any]:
    """Call the LLM to generate health checks for each Poneglyph."""
    poneglyphs_json = json.dumps(state["poneglyphs"], indent=2)
    request = CompletionRequest(
        messages=[
            {"role": "system", "content": DOCTOR_SYSTEM_PROMPT},
            {"role": "user", "content": poneglyphs_json},
        ],
        role=CrewRole.DOCTOR,
    )
    result = await dial_router.route(CrewRole.DOCTOR, request)
    return {"raw_output": result.content}


def validate(state: DoctorState) -> dict[str, Any]:
    """Parse raw LLM output into validated HealthCheckSpec list."""
    try:
        raw = strip_fences(state["raw_output"])
        data = json.loads(raw)
        spec = DoctorOutputSpec.model_validate(data)
        return {"health_checks": spec.health_checks, "error": None}
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        return {"health_checks": None, "error": str(exc)}


def build_doctor_graph(
    dial_router: DialSystemRouter,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the Doctor's two-node graph."""
    graph = StateGraph(DoctorState)

    async def _generate(state: DoctorState) -> dict[str, Any]:
        return await generate(state, dial_router)

    graph.add_node("generate", _generate)
    graph.add_node("validate", validate)

    graph.set_entry_point("generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)

    return graph.compile()
