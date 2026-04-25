"""Role-keyed canned-LLM helper for the pipeline integration test.

Builds a real `DialSystemRouter` whose role mapping is composed of stub
`ProviderAdapter`s that return pre-canned JSON shaped for the matching crew
service's parser. Per-test overrides allow individual roles to return a
custom payload (e.g. a "validation failed" Doctor response or a Shipwright
that raises a `ProviderError` to trigger the failure path).

The canned shapes were derived directly from each crew service's parse
code:
- Captain: ``{"phases": [...]}`` (see ``app/crew/captain_graph.py``)
- Navigator: ``{"poneglyphs": [...]}`` (see ``app/crew/navigator_graph.py``)
- Doctor (write): ``{"health_checks": [...]}`` (see ``app/crew/doctor_graph.py``)
- Shipwright: ``{"files": [{file_path, content, language}]}`` (see
  ``app/crew/shipwright_graph.py``)
- Helmsman: only invoked on backend deploy failure to produce a
  ``{"summary","likely_cause","suggested_action"}`` diagnosis.

The Doctor's *validate* path does NOT call the LLM — DoctorService.validate
runs the execution backend directly. So a "validation failed" failure path
needs to be triggered by the StubExecutionBackend, not by an LLM override.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.den_den_mushi.mushi import DenDenMushi
from app.dial_system.adapters.base import ProviderAdapter, ProviderError
from app.dial_system.router import DialSystemRouter
from app.models.enums import CrewRole
from app.schemas.dial_system import (
    CompletionRequest,
    CompletionResult,
    RateLimitStatus,
    TokenUsage,
)

CannedFn = Callable[[CompletionRequest], Awaitable[str]]
"""A coroutine that takes a CompletionRequest and returns the LLM content."""


class _CannedAdapter(ProviderAdapter):
    """Adapter that returns canned content from a per-role async callable.

    Records every call into `call_log` (a shared `Counter[CrewRole]`) so tests
    can assert on call counts (e.g. resume tests checking that Captain was
    not invoked).
    """

    def __init__(
        self,
        role: CrewRole,
        fn: CannedFn,
        call_log: Counter[CrewRole],
    ) -> None:
        self._role = role
        self._fn = fn
        self._call_log = call_log

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self._call_log[self._role] += 1
        content = await self._fn(request)
        return CompletionResult(
            content=content,
            provider="stub",
            model="stub-model",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    def stream(  # type: ignore[override]
        self, request: CompletionRequest
    ) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            content = await self._fn(request)
            yield content

        return _gen()

    def check_rate_limit(self) -> RateLimitStatus:
        return RateLimitStatus(is_limited=False)


# ---------------------------------------------------------------------------
# Default canned shapes
# ---------------------------------------------------------------------------


def _default_captain_three_phase() -> dict[str, Any]:
    """Captain plan: 3 phases. Phase 2 deps on 1, Phase 3 deps on [1, 2].

    Exercises both depth-2 layering and a multi-dependency phase in one shape.
    """
    return {
        "phases": [
            {
                "phase_number": 1,
                "name": "Foundation",
                "description": "Set up core module",
                "assigned_to": "shipwright",
                "depends_on": [],
                "artifacts": ["src/foundation.py"],
            },
            {
                "phase_number": 2,
                "name": "Feature",
                "description": "Build feature on top of foundation",
                "assigned_to": "shipwright",
                "depends_on": [1],
                "artifacts": ["src/feature.py"],
            },
            {
                "phase_number": 3,
                "name": "Integration",
                "description": "Integrate the two prior phases",
                "assigned_to": "shipwright",
                "depends_on": [1, 2],
                "artifacts": ["src/integration.py"],
            },
        ]
    }


def _default_navigator_for_phases(phase_numbers: list[int]) -> dict[str, Any]:
    """One Poneglyph per phase the LLM was asked about."""
    return {
        "poneglyphs": [
            {
                "phase_number": n,
                "title": f"Phase {n}",
                "task_description": f"Implement phase {n}",
                "technical_constraints": ["python 3.12+", "pytest"],
                "expected_inputs": [],
                "expected_outputs": [f"src/phase{n}.py"],
                "test_criteria": [
                    f"phase {n} module is importable",
                    f"phase {n} happy path returns correct value",
                ],
                "file_paths": [f"src/phase{n}.py"],
                "implementation_notes": "Keep it minimal.",
            }
            for n in phase_numbers
        ]
    }


def _default_doctor_health_checks(phase_numbers: list[int]) -> dict[str, Any]:
    """One pytest health-check per phase."""
    return {
        "health_checks": [
            {
                "phase_number": n,
                "file_path": f"tests/test_phase{n}.py",
                "content": (
                    f"def test_phase{n}_smoke():\n"
                    f"    from src.phase{n} import add\n"
                    f"    assert add(1, 2) == 3\n"
                ),
                "framework": "pytest",
            }
            for n in phase_numbers
        ]
    }


def _default_shipwright_for_phase(phase_number: int) -> dict[str, Any]:
    """Tiny passing python file that the canned ExecutionBackend says passes."""
    return {
        "files": [
            {
                "file_path": f"src/phase{phase_number}.py",
                "content": "def add(a, b):\n    return a + b\n",
                "language": "python",
            }
        ]
    }


def _default_helmsman_diagnosis() -> dict[str, Any]:
    return {
        "summary": "Stub diagnosis",
        "likely_cause": "Synthetic backend failure",
        "suggested_action": "Inspect deployment backend",
    }


# ---------------------------------------------------------------------------
# Public router builder
# ---------------------------------------------------------------------------


def make_role_router(
    mushi: DenDenMushi,
    voyage_id: uuid.UUID,
    *,
    captain_payload: dict[str, Any] | None = None,
    navigator_payload_for: Callable[[list[int]], dict[str, Any]] | None = None,
    doctor_payload_for: Callable[[list[int]], dict[str, Any]] | None = None,
    shipwright_payload_for: Callable[[int], dict[str, Any]] | None = None,
    shipwright_error_phase: int | None = None,
    helmsman_payload: dict[str, Any] | None = None,
    call_log: Counter[CrewRole] | None = None,
) -> DialSystemRouter:
    """Build a `DialSystemRouter` whose adapters return role-specific canned JSON.

    All payloads default to the self-consistent voyage shape described in the
    module docstring. Any subset of overrides may be provided.

    Args:
        mushi: real DenDenMushi (only used by the router for provider-switch
            events, which the stub adapters never trigger — kept for API
            compatibility).
        voyage_id: required by `DialSystemRouter.__init__`.
        captain_payload: VoyagePlanSpec dict; overrides default 3-phase plan.
        navigator_payload_for: callable taking the list of plan-phase numbers
            and returning the Navigator-shape dict.
        doctor_payload_for: callable taking the list of poneglyph-phase numbers
            and returning the Doctor (write) shape dict.
        shipwright_payload_for: callable taking the current phase_number and
            returning the Shipwright shape dict.
        shipwright_error_phase: if set, Shipwright raises `ProviderError` for
            that phase (used by the fail-fast layer test).
        helmsman_payload: diagnosis dict for failed deploys.
        call_log: shared Counter that tracks how often each role's adapter is
            called. Auto-created if None.

    Returns:
        A real `DialSystemRouter`. The returned object exposes its `call_log`
        as the `.call_log` attribute (added dynamically) so tests can assert
        on call counts without threading a separate fixture.
    """
    if call_log is None:
        call_log = Counter()

    # Captain: emit configured plan once (re-emit identical plan for replans).
    cap_payload = captain_payload or _default_captain_three_phase()

    async def _captain_fn(_req: CompletionRequest) -> str:
        return json.dumps(cap_payload)

    # Navigator: read the user message JSON to extract requested phase numbers.
    async def _navigator_fn(req: CompletionRequest) -> str:
        phases = _phases_in_navigator_request(req)
        if navigator_payload_for is not None:
            payload = navigator_payload_for(phases)
        else:
            payload = _default_navigator_for_phases(phases)
        return json.dumps(payload)

    # Doctor (write): same idea — extract phase numbers from user message.
    async def _doctor_fn(req: CompletionRequest) -> str:
        phases = _phases_in_doctor_request(req)
        if doctor_payload_for is not None:
            payload = doctor_payload_for(phases)
        else:
            payload = _default_doctor_health_checks(phases)
        return json.dumps(payload)

    # Shipwright: extract phase number from the user message.
    async def _shipwright_fn(req: CompletionRequest) -> str:
        phase = _phase_in_shipwright_request(req)
        if shipwright_error_phase is not None and phase == shipwright_error_phase:
            raise ProviderError(f"BUILD_FAILED for phase {phase}")
        if shipwright_payload_for is not None:
            payload = shipwright_payload_for(phase)
        else:
            payload = _default_shipwright_for_phase(phase)
        return json.dumps(payload)

    # Helmsman: only invoked on a backend-reported deploy failure.
    helm_payload = helmsman_payload or _default_helmsman_diagnosis()

    async def _helmsman_fn(_req: CompletionRequest) -> str:
        return json.dumps(helm_payload)

    role_mapping: dict[CrewRole, ProviderAdapter] = {
        CrewRole.CAPTAIN: _CannedAdapter(CrewRole.CAPTAIN, _captain_fn, call_log),
        CrewRole.NAVIGATOR: _CannedAdapter(CrewRole.NAVIGATOR, _navigator_fn, call_log),
        CrewRole.DOCTOR: _CannedAdapter(CrewRole.DOCTOR, _doctor_fn, call_log),
        CrewRole.SHIPWRIGHT: _CannedAdapter(CrewRole.SHIPWRIGHT, _shipwright_fn, call_log),
        CrewRole.HELMSMAN: _CannedAdapter(CrewRole.HELMSMAN, _helmsman_fn, call_log),
    }

    router = DialSystemRouter(
        role_mapping=role_mapping,
        fallback_chains={},
        mushi=mushi,
        voyage_id=voyage_id,
    )
    # Stash the call log on the router so tests can read it without an extra
    # fixture wire-up.
    router.call_log = call_log  # type: ignore[attr-defined]
    return router


# ---------------------------------------------------------------------------
# Request parsers — extract the phase numbers each crew service asks about
# ---------------------------------------------------------------------------


def _phases_in_navigator_request(req: CompletionRequest) -> list[int]:
    """Navigator user message is JSON-serialised plan phases."""
    user_msg = _user_content(req)
    try:
        data = json.loads(user_msg)
        return [p["phase_number"] for p in data]
    except (json.JSONDecodeError, KeyError, TypeError):
        return [1]


def _phases_in_doctor_request(req: CompletionRequest) -> list[int]:
    """Doctor user message is JSON-serialised poneglyph summary list."""
    user_msg = _user_content(req)
    try:
        data = json.loads(user_msg)
        return [p["phase_number"] for p in data]
    except (json.JSONDecodeError, KeyError, TypeError):
        return [1]


def _phase_in_shipwright_request(req: CompletionRequest) -> int:
    """Shipwright user message is a markdown blob; the header line names the phase."""
    user_msg = _user_content(req)
    # Header looks like: "## Poneglyph (phase N)\n..."
    for line in user_msg.splitlines():
        line = line.strip()
        if line.startswith("## Poneglyph (phase ") and line.endswith(")"):
            try:
                return int(line[len("## Poneglyph (phase ") : -1])
            except ValueError:
                continue
    return 1


def _user_content(req: CompletionRequest) -> str:
    for msg in reversed(req.messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""
