# PDD Examples: Task Management API

These files demonstrate a Prompt Driven Development project for a **Task Management REST API** built with Node.js, Express, and PostgreSQL.

Browse these examples to see how PDD artifacts look in practice, then adapt them for your own project.

## Table of Contents

### Context files

| File | Purpose |
|---|---|
| [pdd/context/project.md](pdd/context/project.md) | Project overview, tech stack, and quality bar |
| [pdd/context/conventions.md](pdd/context/conventions.md) | Coding standards the AI must follow |
| [pdd/context/decisions.md](pdd/context/decisions.md) | Architecture decisions with rationale |

### Feature prompts

| File | Purpose |
|---|---|
| [pdd/prompts/features/tasks/create-task-endpoint.md](pdd/prompts/features/tasks/create-task-endpoint.md) | Standalone prompt for the POST /tasks endpoint |
| [pdd/prompts/features/tasks/task-filtering-01-schema.md](pdd/prompts/features/tasks/task-filtering-01-schema.md) | Chained prompt 1/2: database query layer for filtering |
| [pdd/prompts/features/tasks/task-filtering-02-api.md](pdd/prompts/features/tasks/task-filtering-02-api.md) | Chained prompt 2/2: API endpoint that uses the query layer |

### Experiments

| File | Purpose |
|---|---|
| [pdd/prompts/experiments/2026-02-05-task-comments-spike.md](pdd/prompts/experiments/2026-02-05-task-comments-spike.md) | Time-boxed spike comparing flat vs. threaded comments |

### Templates

| File | Purpose |
|---|---|
| [pdd/prompts/templates/new-api-endpoint.template.md](pdd/prompts/templates/new-api-endpoint.template.md) | Reusable template for new REST endpoints — extracted after writing 2 similar prompts |

### Evals

| File | Purpose |
|---|---|
| [pdd/evals/create-task-endpoint-eval.md](pdd/evals/create-task-endpoint-eval.md) | Level 1 manual checklist for the create-task prompt |
| [pdd/evals/baselines/create-task-endpoint-baseline.md](pdd/evals/baselines/create-task-endpoint-baseline.md) | Level 2 baseline — saved good output for diff comparison |
| [pdd/evals/task-filtering-eval.md](pdd/evals/task-filtering-eval.md) | Level 2 eval covering the chained filtering prompts |

## How to use these examples

1. Read `pdd/context/project.md` first to understand the fictional project.
2. Look at the feature prompts to see how tasks are scoped and structured.
3. Notice how the chained prompts (`task-filtering-01` and `task-filtering-02`) build on each other.
4. Review the eval checklist to see how prompt output is verified before committing.

Copy any file as a starting point and replace the details with your own project.
