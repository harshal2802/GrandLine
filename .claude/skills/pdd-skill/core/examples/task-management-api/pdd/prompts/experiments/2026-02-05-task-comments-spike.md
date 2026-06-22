# Experiment: Task comments — threading approach

**File**: pdd/prompts/experiments/2026-02-05-task-comments-spike.md
**Created**: 2026-02-05
**Goal**: Explore whether task comments should be flat or threaded
**Timebox**: 1 week (evaluate by 2026-02-12)

## Context

TaskFlow API needs comments on tasks. The team hasn't decided whether to use flat comments (simpler) or threaded comments (richer). This experiment generates both approaches to compare.

## Task

Generate two alternative implementations of `POST /api/v1/tasks/:id/comments`:

1. **Flat**: Simple `comments` table with `task_id` foreign key
2. **Threaded**: `comments` table with `task_id` + `parent_comment_id` for nested replies

For each, produce: Prisma schema addition, repository, and service.

## What to evaluate

- Which model is simpler to query for the frontend?
- Which handles "reply to reply" without deep nesting issues?
- Performance implications for tasks with 100+ comments

## Outcome

_Fill in after running: which approach won, or if neither worked. Then either promote the winning approach to `pdd/prompts/features/tasks/` or delete this file._
