# PDD Reference: Full-Stack Projects

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for full-stack projects where frontend and backend live in the same codebase or are tightly coupled (Next.js, Nuxt, SvelteKit, Remix, T3 stack, etc.).

This reference combines concerns from `frontend.md` and `backend.md`. For deep dives on either side, read those files alongside this one.

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- What full-stack framework? (Next.js, Nuxt, SvelteKit, Remix, Astro + API, etc.)
- Where does the API live — same repo (API routes) or separate backend?
- How is the API contract defined? (OpenAPI, tRPC, GraphQL schema, informal)
- What's the rendering strategy? (SSR, SSG, ISR, CSR, hybrid)
- Database and ORM? (Prisma, Drizzle, Mongoose, SQLAlchemy)
- Auth approach? (NextAuth, Clerk, Auth0, custom JWT, sessions)
- How is state shared between server and client? (RSC, server actions, hydration, API calls)
- Deployment target? (Vercel, Netlify, Fly.io, self-hosted, edge)

### Extended `pdd/context/project.md` sections for full-stack

```markdown
## Framework & rendering
- Framework:
- Rendering strategy: SSR / SSG / ISR / CSR / hybrid
- Deployment target:

## API contract
- Style: API routes / tRPC / GraphQL / REST
- Contract location: (e.g. src/server/routers/, app/api/, openapi.yaml)

## Data layer
- Database:
- ORM:
- Migration tool:

## Auth
- Provider / approach:
- Session storage:
- Protected routes pattern:

## State
- Server state: (React Query, SWR, tRPC hooks)
- Client state: (Zustand, Jotai, Pinia, Context)
```

---

## Conventions Starter (Workflow 2)

```markdown
# Full-Stack Conventions

## Project structure
- app/ or pages/ — routing and page components
- components/ — shared UI components
- server/ or lib/server/ — server-only code (DB, auth, services)
- lib/ or utils/ — shared utilities (safe to run anywhere)
- types/ — shared TypeScript types used on both client and server

## Strict client/server boundary
- Server-only code never imported in client components
- Mark server-only modules with `import 'server-only'` (Next.js) or equivalent
- Types shared freely — logic and side effects are separated

## API design
- Consistent response shape: `{ data, error, meta }`
- Auth checked before any data access — middleware or per-route
- Input validated at the boundary with [Zod / Valibot]

## Data fetching
- Server components / server-side fetch for initial page data
- Client-side fetch only for user-triggered interactions
- Loading, error, and empty states required for all async UI

## Forms
- Validation: same schema on client (UX) and server (security)
- Optimistic updates for fast perceived performance
- Error messages tied to specific fields, not just toasts

## Naming
- Pages / routes: lowercase, kebab-case (e.g. `/user-profile`)
- Components: PascalCase
- Server actions / API handlers: camelCase verbs (e.g. `createUser`, `updatePost`)
- DB tables: snake_case, plural (e.g. `user_profiles`)

## Auth
- Protect routes at middleware level — not inside page components
- Never trust client-side auth state for server decisions
- Session refresh handled automatically — no manual token management in UI
```

---

## Common Feature Prompt Patterns (Workflow 3)

### Full-stack feature (data + UI)

```markdown
# Prompt: <FeatureName> — Full-Stack

## Task
Implement <feature> end-to-end: database schema, server logic, and UI.

## Split into these sub-prompts (do in order):
1. Database migration for <table/field changes>
2. Server action / API route for <CRUD operation>
3. UI component / page that calls the server action

## For this prompt, implement: <pick one of the above>

## Data shape
<describe the entity and its fields>

## Business rules
<what logic the server must enforce>

## UI requirements
<what the user sees and can do>

## Constraints
- Auth required: yes / no
- Validate input with Zod on both client and server
- Loading and error states required in UI
- Follow existing patterns for [API routes / server actions / tRPC]
```

### Authentication-protected page

```markdown
# Prompt: <PageName> — Protected Page

## Task
Create a page at `/<route>` that requires authentication.

## Auth behavior
- Unauthenticated: redirect to /login with `callbackUrl` set
- Authenticated: render the page content

## Page content
<describe what the page shows and any data it needs>

## Data fetching
- Fetch on server side (server component / getServerSideProps)
- Data source: <API route / direct DB / tRPC>

## Constraints
- Auth check at middleware level — not inside the page component
- No sensitive data exposed to client beyond what the UI needs
- Page is SEO-indexed: yes / no (affects rendering strategy)
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions. Also load `frontend.md` and `backend.md` checklists for deeper coverage of each side.

**Client/server boundary**
- [ ] No server-only code (DB, secrets, admin SDK) imported in client components?
- [ ] `server-only` guard in place for server modules?
- [ ] Types shared correctly — not business logic?

**Auth & authorization**
- [ ] Auth enforced at middleware/server level — not just in UI?
- [ ] Protected data inaccessible without valid session?
- [ ] Role-based access (if applicable) checked server-side?

**API contract**
- [ ] Input validated with same schema on client and server?
- [ ] Server response doesn't over-expose fields (no full DB row to client)?
- [ ] Error shape consistent across all endpoints?

**Data fetching**
- [ ] Initial page data fetched server-side (not waterfall client requests)?
- [ ] Client fetches only for interactions, not initial render?
- [ ] Loading, error, empty states all handled in UI?

**Forms**
- [ ] Validation runs on client for UX and server for security?
- [ ] Optimistic updates implemented where appropriate?
- [ ] Field-level error messages returned from server?

**Performance**
- [ ] No unnecessary client-side JavaScript for static content?
- [ ] Images optimized (next/image or equivalent)?
- [ ] No N+1 queries from server components?
