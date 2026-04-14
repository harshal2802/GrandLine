"""Captain Agent LangGraph — decomposes tasks into voyage plans."""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole
from app.schemas.captain import VoyagePlanSpec
from app.schemas.dial_system import CompletionRequest

CAPTAIN_SYSTEM_PROMPT = """\
You are the Captain of a software engineering crew. Given a task description, \
decompose it into ordered phases. Each phase must specify:
- phase_number (starting from 1)
- name (short label)
- description (what to do)
- assigned_to (one of: navigator, doctor, shipwright, helmsman)
- depends_on (list of phase_numbers this phase waits on, empty list if none)
- artifacts (list of expected output file paths or artifact names)

Respond with ONLY a JSON object: {"phases": [...]}
Do not include any other text, markdown formatting, or explanation."""


class CaptainState(TypedDict):
    task: str
    raw_plan: str
    plan: VoyagePlanSpec | None
    error: str | None


async def decompose(
    state: CaptainState,
    dial_router: DialSystemRouter,
) -> dict[str, Any]:
    """Call the LLM to decompose the task into a structured plan."""
    request = CompletionRequest(
        messages=[
            {"role": "system", "content": CAPTAIN_SYSTEM_PROMPT},
            {"role": "user", "content": state["task"]},
        ],
        role=CrewRole.CAPTAIN,
    )
    result = await dial_router.route(CrewRole.CAPTAIN, request)
    return {"raw_plan": result.content}


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs commonly wrap JSON in."""
    text = text.strip()
    match = _FENCE_RE.match(text)
    return match.group(1).strip() if match else text


def validate(state: CaptainState) -> dict[str, Any]:
    """Parse raw LLM output into a validated VoyagePlanSpec."""
    try:
        raw = _strip_fences(state["raw_plan"])
        data = json.loads(raw)
        spec = VoyagePlanSpec.model_validate(data)
        return {"plan": spec, "error": None}
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        return {"plan": None, "error": str(exc)}


def build_captain_graph(
    dial_router: DialSystemRouter,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the Captain's two-node graph."""
    graph = StateGraph(CaptainState)

    async def _decompose(state: CaptainState) -> dict[str, Any]:
        return await decompose(state, dial_router)

    graph.add_node("decompose", _decompose)
    graph.add_node("validate", validate)

    graph.set_entry_point("decompose")
    graph.add_edge("decompose", "validate")
    graph.add_edge("validate", END)

    return graph.compile()
