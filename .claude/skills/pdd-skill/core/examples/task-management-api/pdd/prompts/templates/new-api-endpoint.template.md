# Prompt: <METHOD> /api/v1/<resource>

**File**: pdd/prompts/features/<area>/<feature-name>.md
**Created**: <date>
**Project type**: Backend / API

## Context

<paste relevant section from pdd/context/project.md — tech stack, existing models, auth approach>

## Task

Create the `<METHOD> /api/v1/<resource>` endpoint that <does what>. Implement the full vertical slice: <list layers — e.g., Prisma schema, repository, service, controller, route, validator, tests>.

## Input

<request body schema or query parameters>

Field rules:
- `<field>` (<type>, <required/optional>): <validation rules>

## Output format

Return these files:

1. `prisma/schema.prisma` — add or update the `<Model>` model
2. `src/repositories/<resource>-repository.ts` — data access methods
3. `src/services/<resource>-service.ts` — business logic
4. `src/validators/<action>-<resource>.validator.ts` — Zod schema for the request
5. `src/controllers/<resource>-controller.ts` — request handling
6. `src/routes/<resource>-routes.ts` — route wiring with `requireAuth`
7. `tests/integration/<action>-<resource>.test.ts` — integration tests

## Constraints

- Follow controller/service/repository layering
- Validate input before business logic
- Return consistent error shape: `{ error: { code, message, details? } }`
- <additional endpoint-specific constraints>

## Examples

**Success case:**

Request:
```
<METHOD> /api/v1/<resource>
Authorization: Bearer <valid-jwt>
Content-Type: application/json

<example request body>
```

Response (`<status>`):
```json
<example response body>
```

**Error case:**

Request:
```
<example bad request>
```

Response (`<error status>`):
```json
{
  "error": {
    "code": "<ERROR_CODE>",
    "message": "<human-readable message>",
    "details": {}
  }
}
```
