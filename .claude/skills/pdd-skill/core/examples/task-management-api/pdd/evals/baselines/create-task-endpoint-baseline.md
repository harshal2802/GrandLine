# Baseline: create-task-endpoint

**Prompt**: pdd/prompts/features/tasks/create-task-endpoint.md
**Saved from run on**: 2026-02-10
**Model**: Claude (February 2026)

## Expected output structure

- 8 files produced (schema, repository, service, validator, controller, routes, unit tests, integration tests)
- Prisma `Task` model with 10 fields
- Zod schema in `src/validators/create-task.validator.ts`
- Service validates `assigned_to` exists before creating
- Integration tests cover: success (201), missing title (400), invalid priority (400), unauthenticated (401)

## Key patterns to preserve

- `created_by` sourced from JWT, not request body
- `status` defaults to `open`, not settable by client
- Error shape: `{ error: { code, message, details? } }`

## Diff checklist

When comparing new output against this baseline:

- [ ] Same number of files produced
- [ ] Same layering (no Prisma in controller, no HTTP in service)
- [ ] Same validation rules applied
- [ ] Same error response structure
- [ ] No new dependencies introduced without justification
