"""Shipwright Agent LangGraph — generates code and runs it against the Doctor's tests.

One invocation of the compiled graph is ONE iteration: the `generate` node calls the
LLM to produce source files, and the `run_tests` node executes them against the stored
health-check tests in the sandbox. The iteration loop lives in the service layer so
per-iteration VivreCard checkpoints remain a service concern, not a graph concern.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.crew.utils import strip_fences
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole
from app.schemas.dial_system import CompletionRequest
from app.schemas.execution import ExecutionRequest
from app.schemas.shipwright import BuildArtifactSpec, ShipwrightOutputSpec
from app.services.execution_service import ExecutionService

SHIPWRIGHT_SYSTEM_PROMPT = """\
You are a Shipwright — a developer agent on a software engineering crew. Your job \
is to write source code that makes the Doctor's pre-written failing tests pass. \
The tests are the specification; your code is the implementation.

You will receive:
- A Poneglyph describing one phase of the work (task description, test criteria, \
intended file paths)
- The exact content of the failing test files for that phase
- If this is a retry, the previous test run's output

Produce a complete set of source files that satisfy the tests. Every file you emit \
must be importable and runnable as-is. Do not include the test files themselves in \
your output — those already exist.

Rules for file_path values:
- Use relative paths only (no leading /, no drive letters, no ..)
- Match the style in the Poneglyph's file_paths hint where possible

Respond with ONLY a JSON object: {"files": [{"file_path": "...", "content": "...", \
"language": "python"}, ...]}
Do not include any other text, markdown formatting, or explanation."""


class ShipwrightState(TypedDict):
    voyage_id: uuid.UUID
    user_id: uuid.UUID
    phase_number: int
    poneglyph: dict[str, Any]
    health_checks: list[dict[str, str]]
    iteration: int
    last_test_output: str | None
    raw_output: str
    generated_files: list[BuildArtifactSpec] | None
    exit_code: int | None
    stdout: str
    passed_count: int
    failed_count: int
    total_count: int
    error: str | None


def _build_user_message(state: ShipwrightState) -> str:
    poneglyph_block = json.dumps(state["poneglyph"], indent=2)
    tests_block = "\n\n".join(
        f"### {hc['file_path']} ({hc.get('framework', 'pytest')})\n```\n{hc['content']}\n```"
        for hc in state["health_checks"]
    )
    sections = [
        f"## Poneglyph (phase {state['phase_number']})\n{poneglyph_block}",
        f"## Tests you must make pass\n{tests_block}",
    ]
    if state["iteration"] > 1 and state.get("last_test_output"):
        output = state["last_test_output"] or ""
        sections.append(
            "## Previous attempt — tests still failed\n"
            "The tests above still fail. Fix the issues reported and regenerate the "
            "complete file set.\n"
            f"```\n{output[-2000:]}\n```"
        )
    return "\n\n".join(sections)


async def generate(
    state: ShipwrightState,
    dial_router: DialSystemRouter,
) -> dict[str, Any]:
    """Call the LLM to generate source files for this phase/iteration."""
    user_message = _build_user_message(state)
    request = CompletionRequest(
        messages=[
            {"role": "system", "content": SHIPWRIGHT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        role=CrewRole.SHIPWRIGHT,
        voyage_id=state["voyage_id"],
    )
    result = await dial_router.route(CrewRole.SHIPWRIGHT, request)
    raw = result.content
    try:
        stripped = strip_fences(raw)
        data = json.loads(stripped)
        spec = ShipwrightOutputSpec.model_validate(data)
        return {
            "raw_output": raw,
            "generated_files": spec.files,
            "error": None,
        }
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        return {
            "raw_output": raw,
            "generated_files": None,
            "error": str(exc),
        }


def _parse_counts(stdout: str, exit_code: int, total_hint: int) -> tuple[int, int, int]:
    """Best-effort pass/fail counting from pytest stdout."""
    passed = stdout.count("PASSED")
    failed = stdout.count("FAILED")
    if passed == 0 and failed == 0:
        if exit_code == 0:
            return total_hint, 0, total_hint
        return 0, max(total_hint, 1), max(total_hint, 1)
    return passed, failed, passed + failed


async def run_tests(
    state: ShipwrightState,
    execution_service: ExecutionService,
) -> dict[str, Any]:
    """Run pytest against generated files + stored health-check tests."""
    generated = state.get("generated_files")
    if generated is None:
        # parse failed — nothing to run
        return {
            "exit_code": None,
            "stdout": "",
            "passed_count": 0,
            "failed_count": 0,
            "total_count": len(state["health_checks"]),
        }

    files: dict[str, str] = {f.file_path: f.content for f in generated}
    for hc in state["health_checks"]:
        files[hc["file_path"]] = hc["content"]

    request = ExecutionRequest(
        command="cd /workspace && python -m pytest -x --tb=short",
        files=files,
        timeout_seconds=120,
    )
    result = await execution_service.run(state["user_id"], request)
    passed, failed, total = _parse_counts(
        result.stdout, result.exit_code, len(state["health_checks"])
    )
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "passed_count": passed,
        "failed_count": failed,
        "total_count": total,
    }


def build_shipwright_graph(
    dial_router: DialSystemRouter,
    execution_service: ExecutionService,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build and compile the Shipwright's two-node graph (one iteration per invocation)."""
    graph = StateGraph(ShipwrightState)

    async def _generate(state: ShipwrightState) -> dict[str, Any]:
        return await generate(state, dial_router)

    async def _run_tests(state: ShipwrightState) -> dict[str, Any]:
        return await run_tests(state, execution_service)

    graph.add_node("generate", _generate)
    graph.add_node("run_tests", _run_tests)

    graph.set_entry_point("generate")
    graph.add_edge("generate", "run_tests")
    graph.add_edge("run_tests", END)

    return graph.compile()
