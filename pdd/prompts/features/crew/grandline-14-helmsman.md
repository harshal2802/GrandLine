# Phase 14: Helmsman Agent (DevOps)

## Context

The Helmsman is the fifth crew agent. It's the **DevOps agent** — takes a
voyage + a deployment tier (`preview` | `staging` | `production`) and
triggers a deploy via a swappable `DeploymentBackend`. On success, it
records a `Deployment` row and publishes events. On failure, it asks the
Dial System (once, best-effort) to diagnose the failure into a structured
summary and records it alongside the failed deployment.

Unlike Navigator (multi-phase LLM batch), Doctor (per-phase LLM batch),
and Shipwright (iterative LLM loop), the Helmsman is mostly
**imperative**. The only LLM call is **failure diagnosis**, and it only
fires on `status != "completed"`. A successful deploy makes zero LLM
calls.

Same three-layer crew agent pattern as Captain/Navigator/Doctor/Shipwright
(`graph → service → API` with `reader()` factory), atomic DB commit that
includes a `VivreCard` checkpoint, best-effort event publishing after
commit. Reuse `strip_fences` from `app/crew/utils.py`.

**Key architectural note**: v1 does **not** deploy to real clusters. It
ships with an `InProcessDeploymentBackend` (simulated — dict-backed, no
Docker/k8s) behind a `DeploymentBackend` ABC that mirrors
`ExecutionBackend`. This lets Phase 15 Pipeline wire the Helmsman in as
the `DEPLOYING` step immediately. Real backends (`DockerDeploymentBackend`,
`KubernetesDeploymentBackend`) slot in later without changing the service
layer. This is locked in `pdd/prompts/features/crew/PLAN-helmsman-agent.md`
(2026-04-17).

**Second architectural note**: the production approval gate is an
explicit `approved_by: UUID | None` field on `DeployRequest`. If
`tier == production` and `approved_by` is not set, the service raises
`HelmsmanError("APPROVAL_REQUIRED")` → 403. The check is encapsulated in a
single helper `_require_production_approval(tier, approved_by)` so
Phase 17 (User Intervention) can replace the approval mechanism by
swapping that one function — nothing else in the service needs to change.

**Third architectural note**: Helmsman does **not** orchestrate git
branches or merges. The caller provides `git_ref`; the service only
resolves `git_ref → git_sha` via `GitService.get_head_sha(...)` for
audit. External orchestration (Phase 15 Pipeline) handles the git flow
between tiers.

### Existing Infrastructure

| System | Module | Key Interfaces |
|--------|--------|----------------|
| **Dial System** | `app.dial_system.router.DialSystemRouter` | `route(role, CompletionRequest) -> CompletionResult` |
| **Den Den Mushi** | `app.den_den_mushi.mushi.DenDenMushi` | `publish(stream, event)` |
| **Git Service** | `app.services.git_service.GitService` | `create_branch`, `commit`, `push`, etc. — **NEEDS `get_head_sha` added** (see Deliverable #8) |
| **VivreCard Service** | `app.services.vivre_card_service.VivreCardService` | `checkpoint(session, voyage_id, crew_member, state_data, checkpoint_reason)` |
| **Voyage Model** | `app.models.voyage.Voyage` | Has `status`, `target_repo`, etc. |
| **Enums** | `app.models.enums` | `CrewRole.HELMSMAN`, `VoyageStatus.DEPLOYING`, `VoyageStatus.CHARTED` (all already defined) |
| **Events** | `app.den_den_mushi.events` | `DeploymentCompletedEvent` already exists; `DeploymentStartedEvent` + `DeploymentFailedEvent` need to be ADDED to events.py + `AnyEvent` union |
| **Constants** | `app.den_den_mushi.constants` | `stream_key(voyage_id)` |
| **Shared helpers** | `app.crew.utils` | `strip_fences(text)` |
| **Execution Backend ABC (pattern reference)** | `app.execution.backend.ExecutionBackend` | Mirror this exact shape for `DeploymentBackend` |
| **Shipwright service (pattern reference)** | `app.services.shipwright_service` | `TRUNCATE = 4000`, atomic commit + best-effort events, `reader()` factory |

Current alembic head is `b2c3d4e5f6a1` (Shipwright). New migration's
`down_revision = "b2c3d4e5f6a1"`.

## Deliverables

### 1. Database — new `Deployment` model + migration

One new table. Single migration file under
`src/backend/alembic/versions/`. `down_revision = "b2c3d4e5f6a1"`.

```python
op.create_table(
    "deployments",
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("voyage_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("voyages.id"), nullable=False, index=True),
    sa.Column("tier", sa.String(20), nullable=False),        # preview | staging | production
    sa.Column("action", sa.String(20), nullable=False),      # deploy | rollback
    sa.Column("git_ref", sa.String(255), nullable=False),
    sa.Column("git_sha", sa.String(64), nullable=True),
    sa.Column("status", sa.String(20), nullable=False),      # running | completed | failed
    sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("url", sa.String(500), nullable=True),
    sa.Column("backend_log", sa.Text(), nullable=True),
    sa.Column("diagnosis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("previous_deployment_id", postgresql.UUID(as_uuid=True),
              sa.ForeignKey("deployments.id"), nullable=True, index=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
)
op.create_index(
    "ix_deployments_voyage_tier_created",
    "deployments",
    ["voyage_id", "tier", sa.text("created_at DESC")],
)
```

Downgrade drops the index then the table.

SQLAlchemy model in `app/models/deployment.py`:

```python
class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    voyage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voyages.id"), index=True, nullable=False
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    git_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    backend_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    previous_deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deployments.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),  # SQLAlchemy-level only; migration omits onupdate intentionally.
        nullable=False,
    )
```

Export from `app/models/__init__.py`.

### 2. Pydantic Schemas — `app/schemas/deployment.py`

```python
DeploymentTier = Literal["preview", "staging", "production"]
DeploymentAction = Literal["deploy", "rollback"]
DeploymentStatus = Literal["running", "completed", "failed"]


class DeploymentDiagnosisSpec(BaseModel):
    """Structured LLM diagnosis of a deployment failure."""
    summary: str = Field(min_length=1, max_length=500)
    likely_cause: str = Field(min_length=1, max_length=1000)
    suggested_action: str = Field(min_length=1, max_length=1000)


class DeployRequest(BaseModel):
    tier: DeploymentTier
    git_ref: str | None = Field(default=None, max_length=255)
    approved_by: uuid.UUID | None = None


class RollbackRequest(BaseModel):
    tier: DeploymentTier


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    voyage_id: uuid.UUID
    tier: DeploymentTier
    action: DeploymentAction
    git_ref: str
    git_sha: str | None
    status: DeploymentStatus
    approved_by: uuid.UUID | None
    url: str | None
    backend_log: str | None
    diagnosis: dict[str, Any] | None
    previous_deployment_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DeploymentResponse(BaseModel):
    voyage_id: uuid.UUID
    deployment_id: uuid.UUID
    tier: DeploymentTier
    action: DeploymentAction
    status: DeploymentStatus
    git_ref: str
    git_sha: str | None
    url: str | None
    diagnosis: dict[str, Any] | None


class DeploymentListResponse(BaseModel):
    voyage_id: uuid.UUID
    tier: DeploymentTier | None
    deployments: list[DeploymentRead]
```

Note: `git_ref` is optional in `DeployRequest`; the service fills the
default per tier (see Deliverable #5). `tier` on `RollbackRequest` must
be provided — the caller picks which tier to roll back.

### 3. DeploymentBackend ABC + dataclasses — `app/deployment/backend.py`

Mirror `ExecutionBackend`. New package `app/deployment/` with an empty
`__init__.py`.

```python
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class DeploymentArtifact:
    voyage_id: uuid.UUID
    tier: Literal["preview", "staging", "production"]
    git_ref: str
    git_sha: str | None
    # Reserved for future real backends (Docker/k8s manifest path).
    # v1 callers always pass None; field kept on the ABC for forward-compat.
    manifest_path: str | None = None


@dataclass(frozen=True)
class DeploymentResult:
    status: Literal["completed", "failed"]
    url: str | None
    backend_log: str
    error: str | None = None


class DeploymentError(Exception):
    """Raised when a backend operation fails internally."""


class DeploymentBackend(ABC):
    @abstractmethod
    async def deploy(self, artifact: DeploymentArtifact) -> DeploymentResult:
        """Deploy the artifact to the given tier. Never raises on deploy
        failure — returns status='failed' with a log instead. Raises
        DeploymentError only for backend-internal errors (e.g. client
        connection failure)."""
        ...

    @abstractmethod
    async def status(
        self,
        voyage_id: uuid.UUID,
        tier: Literal["preview", "staging", "production"],
    ) -> DeploymentResult | None:
        """Return the last deploy result for (voyage, tier), or None."""
        ...

    async def close(self) -> None:
        """Release resources (e.g. HTTP client session)."""
```

### 4. InProcessDeploymentBackend — `app/deployment/in_process.py`

Dict-backed, synchronous simulation. Used for v1 and for tests.

```python
from __future__ import annotations

import uuid
from typing import Literal

from app.deployment.backend import (
    DeploymentArtifact,
    DeploymentBackend,
    DeploymentResult,
)


TierLiteral = Literal["preview", "staging", "production"]


class InProcessDeploymentBackend(DeploymentBackend):
    """Simulated deployment backend. Records deploys in an in-memory
    dict and returns synthetic URLs. Used for v1 (no real cluster) and
    for tests.

    Fail-injection: if `fail_tiers` contains the tier being deployed,
    `deploy()` returns status='failed' with a synthetic log. Useful for
    exercising the diagnose path in tests without patching."""

    def __init__(self, *, fail_tiers: set[str] | None = None) -> None:
        self._records: dict[tuple[uuid.UUID, str], DeploymentResult] = {}
        self._fail_tiers = fail_tiers or set()

    async def deploy(self, artifact: DeploymentArtifact) -> DeploymentResult:
        if artifact.tier in self._fail_tiers:
            result = DeploymentResult(
                status="failed",
                url=None,
                backend_log=(
                    f"simulated failure for tier={artifact.tier} "
                    f"ref={artifact.git_ref} sha={artifact.git_sha}"
                ),
                error="SimulatedFailure",
            )
        else:
            url = (
                f"http://{artifact.tier}.voyage-{artifact.voyage_id.hex[:8]}.local"
            )
            result = DeploymentResult(
                status="completed",
                url=url,
                backend_log=(
                    f"deployed tier={artifact.tier} ref={artifact.git_ref} "
                    f"sha={artifact.git_sha} url={url}"
                ),
                error=None,
            )
        self._records[(artifact.voyage_id, artifact.tier)] = result
        return result

    async def status(
        self,
        voyage_id: uuid.UUID,
        tier: TierLiteral,
    ) -> DeploymentResult | None:
        return self._records.get((voyage_id, tier))
```

### 5. LangGraph graph — `app/crew/helmsman_graph.py`

A minimal **two-node** StateGraph with one conditional edge. Graph nodes
are **side-effect-free at the DB layer** — they call the deployment
backend and the dial router only. The service layer owns DB writes,
voyage status transitions, and events.

```
START → deploy → (status == "completed"? END : diagnose) → END
```

**State schema:**

```python
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
```

`manifest_path` is **not** in state for v1 — the simulated backend does
not need it. When a real backend lands, add `manifest_path` to state +
`DeployRequest` schema in one go.

**Nodes:**

- `deploy`: imperative. Builds `DeploymentArtifact(voyage_id, tier,
  git_ref, git_sha)` from the state. Calls
  `deployment_backend.deploy(artifact)`. Stores `status`, `url`,
  `backend_log`, `error` on the state. Sets `diagnosis=None` up front so
  the END branch always has the key populated. Wraps the backend call in
  `try/except DeploymentError`: on `DeploymentError`, the node itself
  **does not raise** — it converts to `status="failed", url=None,
  backend_log=str(exc), error=exc.__class__.__name__` so the conditional
  edge routes to `diagnose` and the service's commit path still runs.
  The ABC contract says `deploy()` returns `status="failed"` on deploy
  failures, so `DeploymentError` is an internal-backend escape hatch
  only; the node handles it defensively.

- `diagnose`: LLM node. **Only runs on `status != "completed"`.** Builds
  a user message containing the `tier`, `git_ref`, `git_sha`, and the
  tail of `backend_log` (last 4000 chars — `backend_log[-TRUNCATE:]`).
  Calls `DialSystemRouter.route(CrewRole.HELMSMAN, CompletionRequest(...))`.
  Runs `strip_fences` + `json.loads` +
  `DeploymentDiagnosisSpec.model_validate` on the raw output. Stores
  `diagnosis = spec.model_dump()` on success. On any exception (LLM
  failure, JSON parse error, validation error), stores `diagnosis = None`
  and logs a warning — **never raise**. A diagnosis-fail must not mask
  the real deploy-fail response.

**System prompt** (constant `HELMSMAN_SYSTEM_PROMPT`):

```
You are a Helmsman — a DevOps agent responsible for diagnosing failed
deployments. You will receive the tier, git ref/SHA, and the last portion
of the backend's failure log. Produce a concise diagnosis that helps a
human operator decide what to do next.

Respond with ONLY a JSON object:
{"summary": "...", "likely_cause": "...", "suggested_action": "..."}

- summary: one sentence describing what went wrong
- likely_cause: the most probable root cause, based on the log
- suggested_action: one concrete next step the operator can take

Do not include any other text, markdown formatting, or explanation.
```

**Conditional routing:**

```python
def _route_after_deploy(state: HelmsmanState) -> str:
    return "diagnose" if state["status"] != "completed" else END
```

**Build function:**

```python
def build_helmsman_graph(
    dial_router: DialSystemRouter,
    deployment_backend: DeploymentBackend,
) -> CompiledStateGraph: ...
```

### 6. Events — add `DeploymentStartedEvent` + `DeploymentFailedEvent`

`DeploymentCompletedEvent` already exists in
`app/den_den_mushi/events.py` — **reuse it, do not redefine**.

Add two new event classes:

```python
class DeploymentStartedEvent(DenDenMushiEvent):
    event_type: Literal["deployment_started"] = "deployment_started"


class DeploymentFailedEvent(DenDenMushiEvent):
    event_type: Literal["deployment_failed"] = "deployment_failed"
```

Add both to the `AnyEvent` discriminated union.

### 7. HelmsmanService — `app/services/helmsman_service.py`

```python
TRUNCATE = 4000  # same constant Shipwright/Doctor use

DEFAULT_GIT_REF_BY_TIER: dict[str, Callable[[uuid.UUID], str]] = {
    "preview": lambda voyage_id: f"agent/shipwright/{voyage_id.hex[:8]}",
    "staging": lambda _voyage_id: "staging",
    "production": lambda _voyage_id: "main",
}


class HelmsmanError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class HelmsmanService:
    def __init__(
        self,
        dial_router: DialSystemRouter,
        mushi: DenDenMushi,
        session: AsyncSession,
        deployment_backend: DeploymentBackend,
        git_service: GitService | None = None,
    ) -> None:
        self._dial_router = dial_router
        self._mushi = mushi
        self._session = session
        self._backend = deployment_backend
        self._git = git_service
        self._graph = build_helmsman_graph(dial_router, deployment_backend)

    @classmethod
    def reader(cls, session: AsyncSession) -> HelmsmanService:
        inst = cls.__new__(cls)
        inst._session = session
        inst._dial_router = None   # type: ignore[assignment]
        inst._mushi = None         # type: ignore[assignment]
        inst._backend = None       # type: ignore[assignment]
        inst._git = None           # type: ignore[assignment]
        inst._graph = None         # type: ignore[assignment]
        return inst

    async def deploy(
        self,
        voyage: Voyage,
        tier: DeploymentTier,
        user_id: uuid.UUID,
        git_ref: str | None = None,
        approved_by: uuid.UUID | None = None,
    ) -> DeploymentResponse: ...

    async def rollback(
        self,
        voyage: Voyage,
        tier: DeploymentTier,
        user_id: uuid.UUID,
    ) -> DeploymentResponse: ...

    async def get_deployments(
        self,
        voyage_id: uuid.UUID,
        tier: DeploymentTier | None = None,
    ) -> list[Deployment]: ...

    async def get_latest_deployment(
        self,
        voyage_id: uuid.UUID,
        tier: DeploymentTier,
    ) -> Deployment | None: ...
```

**`_require_production_approval` helper (module-level or private method):**

```python
def _require_production_approval(
    tier: DeploymentTier,
    approved_by: uuid.UUID | None,
) -> None:
    if tier == "production" and approved_by is None:
        raise HelmsmanError(
            "APPROVAL_REQUIRED",
            "Production deploys require approved_by to be set",
        )
```

This is the single swap-point for Phase 17. Do not inline the check.

**`deploy` flow:**

1. `_require_production_approval(tier, approved_by)` — may raise.
   **Approval is checked BEFORE the status gate.** An unapproved
   production deploy against a non-CHARTED voyage therefore returns 403
   `APPROVAL_REQUIRED`, not 409 `VOYAGE_NOT_DEPLOYABLE`. This is
   intentional — approval is an authorization concern and should fail
   before any state-machine concern.
2. **Status gate**: if `voyage.status != VoyageStatus.CHARTED.value`,
   raise `HelmsmanError("VOYAGE_NOT_DEPLOYABLE", ...)`. (API maps this to
   409.)
3. Resolve `git_ref`: use the provided `git_ref` if set, else
   `DEFAULT_GIT_REF_BY_TIER[tier](voyage.id)`.
4. Resolve `git_sha`: if `self._git is not None` and
   `voyage.target_repo` is set, call
   `await self._git.get_head_sha(voyage.id, user_id, git_ref)`. On
   `GitError`, raise `HelmsmanError("GIT_REF_UNRESOLVABLE", ...)`.
   Otherwise `git_sha = None` (still allow the deploy — simulated
   backend doesn't need a SHA).
5. Transition `voyage.status = VoyageStatus.DEPLOYING.value`, flush.
6. Insert a `Deployment` row with
   `action="deploy", status="running", git_ref, git_sha,
   approved_by, previous_deployment_id=None`. Flush to get `deployment.id`.
7. Build initial graph state. Invoke `await self._graph.ainvoke(state)`.
8. Update the `Deployment` row with `status`, `url`, `backend_log`
   (truncated to `TRUNCATE`), `diagnosis`.
9. Create a `VivreCard` (`crew_member="helmsman"`,
   `state_data={"tier": tier, "action": "deploy", "status": status,
   "deployment_id": deployment.id, "git_sha": git_sha}`,
   `checkpoint_reason="deployment"`).
10. Restore `voyage.status = VoyageStatus.CHARTED.value`.
11. `await session.commit()`, refresh rows.
12. **Best-effort event publish** (in this order):
    - `DeploymentStartedEvent(voyage_id, source_role=CrewRole.HELMSMAN,
      payload={"tier": tier, "deployment_id": str(deployment.id),
      "git_ref": git_ref, "git_sha": git_sha})`
    - On `status=="completed"`:
      `DeploymentCompletedEvent(voyage_id, source_role=CrewRole.HELMSMAN,
      payload={"tier": tier, "deployment_id": str(deployment.id),
      "url": url})`
    - On `status=="failed"`:
      `DeploymentFailedEvent(voyage_id, source_role=CrewRole.HELMSMAN,
      payload={"tier": tier, "deployment_id": str(deployment.id),
      "diagnosis": diagnosis})`
    Each publish in its own try/except — one failure must not prevent the
    others. Never raise from the publish block.
13. If `status == "failed"`, raise `HelmsmanError("DEPLOYMENT_FAILED",
    diagnosis.get("summary") if diagnosis else "Deployment failed")`
    **after** the commit + events, so the row + events are persisted
    before the API returns 422.
14. Otherwise, return `DeploymentResponse(...)`.

Any exception during steps 2-11 must reset `voyage.status = CHARTED.value`
and flush before re-raising, so a client retry sees a clean state.

**`rollback` flow:**

1. **Status gate**: if `voyage.status != VoyageStatus.CHARTED.value`,
   raise `HelmsmanError("VOYAGE_NOT_DEPLOYABLE", ...)` → 409.
2. Find the previous deployment to roll back to:
   `SELECT * FROM deployments WHERE voyage_id = :v AND tier = :t
   AND status = 'completed' AND action = 'deploy'
   ORDER BY created_at DESC LIMIT 1`.
3. If none → raise `HelmsmanError("NO_PREVIOUS_DEPLOYMENT", ...)` → 404
   at API layer.
4. Transition to `DEPLOYING`, flush.
5. Insert a `Deployment` row with `action="rollback", status="running",
   git_ref=<prev.git_ref>, git_sha=<prev.git_sha>,
   previous_deployment_id=prev.id, approved_by=None`.
6. Invoke the graph with the previous deployment's `git_ref`/`git_sha`.
7. Same update/checkpoint/commit/publish flow as `deploy` — events use
   `action="rollback"` in the payload. If the rollback itself fails,
   raise `HelmsmanError("DEPLOYMENT_FAILED", ...)` after commit + events.
8. Return `DeploymentResponse`.

Rollback does **not** require `approved_by` in v1 — rollbacks are an
emergency mechanism. (Log as a known limitation in decisions.md —
Phase 17 can gate rollbacks later.)

**`get_deployments` flow:**

- `SELECT * FROM deployments WHERE voyage_id = :v`.
- If `tier is not None`, add `AND tier = :t`.
- Return ordered by `created_at DESC`.

**`get_latest_deployment` flow:**

- `SELECT * FROM deployments WHERE voyage_id = :v AND tier = :t
  ORDER BY created_at DESC LIMIT 1`.

### 8. GitService — add `get_head_sha`

Add a small method to `app.services.git_service.GitService` (if it does
not already exist — **check `git_service.py` first**, and if a helper
with the same intent exists under a different name, reuse that and skip
this deliverable).

```python
async def get_head_sha(
    self,
    voyage_id: uuid.UUID,
    user_id: uuid.UUID,
    ref: str,
) -> str:
    """Resolve a branch/tag/SHA-ish to a full commit SHA for audit.
    Raises GitError if the ref cannot be resolved."""
    _validate_branch_component(ref)
    sandbox_id = self._get_sandbox(voyage_id)
    stdout = await self._run(
        sandbox_id,
        f"cd {REPO_PATH} && git rev-parse {shlex.quote(ref)}^{{commit}}",
    )
    sha = stdout.strip()
    if not sha:
        raise GitError(f"GIT_REF_UNRESOLVABLE: {ref!r}")
    return sha
```

Unit test: extend `tests/test_git_service.py` with two cases — resolves
a branch to a 40-char SHA; raises `GitError` when the ref doesn't
exist. Mock the `ExecutionBackend` response.

### 9. REST API — `app/api/v1/helmsman.py`

Router with prefix `/voyages/{voyage_id}`, tag `helmsman`.

| Method | Path | Handler | Response |
|--------|------|---------|----------|
| POST | `/deploy` | `deploy_voyage` | 201 → `DeploymentResponse` |
| POST | `/rollback` | `rollback_voyage` | 201 → `DeploymentResponse` |
| GET  | `/deployments` | `list_deployments` | 200 → `DeploymentListResponse` |

**POST `/deploy` body**: `DeployRequest`. Response: 201 on success.
Error mapping:

| `HelmsmanError.code` | HTTP status |
|----------------------|-------------|
| `APPROVAL_REQUIRED` | 403 |
| `VOYAGE_NOT_DEPLOYABLE` | 409 |
| `GIT_REF_UNRESOLVABLE` | 422 |
| `DEPLOYMENT_FAILED` | 422 |
| `UNKNOWN_TIER` | 422 |
| (anything else) | 422 |

Error body: `{"error": {"code": exc.code, "message": exc.message}}`.

**POST `/rollback` body**: `RollbackRequest`. Same status mapping
plus:

| `HelmsmanError.code` | HTTP status |
|----------------------|-------------|
| `NO_PREVIOUS_DEPLOYMENT` | 404 |

**GET `/deployments`**: optional query param `tier: DeploymentTier | None
= None`. Returns `DeploymentListResponse` (empty list OK). Uses
`get_helmsman_reader` (session-only).

**Dependencies:**

```python
def get_deployment_backend(request: Request) -> DeploymentBackend:
    return request.app.state.deployment_backend


async def get_helmsman_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
    deployment_backend: DeploymentBackend = Depends(get_deployment_backend),
    git_service: GitService = Depends(get_git_service),
) -> HelmsmanService:
    return HelmsmanService(
        dial_router, mushi, session,
        deployment_backend=deployment_backend,
        git_service=git_service,
    )


async def get_helmsman_reader(
    session: AsyncSession = Depends(get_db),
) -> HelmsmanService:
    return HelmsmanService.reader(session)
```

Put `get_deployment_backend` in `app/api/v1/dependencies.py` alongside
the other `get_*` helpers.

### 10. Wiring

- Register `Deployment` import in `app/models/__init__.py`.
- Add `helmsman.router` include in `app/api/v1/router.py`.
- In `app/main.py` lifespan — instantiate `InProcessDeploymentBackend()`
  and store at `app.state.deployment_backend = InProcessDeploymentBackend()`.
  On shutdown, `await app.state.deployment_backend.close()` (added
  **before** the existing backend cleanup, in reverse creation order so
  resources tear down cleanly).
- Add `DeploymentStartedEvent` + `DeploymentFailedEvent` to
  `app/den_den_mushi/events.py` and the `AnyEvent` union.

## Test Plan

All tests use mocked dependencies (no real LLM, DB, sandbox, or git).
Use `InProcessDeploymentBackend` directly for backend-layer tests — no
need to mock the ABC.

### Model/Migration Tests — extend `tests/test_models.py`

1. `deployments` appears in `Base.metadata.tables`.
2. `test_deployment_table_columns` — full column set matches.
3. `test_deployment_voyage_tier_created_indexed` — composite index exists.
4. `test_deployment_action_column_values` — only `deploy` / `rollback`
   are valid string values at the application layer (schema-enforced,
   not DB-enforced).

### Schema Tests — `tests/test_helmsman_schemas.py`

1. `DeployRequest` accepts `tier="preview"` with no `git_ref`.
2. `DeployRequest` accepts explicit `git_ref`.
3. `DeployRequest` rejects `tier="invalid"`.
4. `DeployRequest` accepts `approved_by` as a UUID.
5. `DeployRequest` accepts `approved_by=None`.
6. `RollbackRequest` requires `tier`.
7. `DeploymentDiagnosisSpec` accepts valid shape.
8. `DeploymentDiagnosisSpec` rejects empty `summary`.
9. `DeploymentResponse` accepts `status="failed"` with `url=None`.
10. `DeploymentResponse` rejects `status="other"`.

### Backend ABC Tests — `tests/test_deployment_backend.py`

1. `InProcessDeploymentBackend.deploy` returns `status="completed"` with
   a synthetic URL by default.
2. `InProcessDeploymentBackend.deploy` returns `status="failed"` when
   tier is in `fail_tiers`.
3. `InProcessDeploymentBackend.status` returns the last deploy result for
   a `(voyage, tier)` pair.
4. `InProcessDeploymentBackend.status` returns `None` when no deploy has
   happened for that `(voyage, tier)`.
5. `deploy` stores per-`(voyage, tier)` records — two different voyages
   deploying to `preview` don't overwrite each other.
6. `deploy` overwrites the record when the same `(voyage, tier)` is
   re-deployed.
7. `backend_log` contains the tier, git_ref, git_sha, and (on success)
   the URL.

### Graph Tests — `tests/test_helmsman_graph.py`

1. `deploy` node sends `DeploymentArtifact` built from state to the
   backend.
2. `deploy` node stores `status`, `url`, `backend_log`, `error` on
   state.
3. `deploy` node sets `diagnosis=None` on state so END sees the key.
4. `diagnose` node is **not invoked** when `status == "completed"` —
   assert the conditional routes to END.
5. `diagnose` node **is** invoked when `status == "failed"`.
6. `diagnose` node sends `CrewRole.HELMSMAN` to the dial router.
7. `diagnose` node includes the tail of `backend_log` (last 4000 chars)
   in the user message.
8. `diagnose` node stores `diagnosis` dict on valid JSON output.
9. `diagnose` node stores `diagnosis=None` and logs a warning on
   malformed JSON — **does not raise**.
10. `diagnose` node stores `diagnosis=None` and logs a warning when the
    LLM call itself raises — **does not raise**.
11. `diagnose` node strips ```json fences.
12. Full graph returns a full state dict with both nodes' outputs on
    failure path.
13. Full graph returns a state dict with only `deploy` node's outputs on
    success path (plus `diagnosis=None`).
14. `deploy` node converts `DeploymentError` raised by the backend into
    `status="failed"` state (does not propagate the exception). Assert
    `state["backend_log"]` contains the exception message and
    `state["error"]` is set.

### Service Tests — `tests/test_helmsman_service.py`

Fixtures: mock session (`.add`, `.flush`, `.commit`, `.execute`,
`.refresh`), mock dial_router, mock mushi, mock git_service (optional),
real `InProcessDeploymentBackend`, mock graph `.ainvoke` that returns a
preset state. `_mock_voyage(status="CHARTED", target_repo=...)` helper.

**`deploy` — happy path (preview):**

1. Sets voyage status to `DEPLOYING` during the call.
2. Resolves `git_ref = "agent/shipwright/<hex>"` when none provided.
3. Calls `git_service.get_head_sha` when `voyage.target_repo` is set.
4. Skips `get_head_sha` and stores `git_sha=None` when `git_service` is
   `None`.
5. Skips `get_head_sha` and stores `git_sha=None` when `voyage.target_repo`
   is unset.
6. Invokes the graph once with a complete state dict.
7. Persists one `Deployment` row with `action="deploy", status="completed",
   url` populated.
8. Creates a `VivreCard` with `checkpoint_reason="deployment"`.
9. Calls `session.commit()` exactly once.
10. Restores voyage status to `CHARTED`.
11. Publishes `DeploymentStartedEvent` then `DeploymentCompletedEvent`.
12. Does **not** publish `DeploymentFailedEvent` on success.
13. Succeeds when `mushi.publish` raises (best-effort).

**`deploy` — production approval:**

14. Raises `HelmsmanError("APPROVAL_REQUIRED")` when
    `tier="production"` and `approved_by is None`. Voyage status
    **unchanged** (CHARTED) — the check happens before any state
    transition. No graph invocation. No Deployment row inserted.
15. Succeeds when `tier="production"` with `approved_by=<uuid>` set, and
    persists `approved_by` on the Deployment row.
16. `tier="preview"` or `tier="staging"` does **not** require
    `approved_by` (approval check is a no-op).

**`deploy` — status gate:**

17. Raises `HelmsmanError("VOYAGE_NOT_DEPLOYABLE")` when
    `voyage.status == "DEPLOYING"` (already in flight). No graph
    invocation.
18. Raises `HelmsmanError("VOYAGE_NOT_DEPLOYABLE")` when
    `voyage.status == "FAILED"`.

**`deploy` — failure path:**

19. When the graph returns `status="failed"`, raises
    `HelmsmanError("DEPLOYMENT_FAILED")` **after** committing.
20. On failure, the `Deployment` row is still persisted with
    `status="failed"` and `diagnosis` stored.
21. On failure, publishes `DeploymentStartedEvent` and
    `DeploymentFailedEvent` (not Completed) in that order.
22. On failure, voyage status is restored to `CHARTED`.
23. On failure, a `VivreCard` is still written.

**`deploy` — git failure:**

24. When `git_service.get_head_sha` raises `GitError`, the service
    raises `HelmsmanError("GIT_REF_UNRESOLVABLE")`, voyage status is
    restored to `CHARTED`, no Deployment row is persisted, no graph
    invocation.

**`rollback` — happy path:**

25. Finds the most recent `status=completed action=deploy` row for
    `(voyage, tier)` and uses its `git_ref`/`git_sha`.
26. Persists a new `Deployment` row with `action="rollback"`,
    `previous_deployment_id` pointing to the found row.
27. Publishes `DeploymentStartedEvent` + `DeploymentCompletedEvent` on
    rollback success.
28. Restores voyage status to `CHARTED`.

**`rollback` — no previous deployment:**

29. Raises `HelmsmanError("NO_PREVIOUS_DEPLOYMENT")` when no prior
    `status=completed action=deploy` row exists. Voyage status
    unchanged. No graph invocation. No Deployment row inserted.

**`rollback` — status gate:**

30. Raises `HelmsmanError("VOYAGE_NOT_DEPLOYABLE")` when
    `voyage.status != "CHARTED"`.

**`get_deployments` / `get_latest_deployment`:**

31. `get_deployments` returns rows ordered by `created_at DESC`.
32. `get_deployments` filters by `tier` when supplied.
33. `get_deployments` returns empty list when none.
34. `get_latest_deployment` returns the most recent row.
35. `get_latest_deployment` returns `None` when no row exists.
36. Reader instance (`HelmsmanService.reader(session)`) can call both
    query methods.

**`_require_production_approval` helper:**

37. No-op when `tier="preview"` and `approved_by=None`.
38. No-op when `tier="staging"` and `approved_by=None`.
39. No-op when `tier="production"` and `approved_by=<uuid>`.
40. Raises `HelmsmanError("APPROVAL_REQUIRED")` when `tier="production"`
    and `approved_by=None`.

### API Tests — `tests/test_helmsman_api.py`

1. POST `/deploy` returns 201 with `DeploymentResponse` (preview).
2. POST `/deploy` returns 409 `VOYAGE_NOT_DEPLOYABLE` when voyage not
   `CHARTED`.
3. POST `/deploy` returns 403 `APPROVAL_REQUIRED` for production without
   `approved_by`; asserts `deploy` was **not** awaited (fail-fast at
   service entry is fine — just assert the error code + status).
4. POST `/deploy` returns **403** (not 409) for a production deploy
   with no `approved_by` against a voyage whose status is not CHARTED —
   approval precedence test.
5. POST `/deploy` returns 201 for production with `approved_by` set.
6. POST `/deploy` returns 422 `DEPLOYMENT_FAILED` when the backend fails
   (use `InProcessDeploymentBackend(fail_tiers={"preview"})`).
7. POST `/deploy` returns 422 `GIT_REF_UNRESOLVABLE` when git resolution
   fails.
8. POST `/rollback` returns 201 with `DeploymentResponse`.
9. POST `/rollback` returns 404 `NO_PREVIOUS_DEPLOYMENT` when no prior
   deploy exists.
10. POST `/rollback` returns 409 `VOYAGE_NOT_DEPLOYABLE` when voyage not
    `CHARTED`.
11. GET `/deployments` returns 200 with list.
12. GET `/deployments?tier=preview` filters by tier.
13. GET `/deployments` returns 200 with empty list.

## Constraints

- Mock every external: no real LLM, no real DB, no real cluster. The
  `InProcessDeploymentBackend` is a real class used in tests — no
  mocking needed for it.
- **v1 backend is simulated.** Real Docker/k8s backends slot in behind
  the same `DeploymentBackend` ABC later. Do not add Docker/k8s code
  paths in this PR.
- Graph is a thin orchestrator: `deploy` (imperative) →
  conditional → `diagnose` (LLM, best-effort). Zero LLM calls on
  success. Graph nodes have **no DB writes**.
- Follow Navigator/Doctor/Shipwright patterns exactly: `strip_fences`
  from `app/crew/utils.py`, `reader()` factory, atomic DB commit before
  events, best-effort publish, `TRUNCATE = 4000` for `backend_log`.
- **Approval gate is encapsulated.** The `_require_production_approval`
  helper is the single swap-point for Phase 17. Do not inline the
  `tier == "production"` check anywhere else.
- **Status lifecycle** — transient `DEPLOYING`, restored to `CHARTED` on
  both success and failure paths, **including** all error exits
  (approval failure exits before the transition; all others must reset).
  v1 serializes deploys per voyage via this gate — the `voyage.status !=
  CHARTED` 409 check blocks concurrent deploys across tiers. True
  per-tier concurrency waits for a future `deployment_status` refactor.
- **Git is audit-only.** Helmsman calls `GitService.get_head_sha(...)`
  to resolve `git_ref → git_sha` for the Deployment row. No branch
  creation, no merges, no commits. If `voyage.target_repo` is unset or
  `git_service` is `None`, `git_sha=None` is acceptable.
- **Rollback = find-previous-completed-deploy-and-redeploy.** One
  `deployments` table with an `action` column. Rollback rows reference
  the target via `previous_deployment_id` for audit.
- **Diagnosis is best-effort.** If the LLM call or JSON parse fails,
  persist `diagnosis=None` and log a warning. The deploy-fail response
  still returns 422 with whatever diagnosis is available. A
  diagnosis-fail must NEVER mask the real deploy-fail response.
- **Events are best-effort.** Each publish in its own try/except. One
  failure must not block the others.
- `Deployment.backend_log` is truncated to the last 4000 chars before
  persistence. `Deployment.diagnosis` is stored as JSONB (nullable).
- `HelmsmanError.code` → HTTP mapping is non-negotiable:
  `APPROVAL_REQUIRED` → 403, `VOYAGE_NOT_DEPLOYABLE` → 409,
  `NO_PREVIOUS_DEPLOYMENT` → 404, everything else → 422.
- **404 vs 422**: 404 for missing prerequisite resources (no prior
  deployment on rollback). 422 for service-layer invariant violations
  (`DEPLOYMENT_FAILED`, `GIT_REF_UNRESOLVABLE`, `UNKNOWN_TIER`). 403
  specifically for the approval gate. 409 specifically for the voyage
  status gate.
- **GitService.get_head_sha** — check if it (or an equivalent helper)
  already exists in `git_service.py` before adding. If it exists under
  another name, reuse it.
- **Production approval in v1 is trust-the-caller.** `approved_by: UUID`
  is not cross-checked against a separate approval record. This is a
  known limitation; Phase 17 replaces it. Log in `decisions.md`.
- **Rollback does not require approval in v1.** Rollbacks are an
  emergency mechanism. Log this as a known limitation.
- Single Dial System call per deploy, **only on failure**. Zero LLM
  calls on success.
- Wire `InProcessDeploymentBackend` via `app.main.py` lifespan matching
  the `ExecutionBackend` pattern exactly. Cleanup in reverse order.
