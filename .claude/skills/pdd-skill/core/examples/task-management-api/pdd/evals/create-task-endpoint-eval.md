# Eval: create-task-endpoint

**Prompt**: pdd/prompts/features/tasks/create-task-endpoint.md
**Last run**: 2026-02-03

## Criteria

### Correctness

- [ ] Code compiles with `tsc --noEmit` (strict mode, no errors)
- [ ] All tests pass (`vitest run`)
- [ ] POST /tasks with valid body returns 201 and the created task
- [ ] Missing `title` returns 400 with field-level error
- [ ] Empty `title` returns 400
- [ ] `title` over 200 characters returns 400
- [ ] Invalid `priority` value returns 400
- [ ] `due_date` in the past returns 400
- [ ] Non-existent `assigned_to` UUID returns 404
- [ ] Unauthenticated request returns 401
- [ ] `status` defaults to `open` and cannot be set by the client
- [ ] `created_by` is taken from the JWT, not the request body

### Project fit

- [ ] Follows controller/service/repository layering (no Prisma in controller, no HTTP in service)
- [ ] Zod schema defined in `src/validators/`, not inline
- [ ] Error responses use `{ error: { code, message, details? } }` shape
- [ ] Task ID is a UUID
- [ ] File names use kebab-case
- [ ] No `any` types

### Maintainability

- [ ] Service layer has unit tests with mocked repository
- [ ] Integration tests use Supertest and cover success + error paths
- [ ] No hard-coded test data; uses factories or builder functions
- [ ] Custom error classes used (not raw `throw new Error`)

### Security

- [ ] `requireAuth` middleware applied at the router level
- [ ] No raw SQL queries
- [ ] Error responses do not leak stack traces or internal details
- [ ] `assigned_to` validated against the database, not just as a UUID format

### Prompt quality signals

- [ ] Output required minimal manual edits to work (< 5 lines changed)
- [ ] Output did not hallucinate imports or non-existent utility functions
- [ ] Output did not include unrequested features (no PATCH, DELETE, or GET)
- [ ] Running the prompt 3 times produces structurally consistent output

## Run log

| Run | Date | Pass | Fail | Notes |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

## Notes

_Record anything surprising, inconsistent, or worth feeding back into the prompt._
