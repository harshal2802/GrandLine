# Phase 12: Doctor Agent (QA)

## Context

The Doctor is the third crew agent. It operates in **two distinct modes**:

- **Pre-build (TDD)**: consumes the Navigator's Poneglyphs, asks the Dial System to
  write failing tests for each phase, persists them as `HealthCheck` rows, and emits
  `HealthCheckWrittenEvent`.
- **Post-build (Validate)**: takes a set of Shipwright-produced source files, layers
  them alongside the stored health-check tests in a sandbox, runs pytest, updates the
  `HealthCheck` rows with the run result, and emits `ValidationPassedEvent` or
  `ValidationFailedEvent`.

This follows the **crew agent pattern** established by Captain (Phase 10) and Navigator
(Phase 11): three layers (graph → service → API), `reader()` factory for read-only
operations, atomic commits that include a `VivreCard` checkpoint, best-effort event
publishing after commit. Reuse the shared `strip_fences` helper in `app/crew/utils.py`.

### Existing Infrastructure

| System | Module | Key Interfaces |
|--------|--------|----------------|
| **Navigator** | `app.services.navigator_service.NavigatorService` | `get_poneglyphs(voyage_id) -> list[Poneglyph]` |
| **Dial System** | `app.dial_system.router.DialSystemRouter` | `route(role, CompletionRequest) -> CompletionResult` |
| **Den Den Mushi** | `app.den_den_mushi.mushi.DenDenMushi` | `publish(stream, event)` |
| **Execution Service** | `app.services.execution_service.ExecutionService` | `run(user_id, ExecutionRequest) -> ExecutionResult` |
| **Git Service** | `app.services.git_service.GitService` | `create_branch(voyage_id, user_id, crew_member, base)`, `commit(voyage_id, user_id, message, crew_member, files={path: content})`, `push(voyage_id, user_id, branch)` |
| **Models** | `app.models.poneglyph.Poneglyph` | `id, voyage_id, phase_number, content (Text), metadata_` |
| **Events** | `app.den_den_mushi.events` | `HealthCheckWrittenEvent`, `ValidationPassedEvent` (already defined); `ValidationFailedEvent` needs to be added |
| **Enums** | `app.models.enums` | `CrewRole.DOCTOR`, `VoyageStatus.TDD`, `VoyageStatus.REVIEWING` |
| **Constants** | `app.den_den_mushi.constants` | `stream_key(voyage_id)` |
| **Shared helpers** | `app.crew.utils` | `strip_fences(text)` |
| **Navigator Graph** | `app.crew.navigator_graph` | Reference pattern: two-node StateGraph (generate → validate) |

`Poneglyph.content` is a JSON string holding a `PoneglyphContentSpec` (from
`app.schemas.navigator`). The Doctor parses it to extract `test_criteria`,
`file_paths`, and `task_description`, which become the context for test generation.

`CompletionRequest` takes `messages: list[dict[str,str]]`, `role: CrewRole`,
`voyage_id`, `max_tokens`, `temperature`.

`ExecutionRequest` takes `command: str`, `files: dict[str, str] | None = None`,
`timeout_seconds: int | None = None`. `ExecutionResult` has
`stdout, stderr, exit_code, duration_ms`. Paths in `files=` are relative to
`/workspace/` in the sandbox.

## Deliverables

### 1. Database — new `HealthCheck` model + migration

New table `health_checks` (migration file under `src/backend/alembic/versions/`):

```python
op.create_table(
    "health_checks",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("voyage_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("voyages.id"), nullable=False, index=True),
    sa.Column("poneglyph_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("poneglyphs.id"), nullable=True, index=True),
    sa.Column("phase_number", sa.Integer(), nullable=False),
    sa.Column("file_path", sa.String(500), nullable=False),
    sa.Column("content", sa.Text(), nullable=False),
    sa.Column("framework", sa.String(20), nullable=False, server_default="pytest"),
    sa.Column("last_run_status", sa.String(20), nullable=True),
    sa.Column("last_run_output", sa.Text(), nullable=True),
    sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("metadata", postgresql.JSONB(), nullable=True),
    sa.Column("created_by", sa.String(50), nullable=False, server_default="doctor"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
)
```

Downgrade drops the table. Set `revision` to a new random hex; `down_revision` to the
current head (`00b24ef2f7d8`).

SQLAlchemy model — `app/models/health_check.py`:

```python
class HealthCheck(Base):
    __tablename__ = "health_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    voyage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voyages.id"), index=True, nullable=False
    )
    poneglyph_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("poneglyphs.id"), index=True, nullable=True
    )
    phase_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    framework: Mapped[str] = mapped_column(String(20), default="pytest", nullable=False)
    last_run_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_run_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB,
                                                              nullable=True)
    created_by: Mapped[str] = mapped_column(String(50), default="doctor", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Export from `app/models/__init__.py`.

### 2. Pydantic Schemas

`app/schemas/health_check.py` — read model (mirrors `schemas/poneglyph.py`):

```python
class HealthCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    voyage_id: uuid.UUID
    poneglyph_id: uuid.UUID | None
    phase_number: int
    file_path: str
    content: str
    framework: str
    last_run_status: str | None
    last_run_output: str | None
    last_run_at: datetime | None
    metadata_: dict[str, Any] | None
    created_by: str
    created_at: datetime
```

`app/schemas/doctor.py`:

```python
class HealthCheckSpec(BaseModel):
    """What the LLM emits for one phase's test file."""
    phase_number: int = Field(ge=1)
    file_path: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    framework: Literal["pytest", "vitest"] = "pytest"


class DoctorOutputSpec(BaseModel):
    """Full LLM output — one test file per phase minimum."""
    health_checks: list[HealthCheckSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_file_paths(self) -> DoctorOutputSpec:
        paths = [hc.file_path for hc in self.health_checks]
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate file_path values in health_checks")
        return self


class WriteHealthChecksResponse(BaseModel):
    voyage_id: uuid.UUID
    health_check_ids: list[uuid.UUID]
    count: int


class HealthCheckListResponse(BaseModel):
    voyage_id: uuid.UUID
    health_checks: list[HealthCheckRead]


class ValidateCodeRequest(BaseModel):
    """Caller supplies the Shipwright-produced files to test against."""
    files: dict[str, str] = Field(min_length=1)


class ValidationResultResponse(BaseModel):
    voyage_id: uuid.UUID
    status: Literal["passed", "failed"]
    passed_count: int
    failed_count: int
    total_count: int
    summary: str
```

### 3. LangGraph Graph — `app/crew/doctor_graph.py`

A minimal **two-node** StateGraph (same pattern as Navigator). The graph only
handles the pre-build test-generation path; post-build validation is not an LLM call.

```
[generate] → [validate]
```

**State schema:**

```python
class DoctorState(TypedDict):
    poneglyphs: list[dict[str, Any]]  # serialized PoneglyphContentSpec dicts + phase_number
    raw_output: str
    health_checks: list[HealthCheckSpec] | None
    error: str | None
```

**Nodes:**

- `generate`: builds a user message containing each Poneglyph's `phase_number`,
  `title`, `task_description`, `test_criteria`, and `file_paths`. Calls
  `DialSystemRouter.route(CrewRole.DOCTOR, ...)`.
- `validate`: runs `strip_fences(state["raw_output"])`, `json.loads(...)`, then
  `DoctorOutputSpec.model_validate(...)`. On any `json.JSONDecodeError`, `ValueError`,
  or `KeyError`, stores the error string and sets `health_checks=None`.

**System prompt** (constant `DOCTOR_SYSTEM_PROMPT`):

```
You are the Doctor of a software engineering crew. Your job is to write failing
health-check tests (TDD) for each phase of the voyage — BEFORE any implementation
code exists. Your tests should import and reference the modules, classes, and
functions that the Shipwrights will build from the Poneglyphs; those symbols do
not exist yet, and that is intentional. A well-written failing test is the
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
Do not include any other text, markdown formatting, or explanation.
```

**Build function:**

```python
def build_doctor_graph(dial_router: DialSystemRouter) -> CompiledStateGraph: ...
```

### 4. Events — add `ValidationFailedEvent`

Add to `app/den_den_mushi/events.py`, symmetric with `ValidationPassedEvent`:

```python
class ValidationFailedEvent(DenDenMushiEvent):
    event_type: Literal["validation_failed"] = "validation_failed"
```

Include it in the `AnyEvent` discriminated union.

### 5. DoctorService — `app/services/doctor_service.py`

```python
class DoctorError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class DoctorService:
    def __init__(
        self,
        dial_router: DialSystemRouter,
        mushi: DenDenMushi,
        session: AsyncSession,
        execution_service: ExecutionService,
        git_service: GitService | None = None,  # optional
    ) -> None:
        self._dial_router = dial_router
        self._mushi = mushi
        self._session = session
        self._execution = execution_service
        self._git = git_service
        self._graph = build_doctor_graph(dial_router)

    @classmethod
    def reader(cls, session: AsyncSession) -> DoctorService:
        inst = cls.__new__(cls)
        inst._session = session
        inst._dial_router = None  # type: ignore[assignment]
        inst._mushi = None        # type: ignore[assignment]
        inst._execution = None    # type: ignore[assignment]
        inst._git = None          # type: ignore[assignment]
        inst._graph = None        # type: ignore[assignment]
        return inst

    async def write_health_checks(
        self,
        voyage: Voyage,
        poneglyphs: list[Poneglyph],
        user_id: uuid.UUID,
    ) -> list[HealthCheck]: ...

    async def validate_code(
        self,
        voyage: Voyage,
        user_id: uuid.UUID,
        shipwright_files: dict[str, str],
    ) -> ValidationResultResponse: ...

    async def get_health_checks(
        self,
        voyage_id: uuid.UUID,
    ) -> list[HealthCheck]: ...
```

**`write_health_checks` flow:**
1. Set `voyage.status = TDD`, flush.
2. Build `graph_input = [{"phase_number": p.phase_number, **json.loads(p.content)}
   for p in poneglyphs]`. Invoke the graph.
3. On graph raise: reset status to `CHARTED`, flush, re-raise.
4. On `health_checks is None`: reset status to `CHARTED`, flush, raise
   `DoctorError("HEALTH_CHECK_PARSE_FAILED", ...)`.
5. **Phase alignment check** (Fix #5 lesson from Navigator): every returned
   `phase_number` must exist in the Poneglyph set. If not, reset status and raise
   `DoctorError("HEALTH_CHECK_PHASE_MISMATCH", ...)`.
6. **Replace mode** (Fix #1 lesson): `await session.execute(delete(HealthCheck)
   .where(HealthCheck.voyage_id == voyage.id))`.
7. Insert one `HealthCheck` row per spec, linking `poneglyph_id` by matching
   `phase_number`.
8. Create a `VivreCard` checkpoint inline (`crew_member="doctor"`,
   `state_data={"health_check_count": N, "phase_numbers": [...]}`,
   `checkpoint_reason="health_checks_written"`).
9. Set `voyage.status = CHARTED`, `await session.commit()`, refresh rows.
10. **Best-effort git commit** (all in one try/except, after the DB commit):
    if `self._git is not None` and `voyage.target_repo` is set:
    - `create_branch(voyage.id, user_id, "doctor", base_branch="main")`
    - `commit(voyage.id, user_id, "test: add Doctor health checks",
      crew_member="doctor", files={hc.file_path: hc.content for hc in hcs})`
    - `push(voyage.id, user_id, branch)`
    Log warnings on failure — do not fail the request.
11. **Best-effort event publish** — one `HealthCheckWrittenEvent` per row.
12. Return persisted health checks.

**`validate_code` flow:**
1. Set `voyage.status = REVIEWING`, flush.
2. Load existing health checks via a SELECT (raise `DoctorError("NO_HEALTH_CHECKS",
   ...)` if none). Reset status first.
3. Combine `shipwright_files | {hc.file_path: hc.content for hc in hcs}` into a
   single `files` dict.
4. Run via `ExecutionService.run(user_id, ExecutionRequest(
     command="cd /workspace && python -m pytest -x --tb=short",
     files=files, timeout_seconds=300))`.
5. Decide pass/fail by `exit_code == 0`.
6. Parse a simple `passed_count` / `failed_count` from the stdout (count lines
   matching `PASSED`/`FAILED` from pytest's short summary; fallback to
   `exit_code == 0` → `passed_count = total`, else `failed_count = total`).
7. Update each health check row: set `last_run_status = "passed"` or `"failed"`,
   `last_run_at = utcnow()`, `last_run_output = result.stdout[-4000:]` (truncated).
8. Restore `voyage.status = CHARTED`, commit.
9. Publish `ValidationPassedEvent` or `ValidationFailedEvent` best-effort.
10. Return a `ValidationResultResponse`.

### 6. REST API — `app/api/v1/doctor.py`

Router with prefix `/voyages/{voyage_id}`, tag `doctor`.

| Method | Path | Handler | Response |
|--------|------|---------|----------|
| POST | `/health-checks` | `write_health_checks` | 201 → `WriteHealthChecksResponse` |
| GET  | `/health-checks` | `get_health_checks` | 200 → `HealthCheckListResponse` |
| POST | `/validation` | `run_validation` | 200 → `ValidationResultResponse` |

**POST `/health-checks` rules:**
- Voyage must be owned by user and have status `CHARTED` → else 409 `VOYAGE_NOT_TESTABLE`.
- Must have at least one Poneglyph → else 404 `PONEGLYPHS_NOT_FOUND` (fetch via
  `NavigatorService.reader(session).get_poneglyphs(voyage_id)`).
- `DoctorError` → 422 `{"error": {"code": exc.code, "message": exc.message}}`.

**POST `/validation` rules:**
- Body: `ValidateCodeRequest` (non-empty `files`).
- Voyage must be in status `CHARTED` → else 409 `VOYAGE_NOT_TESTABLE`.
- Must have at least one `HealthCheck` → else 404 `NO_HEALTH_CHECKS`.
- `DoctorError` → 422.

**GET `/health-checks`**: 200 with list (empty list is OK).

**Dependencies:**

```python
async def get_doctor_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
    execution_service: ExecutionService = Depends(get_execution_service),
    git_service: GitService = Depends(get_git_service),
) -> DoctorService:
    return DoctorService(dial_router, mushi, session, execution_service, git_service)

async def get_doctor_reader(
    session: AsyncSession = Depends(get_db),
) -> DoctorService:
    return DoctorService.reader(session)
```

Reuse existing dependencies `get_execution_service` and `get_git_service` from
`app/api/v1/dependencies.py` if present; otherwise add them there (check first).
Reuse `get_navigator_reader` from `app/api/v1/navigator.py` to fetch Poneglyphs.

### 7. Wiring

- Register `HealthCheck` in `app/models/__init__.py` imports.
- Add `doctor.router` include in `app/api/v1/router.py`.
- Add `ValidationFailedEvent` to the `AnyEvent` union in
  `app/den_den_mushi/events.py`.

## Test Plan

All tests use mocked dependencies (no real LLM, DB, sandbox, or git).

### Schema Tests — `tests/test_doctor_schemas.py`

1. `HealthCheckSpec` accepts valid pytest data.
2. `HealthCheckSpec` accepts valid vitest data.
3. `HealthCheckSpec` rejects `phase_number < 1`.
4. `HealthCheckSpec` rejects empty `file_path`.
5. `HealthCheckSpec` rejects empty `content`.
6. `HealthCheckSpec` rejects framework other than pytest/vitest.
7. `DoctorOutputSpec` rejects empty `health_checks`.
8. `DoctorOutputSpec` rejects duplicate `file_path`.
9. `DoctorOutputSpec` accepts multi-phase output.
10. `ValidateCodeRequest` rejects empty `files`.

### Graph Tests — `tests/test_doctor_graph.py`

1. `generate` node sends `CrewRole.DOCTOR` and stores `raw_output`.
2. `generate` node includes Poneglyph phase titles and test_criteria in the user
   message.
3. `validate` node parses valid JSON.
4. `validate` node sets error on malformed JSON.
5. `validate` node sets error on empty `health_checks`.
6. `validate` node strips ` ```json ... ``` ` fences.
7. `validate` node strips bare fences.
8. Full graph success: returns parsed `HealthCheckSpec` list.
9. Full graph invalid LLM output: sets error, `health_checks=None`.

### Service Tests — `tests/test_doctor_service.py`

Fixtures: mock session (with `.add`, `.flush`, `.commit`, `.execute`), mock
dial_router, mock mushi (with `.publish`), mock execution_service (with `.run`),
mock git_service (with `.create_branch`, `.commit`, `.push`). Build a
`_mock_poneglyph(phase_number, file_paths)` helper whose `.content` is a JSON
string of a valid `PoneglyphContentSpec`.

**`write_health_checks`:**

1. Sets voyage status to `TDD` during the call.
2. Invokes dial router with `CrewRole.DOCTOR`.
3. Persists one `HealthCheck` row per returned spec.
4. Links `poneglyph_id` by matching `phase_number`.
5. Stores `content` and `file_path` verbatim from the spec.
6. Creates one `VivreCard` with `crew_member="doctor"`.
7. Calls `session.commit()` exactly once.
8. Restores voyage status to `CHARTED` after success.
9. Publishes one `HealthCheckWrittenEvent` per health check.
10. Succeeds even when publish raises (best-effort).
11. Deletes existing `HealthCheck` rows before inserting new ones (Fix #1 pattern —
    assert a `Delete` statement is executed).
12. Raises `DoctorError` with code `HEALTH_CHECK_PARSE_FAILED` on invalid LLM output;
    status is reset to `CHARTED`.
13. Raises `DoctorError` with code `HEALTH_CHECK_PHASE_MISMATCH` when an LLM-returned
    `phase_number` isn't in the Poneglyph set; status reset.
14. When `git_service` is supplied and `voyage.target_repo` is set, calls
    `create_branch`, `commit`, `push` once each (best-effort).
15. When `git_service` is `None`, does not attempt git operations, and the call
    still succeeds.
16. When `git_service.commit` raises, the service still returns successfully and
    logs a warning (best-effort).

**`validate_code`:**

17. Sets voyage status to `REVIEWING` during the call.
18. Layers `shipwright_files` and stored `HealthCheck.content` into
    `ExecutionRequest.files`.
19. Calls `ExecutionService.run` with a pytest command.
20. Returns `status="passed"` with updated counts when `exit_code=0`.
21. Returns `status="failed"` with updated counts when `exit_code!=0`.
22. Updates each `HealthCheck.last_run_status`, `.last_run_output`, `.last_run_at`.
23. Commits DB changes exactly once.
24. Restores voyage status to `CHARTED` after success.
25. Publishes `ValidationPassedEvent` on pass.
26. Publishes `ValidationFailedEvent` on fail.
27. Raises `DoctorError("NO_HEALTH_CHECKS", ...)` when no rows exist; status reset.

**`get_health_checks`:**

28. Returns rows ordered by `phase_number`.
29. Returns empty list when none exist.
30. Reader instance can call it (no dial_router required).

### API Tests — `tests/test_doctor_api.py`

1. POST `/health-checks` returns 201 with IDs.
2. POST `/health-checks` returns 409 when voyage not `CHARTED`.
3. POST `/health-checks` returns 404 when no Poneglyphs exist.
4. POST `/health-checks` returns 422 on `DoctorError`.
5. GET `/health-checks` returns 200 with list.
6. GET `/health-checks` returns 200 with empty list.
7. POST `/validation` returns 200 with `status="passed"`.
8. POST `/validation` returns 200 with `status="failed"`.
9. POST `/validation` returns 409 when voyage not `CHARTED`.
10. POST `/validation` returns 404 when no health checks exist.
11. POST `/validation` returns 422 on `DoctorError`.

## Constraints

- Mock every external: no real LLM, no real DB, no real sandbox, no real git.
- Keep the graph minimal (2 nodes). No retry loops.
- Follow Navigator/Captain patterns exactly: `strip_fences` from
  `app/crew/utils.py`, `reader()` factory, atomic DB commit before events,
  best-effort publish.
- **Delete-before-insert** for `write_health_checks` — re-draft replaces.
- **Phase alignment** — LLM-returned `phase_number` must be a subset of the
  Poneglyph set; otherwise `HEALTH_CHECK_PHASE_MISMATCH`.
- **Status lifecycle** — transient `TDD` or `REVIEWING`, restored to `CHARTED` on
  both success and failure so the voyage remains actionable.
- Git commit path is **best-effort and opt-in** — wrapped in a single try/except,
  logs a warning on failure, never fails the request.
- Reuse `Poneglyph` rows via `NavigatorService.reader(session).get_poneglyphs(...)`.
- Reuse `HealthCheckWrittenEvent` and `ValidationPassedEvent`; add
  `ValidationFailedEvent` to `events.py` + `AnyEvent` union.
- Single Dial System call per `write_health_checks` (one JSON batch for all
  phases). Validation failures of the batch fail the whole call — no partial
  writes.
- `last_run_output` is truncated to the last 4000 chars to keep rows small.
- Pytest invocation is `python -m pytest -x --tb=short`. Counting pass/fail is
  best-effort from stdout; when parsing fails, fall back to `exit_code == 0` →
  `passed_count = total_count`, else `failed_count = total_count`.
