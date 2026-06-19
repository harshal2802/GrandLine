# Eval: task-filtering (chain)

**Prompts**: pdd/prompts/features/tasks/task-filtering-01-schema.md, task-filtering-02-api.md
**Level**: 2 (diff comparison)
**Last run**: 2026-02-15
**Baseline**: Run from 2026-02-10

## Criteria (both prompts)

### Prompt 01 — Database query layer

- [ ] `findMany` method accepts filter, sort, pagination
- [ ] Uses Prisma `where` clauses, no raw SQL
- [ ] Cursor-based pagination, not offset
- [ ] `hasNextPage` boolean included in response
- [ ] Limit clamped between 1 and 100
- [ ] Case-insensitive search on title and description

### Prompt 02 — API endpoint

- [ ] Reuses types from Prompt 01 (no redefinition)
- [ ] Comma-separated query params parsed in Zod validator
- [ ] Sort field validated against allowed list
- [ ] Pagination metadata in response body

### Diff against baseline

- [ ] Output structure matches baseline (same files, same interfaces)
- [ ] No new dependencies introduced
- [ ] Filter interface unchanged (or change is intentional)

## Run log

| Run | Date | Prompt | Baseline match? | Notes |
|---|---|---|---|---|
| 1 | | 01 | | |
| 1 | | 02 | | |
