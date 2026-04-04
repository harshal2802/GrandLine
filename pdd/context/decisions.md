# GrandLine — Architectural Decisions

**Last updated**: 2026-04-04

---

## Decision: Separate frontend and backend languages
**Date**: 2026-04-04
**What was decided**: TypeScript (Next.js) for frontend, Python (FastAPI) for backend
**Why**: The AI/ML ecosystem is Python-native (LangGraph, LangChain, most LLM SDKs). Fighting this with an all-TypeScript backend would mean constant wrapper libraries and ecosystem friction. TypeScript frontend gives type safety and React ecosystem benefits.
**Don't suggest**: All-TypeScript (Node.js backend), all-Python (Django templates for frontend)

---

## Decision: Next.js with hybrid rendering instead of Vite SPA
**Date**: 2026-04-04
**What was decided**: Use Next.js App Router with SSG for public pages and CSR for the dashboard
**Why**: GrandLine needs an attractive, SEO-optimized public landing page AND a real-time dashboard. Next.js handles both in one codebase with per-route rendering strategies. A pure SPA (Vite) would sacrifice SEO and initial load performance for public pages.
**Don't suggest**: Separate repos for landing page and dashboard, Vite for everything, server-side rendering for the dashboard

---

## Decision: REST + SSE + WebSockets (three protocols)
**Date**: 2026-04-04
**What was decided**: Use REST for CRUD, SSE for LLM streaming, WebSockets for bidirectional real-time
**Why**: SSE is the natural fit for LLM token streaming (one-way, server→client) — it's what OpenAI and Anthropic APIs use natively. WebSockets are needed for bidirectional communication (user intervention during agent execution, live multi-workflow dashboard). REST handles standard CRUD. Each protocol fits its use case.
**Don't suggest**: WebSockets for everything (overengineered for streaming), REST polling for real-time updates, GraphQL subscriptions (adds unnecessary complexity at this stage)

---

## Decision: All artifacts under src/
**Date**: 2026-04-04
**What was decided**: All application code (frontend, backend, shared, infra) lives under `src/` with clear subdirectories
**Why**: User preference for a clean repo root. Keeps config files, docs, and PDD files at root level while all buildable/deployable code is contained in `src/`.
**Don't suggest**: Separate top-level directories for frontend/backend, monorepo tools like Turborepo (premature at this stage)

---

## Decision: PDD + TDD mandatory for all features
**Date**: 2026-04-04
**What was decided**: Every feature must follow PDD workflow (context → prompts → review) and TDD (failing test → implementation → green test)
**Why**: User's development philosophy. PDD ensures AI-generated code is well-specified and reviewed. TDD catches bugs before they compound. Combined, they produce reliable, well-documented features.
**Don't suggest**: Skipping tests for "simple" changes, writing code before prompts, post-hoc test writing

---

## Decision: PR-based workflow with GitHub Issues for planning
**Date**: 2026-04-04
**What was decided**: Plan phases become GitHub issues. Each issue is worked on in a separate branch/PR. PRs must pass tests and PDD review before merge. User approves all PRs.
**Why**: Clean git history, traceable work, and human-in-the-loop for quality control. Each PR is a reviewable, revertable unit of work.
**Don't suggest**: Batching multiple issues into one PR, auto-merging without user approval, committing directly to main

---

## Decision: Auto-deployed documentation on GitHub Pages
**Date**: 2026-04-04
**What was decided**: Documentation lives under `docs/` and auto-deploys to GitHub Pages via GitHub Actions on merge to `main`
**Why**: Docs should always reflect the current state of `main`. Automating deployment removes the "forgot to update docs" failure mode.
**Don't suggest**: Manual doc deployment, docs in a separate repo, wiki-only documentation
