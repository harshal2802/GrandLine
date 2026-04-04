# GrandLine

A multi-agent orchestration platform for designing, executing, and monitoring AI agent workflows.

## Overview

GrandLine provides a visual interface and API for composing multi-agent pipelines with per-workflow LLM configuration, real-time execution monitoring, and scalable deployment on Kubernetes.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14+, React, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python, FastAPI, SQLAlchemy, Celery |
| AI/Agents | LangGraph, multi-provider LLM support |
| Database | PostgreSQL, Redis |
| Deployment | Docker, Kubernetes, Helm |
| CI/CD | GitHub Actions |

## Project Structure

```
src/
  frontend/     — Next.js application (SSG landing + CSR dashboard)
  backend/      — FastAPI application (REST + SSE + WebSocket)
  shared/       — Shared types, schemas, constants
  infra/        — Docker, Kubernetes, Helm configs
pdd/            — Prompt Driven Development artifacts
  context/      — Project context files
  prompts/      — Feature prompts and templates
  evals/        — Prompt quality evaluations
docs/           — Documentation (auto-deployed to GitHub Pages)
```

## Development

This project follows **PDD (Prompt Driven Development)** and **TDD (Test Driven Development)** methodologies.

- Every feature starts with a PDD prompt and review cycle
- Every feature starts with a failing test (TDD)
- All changes go through PRs against `main`

## License

MIT
