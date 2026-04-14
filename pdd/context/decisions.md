# GrandLine — Architectural Decisions

**Last updated**: 2026-04-14

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
