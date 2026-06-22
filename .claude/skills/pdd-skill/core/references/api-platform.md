# PDD Reference: API Platform / SDK

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for API-as-product and SDK projects — public-facing APIs consumed by external developers, partner integrations, multi-language SDK generation, and developer platform tooling.

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- Who are the API consumers (external developers, partners, internal teams)?
- API style (REST, GraphQL, gRPC, or mixed)?
- Spec format (OpenAPI 3.x, AsyncAPI, GraphQL SDL, Protobuf)?
- SDK languages to support (JavaScript, Python, Go, Java, Ruby, etc.)?
- SDK generation approach (OpenAPI codegen, hand-written, Stainless, Fern)?
- Versioning strategy (URL path, header, query param)?
- Auth model for consumers (API keys, OAuth2, JWT)?
- Rate limiting model (per-key, per-plan, per-endpoint)?
- Documentation platform (Redoc, Mintlify, ReadMe, Stoplight, custom)?
- Webhook support needed?

### Extended `pdd/context/project.md` sections for API platform / SDK

```markdown
## API Design Principles
- Style: (REST, GraphQL, gRPC, mixed)
- Spec format: (OpenAPI 3.x, AsyncAPI, GraphQL SDL, Protobuf)
- Design philosophy: (resource-oriented, RPC-style, hypermedia)
- Consistency guidelines: (reference — Stripe, GitHub, Twilio patterns)

## Versioning and Compatibility
- Versioning strategy: (URL path /v1/, header, query param)
- Deprecation policy: (timeline — e.g., 12 months notice, sunset header)
- Breaking change definition: (what counts — removed field, type change, new required param)
- Migration guide process: (who writes it, where it lives, when it ships)
- Changelog format: (keep-a-changelog, custom, auto-generated from spec diff)

## Naming Conventions
- Resource naming: (plural nouns, lowercase, e.g., /users, /payment-intents)
- Field casing: (snake_case for JSON, camelCase for GraphQL — pick one per style)
- Abbreviation rules: (no abbreviations, or allowed list — id, url, api)
- Enumeration values: (lowercase_snake, UPPER_SNAKE — pick one)
- Query parameter naming: (filter[status], status, filter_status — pick one pattern)

## Error Response Format
- Error schema: (RFC 7807 Problem Details, custom, GraphQL errors)
- Error code registry: (where codes are defined, how they're assigned)
- Error message guidelines: (developer-facing, actionable, include fix suggestions)
- Validation error format: (per-field errors, nested paths, array index references)
- Rate limit error format: (429 with Retry-After header and quota details)

## Pagination, Filtering, and Sorting
- Pagination style: (cursor-based, offset-limit, page-number)
- Default and max page size:
- Filtering convention: (query params, filter object, OData-style)
- Sorting convention: (sort=field, sort=-field for desc, sort[field]=asc)
- Total count behavior: (always included, opt-in via include=total_count, omitted)

## Rate Limiting and Quotas
- Rate limit model: (per-key, per-plan, per-endpoint, sliding window, token bucket)
- Rate limit tiers: (free, pro, enterprise — requests per minute/hour)
- Rate limit headers: (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
- Quota model: (monthly usage caps, per-resource limits)
- Burst allowance: (short burst above sustained rate)

## SDK Generation and Distribution
- SDK languages: (JavaScript/TypeScript, Python, Go, Java, Ruby, etc.)
- Generation approach: (OpenAPI codegen, Stainless, Fern, hand-written, hybrid)
- SDK style: (thin HTTP wrapper, rich client with typed models, fluent builder)
- Distribution: (npm, PyPI, Maven Central, Go modules, RubyGems)
- SDK versioning: (tracks API version, independent semver, both)

## Authentication and Authorization
- Auth methods: (API keys, OAuth2, JWT, mTLS)
- Key management: (creation, rotation, scoping, revocation)
- Permission model: (scoped keys, RBAC, per-resource ACL)
- Auth error responses: (401 vs 403, include required scope in error)

## Documentation
- Platform: (Redoc, Mintlify, ReadMe, Stoplight, custom)
- Generation: (auto from spec, hand-written, hybrid)
- Code examples: (auto-generated from SDK, hand-written, both)
- Interactive playground: (try-it-out in docs, Postman collection, both)
- Getting started guide: (quick start, authentication walkthrough, first API call)

## Webhooks (if applicable)
- Event catalog: (list of event types, e.g., invoice.paid, user.created)
- Payload format: (JSON, envelope with type + data + timestamp)
- Delivery guarantees: (at-least-once, retry policy, exponential backoff)
- Signature verification: (HMAC, public key, how consumers validate)
- Webhook management API: (CRUD for subscriptions, event filtering)
```

---

## Conventions Starter (Workflow 2)

```markdown
# API Platform / SDK Conventions

## API Design
- Resource-oriented URLs — nouns not verbs (/users, not /getUsers)
- Consistent casing everywhere — pick one (snake_case for REST, camelCase for GraphQL) and never mix
- Plural resource names — /users not /user, even for singletons accessed by ID
- Nest only for true parent-child — /users/{id}/orders, not /users/{id}/preferences/notifications/email
- Use standard HTTP methods and status codes — don't invent custom ones
- Idempotency keys on all mutating operations — clients will retry

## Backward Compatibility
- Never remove or rename a field in a versioned response — add new fields, deprecate old ones
- Never change a field's type — add a new field with the new type
- Never add required request parameters to existing endpoints — new params default to previous behavior
- Version from day one — even internal betas get /v1/
- Spec diff in CI — every PR shows what changed in the API contract
- Deprecation warnings in response headers before removal (Sunset header, Deprecation header)

## Error Responses
- Every error has a machine-readable error code, a human-readable message, and a documentation URL
- Validation errors include the field path, the rejected value, and what was expected
- Never expose internal details (stack traces, SQL, internal service names) in error responses
- Use standard HTTP status codes — 400 for validation, 401 for auth, 403 for permissions, 404 for not found, 429 for rate limit, 500 for server error
- Rate limit errors include Retry-After header and quota details

## Pagination
- Cursor-based pagination by default — offset pagination breaks with concurrent writes
- Always include a next_page cursor (or null) — clients should not construct cursors
- Default page size is reasonable (20-50), max is enforced (100-200)
- Response shape is consistent: { data: [...], has_more: bool, next_cursor: string | null }

## SDK Quality
- Generated SDK code must be idiomatic — Python uses snake_case, Java uses camelCase, Go uses exported names
- SDK wraps auth — consumers pass a key once, not on every call
- SDK types match the API spec exactly — if the spec says optional, the SDK type is nullable
- SDK errors are typed — catch specific errors (RateLimitError, AuthError), not just generic exceptions
- SDK includes auto-pagination helpers — consumers iterate, SDK handles cursors
- SDK has retry with exponential backoff built-in for transient errors

## Documentation
- Every endpoint has a working code example in every supported SDK language
- Examples are tested in CI — broken examples are bugs
- Changelog entry for every API change — auto-generated from spec diff where possible
- Migration guides for every breaking change, published before the change ships
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New API endpoint

```markdown
# Prompt: <ResourceName> API endpoint

## Task
Design and implement the <CRUD / action> endpoint(s) for the <ResourceName> resource.

## API Design
- Resource: /<resource-name> (plural, lowercase, hyphenated)
- Methods: <GET, POST, PUT, PATCH, DELETE — which ones>
- URL structure: <nested under parent? e.g., /orgs/{org_id}/members>
- Query parameters: <filtering, sorting, pagination, field selection>

## Request
- Body schema: <fields, types, required/optional, validation rules>
- Headers: <auth, idempotency key, content type, API version>
- Path parameters: <resource ID format — UUID, slug, auto-increment>

## Response
- Success schema: <fields, types, envelope format>
- Pagination: <cursor-based — include next_cursor, has_more>
- Error responses: <400 validation, 401 auth, 403 permission, 404 not found, 409 conflict, 429 rate limit>
- Each error includes: error code, message, documentation URL, field-level details

## Backward Compatibility
- Is this a new endpoint or a change to an existing one?
- If change: what is the migration path for existing consumers?
- New fields must be optional or have defaults

## Constraints
- Must conform to existing API style guide (casing, naming, envelope format)
- OpenAPI spec must be updated alongside implementation
- Idempotency key support on POST/PUT/PATCH
- Rate limiting applied per tier

## Output format
- OpenAPI spec for the endpoint (paths + schemas)
- Implementation (controller, service, validation)
- Error code definitions added to the error registry
- Unit tests (happy path, validation errors, auth errors, pagination boundaries)
- SDK usage example showing how consumers call this endpoint
```

### SDK generation or client library

```markdown
# Prompt: <Language> SDK for <API>

## Task
Create (or regenerate) the <Language> SDK client for the <API> based on the OpenAPI spec.

## SDK Architecture
- Generation approach: <codegen from spec, hand-written, hybrid>
- Client style: <single client class, resource-scoped clients (api.users.list()), fluent builder>
- Auth: <API key passed to constructor, OAuth2 flow, environment variable fallback>
- HTTP layer: <built-in, requests, httpx, net/http, okhttp — configurable?>

## Idiomatic Conventions
- Naming: <language-specific — snake_case for Python, camelCase for JS, PascalCase for Go exports>
- Types: <fully typed models, generics for paginated responses, discriminated unions for polymorphic types>
- Errors: <typed exception hierarchy — ApiError, AuthError, RateLimitError, ValidationError>
- Async: <async/await support, sync wrapper, both>
- Pagination: <auto-pagination iterator/generator, manual cursor management, both>

## Built-in Behavior
- Retry: <exponential backoff for 429 and 5xx, configurable max retries>
- Rate limit handling: <respect Retry-After header, backoff automatically>
- Timeout: <configurable, sensible defaults (30s connect, 60s read)>
- Logging: <structured, configurable level, never log secrets>
- User-Agent: <sdk-name/version language/version>

## Constraints
- SDK version must track API version
- All public types and methods must have documentation
- No credentials in generated code or examples
- Must work with the language's standard package manager

## Output format
- SDK client implementation
- Type definitions / models
- Auth handling module
- Pagination helpers
- Error types
- Getting started example
- Package configuration (setup.py, package.json, go.mod, etc.)
```

### Webhook system

```markdown
# Prompt: Webhook system for <EventType>

## Task
Implement the webhook delivery system for <event type(s)> (e.g., order.completed, user.created, invoice.paid).

## Event Design
- Event types: <list of event names — dot-notation, past tense verb>
- Payload schema: <per event type — envelope with type, id, timestamp, data>
- Schema versioning: <how payload schema evolves without breaking consumers>

## Delivery
- Transport: <HTTPS POST to consumer URL>
- Retry policy: <exponential backoff — attempts, intervals, max delay>
- Delivery guarantees: <at-least-once — consumers must handle duplicates>
- Timeout: <per delivery attempt — e.g., 30 seconds>
- Ordering: <best-effort ordered, explicitly unordered — document which>

## Security
- Signature: <HMAC-SHA256 of payload with consumer's signing secret>
- Signature header: <X-Signature-256 or similar>
- Timestamp in signature to prevent replay attacks
- IP allowlist (optional): <published webhook source IPs>

## Consumer Management
- Subscription API: <CRUD for webhook endpoints — URL, events, active/inactive>
- Event filtering: <subscribe to specific events or all>
- Secret rotation: <rotate signing secret without downtime>
- Delivery logs: <queryable — event type, status, response code, timestamp>

## Constraints
- Payload must match documented schema exactly
- Delivery must not block the originating operation
- Failed deliveries must be inspectable via API (delivery log)
- Must support consumer endpoint verification (challenge or test event)

## Output format
- Event payload schemas (JSON Schema or OpenAPI)
- Webhook delivery service (queue, dispatch, retry)
- Signature generation and verification utilities
- Consumer management API endpoints
- Consumer-side verification example code
- Tests: successful delivery, retry on failure, signature verification, replay prevention
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**API design consistency**
- [ ] Resource names are plural, lowercase, hyphenated?
- [ ] Field casing is consistent across all endpoints (no mixing snake_case and camelCase)?
- [ ] HTTP methods and status codes used correctly (POST for create, 201 returned, etc.)?
- [ ] Query parameter naming follows the established convention?
- [ ] Enum values follow the established casing convention?
- [ ] No verbs in resource URLs (/users/activate → POST /users/{id}/activation)?

**Backward compatibility**
- [ ] No fields removed or renamed in existing versioned responses?
- [ ] No type changes to existing fields?
- [ ] No new required parameters on existing endpoints?
- [ ] Spec diff reviewed — API contract changes are intentional?
- [ ] Deprecation headers set for deprecated fields/endpoints?
- [ ] Migration guide written for any breaking changes?

**Error responses**
- [ ] Every error includes: machine-readable code, human-readable message, documentation URL?
- [ ] Validation errors include field path, rejected value, and expectation?
- [ ] No internal details leaked (stack traces, SQL, service names)?
- [ ] Standard HTTP status codes used correctly?
- [ ] Rate limit errors include Retry-After and quota headers?

**Pagination and filtering**
- [ ] Cursor-based pagination implemented correctly?
- [ ] next_cursor is null (not absent) on last page?
- [ ] Empty results return empty array with has_more: false, not 404?
- [ ] Page size has a reasonable default and enforced maximum?
- [ ] Filtering and sorting work correctly on edge cases (empty filter, unknown field)?

**SDK quality**
- [ ] SDK generates cleanly from the updated spec in all target languages?
- [ ] Generated code is idiomatic for each language (naming, types, error handling)?
- [ ] SDK types match the spec exactly (nullable fields are optional in SDK)?
- [ ] Auto-pagination helpers work correctly?
- [ ] Retry and rate limit handling built-in?
- [ ] No credentials in generated code or examples?

**Documentation**
- [ ] OpenAPI spec validates without errors or warnings?
- [ ] Every endpoint has working code examples in each SDK language?
- [ ] Examples are tested in CI?
- [ ] Changelog entry written for the change?
- [ ] Documentation renders correctly on the docs platform?

**Webhooks** (if applicable)
- [ ] Payload matches documented schema?
- [ ] Signature verification works (HMAC, timestamp, replay prevention)?
- [ ] Retry policy works correctly (backoff, max attempts)?
- [ ] Delivery does not block the originating operation?
- [ ] Consumer can verify endpoint ownership (challenge or test event)?
- [ ] Delivery logs are queryable via API?
