# GrandLine — Architectural Decisions

**Last updated**: 2026-04-24

---

## Decision: Pipeline REST + SSE API on top of PipelineService; background tasks in `app.state.pipeline_tasks`; SSE via ephemeral consumer groups
**Date**: 2026-04-24
**What was decided**: Added `app/api/v1/pipeline.py` with five endpoints: `POST /voyages/{id}/start` (202 Accepted, spawns `asyncio.create_task(service.start(...))` registered in `app.state.pipeline_tasks: dict[uuid.UUID, asyncio.Task]` and cleaned up via `task.add_done_callback`), `POST /pause` / `POST /cancel` (200, idempotent on terminal status; `/cancel` also cancels the in-flight task), `GET /status` (uses `PipelineService.reader(session)` — no dial router / execution backend constructed), and `GET /stream` (SSE, `text/event-stream`, one fresh ephemeral consumer group per connection named `sse-<uuid>`, replay-from-start at `id="0"`, ~1s block timeout with `request.is_disconnected()` check each loop, terminates on voyage terminal status or client disconnect, destroys the group in the `finally` block). Running-pipeline idempotency on `POST /start` is 409 `PIPELINE_ALREADY_RUNNING`; COMPLETED voyage also 409. `StartVoyageRequest` has `task: str (10–5000 chars)`, `deploy_tier: Literal["preview"]`, `max_parallel_shipwrights: int | None (ge=1 le=10)`. Shutdown in `app/main.py` lifespan cancels in-flight tasks and awaits up to 5s. No `last-event-id` / SSE resume in v1.
**Why**: Making `POST /start` 202 + background task keeps the HTTP layer responsive — the graph run takes minutes, not milliseconds, and clients observe it via SSE. The registry is process-local and single-worker by design; a multi-worker deployment would need to move it to Redis, but v1 runs single-worker and the simplicity is worth more than the horizontal-scale story. Ephemeral per-connection consumer groups sidestep cross-client ack coordination: each SSE consumer gets its own replay and the group dies with the connection (clean finally cleanup). Terminating on DB voyage status — rather than a dedicated "stream-end" event — means the SSE endpoint doesn't need to know about every terminal event type; any final state flip closes the stream. Running-pipeline 409 forces callers to explicitly cancel + restart rather than silently stomping on an in-flight run. The 5s shutdown window gives spawning `PipelineFailedEvent` one chance to reach Redis before the loop tears down.
**Don't suggest**: Persisting `pipeline_tasks` to Redis for multi-worker (out of scope for v1), named SSE events (`event: pipeline_stage_entered\ndata: ...`) — the envelope already carries `event_type` inline, adding a dedicated "pipeline finished" event to terminate SSE (DB status flip is sufficient), reusing a named consumer group across SSE connections (ack coordination headache), making `/start` synchronous (blocks connection for minutes), `last-event-id` support (revisit when stream volume > ~100 events per voyage)

---

## Decision: Master pipeline graph invokes services directly; parallel Shipwright via topological layers + semaphore; pause/resume via DB status
**Date**: 2026-04-23
**What was decided**: Added `app/crew/pipeline_graph.py` (master graph composing Captain → Navigator → Doctor(tests) → Shipwrights → Doctor(validate) → Helmsman) and `app/services/pipeline_service.py` (thin orchestrator: `start`, `pause`, `cancel`, `get_status`). Graph nodes instantiate crew services directly (`CaptainService`, `NavigatorService`, `DoctorService`, `ShipwrightService`, `HelmsmanService`) — they do not invoke each crew's compiled sub-graph. Parallel building uses `topological_layers()` to group phases by dependency layer, then runs each layer's phases concurrently under an `asyncio.Semaphore(max_parallel_shipwrights)`. Pause/resume is implemented via `voyage.status == PAUSED` in the DB, checked between every stage — **not** via LangGraph checkpointers. Resume is "skip-already-satisfied-stages aggressive": each node calls the next guard, and if it passes, the stage's output already exists → skip the LLM call. Five pipeline-level events added (`pipeline_started`, `pipeline_stage_entered`, `pipeline_stage_completed`, `pipeline_completed`, `pipeline_failed`); SSE streams tap the existing `DenDenMushi` bus — no new SSE endpoint. The pipeline owns the terminal `voyage.status` transitions (`COMPLETED` in `finalize_node`, `FAILED` in `fail_end`); crew services retain their transient writes (`BUILDING`, `DEPLOYING`, etc.) but the pipeline does not re-orchestrate them.
**Why**: Direct service invocation keeps the graph thin and composable — wrapping each service in a sub-graph would double the node count, obscure the end-to-end flow, and require synchronizing two state models. Topological layers + semaphore is the simplest correct scheduling: respects dependencies, bounds concurrency, and fails fast on any phase's failure. DB-backed pause/resume leverages the existing voyage status field and avoids pulling in `langgraph.checkpoint` (extra dependency, redis/postgres checkpoint storage, state serialization headaches). Skip-already-satisfied turns the guard module (Phase 15.2) into a cheap resume engine — no need for a separate "what's done?" query pathway. Tapping `DenDenMushi` for SSE reuses the stream-key convention already shipped in Phases 10–14.
**Don't suggest**: LangGraph checkpointers for pause state, sub-graphs per crew (e.g. calling `captain_graph.ainvoke` from a planning node), per-stage `asyncio.gather` without a semaphore (would fan out unbounded), adding a separate "pipeline event stream" distinct from the voyage stream, moving terminal status writes into crew services, making the pipeline aware of `phase_status` transitions at the service level (Shipwright owns those).

---

## Decision: One Piece-themed agent personas over generic agents
**Date**: 2026-04-04
**What was decided**: The platform uses a fixed crew of persona-based agents (Captain, Navigator, Shipwrights, Doctor, Helmsman) with One Piece terminology throughout the codebase, UI, and docs.
**Why**: The theming isn't cosmetic — it enforces role separation. Each persona has a distinct responsibility in the pipeline, preventing the common "god agent" anti-pattern where one agent does everything. The vocabulary (Poneglyphs, Vivre Cards, Den Den Mushi) makes the system self-documenting and memorable.
**Don't suggest**: Generic "Agent 1, Agent 2" naming, dropping the theme for "professionalism", single monolithic agent

---

## Decision: Structured pipeline (PDD → TDD → Implement → Review → Deploy)
**Date**: 2026-04-04
**What was decided**: Every task flows through the full pipeline. The Log Pose (PDD + TDD) is mandatory — no agent skips steps.
**Why**: This is the core product differentiator. Most agent platforms let agents freestyle. GrandLine enforces engineering discipline: the Navigator writes Poneglyphs before code exists, the Doctor writes health checks before Shipwrights build. This produces auditable, tested, documented output — not just "AI-generated code."
**Don't suggest**: Skipping PDD for "simple" tasks, optional TDD, letting agents self-organize without the pipeline

---

## Decision: Redis Streams over Celery for inter-agent communication
**Date**: 2026-04-04
**What was decided**: Use Redis Streams (Den Den Mushi) for the message bus, not Celery.
**Why**: Redis Streams provides native pub/sub with consumer groups, message persistence, and ordered delivery — exactly what inter-agent communication needs. Celery is a task queue (fire-and-forget jobs), not a communication bus. The agents need to subscribe to each other's events, not just dispatch jobs. Redis Streams is also lighter weight and already in the stack for caching.
**Don't suggest**: Celery, RabbitMQ (unnecessary complexity), plain Redis pub/sub (no persistence/replay)

---

## Decision: Dial System (LLM gateway) with config-driven role mapping
**Date**: 2026-04-04 (implemented 2026-04-05)
**What was decided**: All LLM calls go through the Dial System — a gateway that routes requests based on crew role configuration. Each agent persona can be mapped to a different provider/model. Failover is automatic with ProviderError-driven chain traversal.
**Why**: Provider-agnostic by design. Users can run the Captain on Claude, Shipwrights on GPT-4, and the Doctor on a local model — all via config, not code changes. When a provider hits rate limits or errors, the Dial System catches `ProviderError`, tries the fallback chain, and publishes `ProviderSwitchedEvent` via Den Den Mushi.
**Don't suggest**: Direct provider SDK calls from agents, single-provider lock-in, manual failover

---

## Decision: Adapter factory pattern over global adapter instances
**Date**: 2026-04-05
**What was decided**: Provider adapters are created per-request via `create_adapter()` and `build_router_from_config()` in `factory.py`. No global adapter instances — the factory reads DialConfig JSONB from DB and wires a fresh `DialSystemRouter` per request via FastAPI's `Depends(get_dial_router)`.
**Why**: Config can change at any time via `PUT /dial-config`. If adapters were global singletons, config changes would require a restart or cache invalidation. Per-request creation means the next API call picks up new config immediately. The factory also centralizes provider-to-adapter mapping, making it easy to add new providers.
**Don't suggest**: Global adapter singletons, adapter caching without invalidation, direct adapter instantiation in route handlers

---

## Decision: Vivre Card state checkpointing in PostgreSQL
**Date**: 2026-04-04
**What was decided**: Agent state is serialized as Vivre Card snapshots stored in PostgreSQL (JSONB). Checkpoints are taken at defined intervals and before any provider migration.
**Why**: This is the foundation of "no work lost." If a provider goes down, an agent crashes, or the user pauses a voyage, the Vivre Card lets the system resume from the last checkpoint. PostgreSQL JSONB gives flexible schema for different agent state shapes while still being queryable.
**Don't suggest**: In-memory-only state, file-based checkpoints, relying on LLM conversation history as state

---

## Decision: Swappable Execution Service with gVisor containers (v1)
**Date**: 2026-04-04 (updated)
**What was decided**: Agent code execution goes through an `ExecutionService` with a clean `ExecutionBackend` interface. The v1 backend uses Docker containers with gVisor (runsc) runtime for kernel-level syscall filtering. Per-user container isolation. The backend is swappable — future implementations (Firecracker, Wasm, subprocess) plug in via config without changing calling code.
**Why**: Agents generate and execute untrusted code. gVisor provides strong isolation (syscall interception) without the overhead of full VMs. The clean interface boundary means we can upgrade the isolation strategy later without touching crew agent code or the Execution Service API. Per-user containers prevent cross-user contamination.
**Don't suggest**: Running agents in the main process, subprocess-only isolation (insufficient for untrusted code), hardcoding the sandbox implementation without a swappable interface

---

## Decision: Per-agent git branches
**Date**: 2026-04-04
**What was decided**: Agents work in real git repos with per-agent branches (`agent/<crew-member>/<voyage-id>`). Code is merged via the standard PR flow.
**Why**: Git is the source of truth, not agent memory. Per-agent branches mean parallel work without conflicts, full diff visibility, and the ability to review/revert any agent's work independently. It also means the platform's output is standard git history — no proprietary format.
**Don't suggest**: Agents writing to a shared branch, in-memory code generation without git, proprietary version control

---

## Decision: Three-tier deployment (preview → staging → production)
**Date**: 2026-04-04
**What was decided**: Three deployment tiers with increasing gates: auto-preview (on push), semi-auto staging (on PR merge), PR-only production (full review).
**Why**: Agent-generated code needs more gates, not fewer. Auto-preview lets users see output fast. Staging catches integration issues. Production requires human approval (the fleet admiral's final say). This matches the "user can intervene at any point" philosophy.
**Don't suggest**: Direct-to-production deployment, single environment, skipping staging

---

## Decision: Separate frontend and backend languages
**Date**: 2026-04-04
**What was decided**: TypeScript (Next.js) for frontend, Python (FastAPI) for backend.
**Why**: The AI/ML ecosystem is Python-native (LangGraph, LangChain, most LLM SDKs). Fighting this with an all-TypeScript backend would mean constant wrapper libraries and ecosystem friction. TypeScript frontend gives type safety and the React ecosystem for the Observation Deck.
**Don't suggest**: All-TypeScript (Node.js backend), all-Python (Django templates for frontend)

---

## Decision: Next.js with hybrid rendering for landing + dashboard
**Date**: 2026-04-04
**What was decided**: Use Next.js App Router with SSG for the public landing page and CSR for the Observation Deck.
**Why**: GrandLine needs an attractive, SEO-optimized public landing page with visuals AND a real-time dashboard (Observation Deck). Next.js handles both in one codebase with per-route rendering strategies. The landing page uses Framer Motion for smooth animations. The Observation Deck is CSR-only for real-time performance.
**Don't suggest**: Separate repos for landing page and dashboard, Vite for everything, SSR for the Observation Deck

---

## Decision: REST + SSE + WebSockets (three protocols)
**Date**: 2026-04-04
**What was decided**: Use REST for CRUD, SSE for LLM streaming, WebSockets for bidirectional real-time.
**Why**: SSE is the natural fit for LLM token streaming from the Dial System (one-way, server→client) — it's what Anthropic and OpenAI APIs use natively. WebSockets are needed for bidirectional communication (user intervention during a voyage, live Observation Deck updates across all three views). REST handles standard CRUD for voyages, configs, and Vivre Cards.
**Don't suggest**: WebSockets for everything, REST polling for real-time, GraphQL subscriptions

---

## Decision: Local-first with Kubernetes for production
**Date**: 2026-04-04
**What was decided**: Docker Compose is the primary development environment (local-first). Kubernetes + Helm for production deployment.
**Why**: The platform should run fully on a developer's machine with `docker compose up`. No cloud dependency for development. Kubernetes is added for production because agent workloads need independent scaling, and the sandboxed container model maps naturally to K8s pods. Helm charts manage environment-specific config.
**Don't suggest**: Cloud-only development, running without containers locally, serverless (doesn't fit the sandboxed execution model)

---

## Decision: All artifacts under src/
**Date**: 2026-04-04
**What was decided**: All application code (frontend, backend, shared, infra) lives under `src/` with clear subdirectories.
**Why**: User preference for a clean repo root. Keeps config files, docs, and PDD files at root level while all buildable/deployable code is contained in `src/`.
**Don't suggest**: Separate top-level directories for frontend/backend, monorepo tools like Turborepo (premature at this stage)

---

## Decision: Auto-deployed documentation on GitHub Pages
**Date**: 2026-04-04
**What was decided**: Documentation lives under `docs/` and auto-deploys to GitHub Pages via GitHub Actions on merge to `main`.
**Why**: Docs should always reflect the current state of `main`. Automating deployment removes the "forgot to update docs" failure mode. One Piece terminology is used in docs — it's part of the product identity.
**Don't suggest**: Manual doc deployment, docs in a separate repo, wiki-only documentation

---

## Decision: PR-based workflow with GitHub Issues for planning
**Date**: 2026-04-04
**What was decided**: Plan phases become GitHub issues. Each issue is worked on in a separate branch/PR. PRs must pass tests and PDD review before merge. User approves all PRs.
**Why**: Clean git history, traceable work, and human-in-the-loop for quality control. Each PR is a reviewable, revertable unit of work.
**Don't suggest**: Batching multiple issues into one PR, auto-merging without user approval, committing directly to main

---

## Decision: Git host allowlist for token safety
**Date**: 2026-04-13
**What was decided**: Git operations that receive a URL (clone) validate the host against `ALLOWED_GIT_HOSTS` (default: `github.com`, `gitlab.com`). If the config key is absent, host validation is skipped (open by default for self-hosted setups).
**Why**: Git clone URLs are user-supplied. An attacker could point a clone URL at a server they control to exfiltrate the bearer token injected into the credential helper. The allowlist bounds the blast radius.
**Don't suggest**: Disabling host validation, embedding tokens in the URL itself, trusting all hosts unconditionally

---

## Decision: LangGraph two-node graph for Captain Agent
**Date**: 2026-04-14
**What was decided**: The Captain Agent uses a compiled LangGraph `StateGraph` with two nodes — `decompose` (LLM call) → `validate` (JSON parse + Pydantic validation). The graph is compiled once per `CaptainService` instance and cached as `self._graph`.
**Why**: The graph is intentionally minimal for v1. Decompose calls the Dial System via `CrewRole.CAPTAIN`, validate strips markdown fences and runs `VoyagePlanSpec.model_validate()`. No retry loops yet — that's future work. Caching the compiled graph avoids per-request recompilation overhead.
**Don't suggest**: Retry loops in the graph (premature), raw LLM calls without the Dial System, building a new graph per request

---

## Decision: CaptainService.reader() for read-only operations
**Date**: 2026-04-14
**What was decided**: `CaptainService` has a `reader(session)` classmethod that creates a lightweight instance with only a DB session — no dial_router, mushi, or compiled graph. Used by `GET /plan`.
**Why**: The GET endpoint is a simple DB read. Requiring a `DialSystemRouter` dependency means that if the voyage's DialConfig is deleted, the plan becomes unreadable even though it's already persisted. Decoupling read from write dependencies keeps the read path robust.
**Don't suggest**: Sharing the full `get_captain_service` dependency for read endpoints, creating a separate PlanReadService (over-abstraction for one method)

---

## Decision: Best-effort event publishing after DB commit
**Date**: 2026-04-14
**What was decided**: `chart_course` commits plan + VivreCard to PostgreSQL first, then publishes the `VoyagePlanCreatedEvent` to Den Den Mushi in a try/except. If Redis is down, the event is logged as a warning and the request succeeds.
**Why**: The plan is the source of truth, not the event. If publish fails after a successful commit, the caller gets a successful response and can retry the event later. Failing the request after the plan is already committed leaves the caller with a 500 for a successful write and no safe retry path (the voyage status has moved out of CHARTED).
**Don't suggest**: Publishing before commit (data loss risk), failing the request on publish failure, transactional outbox (premature for current scale)

---

## Decision: Shipwright invocation is phase-scoped
**Date**: 2026-04-17
**What was decided**: The Shipwright Agent's build API is phase-scoped (`POST /voyages/{id}/phases/{phase_number}/build`), not voyage-scoped. One invocation builds exactly one phase. The future voyage pipeline (Phase 15) fans out one invocation per phase to enable parallelism.
**Why**: Per-phase invocations are the parallelism primitive. A voyage-level endpoint would force serial phase builds, or require the Shipwright itself to manage internal parallelism — premature complexity. Scoping per-phase also keeps the LLM context small (one Poneglyph + its tests) and enables independent retries.
**Don't suggest**: Voyage-scoped build endpoint that loops over phases internally, hidden intra-Shipwright concurrency

---

## Decision: Service-owned iteration loop, graph stays side-effect-free
**Date**: 2026-04-17
**What was decided**: The Shipwright's generate→test→refine iteration loop is implemented in the **service layer**, not inside the compiled LangGraph graph. The service runs single-iteration graph invocations in a Python loop, writing a `VivreCard` between iterations for "no work lost" guarantees.
**Why**: LangGraph graphs should remain pure — nodes call LLMs and sandboxes but don't own DB state. Per-iteration checkpointing is a DB write; keeping it in the service preserves graph purity and makes the loop trivially testable with mocked graph invocations. The alternative (LangGraph's built-in checkpointer) adds infrastructure without solving the observability problem (we want one VivreCard row per iteration, queryable by the Observation Deck).
**Don't suggest**: Putting `session.commit()` inside graph nodes, relying on LangGraph's internal checkpointer for product-level state, one giant `.ainvoke()` that runs the full loop opaquely

---

## Decision: Shipwright voyage-level status gate (v1 scope-cut)
**Date**: 2026-04-17
**What was decided**: v1 of the Shipwright enforces a single in-flight invocation per voyage via the `voyage.status == CHARTED` gate (transitions to `BUILDING` during the call). True per-phase parallelism is deferred until a `phase_status` map is added to the voyage model.
**Why**: Shipping a correct sequential path first. Concurrent invocations on the same voyage would race the `voyage.status` transition and the `delete-before-insert` step for `BuildArtifact`. A `phase_status` refactor is the right long-term fix but premature for the first Shipwright cut. Phase 15's voyage pipeline will sequence phase builds; user-level fan-out across phases waits for the refactor.
**Don't suggest**: Removing the 409 gate, introducing a voyage-level lock in Redis (heavier than needed), bolting on a phase_status column without a migration plan
**Superseded by**: 2026-04-19 — Shipwright per-phase status gate (Phase 15.1 refactor)

---

## Decision: Shipwright per-phase status gate (Phase 15.1 refactor)
**Date**: 2026-04-19
**What was decided**: Replaced `voyage.status` gate with a `Voyage.phase_status` JSONB map keyed by `str(phase_number)` with values `PENDING | BUILDING | BUILT | FAILED` (module-level string constants in `shipwright_service.py`, no SQLAlchemy enum). `ShipwrightService.build_code` gates on `phase_status.get(key, "PENDING") in {"PENDING", "FAILED"}` and raises `ShipwrightError("PHASE_NOT_BUILDABLE")` → HTTP 409 when the phase is already `BUILDING` or `BUILT`. `voyage.status` is no longer touched by the service. `BuildArtifact` delete-before-insert remains scoped to `(voyage_id, phase_number)`.
**Why**: Phase 15's voyage pipeline wants to build independent phases in parallel (topological layers bounded by `asyncio.Semaphore`). The voyage-level gate made concurrent phase builds impossible — any second invocation 409'd, even for a different phase. Keeping `voyage.status` untouched lets the master pipeline own the outer `CHARTED → BUILDING → COMPLETED` transitions without racing the Shipwright. JSONB over a new table avoids a join on every gate check; dict-copy-before-assign keeps SQLAlchemy's JSONB dirty-tracking happy without `flag_modified`. Per-phase re-buildability (FAILED → buildable) is a pipeline-retry requirement.
**Don't suggest**: Reinstating the `voyage.status` gate, using a SQLAlchemy Enum column (JSONB values are more flexible and cheaper to migrate), introducing `flag_modified` everywhere instead of fresh-dict-assign, adding per-phase row locks (the status map is a single row update)

---

## Decision: Pipeline transition guards as pure predicates
**Date**: 2026-04-20
**What was decided**: Added `app/services/pipeline_guards.py` with six `require_can_enter_*` helpers (`planning`, `pdd`, `tdd`, `building`, `reviewing`, `deploying`) and a single `PipelineError(code, message)` exception distinguished by `.code`. Guards take DB-loaded objects (voyage, plan, poneglyphs, health_checks, build_artifacts, validation_run) and raise on violation — no DB queries, no LLM calls, no event publishing, no state mutation. Error code taxonomy is 1:1 with guards: `VOYAGE_NOT_PLANNABLE`, `PLAN_MISSING`, `PONEGLYPHS_INCOMPLETE`, `HEALTH_CHECKS_INCOMPLETE`, `BUILD_INCOMPLETE`, `VALIDATION_NOT_PASSED`. "Can enter reviewing" checks both `BuildArtifact` presence AND `voyage.phase_status[str(phase)] == "BUILT"` for every planned phase — the first consumer of the Phase 15.1 `phase_status` gate.
**Why**: The master pipeline has six stage transitions, each with different pre-conditions. Putting the checks inline in the graph nodes (Phase 15.3) would scatter invariants across six files and tangle scheduling with validation. Centralizing them as pure predicates means: one place to reason about "what does a voyage need to enter stage X," trivially unit-testable (no DB fixtures — 33 tests, 0.03s), and reusable as the engine for skip-already-satisfied-stages on resume. When a voyage resumes, the pipeline calls the *next* guard; if it passes, the stage's output already exists, so skip the stage + its LLM call entirely. That's token-cost savings on re-run after a fix.
**Don't suggest**: Merging the guard module into `pipeline_service.py` (the separation is the point), one-exception-per-guard (`PlanMissingError`, `PoneglyphsIncompleteError` — unnecessary class sprawl, use `.code`), guards performing DB lookups (couples them to sessions and makes unit tests require mocked sessions), adding guards for status transitions the pipeline doesn't use (e.g. `require_can_enter_completed` — `finalize_node` owns that)

---

## Decision: Configurable Shipwright concurrency via DialConfig (not env/global)
**Date**: 2026-04-19
**What was decided**: Added `ShipwrightRoleConfig.max_concurrency: int | None` (Pydantic `ge=1 le=10`) to `DialConfig.role_mapping.shipwright`. `resolve_shipwright_max_concurrency()` reads the value at pipeline-start time and falls back to `1` on any missing key, non-dict shape, validation failure, or `None`. No migration — piggybacks on the existing `role_mapping` JSONB.
**Why**: Different users have different provider plans — a free-tier Anthropic key can't sustain 5 concurrent Shipwrights, a Tier-4 key easily can. Hard-coding a global max would either starve high-tier users or overload low-tier ones. Per-voyage scoping (via DialConfig) means the knob sits next to the other provider choices the user already tunes. The `1..10` range is a safety rail — parallelism beyond 10 typically hits rate limits anyway and burns tokens on retries. Fail-safe-to-1 means a malformed config never triggers a fan-out storm.
**Don't suggest**: Global env var, per-request query param, removing the upper bound, raising on invalid config (silent fallback preserves "voyages always progress")

---

## Decision: Vitest deferred; Shipwright v1 is pytest-only
**Date**: 2026-04-17
**What was decided**: If a phase's `HealthCheck.framework == "vitest"`, `ShipwrightService.build_code` returns `ShipwrightError("VITEST_NOT_SUPPORTED")` → 422. pytest-only for v1. Vitest support is a follow-up feature.
**Why**: Running Node/Vitest inside the sandbox is a separate integration (different runtime, different pytest-vs-vitest output parsing, different file layout). Scoping v1 to pytest keeps the first Shipwright cut focused. The error code is explicit so the voyage pipeline can surface it cleanly.
**Don't suggest**: Silent fallback to pytest for Vitest tests, adding Vitest runner without a dedicated PDD cycle

---

## Decision: Shipwright max_iterations hardcoded to 3
**Date**: 2026-04-17
**What was decided**: `SHIPWRIGHT_MAX_ITERATIONS = 3` is a module-level constant, not an env/config value. The loop terminates on green tests or after 3 attempts (generate + run, 3x).
**Why**: Config surface area has a cost. 3 matches typical Claude/GPT-4 "fix your own output" attention span and keeps worst-case latency bounded. If Phase 15 integration tests show 3 is too low, bump the constant — no schema change, no API change. Adding an env var now signals "this is a knob we tune" when it's actually a best-effort convergence limit.
**Don't suggest**: Exposing `max_iterations` via API, reading from `.env` at startup, per-voyage overrides
