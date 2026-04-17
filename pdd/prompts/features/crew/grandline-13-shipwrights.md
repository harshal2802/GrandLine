# Phase 13: Shipwright Agent (Developer)

## Context

The Shipwright is the fourth crew agent. It's the **developer** — reads the
Navigator's Poneglyph for one phase, reads the Doctor's failing `HealthCheck`
tests for that phase, and generates source code that makes those tests pass.
When it succeeds, it commits the code to the Shipwright's git branch.

Unlike Navigator (one call, multi-phase batch) and Doctor (one call,
multi-phase batch), the Shipwright is **phase-scoped**: one invocation builds
one phase. This is the parallelism primitive — the future voyage pipeline
(Phase 15) will fan out one Shipwright invocation per phase and run them
concurrently.

The Shipwright also has an **iteration loop** the other agents don't have.
After generating code, it runs pytest against the generated files + the
stored health-check tests in the sandbox. If tests fail and iterations
remain, the failure output is fed back into the prompt and the code is
regenerated. The loop terminates on green tests or after 3 attempts
(`SHIPWRIGHT_MAX_ITERATIONS = 3`).

Same three-layer crew agent pattern as Captain/Navigator/Doctor
(`graph → service → API` with `reader()` factory), atomic DB commit that
includes a `VivreCard` checkpoint, best-effort event publishing after
commit, best-effort git commit path. Reuse `strip_fences` from
`app/crew/utils.py`.

**Key architectural note**: the iteration loop lives in the **service layer**,
not inside the compiled LangGraph graph. The service runs single-iteration
graph invocations in a Python loop and persists a `VivreCard` between
iterations. Graph nodes stay side-effect-free (they only call the Dial
System and the Execution Service). This choice is locked in
`pdd/context/decisions.md` (2026-04-17) — see "Service-owned iteration
loop".

### Existing Infrastructure

| System | Module | Key Interfaces |
|--------|--------|----------------|
| **Navigator** | `app.services.navigator_service.NavigatorService` | `NavigatorService.reader(session).get_poneglyphs(voyage_id)` |
| **Doctor** | `app.services.doctor_service.DoctorService` | `DoctorService.reader(session).get_health_checks(voyage_id)` |
| **Dial System** | `app.dial_system.router.DialSystemRouter` | `route(role, CompletionRequest) -> CompletionResult` |
| **Den Den Mushi** | `app.den_den_mushi.mushi.DenDenMushi` | `publish(stream, event)` |
| **Execution Service** | `app.services.execution_service.ExecutionService` | `run(user_id, ExecutionRequest) -> ExecutionResult` |
| **Git Service** | `app.services.git_service.GitService` | `create_branch(voyage_id, user_id, crew_member, base)`, `commit(voyage_id, user_id, message, crew_member, files={path: content})`, `push(voyage_id, user_id, branch)` |
| **VivreCard Service** | `app.services.vivre_card_service.VivreCardService` | `checkpoint(session, voyage_id, crew_member, state_data, checkpoint_reason)` |
| **Models** | `app.models.poneglyph.Poneglyph` | `id, voyage_id, phase_number, content (Text), metadata_` |
| **Models** | `app.models.health_check.HealthCheck` | `id, voyage_id, phase_number, poneglyph_id, file_path, content, framework, ...` |
| **Events** | `app.den_den_mushi.events` | `CodeGeneratedEvent` (already defined); `TestsPassedEvent` needs to be added |
| **Enums** | `app.models.enums` | `CrewRole.SHIPWRIGHT`, `VoyageStatus.BUILDING`, `VoyageStatus.CHARTED` (all already defined) |
| **Constants** | `app.den_den_mushi.constants` | `stream_key(voyage_id)` |
| **Shared helpers** | `app.crew.utils` | `strip_fences(text)` |
| **Doctor Graph** | `app.crew.doctor_graph` | Reference pattern: two-node StateGraph |

`Poneglyph.content` is a JSON string holding a `PoneglyphContentSpec` (from
`app.schemas.navigator`). The Shipwright parses it to extract
`task_description`, `test_criteria`, and `file_paths`. If a Poneglyph's JSON
is malformed, log a warning and fall back to an empty dict (Doctor lesson —
do not raise, do not silently swallow).

`HealthCheck.content` is the failing test source verbatim. The Shipwright
passes the list of `{file_path, content, framework}` tuples to the LLM so
the model sees the tests it must make pass.

`ExecutionRequest` takes `command: str`, `files: dict[str, str] | None = None`,
`timeout_seconds: int | None = None`. `ExecutionResult` has
`stdout, stderr, exit_code, duration_ms`. Paths in `files=` are relative to
`/workspace/` in the sandbox.

## Deliverables

### 1. Database — new `BuildArtifact` + `ShipwrightRun` models + migration

Two new tables in a single migration file under
`src/backend/alembic/versions/`. `shipwright_runs` is created first so
`build_artifacts.shipwright_run_id` can reference it. The migration's
`down_revision` is the current head — **verify with `alembic history`**; at
time of writing it is `a1b2c3d4e5f6`.

```python
op.create_table(
    "shipwright_runs",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("voyage_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("voyages.id"), nullable=False, index=True),
    sa.Column("poneglyph_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("poneglyphs.id"), nullable=True, index=True),
    sa.Column("phase_number", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(20), nullable=False),  # passed | failed | max_iterations
    sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("exit_code", sa.Integer(), nullable=True),
    sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("output", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
)
op.create_index("ix_shipwright_runs_voyage_phase", "shipwright_runs",
                ["voyage_id", "phase_number"])

op.create_table(
    "build_artifacts",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("voyage_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("voyages.id"), nullable=False, index=True),
    sa.Column("shipwright_run_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("shipwright_runs.id"), nullable=False, index=True),
    sa.Column("phase_number", sa.Integer(), nullable=False),
    sa.Column("file_path", sa.String(500), nullable=False),
    sa.Column("content", sa.Text(), nullable=False),
    sa.Column("language", sa.String(20), nullable=False, server_default="python"),
    sa.Column("created_by", sa.String(50), nullable=False, server_default="shipwright"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
)
op.create_index("ix_build_artifacts_voyage_phase", "build_artifacts",
                ["voyage_id", "phase_number"])
```

Downgrade drops both tables and both indexes in reverse order
(`build_artifacts` first, then `shipwright_runs`).

**No `metadata` JSONB on `BuildArtifact` and no stdout duplicated onto
per-file rows.** Per-run output lives on `ShipwrightRun.output`; the
`BuildArtifact` table is pure source-file content. (Doctor review lesson —
don't re-add a bag-of-extras column and don't duplicate stdout across
every file row.)

SQLAlchemy models:

`app/models/shipwright_run.py`:

```python
class ShipwrightRun(Base):
    __tablename__ = "shipwright_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    voyage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voyages.id"), index=True, nullable=False
    )
    poneglyph_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("poneglyphs.id"), index=True, nullable=True
    )
    phase_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    iteration_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

`app/models/build_artifact.py`:

```python
class BuildArtifact(Base):
    __tablename__ = "build_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    voyage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voyages.id"), index=True, nullable=False
    )
    shipwright_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipwright_runs.id"),
        index=True, nullable=False
    )
    phase_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(20), default="python", nullable=False)
    created_by: Mapped[str] = mapped_column(String(50), default="shipwright",
                                             nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Export both from `app/models/__init__.py`.

### 2. Pydantic Schemas

`app/schemas/build_artifact.py` — read model (mirrors
`schemas/health_check.py`):

```python
class BuildArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    voyage_id: uuid.UUID
    shipwright_run_id: uuid.UUID
    phase_number: int
    file_path: str
    content: str
    language: str
    created_by: str
    created_at: datetime
```

`app/schemas/shipwright.py` — includes **path-safety validators** on every
LLM-supplied path. Reuse the exact validator pattern Doctor landed in PR
#32 (`_validate_relative_path`): reject absolute paths, drive/scheme
prefixes in the first segment, and `..` traversal.

```python
import posixpath

def _validate_relative_path(path: str) -> str:
    if path.startswith("/") or path.startswith("\\"):
        raise ValueError(f"Path must be relative, got {path!r}")
    if ":" in path.split("/")[0]:
        raise ValueError(f"Path must not be a drive/scheme, got {path!r}")
    normalized = posixpath.normpath(path)
    if normalized.startswith("..") or "/../" in f"/{normalized}/":
        raise ValueError(f"Path traversal not allowed in {path!r}")
    if normalized in (".", ""):
        raise ValueError(f"Path must not be empty, got {path!r}")
    return path


class BuildArtifactSpec(BaseModel):
    """What the LLM emits for one generated source file."""
    file_path: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    language: Literal["python", "typescript", "javascript"] = "python"

    @field_validator("file_path")
    @classmethod
    def _validate_file_path(cls, v: str) -> str:
        return _validate_relative_path(v)


class ShipwrightOutputSpec(BaseModel):
    """Full LLM output — at least one source file per invocation."""
    files: list[BuildArtifactSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_file_paths(self) -> ShipwrightOutputSpec:
        paths = [f.file_path for f in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate file_path values in files")
        return self


class BuildResultResponse(BaseModel):
    voyage_id: uuid.UUID
    phase_number: int
    shipwright_run_id: uuid.UUID
    status: Literal["passed", "failed", "max_iterations"]
    iteration_count: int
    passed_count: int
    failed_count: int
    total_count: int
    file_count: int
    summary: str


class BuildArtifactListResponse(BaseModel):
    voyage_id: uuid.UUID
    phase_number: int | None
    artifacts: list[BuildArtifactRead]
```

Note: `BuildCodeRequest` is **not** a body — the phase number lives in the
URL path. `POST /phases/{phase_number}/build` takes no body. (If a future
caller needs to pass overrides, add a body then; v1 keeps it simple.)

### 3. LangGraph Graph — `app/crew/shipwright_graph.py`

A minimal **two-node** StateGraph (same pattern as Navigator/Doctor).
The graph runs **one iteration** per `.ainvoke()` call — the service
wraps it in a Python loop and persists a `VivreCard` between iterations.
Graph nodes have **no DB writes**.

```
[generate] → [run_tests]
```

**State schema:**

```python
class ShipwrightState(TypedDict):
    voyage_id: uuid.UUID
    phase_number: int
    poneglyph: dict[str, Any]           # parsed PoneglyphContentSpec + phase_number
    health_checks: list[dict[str, str]] # [{file_path, content, framework}]
    iteration: int                       # 1-indexed
    last_test_output: str | None         # previous iteration's pytest stdout
    generated_files: list[BuildArtifactSpec] | None
    exit_code: int | None
    stdout: str
    passed_count: int
    failed_count: int
    total_count: int
    error: str | None                    # LLM parse failure, not test failure
```

**Nodes:**

- `generate`: builds a user message containing the Poneglyph's
  `task_description`, `test_criteria`, and `file_paths`, plus the full text
  of each `HealthCheck.content` under a clearly-labeled "## Tests you must
  make pass" section. If `state["iteration"] > 1` and `last_test_output is
  not None`, append a "## Previous attempt — tests still failed" section
  containing `last_test_output[-2000:]` and the directive *"The tests above
  still fail. Fix the issues reported and regenerate the complete file
  set."* Calls `DialSystemRouter.route(CrewRole.SHIPWRIGHT, ...)` and
  stores `raw_output`. Then runs `strip_fences` + `json.loads` +
  `ShipwrightOutputSpec.model_validate`. On any `json.JSONDecodeError`,
  `ValueError`, or `KeyError`, stores the error string and sets
  `generated_files=None`.

- `run_tests`: **only runs if `generated_files is not None`.** Builds
  `files = {f.file_path: f.content for f in state["generated_files"]} |
  {hc["file_path"]: hc["content"] for hc in state["health_checks"]}`.
  Calls `ExecutionService.run(user_id, ExecutionRequest(
  command="cd /workspace && python -m pytest -x --tb=short",
  files=files, timeout_seconds=120))`. Stores `exit_code`, `stdout`, and
  parses `passed_count`/`failed_count` from the stdout (best-effort — same
  parsing rule as Doctor: count `PASSED`/`FAILED` tokens, fall back to
  `exit_code == 0 → passed=total`, else `failed=total`).

**System prompt** (constant `SHIPWRIGHT_SYSTEM_PROMPT`):

```
You are a Shipwright — a developer agent on a software engineering crew.
Your job is to write source code that makes the Doctor's pre-written
failing tests pass. The tests are the specification; your code is the
implementation.

You will receive:
- A Poneglyph describing one phase of the work (task description, test
  criteria, intended file paths)
- The exact content of the failing test files for that phase
- If this is a retry, the previous test run's output

Produce a complete set of source files that satisfy the tests. Every file
you emit must be importable and runnable as-is. Do not include the test
files themselves in your output — those already exist.

Rules for file_path values:
- Use relative paths only (no leading /, no drive letters, no ..)
- Match the style in the Poneglyph's file_paths hint where possible

Respond with ONLY a JSON object: {"files": [{"file_path": "...",
"content": "...", "language": "python"}, ...]}
Do not include any other text, markdown formatting, or explanation.
```

**Build function:**

```python
def build_shipwright_graph(
    dial_router: DialSystemRouter,
    execution_service: ExecutionService,
) -> CompiledStateGraph: ...
```

### 4. Events — add `TestsPassedEvent`

`CodeGeneratedEvent` already exists in `app/den_den_mushi/events.py`.
Add `TestsPassedEvent` symmetric with `ValidationPassedEvent`:

```python
class TestsPassedEvent(DenDenMushiEvent):
    event_type: Literal["tests_passed"] = "tests_passed"
```

Add it to the `AnyEvent` discriminated union. Do not add
`TestsFailedEvent` — the issue doesn't require it and a failed
`build_code` returns an error response; the voyage status reset is the
observable signal.

### 5. ShipwrightService — `app/services/shipwright_service.py`

```python
SHIPWRIGHT_MAX_ITERATIONS = 3


class ShipwrightError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ShipwrightService:
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
        self._graph = build_shipwright_graph(dial_router, execution_service)

    @classmethod
    def reader(cls, session: AsyncSession) -> ShipwrightService:
        inst = cls.__new__(cls)
        inst._session = session
        inst._dial_router = None   # type: ignore[assignment]
        inst._mushi = None         # type: ignore[assignment]
        inst._execution = None     # type: ignore[assignment]
        inst._git = None           # type: ignore[assignment]
        inst._graph = None         # type: ignore[assignment]
        return inst

    async def build_code(
        self,
        voyage: Voyage,
        phase_number: int,
        poneglyph: Poneglyph,
        health_checks: list[HealthCheck],
        user_id: uuid.UUID,
    ) -> BuildResultResponse: ...

    async def get_build_artifacts(
        self,
        voyage_id: uuid.UUID,
        phase_number: int | None = None,
    ) -> list[BuildArtifact]: ...

    async def get_latest_run(
        self,
        voyage_id: uuid.UUID,
        phase_number: int,
    ) -> ShipwrightRun | None: ...
```

**`build_code` flow:**

1. **Framework gate**: if any `hc.framework != "pytest"`, raise
   `ShipwrightError("VITEST_NOT_SUPPORTED", ...)`. Vitest is deferred
   (see `decisions.md` 2026-04-17).
2. Set `voyage.status = BUILDING`, flush.
3. Build the initial graph state:
   - `poneglyph = {"phase_number": poneglyph.phase_number, **_parse_poneglyph_content(poneglyph)}`
     where `_parse_poneglyph_content` does `json.loads` with a
     `try/except json.JSONDecodeError` that logs a warning with
     `poneglyph_id` and `phase_number` and returns `{}`.
   - `health_checks = [{"file_path": hc.file_path, "content": hc.content,
     "framework": hc.framework} for hc in health_checks]`
   - `iteration = 1`, `last_test_output = None`, `generated_files = None`.
4. **Iteration loop** (service-owned, up to `SHIPWRIGHT_MAX_ITERATIONS`):
   ```python
   for i in range(1, SHIPWRIGHT_MAX_ITERATIONS + 1):
       state["iteration"] = i
       state = await self._graph.ainvoke(state)
       # Checkpoint after each iteration (best-effort)
       await self._checkpoint_iteration(voyage, state)
       if state.get("error"):
           # LLM output couldn't be parsed. Try one more iteration with
           # the error fed back in via last_test_output; if it fails a
           # second time, raise.
           if i < SHIPWRIGHT_MAX_ITERATIONS:
               state["last_test_output"] = f"Previous JSON parse failed: {state['error']}"
               continue
           voyage.status = VoyageStatus.CHARTED.value
           await self._session.flush()
           raise ShipwrightError("BUILD_PARSE_FAILED", state["error"])
       if state["exit_code"] == 0:
           break
       # Tests failed — feed output back for next iteration
       state["last_test_output"] = state["stdout"]
   ```
5. After the loop, decide final status:
   - `"passed"` if `exit_code == 0`
   - `"max_iterations"` if all iterations ran without green
6. Create one `ShipwrightRun` row with `status`, `iteration_count = i`,
   `exit_code`, counts, `output = stdout[-4000:]`. Flush to get `run.id`.
7. If status is `"passed"`: delete any existing `BuildArtifact` rows for
   `(voyage_id, phase_number)` (**replace mode** — Navigator/Doctor lesson),
   then insert one `BuildArtifact` per generated file linked to `run.id`.
8. Create a final `VivreCard` (`crew_member="shipwright"`,
   `state_data={"phase_number": phase_number, "iteration_count": i,
   "status": status, "file_count": N}`,
   `checkpoint_reason="build_complete"`).
9. Set `voyage.status = CHARTED`, `await session.commit()`, refresh rows.
10. **Best-effort git commit** (only on `status == "passed"` and only if
    `self._git is not None` and `voyage.target_repo` is set):
    - `create_branch(voyage.id, user_id, "shipwright", base_branch="main")`
    - `commit(voyage.id, user_id,
      f"feat(phase-{phase_number}): Shipwright implementation",
      crew_member="shipwright",
      files={a.file_path: a.content for a in artifacts})`
    - `push(voyage.id, user_id, branch)`
    Wrapped in a single try/except — logs a warning on failure, never
    fails the request.
11. **Best-effort event publish** (only on `status == "passed"`):
    - `CodeGeneratedEvent(voyage_id, source_role=CrewRole.SHIPWRIGHT,
      payload={"phase_number": N, "shipwright_run_id": run.id,
      "file_count": N})`
    - `TestsPassedEvent(voyage_id, source_role=CrewRole.SHIPWRIGHT,
      payload={"phase_number": N, "shipwright_run_id": run.id,
      "passed_count": N})`
    - On failure or max_iterations: do not publish.
12. Return a `BuildResultResponse`.

**`_checkpoint_iteration` helper:**

Writes a `VivreCard` with `crew_member="shipwright"`,
`state_data={"phase_number": N, "iteration": i, "exit_code": X,
"file_count": len(generated_files or [])}`,
`checkpoint_reason="iteration"`. Best-effort — logs on failure but does
not raise. This is how we honor "no work lost" during long loops.

**`get_build_artifacts` flow:**

- `SELECT * FROM build_artifacts WHERE voyage_id = :v`
- If `phase_number is not None`, add `AND phase_number = :p`.
- Return ordered by `phase_number, file_path`.

**`get_latest_run` flow:**

- `SELECT * FROM shipwright_runs WHERE voyage_id = :v AND phase_number = :p
  ORDER BY created_at DESC LIMIT 1`.

### 6. REST API — `app/api/v1/shipwright.py`

Router with prefix `/voyages/{voyage_id}`, tag `shipwright`.

| Method | Path | Handler | Response |
|--------|------|---------|----------|
| POST | `/phases/{phase_number}/build` | `build_phase` | 201 → `BuildResultResponse` |
| GET  | `/phases/{phase_number}/build` | `get_phase_build` | 200 → `BuildResultResponse` |
| GET  | `/build-artifacts` | `list_build_artifacts` | 200 → `BuildArtifactListResponse` |

**POST `/phases/{phase_number}/build` rules:**

1. Voyage must be owned by user and have status `CHARTED` → else
   409 `VOYAGE_NOT_BUILDABLE`. (Serializes invocations per voyage in v1;
   see `decisions.md`.)
2. **API-layer 404 pre-checks** (Doctor lesson — 404 for missing
   prerequisites, 422 is for service-layer invariant violations):
   - Fetch Poneglyphs via `NavigatorService.reader(session).get_poneglyphs(
     voyage_id)`. Find the one matching `phase_number`. If none → 404
     `PONEGLYPH_NOT_FOUND`.
   - Fetch HealthChecks via `DoctorService.reader(session).get_health_checks(
     voyage_id)`. Filter to `phase_number`. If empty → 404
     `HEALTH_CHECKS_NOT_FOUND`.
3. Call `shipwright_service.build_code(voyage, phase_number, poneglyph,
   filtered_health_checks, user.id)`.
4. `ShipwrightError` → 422 `{"error": {"code": exc.code,
   "message": exc.message}}`.

**GET `/phases/{phase_number}/build` rules:**

- Returns the **latest** `ShipwrightRun` for the phase as a
  `BuildResultResponse`.
- 404 `BUILD_NOT_FOUND` if no run exists.
- Uses `get_shipwright_reader` dependency (session-only).

**GET `/build-artifacts` rules:**

- Optional query param `phase_number: int | None = None`.
- 200 with the list (empty list OK).
- Uses `get_shipwright_reader`.

**Dependencies:**

```python
async def get_shipwright_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
    execution_service: ExecutionService = Depends(get_execution_service),
    git_service: GitService = Depends(get_git_service),
) -> ShipwrightService:
    return ShipwrightService(
        dial_router, mushi, session,
        execution_service=execution_service,
        git_service=git_service,
    )

async def get_shipwright_reader(
    session: AsyncSession = Depends(get_db),
) -> ShipwrightService:
    return ShipwrightService.reader(session)
```

Reuse existing `get_execution_service` and `get_git_service` from
`app/api/v1/dependencies.py`. Reuse `get_navigator_reader` from
`app/api/v1/navigator.py` and `get_doctor_reader` from
`app/api/v1/doctor.py` for the 404 pre-checks.

### 7. Wiring

- Register `BuildArtifact` and `ShipwrightRun` imports in
  `app/models/__init__.py`.
- Add `shipwright.router` include in `app/api/v1/router.py`.
- Add `TestsPassedEvent` to `app/den_den_mushi/events.py` and the
  `AnyEvent` union.

## Test Plan

All tests use mocked dependencies (no real LLM, DB, sandbox, or git).

### Model/Migration Tests — extend `tests/test_models.py`

1. `build_artifacts` and `shipwright_runs` appear in
   `Base.metadata.tables`.
2. `test_shipwright_run_table_columns` — full column set matches.
3. `test_build_artifact_table_columns` — full column set matches.
4. `test_shipwright_run_voyage_phase_indexed` — composite index exists.
5. `test_build_artifact_voyage_phase_indexed` — composite index exists.

### Schema Tests — `tests/test_shipwright_schemas.py`

1. `BuildArtifactSpec` accepts valid python file.
2. `BuildArtifactSpec` accepts valid typescript file.
3. `BuildArtifactSpec` rejects empty `file_path`.
4. `BuildArtifactSpec` rejects empty `content`.
5. `BuildArtifactSpec` rejects invalid `language`.
6. `BuildArtifactSpec` defaults `language` to `python`.
7. `BuildArtifactSpec` rejects absolute `file_path`.
8. `BuildArtifactSpec` rejects traversal `../../etc/passwd`.
9. `BuildArtifactSpec` rejects nested traversal.
10. `BuildArtifactSpec` accepts nested relative path.
11. `ShipwrightOutputSpec` rejects empty `files`.
12. `ShipwrightOutputSpec` rejects duplicate file paths.
13. `ShipwrightOutputSpec` accepts multi-file output.
14. `BuildResultResponse` rejects status outside literal set.

### Graph Tests — `tests/test_shipwright_graph.py`

1. `generate` node sends `CrewRole.SHIPWRIGHT` to the dial router.
2. `generate` node includes Poneglyph `task_description` in user message.
3. `generate` node includes each `HealthCheck.content` verbatim in user
   message.
4. `generate` node on `iteration == 2` includes previous test output.
5. `generate` node on valid JSON → `generated_files` populated,
   `error=None`.
6. `generate` node on malformed JSON → `generated_files=None`,
   `error` set.
7. `generate` node strips ```json fences.
8. `run_tests` node skips execution when `generated_files is None`.
9. `run_tests` node calls `ExecutionService.run` with merged files.
10. `run_tests` node parses `exit_code == 0` as pass.
11. `run_tests` node parses `exit_code != 0` as fail.
12. Full graph returns a full state dict with both nodes' outputs.

### Service Tests — `tests/test_shipwright_service.py`

Fixtures: mock session (`.add`, `.flush`, `.commit`, `.execute`), mock
dial_router, mock mushi, mock execution_service, mock git_service,
mock graph `.ainvoke` that returns a preset state. Build a
`_mock_poneglyph(phase_number)` helper with valid JSON content and
`_mock_health_check(phase_number)` helpers.

**`build_code` — happy path:**

1. Sets voyage status to `BUILDING` during the call.
2. Invokes the graph with `iteration=1` initially.
3. On graph returning `exit_code=0` on iteration 1, terminates the loop.
4. Persists one `ShipwrightRun` row with `status="passed"`,
   `iteration_count=1`, counts from the graph state.
5. Deletes existing `BuildArtifact` rows for `(voyage_id, phase_number)`
   before inserting (assert a `Delete` statement is executed).
6. Persists one `BuildArtifact` per generated file, linked to the run id.
7. Creates a `VivreCard` with `checkpoint_reason="build_complete"`.
8. Creates `VivreCard`s with `checkpoint_reason="iteration"` — one per
   iteration.
9. Calls `session.commit()` exactly once.
10. Restores voyage status to `CHARTED`.
11. Publishes `CodeGeneratedEvent` and `TestsPassedEvent` on success.
12. Succeeds when publish raises (best-effort).
13. Calls `git_service.create_branch/commit/push` once each when `git_service`
    and `voyage.target_repo` are both set.
14. When `git_service.commit` raises, `build_code` still returns
    successfully.
15. Skips git entirely when `git_service` is `None`.

**`build_code` — iteration loop:**

16. When iteration 1 returns `exit_code != 0`, graph is invoked again with
    `iteration=2` and `last_test_output` populated.
17. When all iterations fail, terminates with `status="max_iterations"`.
18. On `max_iterations`, no `BuildArtifact` rows are inserted.
19. On `max_iterations`, no `CodeGeneratedEvent` or `TestsPassedEvent` is
    published.
20. On `max_iterations`, voyage status is restored to `CHARTED`.
21. On `max_iterations`, a `ShipwrightRun` row is persisted with
    `iteration_count=3`, `status="max_iterations"`.

**`build_code` — error paths:**

22. Raises `ShipwrightError("VITEST_NOT_SUPPORTED")` when any health check
    has `framework="vitest"`; voyage status reset to `CHARTED`; no graph
    invocation.
23. Raises `ShipwrightError("BUILD_PARSE_FAILED")` when the graph returns
    `error` on every iteration; voyage status reset to `CHARTED`.
24. On malformed Poneglyph JSON, a warning is logged and the service
    still proceeds with an empty-dict fallback (degradation).

**`get_build_artifacts`:**

25. Returns rows ordered by `phase_number, file_path`.
26. Filters by `phase_number` when supplied.
27. Returns empty list when none exist.
28. Reader instance can call it.

**`get_latest_run`:**

29. Returns the most recent row for the phase.
30. Returns `None` when no row exists.

### API Tests — `tests/test_shipwright_api.py`

1. POST `/phases/{n}/build` returns 201 with `BuildResultResponse`.
2. POST `/phases/{n}/build` returns 409 when voyage not `CHARTED`.
3. POST `/phases/{n}/build` returns 404 `PONEGLYPH_NOT_FOUND` when no
   poneglyph matches; asserts `build_code` was **not** awaited.
4. POST `/phases/{n}/build` returns 404 `HEALTH_CHECKS_NOT_FOUND` when no
   health checks match; asserts `build_code` was **not** awaited.
5. POST `/phases/{n}/build` returns 422 on `ShipwrightError`.
6. POST `/phases/{n}/build` returns 422 specifically on
   `VITEST_NOT_SUPPORTED`.
7. GET `/phases/{n}/build` returns 200 with latest run.
8. GET `/phases/{n}/build` returns 404 `BUILD_NOT_FOUND` when no run.
9. GET `/build-artifacts` returns 200 with list.
10. GET `/build-artifacts?phase_number=2` filters by phase.
11. GET `/build-artifacts` returns 200 with empty list.

## Constraints

- Mock every external: no real LLM, no real DB, no real sandbox, no real
  git.
- Keep the graph minimal (2 nodes, one iteration per `.ainvoke()`). The
  iteration loop lives in the service.
- Follow Navigator/Captain/Doctor patterns exactly: `strip_fences` from
  `app/crew/utils.py`, `reader()` factory, atomic DB commit before events,
  best-effort publish.
- **Delete-before-insert** for `BuildArtifact` on successful re-invocation
  — re-builds replace prior artifacts. `ShipwrightRun` rows are
  append-only (history preserved).
- **Status lifecycle** — transient `BUILDING`, restored to `CHARTED` on
  both success and failure. v1 serializes invocations per voyage via this
  gate; true per-phase parallelism waits for a future phase_status
  refactor.
- Git commit path is **best-effort and opt-in** — wrapped in a single
  try/except, logs a warning on failure, never fails the request. Only
  attempted on `status == "passed"`.
- Reuse `Poneglyph` rows via `NavigatorService.reader(session).get_poneglyphs(...)`
  and `HealthCheck` rows via
  `DoctorService.reader(session).get_health_checks(...)`.
- Add `TestsPassedEvent` to `events.py` + `AnyEvent`. `CodeGeneratedEvent`
  already exists.
- Single Dial System call per iteration. One JSON batch of files per call.
- `ShipwrightRun.output` is truncated to the last 4000 chars.
- `BuildArtifact` rows never store stdout — they point to a
  `ShipwrightRun` via `shipwright_run_id`.
- Pytest invocation is `python -m pytest -x --tb=short` with a 120-second
  timeout. Counting pass/fail is best-effort from stdout.
- **Path safety is non-negotiable** — validate every LLM `file_path` at
  the schema layer. LLM output feeds both the sandbox and the host-side
  git commit; traversal must be rejected before either touches it.
- **Vitest is deferred** — return `ShipwrightError("VITEST_NOT_SUPPORTED")`
  → 422 at the top of `build_code` if any health check's framework is
  not `"pytest"`. Logged in `decisions.md` 2026-04-17.
- **`SHIPWRIGHT_MAX_ITERATIONS = 3`** is a module-level constant, not an
  env/config. Locked in `decisions.md` 2026-04-17.
- **404 vs 422**: 404 for missing prerequisite resources (no Poneglyph,
  no HealthChecks, no prior run) — resolved at the API layer via readers.
  422 for service-layer invariant violations (`ShipwrightError`).
- **Malformed Poneglyph content → warn, degrade gracefully.** Log the
  offending `poneglyph_id` and `phase_number` and fall back to an empty
  dict; do not raise and do not silently swallow.
- **No `metadata_` JSONB on `BuildArtifact`.** `language` is a first-class
  column. Add a real column when a second field is actually needed.
- **Iteration VivreCards are best-effort.** A failed checkpoint write
  logs a warning but does not fail the iteration — the LLM call already
  happened.
