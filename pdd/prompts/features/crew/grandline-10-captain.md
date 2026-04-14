# Phase 10: Captain Agent (Project Manager)

## Context

The Captain is the first agent in the GrandLine pipeline. It receives a user's task
description, decomposes it into a structured voyage plan with ordered phases, assigns
each phase to the appropriate crew role, persists the plan, publishes events for
downstream crew, and checkpoints its own state.

### Existing Infrastructure

| System | Module | Key Interfaces |
|--------|--------|----------------|
| **Dial System** | `app.dial_system.router.DialSystemRouter` | `route(role, CompletionRequest) -> CompletionResult` |
| **Den Den Mushi** | `app.den_den_mushi.mushi.DenDenMushi` | `publish(stream, event)` |
| **Vivre Card** | `app.services.vivre_card_service` | `checkpoint(session, voyage_id, crew_member, state_data, reason)` |
| **Models** | `app.models.voyage` | `Voyage` (status field), `VoyagePlan` (phases JSONB, version int) |
| **Enums** | `app.models.enums` | `CrewRole.CAPTAIN`, `VoyageStatus.PLANNING` |
| **Events** | `app.den_den_mushi.events` | `VoyagePlanCreatedEvent` |
| **Constants** | `app.den_den_mushi.constants` | `stream_key(voyage_id)` |

`CompletionRequest` takes `messages: list[dict[str,str]]`, `role: CrewRole`,
`voyage_id`, `max_tokens`, `temperature`.

`VoyagePlan.phases` is a JSONB column — store the full plan structure there.

LangGraph is **not** yet a dependency. Add `langgraph>=0.4` to `requirements.txt`.

## Deliverables

### 1. Pydantic Schemas — `app/schemas/captain.py`

```python
class PhaseSpec(BaseModel):
    phase_number: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    description: str
    assigned_to: CrewRole
    depends_on: list[int] = Field(default_factory=list)  # phase_numbers
    artifacts: list[str] = Field(default_factory=list)

class VoyagePlanSpec(BaseModel):
    phases: list[PhaseSpec] = Field(min_length=1)

class ChartCourseRequest(BaseModel):
    task: str = Field(min_length=10, max_length=5000)

class ChartCourseResponse(BaseModel):
    voyage_id: uuid.UUID
    plan_id: uuid.UUID
    plan: VoyagePlanSpec
    version: int

class VoyagePlanResponse(BaseModel):
    plan_id: uuid.UUID
    voyage_id: uuid.UUID
    phases: list[PhaseSpec]
    version: int
    created_by: str
    created_at: datetime
```

Add a **validator** on `VoyagePlanSpec` that rejects circular dependencies:
topological-sort the `depends_on` graph; raise `ValueError` if a cycle exists.

### 2. CaptainService — `app/services/captain_service.py`

A plain async service class (not a LangGraph graph itself — keeps the graph an
implementation detail).

```python
class CaptainService:
    def __init__(
        self,
        dial_router: DialSystemRouter,
        mushi: DenDenMushi,
        session: AsyncSession,
    ) -> None: ...

    async def chart_course(
        self,
        voyage: Voyage,
        task: str,
    ) -> tuple[VoyagePlan, VoyagePlanSpec]:
        """
        1. Set voyage.status = PLANNING, flush.
        2. Build a LangGraph graph (see §3) and invoke it with the task.
        3. Parse the LLM output into VoyagePlanSpec (with validation).
        4. Persist a VoyagePlan row (phases=spec.model_dump(), version=next).
        5. Checkpoint state via vivre_card_service.checkpoint().
        6. Publish VoyagePlanCreatedEvent via Den Den Mushi.
        7. Return (plan_model, spec).
        """

    async def get_plan(
        self,
        voyage_id: uuid.UUID,
    ) -> VoyagePlan | None:
        """Return the latest VoyagePlan for the voyage (highest version)."""
```

### 3. LangGraph Graph — `app/agents/captain_graph.py`

A minimal **two-node** StateGraph:

```
[decompose] → [validate]
```

**State schema:**

```python
class CaptainState(TypedDict):
    task: str
    raw_plan: str          # LLM output (JSON string)
    plan: VoyagePlanSpec | None
    error: str | None
```

**Nodes:**

- `decompose`: Calls `DialSystemRouter.route(CrewRole.CAPTAIN, ...)` with a system
  prompt instructing the LLM to return a JSON object matching `VoyagePlanSpec`.
  Stores raw JSON in `raw_plan`.
- `validate`: Parses `raw_plan` into `VoyagePlanSpec`. On validation failure, sets
  `error`. (No retry loop in this phase — keep it simple.)

**System prompt** for decompose node (store as constant `CAPTAIN_SYSTEM_PROMPT`):

> You are the Captain of a software engineering crew. Given a task description,
> decompose it into ordered phases. Each phase must specify:
> - phase_number (starting from 1)
> - name (short label)
> - description (what to do)
> - assigned_to (one of: navigator, doctor, shipwright, helmsman)
> - depends_on (list of phase_numbers this phase waits on)
> - artifacts (list of expected output file paths or artifact names)
>
> Respond with ONLY a JSON object: {"phases": [...]}

**Build function:**

```python
def build_captain_graph(dial_router: DialSystemRouter) -> CompiledGraph:
    ...
```

### 4. REST API — `app/api/v1/captain.py`

Two endpoints on the existing voyage router prefix:

| Method | Path | Handler | Response |
|--------|------|---------|----------|
| POST | `/voyages/{voyage_id}/plan` | `chart_course` | 201 → `ChartCourseResponse` |
| GET | `/voyages/{voyage_id}/plan` | `get_plan` | 200 → `VoyagePlanResponse` |

- POST requires the voyage to exist, be owned by the user, and have status `CHARTED`.
  If status != CHARTED, return 409.
- GET returns the latest plan (highest version). If no plan exists, return 404.
- Wire a `get_captain_service` dependency that constructs `CaptainService` from
  `get_dial_router`, `get_den_den_mushi`, and `get_session`.

### 5. Wiring

- Add `captain.router` to `app/api/v1/router.py`.
- Add `langgraph>=0.4` to `requirements.txt`.

## Test Plan

All tests use mocked dependencies (no real LLM calls, no real DB).

### Schema Tests — `tests/test_captain_schemas.py`

1. `PhaseSpec` accepts valid data.
2. `PhaseSpec` rejects `phase_number < 1`.
3. `VoyagePlanSpec` rejects empty phases list.
4. `VoyagePlanSpec` rejects circular dependencies (A→B→A).
5. `VoyagePlanSpec` accepts valid DAG with dependencies.
6. `ChartCourseRequest` rejects task shorter than 10 chars.
7. `ChartCourseRequest` rejects task longer than 5000 chars.

### Service Tests — `tests/test_captain_service.py`

1. `chart_course` sets voyage status to PLANNING.
2. `chart_course` invokes the dial router with CAPTAIN role.
3. `chart_course` persists a VoyagePlan with correct phases.
4. `chart_course` increments plan version on re-plan.
5. `chart_course` publishes VoyagePlanCreatedEvent.
6. `chart_course` creates a vivre card checkpoint.
7. `chart_course` raises on invalid LLM output (non-JSON).
8. `get_plan` returns latest plan by version.
9. `get_plan` returns None when no plan exists.

### API Tests — `tests/test_captain_api.py`

1. POST `/plan` returns 201 with plan.
2. POST `/plan` returns 409 if voyage not in CHARTED status.
3. GET `/plan` returns 200 with latest plan.
4. GET `/plan` returns 404 if no plan exists.

### Graph Tests — `tests/test_captain_graph.py`

1. `decompose` node sends correct system prompt and stores raw_plan.
2. `validate` node parses valid JSON into VoyagePlanSpec.
3. `validate` node sets error on invalid JSON.
4. Full graph invocation returns parsed plan on success.

## Constraints

- No real LLM calls in tests — mock the DialSystemRouter.
- No real database — mock AsyncSession.
- Keep the graph minimal (2 nodes). Retry/feedback loops are future work.
- The Captain only creates plans; it does not execute them.
