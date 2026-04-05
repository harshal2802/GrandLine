# Prompt: Auth & Security

**File**: pdd/prompts/features/auth/grandline-04-auth.md
**Created**: 2026-04-05
**Depends on**: Phase 3 (Database Models & Core Schemas)
**Project type**: Full-stack (FastAPI + Next.js)

## Context

GrandLine is a One Piece-themed multi-agent orchestration platform. Phase 3 delivered SQLAlchemy models (User, Voyage, etc.), Pydantic schemas, and Alembic migrations. The User model has `id`, `email`, `username`, `hashed_password`, `is_active`, `created_at`, `updated_at`. The backend uses FastAPI (async), SQLAlchemy 2.0 with `mapped_column`, and psycopg. Redis is available for session/token storage.

The project follows **default-deny** security: every route is closed unless explicitly opened. Auth middleware must enforce this at the FastAPI level, and Next.js middleware must protect Observation Deck routes (`/app/*`).

## Task

Implement a complete JWT authentication system with:

1. **Backend (FastAPI)**:
   - `app/core/security.py`: JWT token creation/verification (access + refresh), password hashing (bcrypt)
   - `app/services/auth_service.py`: Register, login, refresh business logic
   - `app/api/v1/auth.py`: Three endpoints:
     - `POST /api/v1/auth/register` — create user, return token pair
     - `POST /api/v1/auth/login` — verify credentials, return token pair
     - `POST /api/v1/auth/refresh` — rotate refresh token, return new pair
   - `app/api/v1/dependencies.py`: `get_current_user` dependency (extracts + validates JWT from `Authorization: Bearer` header)
   - Default-deny middleware: all `/api/v1/*` routes require auth EXCEPT explicitly allowlisted paths (health, auth endpoints, docs)

2. **Frontend (Next.js)**:
   - `middleware.ts` at project root: protect `/app/*` routes, redirect unauthenticated users to `/login`
   - Check for auth token in cookies; if missing/expired, redirect

3. **Config additions** (`app/core/config.py`):
   - `jwt_secret_key`, `jwt_algorithm` (default HS256), `access_token_expire_minutes` (default 30), `refresh_token_expire_minutes` (default 10080 = 7 days)

## Input

- Existing User model at `src/backend/app/models/user.py`
- Existing schemas at `src/backend/app/schemas/user.py` (UserCreate, UserRead)
- Existing config at `src/backend/app/core/config.py`
- Existing router at `src/backend/app/api/v1/router.py`

## Output format

- Python files following existing conventions (async, type-annotated, SQLAlchemy 2.0 style)
- Pydantic schemas for auth request/response shapes (`TokenPair`, `LoginRequest`, `RegisterRequest`)
- Alembic migration only if schema changes are needed (User model already exists)
- Next.js middleware.ts for frontend route protection
- All new files under `src/backend/app/` and `src/frontend/`

## Constraints

- Use `python-jose[cryptography]` for JWT and `passlib[bcrypt]` for password hashing
- Tokens: access token (short-lived, 30min default), refresh token (long-lived, 7 days default)
- Default-deny: middleware blocks all routes, allowlist is explicit
- Error responses follow project convention: `{ "error": { "code": "...", "message": "..." } }`
- No raw SQL — all DB access via SQLAlchemy async session
- Refresh token rotation: old refresh token invalidated when new one is issued
- Store refresh tokens in Redis with TTL for server-side invalidation
