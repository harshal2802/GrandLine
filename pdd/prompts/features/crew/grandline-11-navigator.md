# Phase 11: Navigator Agent (Architect)

## Context

The Navigator is the second agent in the GrandLine pipeline. It reads the Captain's
voyage plan and generates **Poneglyphs** — structured PDD prompt artifacts — for each
phase. Poneglyph quality drives everything downstream: the Doctor uses them to write
tests, and the Shipwrights use them to implement.

This follows the **crew agent pattern** established by the Captain (Phase 10):
graph → service → API, with `reader()` factory, atomic commits, and best-effort events.

### Existing Infrastructure

| System | Module | Key Interfaces |
|--------|--------|----------------|
| **Captain** | `app.services.captain_service.CaptainService` | `get_plan(voyage_id) -> VoyagePlan \| None` |
| **Dial System** | `app.dial_system.router.DialSystemRouter` | `route(role, CompletionRequest) -> CompletionResult` |
| **Den Den Mushi** | `app.den_den_mushi.mushi.DenDenMushi` | `publish(stream, event)` |
| **Models** | `app.models.poneglyph.Poneglyph` | `id, voyage_id, phase_number, content (Text), metadata_ (JSONB), created_by, created_at` |
| **Schemas** | `app.schemas.poneglyph.PoneglyphRead` | `id, voyage_id, phase_number, content, metadata_, created_by, created_at` |
| **Events** | `app.den_den_mushi.events.PoneglyphDraftedEvent` | `event_type="poneglyph_drafted"` |
| **Enums** | `app.models.enums` | `CrewRole.NAVIGATOR`, `VoyageStatus.PDD` |
| **Constants** | `app.den_den_mushi.constants` | `stream_key(voyage_id)` |
| **Captain Graph** | `app.crew.captain_graph` | Pattern reference: two-node StateGraph, `_strip_fences()`, `_FENCE_RE` |

`VoyagePlan.phases` is JSONB: `{"phases": [{"phase_number": 1, "name": "Design", "description": "...", "assigned_to": "navigator", "depends_on": [], "artifacts": ["design.md"]}]}`

`Poneglyph.content` is a `Text` column — store the full structured Poneglyph content as a string.
`Poneglyph.metadata_` is JSONB — store structured metadata (phase name, assigned_to, constraints count, etc.).

`CompletionRequest` takes `messages: list[dict[str,str]]`, `role: CrewRole`,
`voyage_id`, `max_tokens`, `temperature`.

## Deliverables

### 1. Pydantic Schemas — `app/schemas/navigator.py`

```python
class PoneglyphContentSpec(BaseModel):
    """Structured content that the LLM generates for one phase."""
    phase_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    task_description: str = Field(min_length=1)
    technical_constraints: list[str] = Field(default_factory=list)
    expected_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    test_criteria: list[str] = Field(min_length=1)  # Doctor needs these
    file_paths: list[str] = Field(default_factory=list)
    implementation_notes: str = ""

class NavigatorOutputSpec(BaseModel):
    """Full LLM output: poneglyphs for all phases."""
    poneglyphs: list[PoneglyphContentSpec] = Field(min_length=1)

class DraftPoneglyphsRequest(BaseModel):
    """Empty body — plan is fetched from DB internally."""
    pass  # voyage_id comes from the URL path

class DraftPoneglyphsResponse(BaseModel):
    voyage_id: uuid.UUID
    poneglyph_ids: list[uuid.UUID]
    count: int

class PoneglyphListResponse(BaseModel):
    voyage_id: uuid.UUID
    poneglyphs: list[PoneglyphRead]
```

Add a **validator** on `NavigatorOutputSpec` that rejects duplicate `phase_number` values
(same pattern as `VoyagePlanSpec.validate_plan_graph`).

### 2. LangGraph Graph — `app/crew/navigator_graph.py`

A minimal **two-node** StateGraph (same pattern as `captain_graph.py`):

```
[generate] → [validate]
```

**State schema:**

```python
class NavigatorState(TypedDict):
    plan_phases: list[dict[str, Any]]  # raw phase dicts from VoyagePlan
    raw_poneglyphs: str                # LLM output (JSON string)
    poneglyphs: list[PoneglyphContentSpec] | None
    error: str | None
```

**Nodes:**

- `generate`: Calls `DialSystemRouter.route(CrewRole.NAVIGATOR, ...)` with a system
  prompt and the plan phases as user message context. Stores raw JSON in `raw_poneglyphs`.
- `validate`: Strips markdown fences (reuse `_strip_fences` pattern from captain_graph),
  parses `raw_poneglyphs` into `NavigatorOutputSpec`. On validation failure, sets `error`.

**System prompt** (store as constant `NAVIGATOR_SYSTEM_PROMPT`):

```
You are the Navigator of a software engineering crew. Given a voyage plan with phases,
generate a Poneglyph (detailed implementation prompt) for each phase.

Each Poneglyph must include:
- phase_number (must match the plan's phase_number)
- title (descriptive name for this implementation step)
- task_description (detailed description of what to build)
- technical_constraints (list of technical requirements and limitations)
- expected_inputs (what this phase receives from prior phases or the user)
- expected_outputs (what this phase produces — files, APIs, artifacts)
- test_criteria (list of specific, testable acceptance criteria — the Doctor uses these to write tests)
- file_paths (list of files to create or modify)
- implementation_notes (additional guidance for the Shipwright)

Respond with ONLY a JSON object: {"poneglyphs": [...]}
Do not include any other text, markdown formatting, or explanation.
```

**User message** format: serialize the plan phases as JSON in the user message so
the LLM has full context.

**Build function:**

```python
def build_navigator_graph(dial_router: DialSystemRouter) -> CompiledStateGraph:
    ...
```

### 3. NavigatorService — `app/services/navigator_service.py`

Follow the Captain pattern exactly. A plain async service class.

```python
class NavigatorError(Exception):
    """Raised when Navigator agent operations fail."""
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class NavigatorService:
    def __init__(
        self,
        dial_router: DialSystemRouter,
        mushi: DenDenMushi,
        session: AsyncSession,
    ) -> None:
        self._dial_router = dial_router
        self._mushi = mushi
        self._session = session
        self._graph = build_navigator_graph(dial_router)

    @classmethod
    def reader(cls, session: AsyncSession) -> NavigatorService:
        """Read-only instance — only needs DB session."""
        inst = cls.__new__(cls)
        inst._session = session
        inst._dial_router = None  # type: ignore[assignment]
        inst._mushi = None        # type: ignore[assignment]
        inst._graph = None        # type: ignore[assignment]
        return inst

    async def draft_poneglyphs(
        self,
        voyage: Voyage,
        plan: VoyagePlan,
    ) -> list[Poneglyph]:
        """
        1. Set voyage.status = PDD, flush.
        2. Invoke navigator graph with plan phases.
        3. On graph failure or parse error, reset status to CHARTED, raise NavigatorError.
        4. Persist one Poneglyph row per phase (use session.add for each).
        5. Create VivreCard checkpoint (inline, same transaction).
        6. Restore voyage.status = CHARTED (replannable).
        7. Commit all writes atomically.
        8. Best-effort publish PoneglyphDraftedEvent for each poneglyph.
        9. Return list of persisted Poneglyph models.
        """

    async def get_poneglyphs(
        self,
        voyage_id: uuid.UUID,
    ) -> list[Poneglyph]:
        """Return all Poneglyphs for the voyage, ordered by phase_number."""
```

**Key implementation details:**
- The `content` field of each Poneglyph row stores the full `PoneglyphContentSpec`
  serialized via `spec.model_dump_json()`.
- The `metadata_` JSONB field stores a summary dict:
  `{"phase_name": title, "assigned_to": ..., "test_criteria_count": N, "file_count": N}`.
- Publish one `PoneglyphDraftedEvent` per poneglyph (all best-effort, inside a single
  try/except block with logging).

### 4. REST API — `app/api/v1/navigator.py`

Two endpoints on the existing voyage router prefix:

| Method | Path | Handler | Response |
|--------|------|---------|----------|
| POST | `/voyages/{voyage_id}/poneglyphs` | `draft_poneglyphs` | 201 → `DraftPoneglyphsResponse` |
| GET | `/voyages/{voyage_id}/poneglyphs` | `get_poneglyphs` | 200 → `PoneglyphListResponse` |

**POST rules:**
- Requires voyage to exist, be owned by the user, and have status `CHARTED`.
- If status != CHARTED, return 409 `VOYAGE_NOT_CHARTABLE`.
- Fetches the latest VoyagePlan internally. If no plan exists, return 404 `PLAN_NOT_FOUND`.
- Catches `NavigatorError` → returns 422 with `{"error": {"code": ..., "message": ...}}`.

**GET rules:**
- Uses `get_navigator_reader` dependency (session-only, no dial_router).
- Returns all poneglyphs for the voyage. If empty list, return 200 with empty list.

**Dependencies:**

```python
async def get_navigator_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
) -> NavigatorService:
    return NavigatorService(dial_router, mushi, session)

async def get_navigator_reader(
    session: AsyncSession = Depends(get_db),
) -> NavigatorService:
    return NavigatorService.reader(session)
```

### 5. Wiring

- Add `navigator.router` to `app/api/v1/router.py`.

## Test Plan

All tests use mocked dependencies (no real LLM calls, no real DB).

### Schema Tests — `tests/test_navigator_schemas.py`

1. `PoneglyphContentSpec` accepts valid data.
2. `PoneglyphContentSpec` rejects `phase_number < 1`.
3. `PoneglyphContentSpec` rejects empty `title`.
4. `PoneglyphContentSpec` rejects empty `test_criteria` list.
5. `NavigatorOutputSpec` rejects empty poneglyphs list.
6. `NavigatorOutputSpec` rejects duplicate phase numbers.
7. `NavigatorOutputSpec` accepts valid multi-phase output.

### Graph Tests — `tests/test_navigator_graph.py`

1. `generate` node sends correct role (`CrewRole.NAVIGATOR`) and stores raw_poneglyphs.
2. `generate` node includes plan phases in user message.
3. `validate` node parses valid JSON into `NavigatorOutputSpec`.
4. `validate` node sets error on invalid JSON.
5. `validate` node sets error on invalid schema (empty poneglyphs).
6. `validate` node strips markdown fences (`json` and bare).
7. Full graph invocation returns parsed poneglyphs on success.
8. Full graph invocation sets error on invalid LLM output.

### Service Tests — `tests/test_navigator_service.py`

1. `draft_poneglyphs` sets voyage status to PDD.
2. `draft_poneglyphs` invokes dial router with NAVIGATOR role.
3. `draft_poneglyphs` persists one Poneglyph per phase.
4. `draft_poneglyphs` stores content as serialized PoneglyphContentSpec.
5. `draft_poneglyphs` stores metadata summary in metadata_ field.
6. `draft_poneglyphs` creates VivreCard checkpoint.
7. `draft_poneglyphs` commits all writes atomically.
8. `draft_poneglyphs` restores CHARTED status after success.
9. `draft_poneglyphs` publishes PoneglyphDraftedEvent per poneglyph.
10. `draft_poneglyphs` succeeds when publish fails (best-effort).
11. `draft_poneglyphs` raises NavigatorError on invalid LLM output.
12. `draft_poneglyphs` resets status to CHARTED on failure.
13. `get_poneglyphs` returns poneglyphs ordered by phase_number.
14. `get_poneglyphs` returns empty list when none exist.
15. Reader instance can call `get_poneglyphs`.

### API Tests — `tests/test_navigator_api.py`

1. POST `/poneglyphs` returns 201 with poneglyph IDs.
2. POST `/poneglyphs` returns 409 if voyage not in CHARTED status.
3. POST `/poneglyphs` returns 404 if no voyage plan exists.
4. POST `/poneglyphs` returns 422 on NavigatorError.
5. GET `/poneglyphs` returns 200 with poneglyph list.
6. GET `/poneglyphs` returns 200 with empty list when no poneglyphs exist.

## Constraints

- No real LLM calls in tests — mock the DialSystemRouter.
- No real database — mock AsyncSession.
- Keep the graph minimal (2 nodes). Retry/feedback loops are future work.
- The Navigator only drafts Poneglyphs; it does not execute them.
- Single LLM call for all phases (one JSON array). If validation fails, entire batch fails.
- Follow the Captain's patterns exactly: `_strip_fences`, `reader()`, atomic commit,
  best-effort publish, `NavigatorError(code, message)`, status reset on failure.
- Reuse `PoneglyphRead` schema from `app/schemas/poneglyph.py` for GET responses.
- Reuse `PoneglyphDraftedEvent` from `app/den_den_mushi/events.py`.
