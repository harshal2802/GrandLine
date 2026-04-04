# Implementation Plan: GrandLine v1

**Created**: 2026-04-04
**Complexity**: High
**Estimated prompts**: 18

## Summary
Build GrandLine bottom-up: infrastructure first, then core platform systems (message bus, LLM gateway, state checkpointing, execution service, git), then the five crew agents one-by-one following the pipeline order, then wire them together via LangGraph, then build the Observation Deck UI, and finally production deployment. The landing page goes early (Phase 2) to establish product identity and gets updated as features land.

## Dependency Graph
```
Phase 1 (Foundation) ─┬─→ Phase 2 (Landing Page)
                      ├─→ Phase 3 (DB & Models) → Phase 4 (Auth)
                      │
Phase 3 ──────────────┼─→ Phase 5 (Den Den Mushi)
                      ├─→ Phase 6 (Dial System)
                      └─→ Phase 7 (Vivre Card)

Phase 3 ──────────────┬─→ Phase 8 (Execution Service + gVisor)
                      └─→ Phase 9 (Git Integration)

Phase 5+6+7+8+9 ─────┬─→ Phase 10 (Captain)
                      ├─→ Phase 11 (Navigator) → depends on 10
                      ├─→ Phase 12 (Doctor) → depends on 11
                      ├─→ Phase 13 (Shipwrights) → depends on 11+12
                      └─→ Phase 14 (Helmsman) → depends on 13

Phase 10-14 ──────────→ Phase 15 (Voyage Pipeline — LangGraph E2E)

Phase 4+15 ───────────→ Phase 16 (Observation Deck)
Phase 16 ─────────────→ Phase 17 (User Intervention)
Phase 15+17 ──────────→ Phase 18 (Production Deployment — K8s + Helm)
```

## Phases

### Phase 1: Project Foundation & Infrastructure
**Produces**: Running Docker Compose stack (FastAPI + Next.js + PostgreSQL + Redis), CI/CD pipeline, GitHub Pages docs deployment
**Depends on**: nothing
**Risk**: Low — standard scaffolding
**Prompt**: `pdd/prompts/features/foundation/grandline-01-foundation.md`

Deliverables:
- Docker Compose with FastAPI, Next.js, PostgreSQL, Redis containers
- FastAPI app skeleton under `src/backend/` with health check endpoint
- Next.js app skeleton under `src/frontend/` with App Router
- Alembic init for migrations
- GitHub Actions: lint + test on PR, docs deploy on merge to main
- `docs/` with initial index page deployed to GitHub Pages
- pytest + httpx setup (backend), Vitest + RTL setup (frontend)

---

### Phase 2: Landing Page
**Produces**: SSG public landing page with One Piece-themed product overview and Framer Motion animations
**Depends on**: Phase 1 (Next.js scaffold)
**Risk**: Low — static content, no backend dependency
**Prompt**: `pdd/prompts/features/landing/grandline-02-landing-page.md`

Deliverables:
- Hero section with tagline ("Assemble your crew. Navigate the GrandLine.")
- Crew overview section (5 agent personas with roles)
- Voyage pipeline visualization (PDD → TDD → Implement → Review → Deploy)
- Observation Deck preview section (3 view mockups)
- Responsive design, Framer Motion scroll animations
- SEO meta tags, Open Graph

---

### Phase 3: Database Models & Core Schemas
**Produces**: SQLAlchemy models, Alembic migrations, Pydantic schemas for all core entities
**Depends on**: Phase 1 (PostgreSQL + Alembic)
**Risk**: Medium — schema design affects everything downstream
**Prompt**: `pdd/prompts/features/core/grandline-03-database-models.md`

Deliverables:
- Models: `User`, `Voyage`, `VoyagePlan`, `VivreCard`, `CrewAction`, `Poneglyph`, `DialConfig`
- JSONB columns for flexible agent state (Vivre Cards) and crew config
- Alembic migration for initial schema
- Pydantic schemas for all request/response shapes
- Seed data script for development

---

### Phase 4: Auth & Security
**Produces**: JWT auth system with default-deny middleware, user registration/login API
**Depends on**: Phase 3 (User model)
**Risk**: Medium — security foundation, must be correct
**Prompt**: `pdd/prompts/features/auth/grandline-04-auth.md`

Deliverables:
- JWT token generation and validation
- Default-deny middleware — every route closed unless explicitly opened
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`
- Password hashing (bcrypt)
- Next.js auth middleware for Observation Deck routes
- Protected route decorator for FastAPI

---

### Phase 5: Den Den Mushi (Message Bus)
**Produces**: Redis Streams wrapper with typed event schemas, consumer groups, dead letter handling
**Depends on**: Phase 1 (Redis), Phase 3 (Pydantic schemas)
**Risk**: Medium — core communication backbone, must be reliable
**Prompt**: `pdd/prompts/features/den-den-mushi/grandline-05-message-bus.md`

Deliverables:
- `DenDenMushi` class wrapping Redis Streams (publish, subscribe, ack)
- Pydantic event schemas: `CrewEvent`, `VoyageEvent`, `DialEvent`
- Consumer groups per crew role
- Dead letter stream for failed messages
- Event replay capability (read from stream offset)
- Integration tests with real Redis

---

### Phase 6: Dial System (LLM Gateway)
**Produces**: Provider-agnostic LLM gateway with config-driven role mapping, rate limit tracking, SSE streaming
**Depends on**: Phase 3 (DialConfig model), Phase 5 (Den Den Mushi for events)
**Risk**: High — provider APIs differ, failover logic is complex
**Prompt**: `pdd/prompts/features/dial-system/grandline-06-llm-gateway.md`

Deliverables:
- `DialSystemRouter` with provider selection by crew role
- Provider adapters: Anthropic, OpenAI, local (Ollama)
- Config-driven mapping (YAML): `captain → claude-sonnet, shipwright → gpt-4o, ...`
- SSE streaming for token-by-token output
- Rate limit tracking per provider
- Failover chain: primary → fallback → park
- Den Den Mushi events on provider switch

---

### Phase 7: Vivre Card (State Checkpointing)
**Produces**: Agent state checkpoint/restore system in PostgreSQL JSONB, with provider migration support
**Depends on**: Phase 3 (VivreCard model), Phase 5 (Den Den Mushi), Phase 6 (Dial System failover trigger)
**Risk**: Medium — serialization must handle any agent state shape
**Prompt**: `pdd/prompts/features/vivre-card/grandline-07-state-checkpointing.md`

Deliverables:
- `VivreCardService`: `checkpoint(agent, state)`, `restore(agent, card_id)`, `list(voyage_id)`
- Automatic checkpointing at configurable intervals
- Triggered checkpoint before provider migration
- State diff tracking (what changed between checkpoints)
- REST API: `GET/POST /api/v1/vivre-cards`
- Restore-and-resume flow tested end-to-end

---

### Phase 8: Execution Service (Containerized Sandbox + gVisor)
**Produces**: Swappable Execution Service behind a clean interface, with containerized gVisor-sandboxed execution and per-user isolation
**Depends on**: Phase 1 (Docker), Phase 3 (models)
**Risk**: High — security boundary, must prevent container escape
**Prompt**: `pdd/prompts/features/sandbox/grandline-08-execution-service.md`

The Execution Service is the security boundary for all agent code execution. It uses a clean interface (`ExecutionBackend`) so the underlying sandbox implementation can be swapped without changing any calling code.

Deliverables:
- `ExecutionService` — public API that crew agents call. Delegates to a backend.
- `ExecutionBackend` — abstract interface defining `create()`, `execute()`, `destroy()`, `status()`
- `GVisorContainerBackend` — default v1 implementation using Docker + gVisor (runsc) runtime
- Per-user container isolation: each user gets their own container pool
- Resource limits: CPU, memory, timeout, network disabled by default
- Filesystem isolation: temp workspace per execution, destroyed on completion
- Execution result capture: stdout, stderr, exit code, artifacts
- Cleanup on timeout, crash, or completion
- Backend is selected via config — future backends (Firecracker, Wasm, subprocess) plug in without code changes
- Integration tests verifying isolation (can't read host filesystem, can't reach host network)

---

### Phase 9: Git Integration
**Produces**: Per-agent branch management with commit, push, and PR operations on real git repos
**Depends on**: Phase 3 (models), Phase 8 (Execution Service for git operations)
**Risk**: Medium — git operations must be atomic and conflict-safe
**Prompt**: `pdd/prompts/features/git/grandline-09-git-integration.md`

Deliverables:
- `GitService`: clone, branch, commit, push, create PR
- Per-agent branch naming: `agent/<crew-member>/<voyage-id>`
- Branch creation from main, isolated per agent
- Commit with structured messages (crew member attribution)
- PR creation via GitHub API
- Conflict detection (fail early, don't auto-merge)
- Git operations run inside Execution Service sandbox

---

### Phase 10: Captain Agent (Project Manager)
**Produces**: LangGraph agent that decomposes user tasks into voyage plans, assigns work to crew
**Depends on**: Phase 5 (Den Den Mushi), Phase 6 (Dial System), Phase 7 (Vivre Card)
**Risk**: Medium — task decomposition quality depends on prompt engineering
**Prompt**: `pdd/prompts/features/crew/grandline-10-captain.md`

Deliverables:
- `CaptainAgent` LangGraph graph definition
- Task decomposition: user input → structured voyage plan (phases, assignments, dependencies)
- Voyage plan stored in PostgreSQL
- Crew assignment: map phases to crew roles
- Den Den Mushi: publish `VoyagePlanCreated`, `PhaseAssigned` events
- Vivre Card checkpointing after plan creation
- REST API: `POST /api/v1/voyages` (Chart a Course)

---

### Phase 11: Navigator Agent (Architect)
**Produces**: LangGraph agent that generates Poneglyphs (PDD prompt artifacts) from the voyage plan
**Depends on**: Phase 10 (Captain's voyage plan output)
**Risk**: Medium — Poneglyph quality drives the entire downstream pipeline
**Prompt**: `pdd/prompts/features/crew/grandline-11-navigator.md`

Deliverables:
- `NavigatorAgent` LangGraph graph definition
- Receives voyage plan phases from Captain
- Generates structured Poneglyphs (PDD prompts) for each phase
- Technical architecture decisions included in Poneglyphs
- Poneglyphs stored in DB and written to git (Navigator's branch)
- Den Den Mushi: publish `PoneglyphDrafted` events
- Vivre Card checkpointing

---

### Phase 12: Doctor Agent (QA — Pre-build)
**Produces**: LangGraph agent that writes failing tests (TDD health checks) from Poneglyphs before any code exists
**Depends on**: Phase 11 (Navigator's Poneglyphs)
**Risk**: Medium — tests must be meaningful, not just syntactically valid
**Prompt**: `pdd/prompts/features/crew/grandline-12-doctor.md`

Deliverables:
- `DoctorAgent` LangGraph graph definition
- Reads Poneglyphs, generates test files (pytest / Vitest depending on target)
- Tests are written to Doctor's git branch
- Tests must fail initially (TDD — health checks before implementation)
- Post-build validation mode: run tests against Shipwright output, report results
- Den Den Mushi: publish `HealthCheckWritten`, `ValidationPassed/Failed` events
- Vivre Card checkpointing

---

### Phase 13: Shipwright Agents (Developers)
**Produces**: LangGraph agents that generate code following Poneglyphs, execute in Execution Service, commit to per-agent branches
**Depends on**: Phase 8 (Execution Service), Phase 9 (Git), Phase 11 (Poneglyphs), Phase 12 (Doctor's tests to pass)
**Risk**: High — code generation + sandboxed execution + git integration all together
**Prompt**: `pdd/prompts/features/crew/grandline-13-shipwrights.md`

Deliverables:
- `ShipwrightAgent` LangGraph graph definition
- Reads Poneglyphs and Doctor's health checks
- Generates code in Execution Service sandbox
- Runs Doctor's tests inside sandbox — iterates until green
- Commits passing code to Shipwright's git branch
- Den Den Mushi: publish `CodeGenerated`, `TestsPassed` events
- Vivre Card checkpointing at each iteration
- Multiple Shipwrights can work in parallel on independent phases

---

### Phase 14: Helmsman Agent (DevOps)
**Produces**: LangGraph agent that deploys across three tiers (preview → staging → production)
**Depends on**: Phase 8 (Execution Service), Phase 9 (Git — PR creation), Phase 13 (Shipwright's committed code)
**Risk**: Medium — deployment must be safe, gated, reversible
**Prompt**: `pdd/prompts/features/crew/grandline-14-helmsman.md`

Deliverables:
- `HelmsmanAgent` LangGraph graph definition
- Preview tier: auto-deploy on branch push (containerized preview)
- Staging tier: deploy on PR merge, lightweight validation
- Production tier: PR to main, requires user approval
- Rollback capability per tier
- Den Den Mushi: publish `DeploymentStarted`, `DeploymentCompleted/Failed` events
- Vivre Card checkpointing

---

### Phase 15: Voyage Pipeline (LangGraph End-to-End)
**Produces**: Complete LangGraph graph wiring all 5 crew agents into the structured pipeline with state machine transitions
**Depends on**: Phases 10-14 (all crew agents)
**Risk**: High — integration of all agents, state transitions, error recovery
**Prompt**: `pdd/prompts/features/pipeline/grandline-15-voyage-pipeline.md`

Deliverables:
- Master LangGraph graph: Captain → Navigator → Doctor → Shipwrights → Doctor (validate) → Helmsman
- State machine: `CHARTED → PLANNING → PDD → TDD → BUILDING → REVIEWING → DEPLOYING → COMPLETED`
- Error states: `FAILED`, `PAUSED`, `PARKED`
- Transition guards (e.g., can't enter BUILDING until TDD tests exist)
- Parallel Shipwright execution where phases are independent
- REST API: `POST /api/v1/voyages/{id}/start`, `GET /api/v1/voyages/{id}/status`
- SSE endpoint: `GET /api/v1/voyages/{id}/stream` (live pipeline output)
- Full integration test: submit task → all agents run → code deployed

---

### Phase 16: Observation Deck (Real-time Dashboard)
**Produces**: Three-view dashboard (Sea Chart, Crew Map, Ship's Log) with real-time updates via WebSocket + SSE
**Depends on**: Phase 4 (Auth), Phase 15 (Voyage Pipeline APIs + events)
**Risk**: High — real-time UI with three complex views
**Prompt**: `pdd/prompts/features/observation-deck/grandline-16-observation-deck.md`

Deliverables:
- **Sea Chart** (Board View): Kanban-style columns for pipeline stages, tasks flow left-to-right
- **Crew Map** (Graph View): Live DAG visualization of agents, edges show Den Den Mushi messages
- **Ship's Log** (Timeline View): Chronological feed of crew actions, filterable by crew member
- WebSocket connection for real-time state changes
- SSE connection for agent output streaming
- Zustand stores for Observation Deck state
- React Query integration for REST data
- Responsive layout, dark mode (nautical theme)

---

### Phase 17: User Intervention System
**Produces**: Ability to pause, resume, redirect agents and inject context mid-voyage from the Observation Deck
**Depends on**: Phase 16 (Observation Deck UI), Phase 15 (Voyage Pipeline control)
**Risk**: Medium — must safely interrupt running agents without losing state
**Prompt**: `pdd/prompts/features/intervention/grandline-17-user-intervention.md`

Deliverables:
- Pause/resume any agent mid-execution (Vivre Card checkpoint on pause)
- Redirect work: reassign a phase to a different approach
- Inject context: add instructions to a running agent's context
- Cancel voyage: graceful shutdown with Vivre Card preservation
- WebSocket commands from Observation Deck → backend
- REST API: `POST /api/v1/voyages/{id}/pause`, `/resume`, `/inject`, `/cancel`
- Confirmation UI for destructive actions

---

### Phase 18: Production Deployment (Kubernetes + Helm)
**Produces**: Kubernetes manifests, Helm charts, production CI/CD pipeline, monitoring
**Depends on**: Phase 15 (working pipeline), Phase 17 (complete feature set)
**Risk**: Medium — K8s configuration, secrets management, scaling
**Prompt**: `pdd/prompts/features/deployment/grandline-18-production-k8s.md`

Deliverables:
- Helm chart with values per environment (dev, staging, prod)
- K8s manifests: FastAPI deployment, Next.js deployment, PostgreSQL StatefulSet, Redis deployment
- Sandbox pods: dynamic pod creation for agent execution (gVisor runtime class)
- GitHub Actions: build → push images → deploy to staging → manual gate → deploy to prod
- Health checks and readiness probes
- Resource limits and autoscaling
- Secrets management via K8s secrets
- Monitoring: structured logging, basic alerting

---

## Risks & Unknowns

- **Poneglyph quality**: The Navigator's prompt generation quality will determine the entire platform's output quality. May need iteration and eval cycles (Phase 11).
- **gVisor compatibility**: Some syscalls may not be supported by gVisor. Need to test that agent workloads (Python, Node.js, git operations) run correctly under runsc. The swappable ExecutionBackend lets us fall back if needed.
- **LangGraph state size**: Large voyages with many phases may produce large LangGraph state objects. Need to validate Vivre Card serialization performance.
- **Real-time performance**: Three simultaneous real-time views (Sea Chart, Crew Map, Ship's Log) may strain WebSocket connections. May need event throttling or view-specific subscriptions.
- **Git conflict handling**: Parallel Shipwrights on independent phases should be conflict-free, but overlapping file edits need a strategy (fail-fast decided in decisions.md).

## Decisions Needed
- None — all major architectural decisions are logged in `decisions.md`. Containerized execution with gVisor confirmed, behind swappable Execution Service boundary.
