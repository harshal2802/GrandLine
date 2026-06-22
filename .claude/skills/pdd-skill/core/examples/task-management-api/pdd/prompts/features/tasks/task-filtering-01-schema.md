# Chain: Task Filtering (Prompt 1 of 2)

# Prompt: Task filtering — database query layer

**File**: pdd/prompts/features/tasks/task-filtering-01-schema.md
**Created**: 2026-02-10
**Project type**: Backend / API

## Context

TaskFlow is a task management REST API (Node.js, Express, TypeScript, Prisma, PostgreSQL). Tasks have these columns: `id`, `title`, `description`, `status` (open/in_progress/done/closed), `priority` (low/medium/high/urgent), `due_date`, `assigned_to`, `created_by`, `created_at`, `updated_at`.

The `Task` Prisma model and basic CRUD (create, get by ID, update, delete) already exist in `src/repositories/task-repository.ts`. We now need to add filtered listing.

## Task

Add a `findMany` method to the task repository that supports filtering, sorting, and cursor-based pagination. This prompt covers the data layer only; the API endpoint is handled in a follow-up prompt.

## Input

The method should accept a filter object with this shape:

```typescript
interface TaskFilter {
  status?: TaskStatus | TaskStatus[];
  priority?: Priority | Priority[];
  assigned_to?: string;          // user UUID
  created_by?: string;           // user UUID
  due_before?: Date;
  due_after?: Date;
  search?: string;               // partial match on title and description
}

interface TaskSort {
  field: 'created_at' | 'updated_at' | 'due_date' | 'priority';
  direction: 'asc' | 'desc';
}

interface PaginationOptions {
  cursor?: string;               // task UUID — fetch items after this ID
  limit: number;                 // max 100, default 20
}
```

## Output format

Return these files:

1. `src/repositories/task-repository.ts` — updated with the `findMany(filter, sort, pagination)` method
2. `src/types/task-filters.ts` — TypeScript interfaces for the filter, sort, and pagination types
3. `src/repositories/task-repository.test.ts` — unit tests covering: no filters (returns all), single filter, multiple filters combined, search, pagination (first page, next page via cursor), sorting, and empty results

## Constraints

- Use Prisma `where` clauses; no raw SQL
- `search` should use case-insensitive `contains` on both `title` and `description` (OR)
- Cursor pagination, not offset-based — we need stable pagination for the frontend
- The response must include `hasNextPage: boolean` so the caller knows whether to request more
- Limit must be clamped between 1 and 100
- Default sort: `created_at desc`
- Do not add any route or controller code; that is Prompt 02

## Examples

```typescript
// All high-priority tasks assigned to a specific user, newest first
const result = await taskRepository.findMany(
  { priority: 'high', assigned_to: 'user-uuid' },
  { field: 'created_at', direction: 'desc' },
  { limit: 20 }
);

// result: { tasks: Task[], hasNextPage: boolean, nextCursor: string | null }
```
