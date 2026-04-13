# Prompt: Git Integration Service

**File**: pdd/prompts/features/git/grandline-09-git-integration.md
**Created**: 2026-04-12
**Updated**: 2026-04-12
**Depends on**: Phase 3 (models), Phase 8 (Execution Service)
**Project type**: Backend (FastAPI + aiodocker + GitHub REST API)

## Context

GrandLine is a One Piece-themed multi-agent orchestration platform. Phases 1-8 delivered Docker infrastructure, database models, JWT auth, Den Den Mushi message bus, Dial System LLM gateway, Vivre Card state checkpointing, and the Execution Service (containerized sandbox with gVisor). Crew agents (Shipwright, Doctor, Helmsman) work in real git repos with per-agent branches. Git is the source of truth — code merges via the standard PR flow.

The Git Integration Service manages the full git lifecycle for agent work: cloning repos into sandboxes, creating per-agent branches, committing with crew member attribution, pushing to remotes, creating PRs via GitHub API, and detecting conflicts before merge. All git operations (clone, branch, commit, push) run inside the Execution Service sandbox. GitHub API operations (create PR, list PRs) run from the backend via `httpx`.

## Task

Implement the Git Integration Service. TDD — tests first, then implementation.

1. **Schemas** (`app/schemas/git.py`):

   - `GitCloneRequest`:
     - `repo_url: str | None = None` — HTTPS git URL; defaults to `voyage.target_repo` if None
     - Validate: must start with `https://` if provided

   - `GitBranchRequest`:
     - `crew_member: str` — agent role (e.g. "shipwright", "doctor")
     - `base_branch: str = "main"` — branch to create from

   - `GitCommitRequest`:
     - `message: str` — commit message (1-500 chars)
     - `crew_member: str` — for author attribution
     - `files: dict[str, str] = {}` — path -> content to write before committing

   - `GitPushRequest`:
     - `branch: str` — branch to push

   - `GitPRRequest`:
     - `title: str` — PR title (1-200 chars)
     - `body: str = ""` — PR description
     - `head_branch: str` — source branch
     - `base_branch: str = "main"` — target branch

   - `GitConflictCheckRequest`:
     - `branch: str` — branch to check
     - `target_branch: str = "main"` — merge target

   Response schemas:

   - `GitRepoInfo`:
     - `sandbox_id: str`
     - `repo_url: str`
     - `default_branch: str`

   - `GitBranchInfo`:
     - `name: str`
     - `is_current: bool`

   - `GitCommitInfo`:
     - `sha: str`
     - `short_sha: str`
     - `message: str`
     - `author: str`
     - `timestamp: str`

   - `GitPushInfo`:
     - `branch: str`
     - `pushed: bool`

   - `GitPRInfo`:
     - `number: int`
     - `url: str`
     - `title: str`
     - `head: str`
     - `base: str`

   - `GitConflictInfo`:
     - `has_conflicts: bool`
     - `conflicting_files: list[str] = []`

2. **GitService** (`app/services/git_service.py`):

   Class-based (needs state for sandbox tracking per voyage):

   - `__init__(self, backend: ExecutionBackend, settings: Any)` — inject the git-configured backend and settings
   - `_repos: dict[uuid.UUID, str]` — maps voyage_id -> sandbox_id
   - `REPO_PATH = "/workspace/repo"` — cloned repo path inside sandbox

   **Branch naming convention**: `agent/<crew_member>/<voyage_id_hex8>`
   - e.g. `agent/shipwright/a1b2c3d4` (first 8 hex chars of voyage UUID)
   - Computed via `_branch_name(crew_member, voyage_id)` helper

   Methods:

   - `async clone_repo(voyage_id, user_id, repo_url) -> GitRepoInfo`:
     - Create sandbox via `backend.create(user_id)`
     - Store in `_repos[voyage_id] = sandbox_id`
     - Run: `git clone <repo_url> /workspace/repo`
     - Configure author: `git config user.name`, `git config user.email`
     - Return `GitRepoInfo`
     - Repo URL injected via HTTPS token URL: `https://<token>@github.com/owner/repo.git`
     - Parse owner/repo from URL for later GitHub API calls

   - `async create_branch(voyage_id, user_id, crew_member, base_branch) -> GitBranchInfo`:
     - Get sandbox from `_repos[voyage_id]`; raise `GitError("REPO_NOT_CLONED")` if missing
     - Branch name: `agent/<crew_member>/<voyage_id_hex8>`
     - Run: `cd /workspace/repo && git fetch origin && git checkout <base> && git checkout -b <branch_name>`
     - Return `GitBranchInfo(name=branch_name, is_current=True)`

   - `async list_branches(voyage_id, user_id) -> list[GitBranchInfo]`:
     - Run: `cd /workspace/repo && git branch --format='%(refname:short) %(HEAD)'`
     - Parse output: lines like `main ` or `agent/shipwright/abc12345 *`
     - Return list of `GitBranchInfo`

   - `async commit(voyage_id, user_id, message, crew_member, files) -> GitCommitInfo`:
     - If `files` non-empty: inject files via `backend.execute()` with `ExecutionRequest.files`
     - Run: `cd /workspace/repo && git add -A && git commit -m "<message>" --author="<crew_member> <GrandLine Crew <crew_member>@grandline.dev>"`
     - Parse output for commit SHA: `git rev-parse --short HEAD` and `git rev-parse HEAD`
     - Return `GitCommitInfo`

   - `async push(voyage_id, user_id, branch) -> GitPushInfo`:
     - Run: `cd /workspace/repo && git push origin <branch>`
     - Return `GitPushInfo(branch=branch, pushed=True)`

   - `async create_pr(voyage_id, user_id, title, body, head, base) -> GitPRInfo`:
     - **Not sandboxed** — uses `httpx.AsyncClient` to call GitHub REST API
     - Parse owner/repo from stored repo URL
     - `POST https://api.github.com/repos/{owner}/{repo}/pulls`
     - Headers: `Authorization: Bearer <github_token>`, `Accept: application/vnd.github+json`
     - Body: `{"title": title, "body": body, "head": head, "base": base}`
     - Return `GitPRInfo` from response

   - `async get_log(voyage_id, user_id, branch, limit=20) -> list[GitCommitInfo]`:
     - Run: `cd /workspace/repo && git log <branch> -<limit> --format='%H|%h|%s|%an|%aI'`
     - Parse pipe-delimited output
     - Return list of `GitCommitInfo`

   - `async check_conflicts(voyage_id, user_id, branch, target) -> GitConflictInfo`:
     - Run: `cd /workspace/repo && git fetch origin && git checkout <branch>`
     - Run: `git merge --no-commit --no-ff origin/<target> 2>&1; echo "EXIT:$?"`
     - If exit code != 0: `git diff --name-only --diff-filter=U` to list conflicting files
     - Run: `git merge --abort` to clean up
     - Return `GitConflictInfo`

   - `async cleanup_branches(voyage_id, user_id) -> None`:
     - List remote branches matching `agent/*/<voyage_id_hex8>`
     - Run: `git push origin --delete <branch>` for each
     - Destroy sandbox: `backend.destroy(sandbox_id)`
     - Remove from `_repos`

   - `async cleanup_all() -> None`:
     - Destroy all tracked sandboxes (for app shutdown)
     - Log but don't raise on individual failures
     - Clear `_repos`

   **Error handling**: `GitError(Exception)` in `app/services/git_service.py` — follows `ExecutionError` pattern.

   **Command safety**: All user-provided values (branch names, messages, URLs) passed through `shlex.quote()` before shell execution. Branch names validated: alphanumeric, hyphens, slashes, dots only.

   **GitHub token injection**: For clone/push, the repo URL is rewritten as `https://x-access-token:<token>@github.com/owner/repo.git`. The token comes from `settings.github_api_token`. Never logged or returned in responses.

3. **Config settings** (`app/core/config.py`):

   Add under a `# Git Integration` comment block:
   - `git_sandbox_image: str = "bitnami/git:latest"` — container image with git installed
   - `git_sandbox_memory_limit: str = "512m"` — repos need more memory than code execution
   - `git_default_branch: str = "main"`
   - `git_author_name: str = "GrandLine Crew"`
   - `git_author_email: str = "crew@grandline.dev"`
   - `github_api_token: str = ""` — GitHub personal access token for push/PR operations

4. **Factory update** (`app/execution/factory.py`):

   Add `create_git_backend(settings) -> ExecutionBackend`:
   - Creates a `GVisorContainerBackend` with git-specific settings:
     - Image: `settings.git_sandbox_image`
     - Network: **enabled** (git needs to reach remotes)
     - Memory: `settings.git_sandbox_memory_limit`
     - Other settings (runtime, cpu quota/period) inherited from main execution settings
   - Uses `types.SimpleNamespace` to construct a settings-like object with overrides

5. **REST API** (`app/api/v1/git.py`):

   Router prefix: `/voyages/{voyage_id}/git`. Tags: `["git"]`.
   All endpoints require auth (`get_current_user`) + voyage ownership (`get_authorized_voyage`).

   - `POST /clone` -> `GitRepoInfo`:
     - Body: `GitCloneRequest`
     - Uses `voyage.target_repo` if `body.repo_url` is None; 400 if both are None
     - Calls `git_service.clone_repo(voyage_id, user.id, repo_url)`

   - `POST /branches` -> `GitBranchInfo`:
     - Body: `GitBranchRequest`
     - Calls `git_service.create_branch(...)`

   - `GET /branches` -> `list[GitBranchInfo]`:
     - Calls `git_service.list_branches(voyage_id, user.id)`

   - `POST /commit` -> `GitCommitInfo`:
     - Body: `GitCommitRequest`
     - Calls `git_service.commit(...)`

   - `POST /push` -> `GitPushInfo`:
     - Body: `GitPushRequest`
     - Calls `git_service.push(...)`

   - `POST /pr` -> `GitPRInfo`:
     - Body: `GitPRRequest`
     - Calls `git_service.create_pr(...)`

   - `GET /log` -> `list[GitCommitInfo]`:
     - Query params: `branch: str = "main"`, `limit: int = 20`
     - Calls `git_service.get_log(...)`

   - `POST /conflicts` -> `GitConflictInfo`:
     - Body: `GitConflictCheckRequest`
     - Calls `git_service.check_conflicts(...)`

   - `DELETE /branches` -> 204 No Content:
     - Calls `git_service.cleanup_branches(voyage_id, user.id)`

   **Error mapping**:
   - `GitError("REPO_NOT_CLONED")` -> 409 Conflict
   - `GitError("REPO_ALREADY_CLONED")` -> 409 Conflict
   - `GitError("NO_TARGET_REPO")` -> 400 Bad Request
   - `GitError("INVALID_BRANCH_NAME")` -> 400 Bad Request
   - `GitError("GITHUB_API_ERROR")` -> 502 Bad Gateway
   - Other `GitError` -> 500 Internal Server Error

   **Dependencies** (`app/api/v1/dependencies.py`):
   - Add `get_git_service(request: Request) -> GitService` — reads from `request.app.state.git_service`

   Wire into `app/api/v1/router.py`.

6. **App lifespan** (`app/main.py`):

   In the `lifespan()` context manager:
   ```python
   git_backend = create_git_backend(settings)
   app.state.git_service = GitService(git_backend, settings)
   # ... yield ...
   await app.state.git_service.cleanup_all()
   await git_backend.close()
   ```

## Input

- Existing `Voyage` model with `target_repo: str | None` at `app/models/voyage.py`
- Existing `CrewAction` model at `app/models/crew_action.py` — for logging git operations (future)
- Existing `ExecutionBackend` ABC at `app/execution/backend.py`
- Existing `GVisorContainerBackend` at `app/execution/gvisor_backend.py`
- Existing `create_backend` factory at `app/execution/factory.py`
- Existing `get_current_user`, `get_authorized_voyage` at `app/api/v1/dependencies.py`
- Existing `Settings` at `app/core/config.py` — GRANDLINE_ prefix, pydantic-settings
- `httpx>=0.27.2` already in requirements (for GitHub API calls)

## Output format

- Python files following existing conventions (async, type-annotated, Pydantic v2)
- GitService as a class (needs state for per-voyage sandbox tracking)
- Unit tests with mocked ExecutionBackend (AsyncMock) — no Docker/git daemon required for CI
- All new files under `src/backend/app/` and `src/backend/tests/`

## Constraints

- Git operations (clone, branch, commit, push) run inside sandboxed containers — never on the host
- GitHub API operations (create PR) run from the backend via `httpx` — no `gh` CLI needed
- GitHub token never exposed in logs, responses, or error messages
- All user-provided values passed through `shlex.quote()` before shell execution
- Branch names validated: `^[a-zA-Z0-9/_.-]+$` — no special shell characters
- Repo URLs must be HTTPS only — no `file://`, `git://`, or `ssh://` protocols
- Per-voyage sandboxes — one git sandbox per voyage, not per user
- `Voyage.target_repo` is the default repo URL; clone request can override it
- `create_git_backend()` creates a separate backend instance with network enabled and git image
- No new database models in v1 — sandbox tracking is in-memory (like ExecutionService)
- Factory only adds `create_git_backend()` — existing `create_backend()` unchanged

## Edge Cases

- `clone_repo()` when `voyage.target_repo` is None and no URL in request -> `GitError("NO_TARGET_REPO")`
- `clone_repo()` when repo is already cloned for this voyage -> `GitError("REPO_ALREADY_CLONED")`
- `create_branch()` before cloning -> `GitError("REPO_NOT_CLONED")`
- `create_branch()` with duplicate branch name -> git returns non-zero exit code, wrapped in `GitError`
- `commit()` with no changes -> git returns "nothing to commit", wrapped in `GitError`
- `push()` when remote rejects (force push needed) -> `GitError` with git stderr
- `push()` with invalid GitHub token -> authentication failure captured in exit code/stderr
- `create_pr()` when GitHub API returns error (e.g., PR already exists) -> `GitError("GITHUB_API_ERROR")`
- `create_pr()` when head branch has no new commits vs base -> GitHub returns 422, wrapped in error
- `check_conflicts()` with no conflicts -> `GitConflictInfo(has_conflicts=False, conflicting_files=[])`
- `check_conflicts()` with conflicts -> populated `conflicting_files` list
- `cleanup_branches()` when no branches to clean -> succeeds silently
- `cleanup_branches()` when sandbox already destroyed -> handle gracefully
- Branch name with shell injection attempt (e.g., `; rm -rf /`) -> `shlex.quote()` neutralizes, validation rejects
- Repo URL with embedded credentials -> URL validation rejects non-HTTPS schemes
- Sandbox killed externally between operations -> backend raises `ExecutionError`, wrapped in `GitError`
- `cleanup_all()` during shutdown with some sandboxes already gone -> log and continue

## Test Plan

### tests/test_git_schemas.py
- `test_clone_request_defaults` — repo_url defaults to None
- `test_clone_request_rejects_non_https` — `file://` and `ssh://` URLs rejected
- `test_clone_request_accepts_https` — valid HTTPS URL accepted
- `test_branch_request_defaults` — base_branch defaults to "main"
- `test_commit_request_validation` — message min/max length
- `test_commit_request_defaults` — files default to empty dict
- `test_pr_request_validation` — title min/max length
- `test_conflict_check_defaults` — target_branch defaults to "main"
- `test_response_schemas_fields` — all response schemas construct correctly

### tests/test_git_service.py (mocked ExecutionBackend)
- `test_clone_creates_sandbox_and_runs_clone` — backend.create + backend.execute called
- `test_clone_configures_git_author` — git config commands include author name/email
- `test_clone_injects_github_token_in_url` — URL rewritten with token
- `test_clone_already_cloned_raises` — second clone for same voyage -> REPO_ALREADY_CLONED
- `test_create_branch_naming_convention` — branch name matches `agent/<member>/<hex8>`
- `test_create_branch_before_clone_raises` — REPO_NOT_CLONED error
- `test_create_branch_runs_checkout` — correct git commands
- `test_list_branches_parses_output` — git branch output parsed into GitBranchInfo list
- `test_commit_stages_and_commits` — git add + git commit with correct message/author
- `test_commit_with_files_injects_files` — files dict passed in ExecutionRequest
- `test_push_runs_push_command` — git push origin <branch>
- `test_create_pr_calls_github_api` — httpx POST to correct endpoint
- `test_create_pr_parses_response` — GitPRInfo from GitHub response
- `test_create_pr_handles_api_error` — non-200 response -> GitError
- `test_get_log_parses_output` — git log format parsed into GitCommitInfo list
- `test_check_conflicts_no_conflicts` — clean merge -> has_conflicts=False
- `test_check_conflicts_with_conflicts` — conflict detected, files listed
- `test_check_conflicts_aborts_merge` — git merge --abort called after check
- `test_cleanup_branches_destroys_sandbox` — backend.destroy called
- `test_cleanup_all_destroys_all` — all tracked sandboxes destroyed
- `test_cleanup_all_continues_on_error` — one failure doesn't block others
- `test_branch_name_validation_rejects_injection` — shell chars rejected

### tests/test_git_api.py (mocked GitService)
- `test_clone_returns_repo_info` — POST /clone returns GitRepoInfo
- `test_clone_uses_voyage_target_repo` — repo_url=None uses voyage.target_repo
- `test_clone_no_target_repo_400` — no URL anywhere -> 400
- `test_create_branch_returns_info` — POST /branches returns GitBranchInfo
- `test_list_branches_returns_list` — GET /branches returns list
- `test_commit_returns_commit_info` — POST /commit returns GitCommitInfo
- `test_push_returns_push_info` — POST /push returns GitPushInfo
- `test_create_pr_returns_pr_info` — POST /pr returns GitPRInfo
- `test_get_log_returns_entries` — GET /log returns list
- `test_check_conflicts_returns_info` — POST /conflicts returns GitConflictInfo
- `test_cleanup_branches_204` — DELETE /branches returns 204
- `test_repo_not_cloned_409` — REPO_NOT_CLONED -> 409
- `test_github_api_error_502` — GITHUB_API_ERROR -> 502
- `test_unauthorized_401` — no token -> 401
