"""Navigator Agent LangGraph — generates Poneglyphs from voyage plans."""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionRequest
from app.schemas.navigator import NavigatorOutputSpec, PoneglyphContentSpec

NAVIGATOR_SYSTEM_PROMPT = """\
You are the Navigator of a software engineering crew. Given a voyage plan with phases, \
generate a Poneglyph (detailed implementation prompt) for each phase.

Each Poneglyph must include:
- phase_number (must match the plan's phase_number)
- title (descriptive name for this implementation step)
- task_description (detailed description of what to build)
- technical_constraints (list of technical requirements and limitations)
- expected_inputs (what this phase receives from prior phases or the user)
- expected_outputs (what this phase produces — files, APIs, artifacts)
- test_criteria (list of specific, testable acceptance criteria — the Doctor uses these)
- file_paths (list of files to create or modify)
- implementation_notes (additional guidance for the Shipwright)

Respond with ONLY a JSON object: {"poneglyphs": [...]}
Do not include any other text, markdown formatting, or explanation."""


class NavigatorState(TypedDict):
    plan_phases: list[dict[str, Any]]
    raw_poneglyphs: str
    poneglyphs: list[PoneglyphContentSpec] | None
    error: str | None


async def generate(
    state: NavigatorState,
    dial_router: DialSystemRouter,
) -> dict[str, Any]:
    """Call the LLM to generate Poneglyphs for each plan phase."""
    phases_json = json.dumps(state["plan_phases"], indent=2)
    request = CompletionRequest(
        messages=[
            {"role": "system", "content": NAVIGATOR_SYSTEM_PROMPT},
            {"role": "user", "content": phases_json},
        ],
        role=CrewRole.NAVIGATOR,
    )
    result = await dial_router.route(CrewRole.NAVIGATOR, request)
    return {"raw_poneglyphs": result.content}


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs commonly wrap JSON in."""
    text = text.strip()
    match = _FENCE_RE.match(text)
    return match.group(1).strip() if match else text


def validate(state: NavigatorState) -> dict[str, Any]:
    """Parse raw LLM output into validated PoneglyphContentSpec list."""
    try:
        raw = _strip_fences(state["raw_poneglyphs"])
        data = json.loads(raw)
        spec = NavigatorOutputSpec.model_validate(data)
        return {"poneglyphs": spec.poneglyphs, "error": None}
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        return {"poneglyphs": None, "error": str(exc)}


def build_navigator_graph(
    dial_router: DialSystemRouter,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the Navigator's two-node graph."""
    graph = StateGraph(NavigatorState)

    async def _generate(state: NavigatorState) -> dict[str, Any]:
        return await generate(state, dial_router)

    graph.add_node("generate", _generate)
    graph.add_node("validate", validate)

    graph.set_entry_point("generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)

    return graph.compile()
