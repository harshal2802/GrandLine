# Implementation Plan: Helmsman Agent (Phase 14)

**Created**: 2026-04-17
**Issue**: #15
**Complexity**: Medium — imperative orchestration over real (simulated) infra, new approval gate, rollback semantics, but only ONE LLM call (failure diagnosis). Less novel than Shipwright's iteration loop.
**Estimated prompts**: 1 (single PDD prompt, matching crew precedent)

## Summary

The Helmsman is a **voyage-scoped DevOps agent**. One invocation takes a voyage + a deployment tier (`preview` | `staging` | `production`) and triggers a deploy via a swappable `DeploymentBackend`. The v1 backend is a **simulated in-process backend** — no real Docker/k8s yet, which lets us ship the agent and let Phase 15's pipeline wire it in as the `DEPLOYING` state without requiring cluster infrastructure. A future phase slots in a real backend behind the same interface.

Unlike Shipwright (iterative LLM loop) and Doctor (LLM generation + sandbox exec), Helmsman is mostly **imperative**: it reads repo infra files, calls the backend, records a `Deployment` row. The only LLM call is optional **failure diagnosis** — when a deploy fails, the Helmsman asks the Dial System (`CrewRole.HELMSMAN`) to summarize the error logs into a structured `DeploymentDiagnosis` for the Observation Deck. On success, no LLM call.

Three tiers with increasing gates:
- **Preview** — deploys from `agent/shipwright/<voyage-id>` branch, auto, no approval.
- **Staging** — deploys from `staging` branch, auto.
- **Production** — deploys from `main`, requires explicit `approved_by=user_id` in the request. No approval → 403 `APPROVAL_REQUIRED`. (Phase 17 User Intervention later replaces this flag with a full workflow.)

Rollback is a separate explicit action: `POST /voyages/{id}/rollback?tier=<tier>` finds the previous `status=completed` Deployment for that `(voyage, tier)` and redeploys its stored git ref.

Same three-layer crew pattern (`graph → service → API` with `reader()` factory), atomic DB commit before best-effort events, best-effort LLM diagnosis on failure.

## Phases

### Phase 1 (single prompt): Helmsman Agent end-to-end

**Produces**:
- `alembic/versions/<rev>_deployment.py` — migration adding the `deployments` table
- `app/models/deployment.py` — `Deployment` SQLAlchemy model (one row per deploy/rollback action)
- `app/schemas/deployment.py` — Pydantic schemas: `DeploymentTier` enum, `DeploymentStatus` enum, `DeployRequest`, `RollbackRequest`, `DeploymentResponse`, `DeploymentRead`, `DeploymentListResponse`, `DeploymentDiagnosisSpec`
- `app/deployment/backend.py` — `DeploymentBackend` ABC + `DeploymentArtifact`/`DeploymentResult` dataclasses (mirrors `app/execution/backend.py`)
- `app/deployment/in_process.py` — `InProcessDeploymentBackend` (simulated; records deploys to a dict keyed by `(voyage_id, tier)`, returns synthetic URLs like `http://preview.voyage-<hex>.local`)
- `app/crew/helmsman_graph.py` — LangGraph graph with nodes: `deploy` (imperative) → conditional → `diagnose` (LLM, on failure only) → `END`
- `app/services/helmsman_service.py` — `HelmsmanService` with `deploy(voyage, tier, git_ref, user_id, approved_by=None)`, `rollback(voyage, tier, user_id)`, `get_deployments(voyage_id, tier=None)`, `get_latest_deployment(voyage_id, tier)`, and `reader(session)` classmethod
- `app/api/v1/helmsman.py` — `POST /voyages/{id}/deploy`, `POST /voyages/{id}/rollback`, `GET /voyages/{id}/deployments`
- `app/den_den_mushi/events.py` — add `DeploymentStartedEvent`, `DeploymentFailedEvent` (note: `DeploymentCompletedEvent` already exists; verify and reuse)
- `app/api/v1/router.py` — include the new router
- `app/main.py` — instantiate `InProcessDeploymentBackend` in lifespan, register via `app.state.deployment_backend` + `get_deployment_backend` dependency
- Tests: `tests/test_helmsman_schemas.py`, `tests/test_helmsman_graph.py`, `tests/test_helmsman_service.py`, `tests/test_helmsman_api.py`, `tests/test_deployment_backend.py`, `tests/test_models.py` (extended)

**Depends on**:
- `GitService` — used *lightly* to resolve a git SHA for the requested ref (for auditability); optional if `target_repo` is unset
- `DialSystemRouter` — only for the `diagnose` node, only on failure
- `DenDenMushi` — event publishing

**Risk**: Medium — new `DeploymentBackend` abstraction + approval gate are novel. Rollback semantics (find-previous-completed-and-redeploy) are new. But the graph itself is trivial compared to Shipwright's loop.

**Prompt**: `pdd/prompts/features/crew/grandline-14-helmsman.md`

## Key design decisions (proposed — please confirm before prompt)

### (a) What does "deploy" DO in v1? — Simulated backend behind a swappable ABC

**Decision**: Ship v1 with an `InProcessDeploymentBackend` that simulates deployments. Same pattern as `ExecutionBackend` (swappable, ABC-first). The backend records deploys keyed by `(voyage_id, tier)`, generates a synthetic URL, and can simulate failures for testing via a config flag. Real `DockerDeploymentBackend` / `KubernetesDeploymentBackend` slot in later without changing the service layer.

**Why**: Shipping the agent without a cluster. Phase 15 Pipeline can wire the Helmsman in as `DEPLOYING` immediately. Decouples "the agent logic is correct" from "the cluster is set up."

**Log in decisions.md**: _"Helmsman v1 uses a simulated DeploymentBackend; real backends are follow-up work behind the same ABC."_

### (b) Where does tier config live? — Global defaults, no per-voyage override in v1

**Decision**: v1 has hardcoded defaults for each tier (backend selection, URL format) in a `DEPLOYMENT_DEFAULTS` constant in `app/deployment/config.py`. No per-voyage override. Follow-up phase can add a JSONB `deployment_config` column on `Voyage` if users ask for per-voyage targets.

**Why**: Config surface area has a cost. The simulated backend doesn't need real config. Defer real config until a real backend demands it.

### (c) Rollback target storage — `Deployment` table, append-only history

**Decision**: One `Deployment` row per deploy or rollback action. Columns: `id`, `voyage_id`, `tier`, `action` (`deploy` | `rollback`), `git_ref`, `git_sha` (resolved), `status` (`awaiting_approval` | `running` | `completed` | `failed`), `approved_by` (UUID or null), `url` (synthetic in v1), `backend_log` (Text, truncated), `diagnosis` (JSONB, null on success), `previous_deployment_id` (FK for rollbacks), `created_at`, `updated_at`. Indexed on `(voyage_id, tier, created_at DESC)`.

**Why**: Full audit trail. Rollback works by finding the previous `status=completed action=deploy` for the same `(voyage, tier)` and deploying its `git_sha`. Matches the `ValidationRun` / `ShipwrightRun` pattern.

### (d) Production approval gate — explicit `approved_by` field, no separate endpoint in v1

**Decision**: `DeployRequest` includes optional `approved_by: UUID | None`. If `tier == production` and `approved_by` is null or doesn't match a valid user, the service raises `HelmsmanError("APPROVAL_REQUIRED")` → API returns 403. Preview/staging ignore `approved_by`. Phase 17 (User Intervention) later replaces this with a proper workflow (approval request → UI prompt → approval event).

**Why**: Minimum viable approval. Doesn't block Phase 15 Pipeline from integrating. Client-side orchestration (CLI or UI) collects user confirmation and passes `approved_by=user_id`. The field is persisted on `Deployment` for audit.

**Log in decisions.md**: _"Helmsman v1 uses an explicit `approved_by` field on DeployRequest as the production approval gate. Phase 17 replaces with a full intervention workflow."_

### (e) Inputs to Helmsman — `voyage + tier + user_id` (+ optional `approved_by` for prod, optional `git_ref` override)

**Decision**: The service resolves `git_ref` from the tier by default:
- `preview` → `agent/shipwright/<voyage-id>`
- `staging` → `staging`
- `production` → `main`

Caller can override with an explicit `git_ref` in the request (useful for Phase 15 Pipeline which may want to deploy a specific SHA). `git_sha` is resolved from `git_ref` via `GitService.get_head_sha(...)` if `target_repo` is set; otherwise stored as null.

**Why**: Sensible defaults, explicit override. The service doesn't take `BuildArtifacts` directly — git is the source of truth, and the artifacts are already committed.

### (f) Infrastructure files — consume pre-existing, no LLM generation

**Decision**: v1 assumes the repo contains deployment-ready infra (Dockerfile or `docker-compose.yml` at repo root). The Helmsman reads a manifest hint (e.g., `Dockerfile` path) and passes it to the backend. No LLM-generated Dockerfiles in v1. The simulated backend accepts the file path as a string and records it without parsing.

**Why**: Keeps v1 scope tight. LLM-generated infra is a meaningful feature but deserves its own PDD cycle.

### (g) Git interaction — `get_head_sha` only, no merge orchestration

**Decision**: Helmsman calls `GitService.get_head_sha(voyage_id, user_id, branch)` (we'll need to ADD this if missing — check first) to resolve the git ref to a SHA for auditability. No branch creation, no merging. External orchestration (Phase 15 Pipeline) handles git flow between tiers.

**Why**: Separation of concerns. Helmsman's job is "deploy what you're told to deploy," not "manage the git flow." Matches how real-world deployers work — CI pipelines stage the code, the deployer takes it from there.

### (h) Iteration / retry — single-shot, explicit rollback is a separate action

**Decision**: Deploy is single-shot. On failure, the `diagnose` node runs (one LLM call), persists the diagnosis, publishes `DeploymentFailedEvent`, and the request returns `status=failed`. Retry is the caller's responsibility (re-POST `/deploy`). Rollback is a separate endpoint that targets the previous completed deployment.

**Why**: Deploy failures usually need human inspection (cluster state, credentials, etc.) — retrying blindly is often wrong. Rollback is the first-class safety mechanism, not retry.

### Graph shape

Two nodes, one conditional edge:

```
START → deploy → [success? END : diagnose → END]
```

- `deploy` — imperative node. Calls `DeploymentBackend.deploy(request) -> DeploymentResult`. Returns `{status, url, backend_log, error}` in graph state. No LLM call.
- `diagnose` — LLM node. Only runs on `status != "completed"`. Calls `DialSystemRouter.route(CrewRole.HELMSMAN, ...)` with `backend_log` and asks for a structured `DeploymentDiagnosisSpec` (`summary: str`, `likely_cause: str`, `suggested_action: str`). Best-effort — if the LLM call itself fails, store `diagnosis=None` and log a warning. Never fails the deploy request purely because diagnosis failed.

### State shape (TypedDict)

```python
class HelmsmanState(TypedDict):
    voyage_id: uuid.UUID
    user_id: uuid.UUID
    tier: Literal["preview", "staging", "production"]
    git_ref: str
    git_sha: str | None
    deployment_id: uuid.UUID
    manifest_path: str | None
    # filled by deploy node:
    status: Literal["completed", "failed"]
    url: str | None
    backend_log: str
    error: str | None
    # filled by diagnose node:
    diagnosis: dict[str, Any] | None
```

### `HelmsmanError` codes

- `APPROVAL_REQUIRED` — production deploy without valid `approved_by` → 403
- `UNKNOWN_TIER` → 422 (shouldn't happen if Pydantic validates)
- `NO_PREVIOUS_DEPLOYMENT` — rollback requested but no prior completed deploy → 404
- `DEPLOYMENT_FAILED` → 422, carries the diagnosis summary
- `GIT_REF_UNRESOLVABLE` → 422, when `get_head_sha` fails

### Status lifecycle on Voyage

Voyage moves `CHARTED → DEPLOYING` during the call, restores to `CHARTED` on both success and failure. Preserves re-invocation. (Note: for rollback, also transition through `DEPLOYING`.) On production deploy success we might eventually transition to `COMPLETED`, but leave that orchestration to Phase 15 — v1 always restores to `CHARTED`.

### Atomic commit + best-effort side effects

Same pattern as Shipwright/Doctor:
1. `status=running` Deployment row inserted, flushed
2. Backend call executes
3. Row updated with final status, url, backend_log, diagnosis
4. Voyage status restored
5. `session.commit()`
6. _Best-effort_ `DeploymentStartedEvent` + (`DeploymentCompletedEvent` | `DeploymentFailedEvent`) published

`DeploymentStartedEvent` is emitted just before step 2 via a nested `session.begin_nested()` commit OR (simpler) emitted alongside the terminal event after the main commit. **Proposed**: emit both events alongside the final commit, in start→terminal order. The "started" event in a post-commit publish is still useful to the Observation Deck for timeline purposes.

## Risks & Unknowns

- **GitService may lack `get_head_sha`.** If so, the prompt adds it (small, non-invasive — `git rev-parse HEAD` in the sandbox). Check existing git_service.py first; if the helper exists under a different name, use that.
- **Approval field is trust-the-caller.** The `approved_by` UUID is not verified against a separate approval record in v1. A malicious/buggy client could pass any UUID. Phase 17 fixes this with a signed approval token + workflow. **Log as a known limitation in decisions.md.**
- **Rollback on tier with only one deployment.** No previous completed deploy → 404 `NO_PREVIOUS_DEPLOYMENT`. Correct behavior; the test matrix includes this.
- **Concurrent deploy requests to same tier.** Two clients deploy to `preview` simultaneously — last write wins at the `deployments` table (both rows persisted), but the backend's state is racy. v1 accepts this; the `voyage.status = DEPLOYING` gate provides some protection but only cross-tier (since one voyage can't be DEPLOYING in two tiers simultaneously without the gate rejecting the second). **Propose**: enforce voyage-level serialization via the `voyage.status != CHARTED` 409 check, same as Shipwright. Cross-tier concurrent deploys are deferred until a `per-tier status` refactor. **Log in decisions.md.**
- **LLM diagnosis latency on failure.** Adds an LLM round-trip to the error path. Acceptable — failure diagnosis is valuable. Wrapped in try/except so a diagnosis-fail doesn't mask the real deploy-fail response.
- **Token bloat in `backend_log`.** Trunc to last 4000 chars (same constant Shipwright uses) before sending to LLM and before persisting.

## Decisions Locked (confirmed 2026-04-17)

1. ✅ **Simulated v1 backend** behind `DeploymentBackend` ABC. Modular so `DockerDeploymentBackend`/`KubernetesDeploymentBackend` slot in later without changing service code.
2. ✅ **Approval via `approved_by: UUID` field** on `DeployRequest`. Check encapsulated in a single `_require_production_approval(tier, approved_by)` helper so Phase 17 replaces it by swapping that one function.
3. ✅ **No git merge orchestration in Helmsman** — caller provides `git_ref`; service only resolves `git_ref → git_sha` for audit.
4. ✅ **Single `Deployment` table** with `action` column (`deploy` | `rollback`).
5. ✅ **Voyage-level status gate** — `voyage.status == CHARTED` required; transitions to `DEPLOYING` during call, restores to `CHARTED` on both success and failure. 409 if already `DEPLOYING`.
6. ✅ **LLM diagnosis on failure only** — `deploy → (if fail) diagnose → END`. Zero LLM calls on success. Diagnosis wrapped in best-effort try/except.

## Scope cuts proposed (all logged in decisions.md if confirmed)

- No real cluster deploy in v1 (simulated backend)
- No per-voyage config overrides (hardcoded defaults)
- No approval workflow endpoint (simple `approved_by` field)
- No git merge orchestration (caller provides git_ref)
- No LLM-generated infrastructure files
- No retry loop (single-shot, explicit rollback)
- No cross-tier concurrency (one deploy-in-flight per voyage)

## Next step

Once you confirm the six decisions above (or redirect any of them), I'll run `/pdd-skill:pdd-prompts` to produce `pdd/prompts/features/crew/grandline-14-helmsman.md` and we start implementing TDD-first.
