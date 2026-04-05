# Prompt: Project Foundation & Infrastructure
**File**: pdd/prompts/features/foundation/grandline-01-foundation.md
**Created**: 2026-04-04
**Project type**: Full-stack AI (Next.js + FastAPI + PostgreSQL + Redis)
**Issue**: #2

## Context
GrandLine is a multi-agent orchestration platform. This is Phase 1 — the foundation that everything else builds on. Nothing exists yet except PDD context files and a README. All application code goes under `src/`. The project follows PDD + TDD methodology and uses Docker Compose for local-first development.

### Source structure (from conventions.md)
```
src/
  frontend/           — Next.js 14+ (App Router)
  backend/            — FastAPI (Python, async)
  shared/             — Shared types, schemas, constants
  infra/              — Docker, Kubernetes, Helm configs
    docker/           — Dockerfiles and docker-compose
```

### Tech stack
- **Frontend**: Next.js 14+ (App Router), TypeScript, Tailwind CSS, shadcn/ui
- **Backend**: Python 3.12+, FastAPI, SQLAlchemy, Alembic
- **Database**: PostgreSQL 16
- **Cache/Message bus**: Redis 7 (will be used for Redis Streams later)
- **Testing**: pytest + httpx (backend), Vitest + React Testing Library (frontend)
- **CI/CD**: GitHub Actions
- **Docs**: GitHub Pages, auto-deployed on merge to main

## Task
Scaffold the complete GrandLine project foundation so that `docker compose up` starts all services, tests can run, CI/CD is configured, and docs deploy to GitHub Pages.

## Input
- Existing repo: has `pdd/`, `README.md`, `.gitignore` — no application code yet
- GitHub repo: `harshal2802/GrandLine` (public, main branch protected)

## Output format
All files under `src/` following the conventions. Specifically:

### Backend (`src/backend/`)
```
src/backend/
  app/
    __init__.py
    main.py              — FastAPI app factory, CORS, middleware
    api/
      __init__.py
      v1/
        __init__.py
        router.py        — v1 API router
        health.py        — GET /api/v1/health endpoint
    core/
      __init__.py
      config.py          — Settings via pydantic-settings (env vars)
    models/
      __init__.py        — SQLAlchemy base, engine, session
  alembic/
    env.py
    alembic.ini
  requirements.txt       — Python dependencies (pinned)
  Dockerfile
  pytest.ini             — or pyproject.toml pytest config
  conftest.py            — pytest fixtures (async client, db session)
```

### Frontend (`src/frontend/`)
```
src/frontend/
  app/
    layout.tsx           — Root layout with Tailwind, metadata
    page.tsx             — Placeholder landing page
    (app)/
      layout.tsx         — Observation Deck layout (CSR, will be auth-gated)
  components/            — empty, with .gitkeep
  hooks/                 — empty, with .gitkeep
  lib/                   — empty, with .gitkeep
  stores/                — empty, with .gitkeep
  types/                 — empty, with .gitkeep
  tailwind.config.ts
  next.config.ts
  tsconfig.json
  package.json           — dependencies: next, react, tailwind, shadcn/ui, vitest, @testing-library/react
  vitest.config.ts
  Dockerfile
```

### Infrastructure (`src/infra/docker/`)
```
src/infra/docker/
  docker-compose.yml     — FastAPI, Next.js, PostgreSQL 16, Redis 7
  .env.example           — All required env vars with placeholder values
```

### CI/CD (`.github/workflows/`)
```
.github/workflows/
  ci.yml                 — On PR: lint (ruff + eslint), type-check (mypy + tsc), test (pytest + vitest)
  docs.yml               — On merge to main: deploy docs/ to GitHub Pages
```

### Docs (`docs/`)
```
docs/
  index.html             — Simple landing page: "GrandLine Documentation" with links to sections
```

## Constraints
- All code under `src/` — nothing at repo root except config files
- Backend uses async FastAPI with async SQLAlchemy
- `docker-compose.yml` lives at `src/infra/docker/docker-compose.yml` with a convenience symlink or run instruction from repo root
- PostgreSQL and Redis containers must have health checks in docker-compose
- FastAPI health endpoint returns `{"status": "healthy", "service": "grandline-api", "version": "0.1.0"}`
- Next.js placeholder page should say "GrandLine — Observation Deck coming soon" with basic Tailwind styling
- All environment variables documented in `.env.example` with comments
- GitHub Actions CI must run both backend and frontend tests
- GitHub Actions docs workflow deploys `docs/` directory to GitHub Pages
- Python linting: ruff. TypeScript linting: eslint.
- No `any` types in TypeScript
- Backend error responses follow convention: `{ "error": { "code": "...", "message": "..." } }`
- Alembic configured to connect to the same PostgreSQL as the app (via env var)
- Docker Compose uses named volumes for PostgreSQL data persistence

## Acceptance Criteria
- [ ] `docker compose up` starts FastAPI, Next.js, PostgreSQL, Redis — all healthy
- [ ] `GET /api/v1/health` returns 200 with expected JSON shape
- [ ] Next.js renders placeholder page at `http://localhost:3000`
- [ ] `pytest` runs successfully (0 tests collected, infrastructure works)
- [ ] `npx vitest run` runs successfully (0 tests collected, infrastructure works)
- [ ] GitHub Actions CI triggers on PR and runs lint + test for both frontend and backend
- [ ] GitHub Actions docs workflow deploys to GitHub Pages on merge to main
- [ ] `.env.example` documents all required environment variables
- [ ] Alembic can run `alembic upgrade head` against PostgreSQL (no migrations yet, but infrastructure works)
