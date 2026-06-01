# GrandLine Helm Chart

Packages the full GrandLine stack for Kubernetes (#19): FastAPI backend,
Next.js frontend, PostgreSQL (StatefulSet), Redis, ingress + TLS, HPAs,
deny-by-default NetworkPolicies, and a gVisor RuntimeClass for agent sandbox
pods.

## Layout

```
grandline/
  Chart.yaml
  values.yaml            # defaults
  values-dev.yaml        # 1 replica, no HPA, self-managed dev secret, no TLS
  values-staging.yaml    # prod-like, smaller ceilings, injected secrets
  values-prod.yaml       # full HPA, external secrets, TLS, network policies
  templates/             # deployments, services, HPAs, statefulset, ingress,
                         # networkpolicy, runtimeclass, secret, configmap
```

## Quick start (local kind/minikube)

```bash
helm install grandline ./grandline -f ./grandline/values-dev.yaml
kubectl port-forward svc/grandline-frontend 3000:3000
```

## Staging / production

Secrets are NEVER in git. For staging/prod, `secrets.create=false` and you must
provision the `grandline-secrets` Secret out-of-band (sealed-secrets,
external-secrets, or CI) with:

- `GRANDLINE_DATABASE_URL`
- `GRANDLINE_REDIS_URL`
- `GRANDLINE_JWT_SECRET`
- `POSTGRES_PASSWORD`
- `GRANDLINE_DIAL_ANTHROPIC_API_KEY` (and any other provider keys)

```bash
helm upgrade --install grandline ./grandline \
  --namespace grandline-prod --create-namespace \
  -f ./grandline/values-prod.yaml \
  --set backend.image.tag=<sha> --set frontend.image.tag=<sha> --wait
```

## CI/CD

`.github/workflows/cd.yml`: build images (`Dockerfile.prod`) → push to GHCR →
deploy to **staging** automatically → **manual approval gate** (the
`production` GitHub Environment with required reviewers) → deploy to **prod**.
Provide `STAGING_KUBECONFIG` / `PROD_KUBECONFIG` (base64) as environment secrets.

## Notes

- Backend `initContainer` runs `alembic upgrade head` before serving.
- Liveness/readiness probes: backend `/api/v1/health`, frontend `/`,
  postgres `pg_isready`, redis `redis-cli ping`.
- Agent sandbox pods are created at runtime by the backend with
  `runtimeClassName: gvisor`; nodes need the gVisor (runsc) runtime installed.
- Structured JSON logging is emitted by the app; ship logs to your aggregator
  via a node-level agent (Fluent Bit / Loki) — out of chart scope.
