# GrandLine — First Staging/Production Deploy Runbook

The CD pipeline (`.github/workflows/cd.yml`) is opt-in: every build/deploy job
is gated on the `DEPLOY_ENABLED` repository variable, and the chart's
staging/prod overlays expect an externally-provisioned Secret. This runbook is
the checklist for turning it on for the first time. CI already validates the
chart (`helm lint` + rendering every overlay) on each PR.

## 0. Prerequisites

- A Kubernetes cluster per environment (staging, prod) with:
  - an NGINX ingress controller (`ingress.className: nginx`)
  - cert-manager with a `letsencrypt-prod` ClusterIssuer — or disable TLS
    (`ingress.tls.enabled=false`) / change the annotation in `values.yaml`
- DNS records for your real hostnames (the committed
  `grandline.example.com` / `staging.grandline.example.com` are placeholders —
  override them, see step 2)
- GHCR images pullable from the cluster (public packages, or an
  `imagePullSecret` added to the chart's ServiceAccount)
- `kubectl` + `helm` access to both clusters

## 1. Provision the application Secret (per environment)

The Deployment consumes the Secret via `envFrom`, so **key names must match
the backend's `GRANDLINE_`-prefixed settings exactly** (see
`src/backend/.env.example`):

```bash
kubectl create namespace grandline-staging

PGPASS="$(openssl rand -hex 24)"
kubectl -n grandline-staging create secret generic grandline-secrets \
  --from-literal=POSTGRES_PASSWORD="$PGPASS" \
  --from-literal=GRANDLINE_JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=GRANDLINE_DATABASE_URL="postgresql+psycopg://grandline:${PGPASS}@grandline-postgres:5432/grandline" \
  --from-literal=GRANDLINE_REDIS_URL="redis://grandline-redis:6379/0" \
  --from-literal=GRANDLINE_ANTHROPIC_API_KEY="sk-ant-..." \
  --from-literal=GRANDLINE_OPENAI_API_KEY=""
```

> The backend refuses to boot with the default JWT secret when
> `GRANDLINE_DEBUG=false`, so a missing/mis-keyed Secret fails loudly at pod
> start instead of serving with insecure defaults.

Repeat for `grandline-prod`. Prefer sealed-secrets/external-secrets in real
setups; `kubectl create secret` is the minimum viable path.

## 2. Point the overlays at your domains

Edit (or `--set` at deploy time) in `values-staging.yaml` / `values-prod.yaml`:

- `ingress.host`
- `backend.env.GRANDLINE_CORS_ORIGINS` (JSON list containing the frontend origin)
- `frontend.env.NEXT_PUBLIC_API_BASE_URL` (the public API origin; empty string
  for a same-origin proxy setup)

`NEXT_PUBLIC_*` values are baked at image build time — the CD `build-push` job
builds with `NEXT_PUBLIC_API_BASE_URL=` (same-origin). If your API is on a
different origin, set the build-arg in `cd.yml` accordingly.

## 3. Configure GitHub

1. Repo **Variables**: `DEPLOY_ENABLED=true`.
2. Repo **Secrets**: `STAGING_KUBECONFIG` and `PROD_KUBECONFIG`
   (base64-encoded kubeconfigs: `base64 -w0 < kubeconfig`).
3. **Environments**: create `staging` and `production`; add required
   reviewers on `production` — that approval is the manual gate between
   staging and prod deploys.

When `DEPLOY_ENABLED` is not `true`, the `deploy-gate` job posts a notice to
the run summary explaining that deploys were skipped (they no longer skip
silently).

## 4. Ship it

Push to `main` (or run the CD workflow manually). Sequence:
`build-push` (GHCR, tags incl. `sha-<short>`) → `deploy-staging`
(`helm upgrade --install -f values-staging.yaml --set *.image.tag=sha-…`) →
manual approval → `deploy-prod`.

## 5. Smoke-test staging before approving prod

```bash
# API up + migrations applied (init container runs alembic upgrade head)
curl -fsS https://staging.example.com/api/v1/health

# End-to-end: register, chart a course, set sail, watch events
# (or use the UI: /register → Observation Deck → "+ Chart")
```

- Register a user, chart a voyage from the deck, confirm the WS stream
  connects (Network tab: the `/events` connection uses the
  `grandline-bearer` subprotocol — no token in the URL).
- `kubectl -n grandline-staging get pods` — backend/frontend Ready, HPA happy.

## 6. Rollback

```bash
helm -n grandline-staging history grandline
helm -n grandline-staging rollback grandline <revision>
```

## Appendix: Claude Code CLI provider in K8s

The `claude_code` dial provider shells out to the `claude` binary, which is
not in the default backend image. To use it in-cluster, extend
`src/backend/Dockerfile.prod` with Node + the CLI:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
 && npm install -g @anthropic-ai/claude-code \
 && rm -rf /var/lib/apt/lists/*
```

and provide auth via the Secret (`CLAUDE_CODE_OAUTH_TOKEN=...` from
`claude setup-token`, or rely on `ANTHROPIC_API_KEY`). API-key based
providers (`anthropic`, `openai`) need no image changes.
