# GrandLine Conventions

**Last updated**: 2026-04-05

## Philosophy
- **Local-first**: Docker Compose is the primary dev environment. Everything runs locally.
- **The Log Pose (PDD + TDD)**: No feature ships without Poneglyphs (PDD prompts) AND health checks (tests) written first. This is non-negotiable.
- **Default-deny**: Auth, network, container permissions — everything is closed unless explicitly opened.
- **No work lost**: Vivre Card checkpointing ensures agent state survives provider failures, crashes, and migrations.

## Development methodology
- **PDD first**: Navigator writes Poneglyphs (prompt artifacts) before any code is written
- **TDD first**: Doctor writes health checks (failing tests) before Shipwrights implement
- **Full pipeline**: PDD → TDD → Implement → Review → Deploy — no shortcuts
- **PR-based workflow**: All changes go through PRs against `main`. No direct commits to `main`.
- **Issue-driven**: Every PR links to a GitHub issue. Plan phases become issues.

## One Piece terminology in code
Use themed names consistently throughout the codebase:

| Code concept | Themed name | Used in |
|---|---|---|
| Agent definitions | Crew members (Captain, Navigator, etc.) | Class names, module names |
| PDD prompt files | Poneglyphs | File names, comments, docs |
| LLM gateway module | Dial System | Module name, API references |
| State checkpoints | Vivre Cards | Model names, function names |
| Message bus events | Den Den Mushi | Module name, event references |
| Dashboard app | Observation Deck | Route names, component names |
| Task submission | Chart a Course | API endpoint names, UI labels |
| Task plan | Voyage Plan | Model names, UI labels |

## Source directory structure
All application code lives under `src/`. Nothing outside `src/` except config, docs, and PDD files.

```
src/
  frontend/                 — Next.js application
    app/                    — App Router pages and layouts
      (public)/             — Landing page (SSG, Framer Motion)
      (app)/                — Observation Deck (CSR, behind auth)
        sea-chart/          — Board View (task pipeline)
        crew-map/           — Graph View (live DAG)
        ships-log/          — Timeline View (agent actions)
    components/             — Shared UI components
    hooks/                  — Custom React hooks
    lib/                    — Utilities, API clients
    stores/                 — Zustand stores
    types/                  — Frontend-specific TypeScript types
  backend/                  — FastAPI application
    api/                    — Route handlers (REST, SSE, WebSocket)
      v1/                   — Versioned API routes
    core/                   — Config, security, dependencies
    crew/                   — Agent persona definitions
      captain.py            — PM agent (task decomposition)
      navigator.py          — Architect agent (Poneglyph drafting)
      shipwright.py         — Developer agent (code generation)
      doctor.py             — QA agent (test writing + validation)
      helmsman.py           — DevOps agent (deployment)
    dial_system/            — LLM gateway
      router.py             — DialSystemRouter (role routing + failover)
      factory.py            — Adapter factory (create_adapter, build_router_from_config)
      rate_limiter.py       — Redis sliding-window rate limiter
      adapters/             — Provider adapters
        base.py             — ProviderAdapter ABC + ProviderError
        anthropic.py        — Anthropic SDK adapter
        openai.py           — OpenAI SDK adapter
        ollama.py           — Ollama HTTP adapter (httpx)
    den_den_mushi/          — Message bus (Redis Streams)
    models/                 — SQLAlchemy models
    schemas/                — Pydantic request/response schemas
    services/               — Business logic layer
  shared/                   — Shared types, schemas, constants
  infra/                    — Docker, Kubernetes, Helm configs
    docker/                 — Dockerfiles and docker-compose
    k8s/                    — Kubernetes manifests
    helm/                   — Helm charts
    sandboxes/              — Agent execution sandbox configs
```

## Documentation
- All docs live under `docs/` at the repo root
- Docs auto-deploy to GitHub Pages via GitHub Actions on merge to `main`
- When a feature changes, its docs MUST be updated in the same PR
- API docs auto-generated from FastAPI OpenAPI spec
- Use One Piece terminology in docs — it's part of the product identity

## Frontend conventions

### Naming
- Components: PascalCase (`SeaChart.tsx`, `CrewMap.tsx`)
- Hooks: camelCase, prefixed with `use` (`useVoyageStatus.ts`)
- Utilities: camelCase (`formatTimestamp.ts`)
- Pages/routes: lowercase, kebab-case (`/sea-chart`, `/crew-map`, `/ships-log`)
- CSS: Tailwind utility classes only

### Components
- One component per file
- File name matches component name
- Co-locate tests with the component (`ComponentName.test.tsx`)
- Define prop types explicitly with `interface` — no `any`
- Required props first, optional props last

### State
- Keep state as local as possible
- Zustand for app-wide state only (auth, active voyage, crew status)
- React Query for all server state — no manual fetch in components
- Loading, error, and empty states required for every async operation

### Rendering strategy
- Public landing page (`/`): SSG with Framer Motion animations
- Observation Deck (`/app/*`): CSR, behind auth middleware
- No server components for real-time Observation Deck views

### Real-time updates
- SSE for agent output streaming (token-by-token from Dial System)
- WebSocket for Observation Deck live updates (Crew Map, Sea Chart state changes)
- React Query + WebSocket for automatic cache invalidation

## Backend conventions

### Naming
- Files: snake_case (`voyage_service.py`, `captain.py`)
- Classes: PascalCase (`CaptainAgent`, `DialSystemRouter`, `VivreCard`)
- Functions/variables: snake_case (`chart_course`, `create_vivre_card`)
- Database tables: snake_case, plural (`voyages`, `vivre_cards`, `crew_actions`)
- API endpoints: kebab-case, plural nouns (`/api/v1/voyages`, `/api/v1/crew-actions`)

### Architecture
- Routes/controllers separate from business logic
- Business logic in service layer (`services/`)
- Agent definitions in crew layer (`crew/`)
- LLM routing in Dial System (`dial_system/`)
- Data access via SQLAlchemy models — no raw SQL in route handlers
- Pydantic schemas for all request/response validation

### Error handling
- Consistent error shape: `{ "error": { "code": "<ERROR_CODE>", "message": "<human readable>" } }`
- Never expose internal error details to clients
- Use correct HTTP status codes
- Log errors with context (user ID, request ID, voyage ID, crew member)

### Validation
- Validate all inputs at the API boundary with Pydantic
- Return 400 with field-level error messages on validation failure

### Database
- All schema changes via Alembic migrations, never direct DB edits
- Transactions required for multi-step writes
- Index foreign keys and commonly filtered columns
- Vivre Card state stored as JSONB for flexible agent snapshots

### Security
- **Default-deny** at middleware level — every route is closed unless explicitly opened
- Secrets via environment variables — never in code
- Parameterized queries only (SQLAlchemy handles this)
- CORS configured explicitly — no wildcard in production
- Agent execution in sandboxed containers — no host access

## Message bus (Den Den Mushi)
- Built on **Redis Streams** — not Celery
- Inter-agent communication: crew members publish events, others subscribe
- Event schema defined in Pydantic — no ad-hoc messages
- Consumer groups for reliable delivery
- Dead letter handling for failed messages

## Agent execution
- Each agent runs in a **sandboxed container** — isolated from host and other agents
- Agents work in **real git repos** with **per-agent branches**
- Agent state checkpointed as **Vivre Cards** in PostgreSQL
- On provider failure: checkpoint → migrate to fallback → resume (or park non-critical agents)
- All actions logged to Ship's Log for full observability

## Dial System (LLM Gateway)
- Config-driven: each crew role maps to a provider + model via DialConfig JSONB
- Provider adapters: `ProviderAdapter` ABC — Anthropic, OpenAI, Ollama implementations
- Adapter factory: `create_adapter()` creates adapters from strings; `build_router_from_config()` wires the full router from DB config
- Failover chain: primary → fallback chain → `RuntimeError("All providers exhausted")`
- Rate limiter: Redis sorted-set sliding window tracking tokens + requests per provider per minute
- Error handling: SDK errors (`RateLimitError`, `APIError`) caught and re-raised as `ProviderError` for uniform failover
- SSE streaming: `POST /completions/stream` with `text/event-stream` and `data: {token}\n\n` format
- Failover applies to both `route()` and `stream()` — identical logic
- All LLM calls go through the Dial System — no direct provider calls

## API protocols
- **REST**: CRUD operations on voyages, crew configs, Vivre Cards
- **SSE**: LLM token streaming from Dial System, agent step-by-step output
- **WebSocket**: Bidirectional — user intervention mid-voyage, live Observation Deck updates

## Git conventions
- Branch naming: `feat/issue-<number>-<short-description>`, `fix/issue-<number>-<short-description>`
- Agent branches: `agent/<crew-member>/<voyage-id>` (e.g., `agent/shipwright/voyage-42`)
- Commit messages: Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`)
- Every PR must pass tests and PDD review before merge
- Squash merge to `main`

## Testing
- **TDD**: Doctor writes failing health checks first, then Shipwrights implement
- Frontend: Vitest + React Testing Library
- Backend: pytest + httpx (async test client)
- Minimum coverage: aim for meaningful coverage, not arbitrary percentages
- Test files co-located with source: `*.test.tsx`, `*_test.py`

## Deployment tiers
- **Preview** (auto): Automatic on branch push — no approval needed
- **Staging** (semi-auto): Automatic on PR merge to staging — lightweight review
- **Production** (PR-only): PR merge to main — full review required
