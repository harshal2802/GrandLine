# Prompt: The Cabin — per-user persistent sandbox container (Phase 0b)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-0b-cabin.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Auth (Phase 4 — `get_current_user`, default-deny middleware), the
`User` model, `Settings` (`GRANDLINE_` env prefix), the **Sea Chest** (Phase 0a —
`SeaChestService(session, settings).reveal(user_id, kind)`), and the established
swappable-backend pattern (`ExecutionBackend`/`DeploymentBackend`/
`BrowserCheckBackend`). `aiodocker` is in `requirements.txt` but MUST stay a LAZY
import (never module-top) so app startup and the test suite never need Docker.

**Project type**: Backend (FastAPI + Pydantic v2 + SQLAlchemy async)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. Phase 0
is the keystone foundation for the deck-capabilities epic: a **Cabin** (per-user
container) + a **Sea Chest** (per-user credential vault). The Sea Chest (Phase 0a)
is built — it stores secrets encrypted at rest and reveals them INTERNALLY. This
phase, **0b**, builds the runtime half: the **Cabin**.

In One Piece a cabin is a crew member's own quarters aboard the ship. Here it is a
**persistent, per-user, isolated container** that holds the user's credentials
(materialized from the Sea Chest) and will later run their workloads — C0
device-login Claude Code, A3 git ops, B0–B3 preview + interactive terminal. This
phase delivers ONLY the substrate: Cabin **lifecycle + secret materialization +
idle reaper** behind a swappable backend. It does NOT build the preview/terminal
(B0–B3) or the credential-capture UI (C0/A3).

PLAN reference: PLAN-deck-capabilities.md, Phase 0 = Cabin + Sea Chest. This is the
**Cabin** half; the Sea Chest is the sibling (already built).

## Locked design decisions

- **Persistent, per-user.** ONE Cabin per user, reused across voyages (not
  per-voyage, not one-shot like the Execution sandbox). This is the evolution of
  `ExecutionService._sandboxes` from ephemeral to long-lived.
- **Idle reaper + hard max lifetime.** A background task destroys Cabins idle past
  `cabin_idle_timeout_seconds` OR older than `cabin_max_lifetime_seconds`. A Cabin
  must never outlive its need.
- **Swappable backend, Null default.** Mirror the
  `ExecutionBackend`/`DeploymentBackend`/`BrowserCheckBackend` seam: a
  deterministic, container-free **`NullCabinBackend` is the CI-safe default**; the
  real **`GVisorCabinBackend`** is opt-in and lazily imports `aiodocker`.
- **gVisor isolation, reused but persistent.** The real backend reuses the
  `execution/gvisor_backend.py` isolation (runsc runtime, labels, readonly rootfs,
  tmpfs, mem/cpu limits) but the container is PERSISTENT and may allow-list egress
  (deny-by-default) rather than `NetworkMode: none`.

## Security requirements (NON-NEGOTIABLE)

- **Secrets materialized INTO the Cabin only.** The Cabin reveals the user's Sea
  Chest secrets (`reveal(user_id, "claude_code"|"github")`) and injects them inside
  the container as env/files at spawn (e.g. `CLAUDE_CODE_OAUTH_TOKEN`, the GitHub
  token). Secrets are NEVER returned to the browser, NEVER put in `CabinStatus`,
  NEVER logged or placed in an exception message.
- **`CabinStatus` carries NO secret.** Status is `{user_id, cabin_id, state,
  created_at, last_active, network_allow}` — provenance + lifecycle only.
- **Deny-by-default egress.** The Cabin's network egress is an allow-list
  (`cabin_network_allow`, default `[]` = deny all). Only the hosts a phase needs
  (e.g. `api.github.com` for git, the Anthropic endpoint for Claude Code) are
  opened, and only by explicit config.
- **Per-user isolation.** A user only ever touches THEIR Cabin. The API is
  owner-scoped via `get_current_user` — there is no path to another user's Cabin.
- **Lazy `aiodocker` import.** Importing the gVisor backend module must NOT import
  `aiodocker`; the import lives inside the methods. If `aiodocker` is unavailable,
  raise a clear `CabinError`, never an opaque `ImportError`. App startup + tests
  stay Docker-free.

## Task

1. **Backend ABC** `app/cabin/backend.py` — `CabinBackend` ABC + `CabinError`, plus
   Pydantic `CabinInfo` / `CabinStatus` / `CabinRunResult` (status carries NO
   secret). Methods: `ensure(user_id, *, secrets, network_allow) -> CabinInfo`
   (get-or-create the user's persistent Cabin, materialize `secrets` by kind, apply
   the egress allow-list), `run(user_id, command, *, timeout) -> CabinRunResult`
   (one-shot exec inside the Cabin), `status(user_id) -> CabinStatus`,
   `destroy(user_id) -> None`, `close() -> None`.
2. **Null backend** `app/cabin/null_backend.py` — `NullCabinBackend`: deterministic,
   in-memory, container-free default. Tracks Cabins in a dict; `run` returns a
   canned success; records THAT secrets were materialized (by kind) WITHOUT storing
   or echoing their values. The CI default.
3. **gVisor backend** `app/cabin/gvisor_backend.py` — `GVisorCabinBackend`: real
   persistent-per-user gVisor container. Lazy `import aiodocker` inside methods;
   raise `CabinError` if unavailable. Reuse the `execution/gvisor_backend.py`
   isolation but persistent; egress restricted to `network_allow`; secrets injected
   as env at spawn, never logged. Opt-in only.
4. **Factory** `app/cabin/factory.py` — `create_cabin_backend(settings)` on
   `settings.cabin_backend` (default `"null"`, `"gvisor"` opt-in, unknown ->
   `ValueError`). Lazy backend imports inside the branches.
5. **Service** `app/services/cabin_service.py` — `CabinService(backend, settings)` +
   reuse `CabinError`. In-memory per-user registry with `created_at`/`last_active`
   (process-local, v1 single-worker — note like `pipeline_tasks`). `ensure(user_id,
   session)` reveals the user's Sea Chest secrets for the kinds present and calls
   `backend.ensure(...)`; `run(user_id, session, command, *, timeout)` ensures then
   runs; `status`/`destroy`; `reap_idle(*, now=None)` destroys idle-past-timeout OR
   past-max-lifetime Cabins (inject `now` for unit tests).
6. **Settings**: `cabin_backend: str = "null"`, `cabin_idle_timeout_seconds = 1800`,
   `cabin_max_lifetime_seconds = 3600`, `cabin_reap_interval_seconds = 300`,
   `cabin_network_allow: list[str] = []` (deny-by-default; document each kind's
   needed hosts as a comment).
7. **App wiring** (`main.py`): construct `app.state.cabin_service` on startup; spawn
   a background reaper task looping `await cabin_service.reap_idle()` every
   `cabin_reap_interval_seconds`, cancelled + awaited on shutdown (mirroring the
   pipeline-task drain); close the backend on shutdown.
8. **API** `app/api/v1/cabin.py` (default-deny via `get_current_user`, per-user):
   `GET /api/v1/cabin` (my Cabin status), `POST /api/v1/cabin` (ensure/wake ->
   status), `DELETE /api/v1/cabin` (destroy -> 204). Register in `router.py`.

## Output format

- Type-annotated Python, async, Pydantic v2, classes PascalCase, functions
  snake_case, One Piece themed naming ("Cabin"). New artifacts only under
  `src/backend/app/`, `src/backend/tests/`, and the named pdd files.
- TDD: failing tests first, then implement to green. Null backend / mocked sessions
  (`AsyncMock`/`MagicMock`), no Docker, no Postgres.

## Constraints

- Mirror the `ExecutionBackend`/`DeploymentBackend`/`BrowserCheckBackend` swap: ABC
  behind a factory, Null deterministic default, gVisor opt-in with a LAZY
  `aiodocker` import inside methods.
- In-memory registry only — NO migration needed (note v1 single-worker, like
  `pipeline_tasks`). If a DB audit table were added it would chain
  `down_revision='c1d2e3f4a5b6'`; not needed here.
- Secrets materialized into the Cabin ONLY — never logged, never in `CabinStatus`/
  API responses. Deny-by-default egress. Do NOT break existing tests. No git.

## Edge Cases

- `cabin_backend` unset -> Null backend (the CI default).
- `cabin_backend="gvisor"` but `aiodocker` absent -> `CabinError` (clear message),
  never an opaque `ImportError`; importing the module never imports `aiodocker`.
- `cabin_backend="podman"` (unknown) -> `ValueError`.
- `ensure` twice for one user -> ONE Cabin (get-or-create), `last_active` refreshed.
- `ensure` reveals only the kinds the user has connected; an absent kind is skipped.
- `reap_idle`: a Cabin idle past `cabin_idle_timeout_seconds` is reaped; a Cabin
  older than `cabin_max_lifetime_seconds` is reaped even if recently active; a fresh
  Cabin is kept. Returns the reaped user_ids.
- `status`/`destroy` for a user with no Cabin -> `CabinError("NOT_FOUND")`.
- No secret (value) ever appears in `CabinStatus`, an API response, a log line, or
  an exception message — only the KINDS materialized are observable.
