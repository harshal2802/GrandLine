# PDD Reference: Backend / API Projects

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for backend and API projects (REST, GraphQL, gRPC, serverless functions, and related stacks).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- What framework and runtime? (Express, FastAPI, Django, Rails, Go, etc.)
- REST, GraphQL, gRPC, or mixed?
- What database(s) and ORM? (Postgres + Prisma, MySQL + SQLAlchemy, MongoDB + Mongoose, etc.)
- How is authentication handled? (JWT, sessions, OAuth, API keys)
- Is there an API spec? (OpenAPI / Swagger, GraphQL schema, Protobuf)
- What's the deployment target? (serverless, containers, VM, managed platform)
- Any rate limiting, caching, or queue systems in use?

### Extended `pdd/context/project.md` sections for backend

```markdown
## API design
- Style: REST / GraphQL / gRPC
- Versioning strategy: (e.g. /v1/ prefix, headers)
- Auth method:
- API spec location:

## Data layer
- Primary database:
- ORM / query builder:
- Migration tool:
- Caching layer: (Redis, Memcached, none)

## Infrastructure
- Deployment: (serverless / container / VM)
- Queue / async: (SQS, RabbitMQ, BullMQ, none)
- Secrets management:
```

---

## Conventions Starter (Workflow 2)

```markdown
# Backend Conventions

## Project structure
- Routes / controllers separate from business logic
- Business logic in service layer
- Data access in repository layer
- No database queries in route handlers

## Naming
- Files: kebab-case (e.g. `user-service.ts`)
- Classes: PascalCase
- Functions / variables: camelCase
- Database tables: snake_case
- API endpoints: kebab-case, plural nouns (e.g. `/api/v1/user-profiles`)

## Error handling
- All errors caught and returned in consistent shape: `{ error: { code, message } }`
- Never expose internal error details to clients
- Use HTTP status codes correctly (400 client errors, 500 server errors)
- Log errors server-side with context (user ID, request ID, timestamp)

## Validation
- Validate all inputs at the API boundary before they reach business logic
- Use [Zod / Joi / Pydantic / class-validator — pick one]
- Return 400 with field-level error messages on validation failure

## Database
- No raw queries — use ORM or query builder
- All schema changes via migrations, never direct DB edits
- Transactions required for multi-step writes

## Security
- Sanitize all user inputs
- Parameterized queries only — no string interpolation in SQL
- Auth middleware applied at router level, not per-handler
- Secrets via environment variables — never in code
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New API endpoint

```markdown
# Prompt: <METHOD> /api/<resource>

## Task
Create a <GET | POST | PUT | DELETE> endpoint at `/api/v1/<resource>` that <does what>.

## Request
- Method: <METHOD>
- Auth required: yes / no
- Request body / params: <schema or description>

## Response
- Success: <HTTP status> + <response shape>
- Error cases: <list of error conditions and status codes>

## Business logic
- <step-by-step logic the handler should implement>
- <validation rules>
- <any side effects: emails, queue events, etc.>

## Constraints
- Follow service/repository pattern in the codebase
- Validate input before any business logic
- No database logic in the route handler
- Return consistent error shape: `{ error: { code, message } }`
```

### Database migration

```markdown
# Prompt: Migration — <description>

## Task
Write a database migration that <adds / modifies / removes> <table or column>.

## Schema change
<describe the change in plain language>

## Constraints
- Use [Prisma / Alembic / Knex / ActiveRecord — match existing tool]
- Include both up and down migrations
- No destructive changes without a data migration plan
- Index any new foreign keys
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Security**
- [ ] Auth / authorization checked before data access?
- [ ] All inputs validated and sanitized?
- [ ] No SQL string interpolation?
- [ ] Secrets in env vars, not in code?
- [ ] Error responses don't leak internal details?

**Data integrity**
- [ ] Multi-step writes wrapped in transactions?
- [ ] Foreign key constraints respected?
- [ ] Race conditions considered for concurrent writes?

**API design**
- [ ] Correct HTTP status codes used?
- [ ] Consistent error response shape?
- [ ] Pagination for list endpoints?
- [ ] Idempotent where it should be (PUT, DELETE)?

**Performance**
- [ ] N+1 query problems? (check loops that query DB)
- [ ] Missing indexes on filtered/sorted columns?
- [ ] Expensive operations offloaded to async/queue?

**Observability**
- [ ] Errors logged with sufficient context?
- [ ] Request IDs propagated through logs?
- [ ] Sensitive data absent from logs?
