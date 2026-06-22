# TaskFlow API — Architecture Decisions

## Decision: PostgreSQL over MongoDB

**Date**: 2026-01-10
**What was decided**: Use PostgreSQL as the primary database.
**Why**: Task management data is highly relational (tasks belong to users, have labels, live in projects). We need strong consistency for assignment and status transitions, and PostgreSQL's support for complex queries (filtering, sorting, full-text search) fits our roadmap. The team also has deeper PostgreSQL experience.
**Don't suggest**: MongoDB, DynamoDB, or other document stores. If someone suggests "just use a NoSQL database for flexibility," point them here.

---

## Decision: REST over GraphQL

**Date**: 2026-01-10
**What was decided**: Build a REST API with versioned URL prefixes (`/api/v1/`).
**Why**: The frontend team is familiar with REST, our use cases are straightforward CRUD with filtering, and we want to keep the backend simple. GraphQL adds complexity (resolvers, N+1 prevention, schema stitching) that we do not need at this scale. REST also gives us simpler caching with standard HTTP semantics.
**Don't suggest**: GraphQL or gRPC for client-facing endpoints. If the need arises for internal service-to-service calls, gRPC can be reconsidered — but that is not on the current roadmap.

---

## Decision: JWT with refresh tokens for authentication

**Date**: 2026-01-15
**What was decided**: Use short-lived JWTs (15 min) for access and long-lived refresh tokens (7 days, stored in the database) for session continuity.
**Why**: Stateless access tokens keep per-request auth fast without a database lookup. Refresh tokens stored in the DB give us revocation capability (logout, password change invalidates all sessions). This balances performance with security.
**Don't suggest**: Session-based auth with server-side session stores. We chose JWTs deliberately to avoid session affinity requirements in our ECS deployment. Also do not suggest third-party auth services (Auth0, Clerk) — we want to own the auth layer for this project.
