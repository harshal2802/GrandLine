# GrandLine

A web-based multi-agent orchestration platform where a crew of persona-based AI agents — **Captain** (PM), **Navigator** (Architect), **Shipwrights** (Developers), **Doctor** (QA), and **Helmsman** (DevOps) — voyage together through a structured pipeline to build, test, and deploy software solutions.

## How It Works

Users **chart a course** (submit a task). The **Captain** decomposes it into a voyage plan. The **Navigator** drafts the **Poneglyphs** (PDD prompt artifacts). The **Doctor** writes health checks before any code is written (TDD). The **Shipwrights** build. The **Doctor** validates. The **Helmsman** deploys.

PDD and TDD aren't optional — they're the **Log Pose**. Without them, the crew doesn't sail.

## The Observation Deck

A real-time war room UI lets users watch the voyage unfold:

- **Sea Chart** (Board View) — tasks flowing through waters: PDD → TDD → Implement → Review → Deployed
- **Crew Map** (Graph View) — live DAG showing agents communicating via Den Den Mushi
- **Ship's Log** (Timeline View) — chronological record of every agent action

Users can intervene at any point — pause an agent, redirect work, inject context.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14+, React, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python, FastAPI, SQLAlchemy |
| AI/Agents | LangGraph, multi-provider via Dial System |
| Message Bus | Redis Streams (Den Den Mushi) |
| Database | PostgreSQL (Vivre Card state + JSONB) |
| Deployment | Docker Compose (local-first), Kubernetes + Helm (production) |
| CI/CD | GitHub Actions |

## Project Structure

```
src/
  frontend/         — Next.js (SSG landing + CSR Observation Deck)
  backend/          — FastAPI (REST + SSE + WebSocket)
    crew/           — Agent personas (Captain, Navigator, etc.)
    dial_system/    — LLM gateway with failover
    den_den_mushi/  — Redis Streams message bus
  shared/           — Shared types, schemas, constants
  infra/            — Docker, Kubernetes, Helm configs
pdd/                — Prompt Driven Development artifacts
  context/          — Project context files
  prompts/          — Poneglyphs (feature prompts)
  evals/            — Prompt quality evaluations
docs/               — Documentation (auto-deployed to GitHub Pages)
```

## Development

This project follows **PDD** (Prompt Driven Development) and **TDD** (Test Driven Development) — the Log Pose.

- Every feature starts with Poneglyphs (PDD prompts) and a review cycle
- Every feature starts with health checks (failing tests) from the Doctor
- All changes go through PRs against `main`

## Assemble your crew. Navigate the GrandLine.

## License

MIT
