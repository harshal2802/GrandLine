# GrandLine Conventions

**Last updated**: 2026-04-04

## Development methodology
- **PDD first**: Every feature starts with context → research (if complex) → plan → prompts → review
- **TDD first**: Write failing tests before implementation code. No exceptions.
- **PR-based workflow**: All changes go through PRs against `main`. No direct commits to `main`.
- **Issue-driven**: Every PR links to a GitHub issue. Plan phases become issues.

## Source directory structure
All application code lives under `src/`. Nothing outside `src/` except config, docs, and PDD files.

```
src/
  frontend/           — Next.js application
    app/              — App Router pages and layouts
    components/       — Shared UI components
    hooks/            — Custom React hooks
    lib/              — Utilities, API clients
    stores/           — Zustand stores
    types/            — Frontend-specific TypeScript types
  backend/            — FastAPI application
    api/              — Route handlers (REST, SSE, WebSocket)
      v1/             — Versioned API routes
    core/             — Config, security, dependencies
    models/           — SQLAlchemy models
    schemas/          — Pydantic request/response schemas
    services/         — Business logic layer
    agents/           — LangGraph agent definitions and workflows
    workers/          — Celery task definitions
  shared/             — Shared types, schemas, constants
  infra/              — Docker, Kubernetes, Helm configs
    docker/           — Dockerfiles and docker-compose
    k8s/              — Kubernetes manifests
    helm/             — Helm charts
```

## Documentation
- All docs live under `docs/` at the repo root
- Docs auto-deploy to GitHub Pages via GitHub Actions on merge to `main`
- When a feature changes, its docs MUST be updated in the same PR
- API docs auto-generated from FastAPI OpenAPI spec

## Frontend conventions

### Naming
- Components: PascalCase (`UserCard.tsx`)
- Hooks: camelCase, prefixed with `use` (`useWorkflowStatus.ts`)
- Utilities: camelCase (`formatDate.ts`)
- Pages/routes: lowercase, kebab-case (`/workflow-builder`)
- CSS: Tailwind utility classes only

### Components
- One component per file
- File name matches component name
- Co-locate tests with the component (`ComponentName.test.tsx`)
- Define prop types explicitly with `interface` — no `any`
- Required props first, optional props last

### State
- Keep state as local as possible
- Zustand for app-wide state only (auth, theme, active workflow)
- React Query for all server state — no manual fetch in components
- Loading, error, and empty states required for every async operation

### Rendering strategy
- Public pages (`/`, `/features`, `/docs`): SSG with Framer Motion animations
- Dashboard (`/app/*`): CSR, behind auth middleware
- No server components for real-time dashboard views

## Backend conventions

### Naming
- Files: snake_case (`workflow_service.py`)
- Classes: PascalCase (`WorkflowService`)
- Functions/variables: snake_case (`create_workflow`)
- Database tables: snake_case, plural (`agent_workflows`)
- API endpoints: kebab-case, plural nouns (`/api/v1/agent-workflows`)

### Architecture
- Routes/controllers separate from business logic
- Business logic in service layer (`services/`)
- Data access via SQLAlchemy models — no raw SQL in route handlers
- Pydantic schemas for all request/response validation

### Error handling
- Consistent error shape: `{ "error": { "code": "<ERROR_CODE>", "message": "<human readable>" } }`
- Never expose internal error details to clients
- Use correct HTTP status codes
- Log errors with context (user ID, request ID, timestamp)

### Validation
- Validate all inputs at the API boundary with Pydantic
- Return 400 with field-level error messages on validation failure

### Database
- All schema changes via Alembic migrations, never direct DB edits
- Transactions required for multi-step writes
- Index foreign keys and commonly filtered columns

### Security
- Auth middleware at router level, not per-handler
- Secrets via environment variables — never in code
- Parameterized queries only (SQLAlchemy handles this)
- CORS configured explicitly — no wildcard in production

## API protocols
- **REST**: CRUD operations on resources (workflows, agents, jobs)
- **SSE**: LLM token streaming, agent step-by-step output (server → client)
- **WebSocket**: Bidirectional — user intervention mid-execution, live dashboard status

## Git conventions
- Branch naming: `feat/issue-<number>-<short-description>`, `fix/issue-<number>-<short-description>`
- Commit messages: Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`)
- Every PR must pass tests and PDD review before merge
- Squash merge to `main`

## Testing
- **TDD**: Write the failing test first, then implement
- Frontend: Vitest + React Testing Library
- Backend: pytest + httpx (async test client)
- Minimum coverage: aim for meaningful coverage, not arbitrary percentages
- Test files co-located with source: `*.test.tsx`, `*_test.py`

## AI / Agent conventions
- Each agent workflow is a LangGraph graph definition
- Workflows are configurable: LLM provider, model, temperature, tools
- Agent state is persisted to PostgreSQL for resumability
- All agent executions are logged for observability
