# Chain: Task Filtering (Prompt 2 of 2)

# Prompt: Task filtering — API endpoint

**File**: pdd/prompts/features/tasks/task-filtering-02-api.md
**Created**: 2026-02-10
**Project type**: Backend / API
**Depends on**: Output from `task-filtering-01-schema.md`

## Context

TaskFlow is a task management REST API (Node.js, Express, TypeScript, Prisma, PostgreSQL). In the previous prompt, we built a `findMany` method on `TaskRepository` that accepts filter, sort, and pagination parameters and returns `{ tasks, hasNextPage, nextCursor }`.

The `TaskFilter`, `TaskSort`, and `PaginationOptions` types are defined in `src/types/task-filters.ts`.

## Task

Create the `GET /api/v1/tasks` endpoint that exposes the repository's filtering capabilities through query string parameters. Implement the service method, Zod validator, controller, and route wiring.

## Input

The endpoint accepts query string parameters:

```
GET /api/v1/tasks?status=open,in_progress&priority=high&assigned_to=uuid&search=onboarding&due_before=2026-04-01&sort=due_date:asc&cursor=task-uuid&limit=25
```

Parameter rules:
- `status` (optional): comma-separated list of valid statuses
- `priority` (optional): comma-separated list of valid priorities
- `assigned_to` (optional): single user UUID
- `created_by` (optional): single user UUID
- `search` (optional): string, 1-200 characters
- `due_before` (optional): ISO 8601 date
- `due_after` (optional): ISO 8601 date
- `sort` (optional): `field:direction` format, default `created_at:desc`
- `cursor` (optional): UUID of the last item from previous page
- `limit` (optional): integer 1-100, default 20

## Output format

Return these files:

1. `src/validators/list-tasks.validator.ts` — Zod schema that parses and transforms query string parameters into the `TaskFilter`, `TaskSort`, and `PaginationOptions` types
2. `src/services/task-service.ts` — add a `listTasks(filter, sort, pagination)` method that calls the repository
3. `src/controllers/task-controller.ts` — add a `list` handler that validates query params, calls the service, and formats the response
4. `src/routes/task-routes.ts` — wire `GET /` to the controller, apply `requireAuth`
5. `tests/integration/list-tasks.test.ts` — integration tests

## Constraints

- The controller must use the types and repository method created in Prompt 01 — do not redefine them
- Parse comma-separated query params into arrays in the Zod validator, not in the controller
- Validate that `sort` field is one of the allowed fields before passing to the service
- Return pagination metadata alongside the task list (see example below)
- An authenticated user can see all tasks (no row-level access control for now)
- Follow the existing error shape: `{ error: { code, message, details? } }`

## Examples

**Successful filtered list:**

Request:
```
GET /api/v1/tasks?status=open&priority=high,urgent&limit=2
Authorization: Bearer <valid-jwt>
```

Response (`200 OK`):
```json
{
  "data": {
    "tasks": [
      {
        "id": "task-uuid-1",
        "title": "Fix critical auth bug",
        "status": "open",
        "priority": "urgent",
        "due_date": "2026-02-15",
        "assigned_to": "user-uuid",
        "created_by": "user-uuid",
        "created_at": "2026-02-10T08:00:00.000Z",
        "updated_at": "2026-02-10T08:00:00.000Z"
      },
      {
        "id": "task-uuid-2",
        "title": "Review API design doc",
        "status": "open",
        "priority": "high",
        "due_date": null,
        "assigned_to": null,
        "created_by": "user-uuid",
        "created_at": "2026-02-09T14:00:00.000Z",
        "updated_at": "2026-02-09T14:00:00.000Z"
      }
    ],
    "pagination": {
      "next_cursor": "task-uuid-2",
      "has_next_page": true,
      "limit": 2
    }
  }
}
```

**Invalid sort parameter:**

Request:
```
GET /api/v1/tasks?sort=title:asc
Authorization: Bearer <valid-jwt>
```

Response (`400 Bad Request`):
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid query parameters",
    "details": {
      "sort": "Sort field must be one of: created_at, updated_at, due_date, priority"
    }
  }
}
```
