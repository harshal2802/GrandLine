# Prompt: Real git diffs in the deck (Phase A2)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-A2-git-diffs.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: A1 (the artifact-based Changes tab), Phase 9 (Git Integration Service)
**Project type**: Full-stack (FastAPI git service + Next.js diff viewer)

## Context

A1 added a **Changes** tab that lists the files the Shipwright generated (`BuildArtifact`
content) — the always-available view. A2 adds the real thing: **true git diffs** between the
base branch and the crew's working branch, plus changed-file lists and file-content-at-ref.
When a voyage actually used git (cloned a repo, the Shipwright committed to its branch), users
see real before/after; when it didn't, the UI falls back to A1's artifacts view.

`GitService` already runs git inside the per-voyage sandbox (clone/branch/commit/push/PR/log/
conflicts) but had no diff capability. This phase fills that gap and surfaces it in the deck.

## Task

1. **GitService** (`app/services/git_service.py`) — new methods mirroring the existing
   exec-git-in-sandbox `_run` pattern + `GitError`:
   - `list_changed_files(voyage_id, user_id, base, head) -> list[GitChangedFile]` —
     `git diff --name-status base...head`, rename-aware.
   - `diff(voyage_id, user_id, base, head, *, path=None) -> str` — unified diff
     (`git diff base...head [-- path]`), whole-branch or single file.
   - `get_file_content(voyage_id, user_id, ref, path) -> str` — `git show ref:path`.
   - **Security**: validate `base`/`head` with the existing `BRANCH_NAME_RE`; `shlex.quote`
     every ref; `_validate_repo_path(path)` rejects empty / absolute / `~` / `..` segments
     (traversal + injection defense).
2. **Schemas** (`app/schemas/git.py`): `GitChangedFile{path,status}`, `GitDiff{base,head,path,unified}`,
   `GitFileContent{ref,path,content}`.
3. **API** (`app/api/v1/git.py`, owner-scoped via `get_authorized_voyage`):
   `GET /voyages/{id}/git/changed-files`, `/diff`, `/file-content`; `GitError` via
   `_handle_git_error`, `INVALID_PATH` → 400.
4. **Frontend**:
   - `hooks/useGitDiff.ts` — discovers the crew's head branch from `/git/branches`
     (`pickHeadBranch`: first `agent/*`, else current non-`main`, else null) so `ChangesPanel`'s
     `{voyageId}` contract is unchanged; `useChangedFiles`/`useFileDiff` React Query reads,
     `enabled`-gated on a head branch.
   - `ChangesPanel.tsx` — a **Files | Diff** mode toggle; Diff mode shows the changed-file list
     (A/M/D/R badge) + the selected file's unified diff with added/removed line tint. Falls back
     to the A1 Files view when there's no crew branch or the git calls error. Loading/error/empty
     throughout; A1 intact.

## Output format
- Backend: async, type-annotated, Pydantic v2; new methods mirror the existing `_run` helper.
- Frontend: TS strict, `interface` props, Tailwind, React Query; reuse `prism-react-renderer`
  (no new dependency).
- Tests: pytest (mocked sandbox exec — name-status parse, three-dot argv, ref/path rejection,
  endpoint shapes + owner-scoping) and Vitest (hook + mode toggle + no-git fallback).

## Constraints
- No new frontend dependency. No Alembic migration.
- Path/ref validation is mandatory (security): reject traversal/absolute paths; quote all refs.
- Falling back to A1 when a voyage didn't use git is required — A2 never breaks the
  always-available view.

## Edge Cases
- Voyage never used git / no `agent/*` branch → `pickHeadBranch` returns null → UI shows A1 Files.
- Diff endpoint errors/empty → graceful fallback + note, never a crash.
- Renamed files (`R` status) → surface the new path.
- `path` with `..` / absolute / `~` → `INVALID_PATH` 400, never executed.
- Binary files / very large diffs → render as-is (plain), no token explosion.

## Note (implementation reality)
`prism-react-renderer`'s bundled Prism lacks the `diff` grammar and `prismjs/components` isn't
reachable without a new dep, so the unified diff renders via graceful plaintext tokenization
with explicit per-line `+`/`-` background tint (functionally equivalent, zero new deps).
Registering `prism-diff` / adding `prismjs` directly is a possible later enhancement.
