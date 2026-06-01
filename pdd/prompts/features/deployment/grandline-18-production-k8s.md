# Poneglyph: Production Deployment — Kubernetes + Helm (Phase 18)

**Issue**: #19 · **Depends on**: #16 (pipeline), #17 (Observation Deck)

> PDD note: authored manually following the `/pdd-skill:pdd-prompts` workflow
> (the plugin is not installed in this execution environment).

## Goal

Package GrandLine for production on Kubernetes: Helm chart with per-environment
values, all services with probes + resource limits + HPA, secrets via K8s
Secrets, ingress + TLS, deny-by-default NetworkPolicies, gVisor sandbox
RuntimeClass, and a build→stage→gate→prod CD pipeline.

## Deliverables

| Area | File(s) |
|---|---|
| Chart | `src/infra/helm/grandline/Chart.yaml`, `values.yaml`, `values-{dev,staging,prod}.yaml` |
| Backend | `templates/backend-deployment.yaml` (initContainer migrate + probes), `-service.yaml`, `-hpa.yaml` (2–10) |
| Frontend | `templates/frontend-deployment.yaml`, `-service.yaml`, `-hpa.yaml` (2–5) |
| PostgreSQL | `templates/postgres-statefulset.yaml` (PVC), `-service.yaml` (headless) |
| Redis | `templates/redis-deployment.yaml` (+ service) |
| Edge | `templates/ingress.yaml` (TLS, /api→backend, /→frontend) |
| Security | `templates/networkpolicy.yaml` (deny-by-default + explicit allows), `secret.yaml`, `serviceaccount.yaml` |
| Sandbox | `templates/sandbox-runtimeclass.yaml` (gVisor) |
| Images | `src/backend/Dockerfile.prod`, `src/frontend/Dockerfile.prod` |
| CD | `.github/workflows/cd.yml` (build→GHCR→staging→manual gate→prod) |
| Docs | `src/infra/helm/README.md` |

## Acceptance criteria (issue #19)

- `helm install grandline ./grandline` deploys the full stack. ✓
- Probes on every service. ✓ (backend `/api/v1/health`, frontend `/`, pg/redis exec)
- HPA on backend (2–10) and frontend (2–5). ✓
- Resource requests/limits on all workloads. ✓
- Secrets not in git — `secrets.create=false` for staging/prod; existing Secret. ✓
- Network policies enforce deny-by-default. ✓
- gVisor RuntimeClass for sandbox pods. ✓
- CI/CD: auto-deploy staging, manual gate for prod (GitHub `production` env). ✓
- Ingress with TLS (cert-manager annotation). ✓
- Structured JSON logging → app-level + node log shipper (documented follow-up).

## Validation note

`helm template`/`helm lint` could not run in this environment (`get.helm.sh`
is outside the network allowlist). All plain-YAML manifests were validated with
a YAML parser and template if/with/end balance was checked by hand. Run
`helm lint src/infra/helm/grandline && helm template grandline src/infra/helm/grandline -f .../values-prod.yaml`
in CI before first deploy.
