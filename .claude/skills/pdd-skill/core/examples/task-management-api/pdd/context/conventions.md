# TaskFlow API — Coding Conventions

## Project structure

```
src/
├── controllers/     # Request parsing, validation, response formatting
├── services/        # Business logic (no DB or HTTP awareness)
├── repositories/    # Prisma queries, data access only
├── middleware/       # Auth, error handling, request logging
├── routes/          # Express router definitions
├── validators/      # Zod schemas for request validation
├── types/           # Shared TypeScript interfaces and types
├── utils/           # Pure helper functions
├── jobs/            # BullMQ job processors
└── config/          # Environment config, constants
```

## Naming

- **Files**: kebab-case (`task-service.ts`, `create-task.validator.ts`)
- **Classes**: PascalCase (`TaskService`, `TaskRepository`)
- **Functions / variables**: camelCase (`getTaskById`, `isOverdue`)
- **Database tables**: snake_case, plural (`tasks`, `task_labels`)
- **Database columns**: snake_case (`created_at`, `assigned_to`)
- **API endpoints**: kebab-case, plural nouns (`/api/v1/tasks`, `/api/v1/task-labels`)
- **Environment variables**: SCREAMING_SNAKE_CASE (`DATABASE_URL`, `JWT_SECRET`)

## Layering rules

1. **Controllers** call **services**, never repositories directly.
2. **Services** call **repositories** and other services.
3. **Repositories** call Prisma and return plain objects; no HTTP or business logic.
4. Each layer only imports from the layer directly below it.

## Error handling

- All errors returned as `{ error: { code: string, message: string, details?: object } }`.
- Use custom error classes (`NotFoundError`, `ValidationError`, `AuthorizationError`) that extend a base `AppError`.
- Controllers catch service errors and map them to HTTP status codes.
- Never expose internal error messages or stack traces to clients.
- Log all 5xx errors with request ID, user ID, and timestamp.

## Validation

- Define one Zod schema per request shape in `src/validators/`.
- Validate in the controller before calling the service.
- Return `400` with field-level errors: `{ error: { code: "VALIDATION_ERROR", message: "...", details: { field: "reason" } } }`.

## Database

- All queries go through Prisma; no raw SQL.
- Schema changes only through `prisma migrate dev`.
- Multi-step writes use Prisma interactive transactions.
- Always include `created_at` and `updated_at` on every table.

## Testing

- Unit tests for services: mock the repository layer.
- Integration tests for endpoints: use Supertest against a test database.
- Test files live next to source files: `task-service.ts` / `task-service.test.ts`.
- Use factories for test data, not hard-coded objects.

## Security

- Auth middleware applied at the router level via `requireAuth`.
- All user-facing IDs are UUIDs, never auto-increment integers.
- Rate limiting on auth endpoints (10 req/min) and general API (100 req/min).
- CORS configured for known frontend origins only.
