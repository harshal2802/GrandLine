# GrandLine — Release Readiness Review

Deep review of backend, frontend, infra, and CI/CD (June 2026).
Each finding is marked **FIXED** (addressed in this review's PR) or **OPEN**
(needs a decision or follow-up work before/after release).

## Verdict

The codebase is in good shape — clean lint, 900+ passing tests, no TODO/stub
debt, auth enforced on every endpoint, parameterized SQL throughout. All
**blocking** findings from the original review are now FIXED; one operational
step remains (run the first staging deploy — see `docs/DEPLOYMENT.md`), plus
the non-blocking hardening list at the bottom.

---

## Critical — fixed in this pass

1. **Helm secret key names didn't match the backend settings** — `secret.yaml`
   shipped `GRANDLINE_JWT_SECRET` and `GRANDLINE_DIAL_ANTHROPIC_API_KEY`, but
   the backend (pydantic `env_prefix="GRANDLINE_"`) reads
   `GRANDLINE_JWT_SECRET_KEY` and `GRANDLINE_ANTHROPIC_API_KEY`. Because the
   Deployment uses `envFrom`, both values were **silently ignored**: every K8s
   deploy ran with the JWT secret `change-me-in-production` and no Anthropic
   key. **FIXED**: keys renamed in `templates/secret.yaml`, `values.yaml`,
   `NOTES.txt`, `helm/README.md`; `GRANDLINE_OPENAI_API_KEY` added.

2. **App boots with the default JWT secret in production** — nothing stopped
   a non-debug deployment from signing tokens with the known default.
   **FIXED**: `validate_production_settings()` in `app/main.py` refuses to
   start when `GRANDLINE_DEBUG=false` and the JWT secret is the default. Dev
   flows (`make api-dev`, docker-compose, Helm dev overlay) set
   `GRANDLINE_DEBUG=true` and are unaffected.

3. **CORS allowed all methods/headers with credentials** —
   `allow_methods=["*"]`, `allow_headers=["*"]` combined with
   `allow_credentials=True`. **FIXED**: restricted to the methods the API
   serves and `Authorization`/`Content-Type` headers.

4. **No security headers on the frontend** — the non-HttpOnly auth cookie is
   a documented trade-off "mitigated by CSP", but no CSP existed. **FIXED**:
   `next.config.mjs` now sends CSP (incl. `frame-ancestors 'none'`,
   `object-src 'none'`), `X-Frame-Options`, `X-Content-Type-Options`,
   `Referrer-Policy`, `Permissions-Policy` on every route.

5. **Config drift: `NEXT_PUBLIC_API_URL` vs `NEXT_PUBLIC_API_BASE_URL`** —
   compose and `.env.example` set a variable the frontend never reads, so the
   frontend silently fell back to `localhost:8000`. **FIXED** in
   `docker-compose.yml` + env examples (frontend reads
   `NEXT_PUBLIC_API_BASE_URL`, see `lib/config.ts`).

6. **Seed data crashed the dial router** — `scripts/seed.py` wrote
   `fallback_chain={"order": [...]}`, which `build_router_from_config` parses
   as a role name → `ValueError: 'order' is not a valid CrewRole` → HTTP 500
   on any completions call for the seeded voyage. **FIXED**: seeded shape is
   now `role -> [provider, ...]`.

7. **No `.env.example` for backend/frontend** — required vars were
   undocumented. **FIXED**: `src/backend/.env.example`,
   `src/frontend/.env.example`, and a corrected
   `src/infra/docker/.env.example`.

8. **No error boundary in the Observation Deck** — a render error inside
   `/app` blanked the screen. **FIXED**: `app/app/error.tsx` route-segment
   boundary with a reset action.

## Former blockers — fixed in the follow-up pass

9. **No voyage-creation endpoint.** ~~Voyages only existed via
   `scripts/seed.py`.~~ **FIXED**: `POST /api/v1/voyages` ("chart a course")
   creates the voyage plus a default dial config (provider/model from
   `GRANDLINE_DIAL_DEFAULT_PROVIDER` / `GRANDLINE_DIAL_DEFAULT_MODEL`), and
   the Observation Deck sidebar grew a "+ Chart" dialog that creates the
   voyage and optionally sets sail immediately (`POST /voyages/{id}/start`
   with the mission text as the task). Users can now go register → chart →
   sail → watch end-to-end.

10. **WS auth token exposed in URL.** ~~`…/events?token=<jwt>` landed in
    proxy logs and browser history.~~ **FIXED**: the WS handshake now
    authenticates via `Sec-WebSocket-Protocol: grandline-bearer, <jwt>`
    (echoed by the server on accept) with the `access_token` cookie as the
    same-origin fallback; the `?token=` query param is removed and ignored.
    Follow-up (non-blocking): moving the cookie to HttpOnly still requires
    reworking session restore, since the in-memory auth store re-hydrates
    from that cookie after a page reload.

11. **Production deploy pipeline never exercised.** **MOSTLY FIXED**: CI now
    runs `helm lint` + renders every overlay on each PR (catches chart/values
    drift like the secret-key mismatch class), CD's new `deploy-gate` job
    reports loudly when `DEPLOY_ENABLED` is off instead of skipping silently,
    and `docs/DEPLOYMENT.md` is the first-deploy runbook (secret provisioning
    with exact key names, domains, GitHub environments, smoke tests,
    rollback). **Remaining manual step**: provision a staging cluster and run
    the pipeline once before the public release.

## Open — recommended hardening (non-blocking)

12. **Dev credentials normalize weak defaults** — compose/dev-overlay use
    `grandline:grandline` and `changeme-dev*`. Acceptable for local dev, but
    consider `openssl rand`-generated defaults in `make setup`.
13. **Redis runs without AUTH and Postgres/Redis ports are host-exposed in
    compose** — fine locally; never copy to a server.
14. **Broad `except Exception` blocks** in service-layer code (they re-raise,
    but narrow types would aid monitoring).
15. **Provider SDK floors not pinned** — `anthropic>=0.40.0`,
    `openai>=1.50.0`, `langgraph>=0.4` allow breaking minor upgrades; pin
    before cutting a release build.
16. **Postgres StatefulSet lacks `runAsNonRoot`**; Redis has no resource
    limits in some paths; `imagePullPolicy: IfNotPresent` with `latest` tags
    can serve stale images — prefer digest/SHA tags (CD already passes
    `--set image.tag=<sha>`).
17. ~~**`DEPLOY_ENABLED` skip is silent**~~ — **FIXED**: the `deploy-gate`
    job posts the gating state to the workflow run summary.

---

## New in this pass: `claude_code` provider

The Dial System now supports **Claude Code CLI** as a provider (see README
"The Dial System"). It shells out to the local `claude` CLI in non-interactive
print mode (`--print --output-format json|stream-json`), so it can run on a
Claude subscription (`claude login` / `CLAUDE_CODE_OAUTH_TOKEN`) or an
`ANTHROPIC_API_KEY`, with no key stored in GrandLine. Includes streaming,
failover-compatible error mapping, rate-limit detection, timeouts, and a
sandboxed working directory (system temp dir by default, never the backend
cwd). Configure via `GRANDLINE_CLAUDE_CODE_*` (see `src/backend/.env.example`).
Note: the Claude Code CLI must be installed in the backend runtime image for
this provider to work in containers (`npm install -g @anthropic-ai/claude-code`).
