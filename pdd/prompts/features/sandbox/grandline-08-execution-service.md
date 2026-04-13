# Prompt: Execution Service (Containerized Sandbox + gVisor)

**File**: pdd/prompts/features/sandbox/grandline-08-execution-service.md
**Created**: 2026-04-09
**Updated**: 2026-04-12
**Depends on**: Phase 1 (Docker infrastructure), Phase 3 (CrewAction model)
**Project type**: Backend (FastAPI + Docker + aiodocker)

## Context

GrandLine is a One Piece-themed multi-agent orchestration platform. Phases 1-7 delivered Docker infrastructure, database models, JWT auth, the Den Den Mushi message bus, the Dial System LLM gateway, and Vivre Card state checkpointing.

Crew agents (Shipwrights, Doctor, Helmsman) generate and execute untrusted code. This code must never run on the host. The Execution Service is the security boundary — it runs all agent-generated code inside isolated containers with gVisor runtime, resource limits, and no network access. The architecture decision mandates a swappable `ExecutionBackend` interface so the sandbox implementation can evolve (gVisor → Firecracker → Wasm) without changing the calling code.

## Task

Implement the Execution Service with a swappable backend and Docker + gVisor v1 implementation. TDD — tests first, then implementation.

1. **Schemas** (`app/schemas/execution.py`):

   - `ExecutionRequest`:
     - `command: str` — the shell command to run inside the container
     - `working_dir: str = "/workspace"` — working directory inside container
     - `timeout_seconds: int = 30` — max execution time (1-300 range)
     - `environment: dict[str, str] = {}` — env vars to inject
     - `files: dict[str, str] = {}` — path → content to write before execution
   
   Note: `user_id` and `voyage_id` are NOT in the schema — they come from auth context in the API layer.

   - `ExecutionResult`:
     - `exit_code: int`
     - `stdout: str`
     - `stderr: str`
     - `timed_out: bool = False`
     - `duration_seconds: float`
     - `sandbox_id: str`

   - `SandboxStatus`:
     - `sandbox_id: str`
     - `state: Literal["running", "idle", "destroyed"]` — enforced by Pydantic, rejects invalid values
     - `user_id: uuid.UUID`
     - `created_at: datetime`

2. **ExecutionBackend ABC** (`app/execution/backend.py`):

   Create `app/execution/` package with `__init__.py`.

   - `ExecutionBackend(ABC)`:
     - `async create(user_id: UUID) -> str` — provision a sandbox, return sandbox_id
     - `async execute(sandbox_id: str, request: ExecutionRequest) -> ExecutionResult`
     - `async destroy(sandbox_id: str) -> None` — tear down the sandbox
     - `async status(sandbox_id: str) -> SandboxStatus` — query sandbox state

   - `ExecutionError(Exception)` — raised on sandbox failures (same pattern as `ProviderError` in `dial_system/adapters/base.py`)

3. **GVisorContainerBackend** (`app/execution/gvisor_backend.py`):

   Docker + gVisor implementation using `aiodocker`:

   - Constructor: takes `Settings` instance, creates `aiodocker.Docker()` client
   
   - `create(user_id)`:
     - Container config:
       - Image: `settings.execution_image` (default `python:3.13-slim`)
       - Command: `["tail", "-f", "/dev/null"]` (keep container alive)
       - Runtime: `settings.execution_gvisor_runtime` (default `"runsc"`)
       - `HostConfig`:
         - `Memory`: parse `settings.execution_memory_limit` (e.g., `"256m"` → bytes)
         - `CpuQuota`: `settings.execution_cpu_quota` (default 50000)
         - `CpuPeriod`: `settings.execution_cpu_period` (default 100000)
         - `NetworkMode`: `"none"` if not `settings.execution_network_enabled`
         - `ReadonlyRootfs`: `True`
         - `Tmpfs`: `{"/workspace": "rw,size=64m", "/tmp": "rw,size=32m"}`
       - Labels: `{"grandline.user_id": str(user_id), "grandline.managed": "true"}`
     - Start the container
     - Return the container ID as sandbox_id
     - Wrap Docker errors in `ExecutionError`

   - `execute(sandbox_id, request)`:
     - If `request.files` is non-empty: validate paths via `_validate_file_path()`, check sizes against `MAX_FILE_SIZE`, create a tar archive in memory, and inject via `put_archive("/workspace")`
     - Create exec instance: `container.exec(cmd=["sh", "-c", request.command], workdir=request.working_dir, environment=[f"{k}={v}" for k, v in request.environment.items()], tty=False)`
     - Start exec with `exec_obj.start(detach=False)` — returns a `Stream` object (sync call, NOT async)
     - Read output via `stream.read_out()` loop: `msg.stream == 1` → stdout, `msg.stream == 2` → stderr, `None` → EOF
     - Wrap the read loop in `asyncio.wait_for()` with `request.timeout_seconds` for timeout enforcement
       - On `TimeoutError`: close the stream, set `timed_out=True`
     - Inspect exec to get exit code: `exec_obj.inspect()` → `ExitCode`
     - Track duration with `time.monotonic()` before/after
     - Return `ExecutionResult`
     - **Important aiodocker API notes**:
       - `exec.start(detach=True)` fires and forgets — no output, no blocking. Must use `detach=False`.
       - `containers.container()` is **sync**, `container.exec/show/kill/delete/put_archive/start` are **async**
       - `exec.start(detach=False)` is **sync** (returns Stream), `stream.read_out()` is **async**

   - `destroy(sandbox_id)`:
     - Get container: `docker.containers.container(sandbox_id)`
     - Kill (force stop): `container.kill()`
     - Delete: `container.delete(force=True)`
     - Catch `DockerError` for already-removed containers — log and ignore
   
   - `status(sandbox_id)`:
     - Inspect container: `container.show()`
     - Map Docker `State.Status` to SandboxStatus state:
       - `"running"` → `"running"`
       - `"created"`, `"paused"` → `"idle"`
       - Everything else → `"destroyed"`
     - Extract `user_id` from labels
     - Extract `Created` timestamp
     - Raise `ExecutionError` if container not found

   - `close()`: Close the aiodocker client session

   **Memory limit parsing**: `_parse_memory("256m")` → `268435456` bytes. Support `m` (MiB) and `g` (GiB) suffixes. Validates input: raises `ValueError` for empty strings, invalid suffixes (e.g. `"256x"`), and non-numeric values (e.g. `"abcm"`).

   **File size limit**: `MAX_FILE_SIZE = 1_048_576` (1 MiB). Each file in `request.files` is checked before tar injection; exceeding the limit raises `ExecutionError`.

   **Path traversal sanitization**: `_validate_file_path()` rejects absolute paths and `..` components in file paths before tar archive creation, raising `ExecutionError`.

4. **ExecutionService** (`app/services/execution_service.py`):

   Class-based (needs state for sandbox pool tracking):

   - `__init__(self, backend: ExecutionBackend)` — inject the backend
   - `_sandboxes: dict[uuid.UUID, str]` — maps user_id → sandbox_id

   - `async run(self, user_id: UUID, request: ExecutionRequest) -> ExecutionResult`:
     - Get or create sandbox for the user
     - Call `backend.execute(sandbox_id, request)`
     - Return result

   - `async get_or_create_sandbox(self, user_id: UUID) -> str`:
     - If `user_id` in `_sandboxes`: verify sandbox is still alive via `backend.status()`
       - If status check fails (ExecutionError): remove from tracking, create new
     - If not tracked: `sandbox_id = await backend.create(user_id)`
     - Store in `_sandboxes[user_id] = sandbox_id`
     - Return sandbox_id

   - `async destroy_sandbox(self, user_id: UUID) -> None`:
     - If user has a tracked sandbox: `await backend.destroy(sandbox_id)`, remove from `_sandboxes`
     - Raise `ExecutionError("SANDBOX_NOT_FOUND", ...)` if no sandbox for user

   - `async cleanup_all(self) -> None`:
     - Destroy all tracked sandboxes (for app shutdown)
     - Log but don't raise on individual failures
     - Clear `_sandboxes`

5. **Backend factory** (`app/execution/factory.py`):

   - `create_backend(settings: Settings) -> ExecutionBackend`:
     - `"gvisor"` → `GVisorContainerBackend(settings)`
     - Raise `ValueError(f"Unknown execution backend: {name}")` for unknown

6. **Config settings** (`app/core/config.py`):

   Add under a `# Execution Service (Sandbox)` comment block:
   - `execution_backend: str = "gvisor"`
   - `execution_image: str = "python:3.13-slim"`
   - `execution_memory_limit: str = "256m"`
   - `execution_cpu_quota: int = 50000`
   - `execution_cpu_period: int = 100000`
   - `execution_default_timeout: int = 30`
   - `execution_network_enabled: bool = False`
   - `execution_gvisor_runtime: str = "runsc"`

7. **REST API** (`app/api/v1/execution.py`):

   Router prefix: none (endpoints have distinct paths). Tags: `["execution"]`.

   - `POST /api/v1/voyages/{voyage_id}/execute` → `ExecutionResult`:
     - Body: `ExecutionRequest`
     - Requires auth (`get_current_user`) + voyage ownership (`get_authorized_voyage`)
     - Sets `user_id` from the authenticated user — NOT from request body
     - Calls `execution_service.run(user_id, request)`
     - Error differentiation:
       - `ExecutionError` with "Invalid file path" or "File too large" → **400** `INVALID_REQUEST`
       - Other `ExecutionError` → **500** `EXECUTION_ERROR`

   - `GET /api/v1/sandbox/status` → `SandboxStatus`:
     - Requires auth (`get_current_user`)
     - Calls `execution_service.get_sandbox_status(user_id)` → looks up user's sandbox, calls `backend.status()`
     - 404 if no active sandbox

   - `DELETE /api/v1/sandbox` → 204 No Content:
     - Requires auth (`get_current_user`)
     - Calls `execution_service.destroy_sandbox(user_id)`
     - 404 if no active sandbox

   **Dependencies** (`app/api/v1/dependencies.py`):
   - Add `get_execution_service()` dependency:
     - Uses `request.app.state.execution_service` (set during app startup)
     - Returns the `ExecutionService` singleton

   Wire into `app/api/v1/router.py`.

   **App lifespan wiring** (`app/main.py`):
   - In the `lifespan()` context manager, create the backend via `create_backend(settings)` and wrap it in `ExecutionService(backend)`
   - Set `app.state.execution_service = ExecutionService(backend)`
   - On shutdown: `await app.state.execution_service.cleanup_all()` then `await backend.close()`

## Input

- Existing `CrewAction` model at `src/backend/app/models/crew_action.py` — for future Ship's Log integration
- Existing `ProviderAdapter` ABC at `src/backend/app/dial_system/adapters/base.py` — pattern reference for the `ExecutionBackend` ABC
- Existing `Settings` at `src/backend/app/core/config.py` — GRANDLINE_ prefix, pydantic-settings
- Existing `get_current_user`, `get_authorized_voyage` at `src/backend/app/api/v1/dependencies.py`
- Existing `AuthError` pattern at `src/backend/app/services/auth_service.py`

## Output format

- Python files following existing conventions (async, type-annotated, Pydantic v2)
- New `execution/` package under `src/backend/app/`
- ExecutionService is a class (needs state), unlike auth_service/vivre_card_service which are module-level functions
- Unit tests with mocked aiodocker (AsyncMock) — no Docker daemon required for CI
- Integration tests marked `@pytest.mark.integration` — require Docker daemon
- All new files under `src/backend/app/` and `src/backend/tests/`

## Constraints

- Add `aiodocker>=0.23.0` to `requirements.txt`
- Never execute code on the host — all execution goes through the backend
- `user_id` comes from auth context, never from the request body (prevents impersonation)
- Network disabled by default — `NetworkMode: "none"`
- Read-only root filesystem — only `/workspace` (tmpfs) and `/tmp` (tmpfs) are writable
- Memory limit enforced at container level, not just in-process
- Timeout enforced via `asyncio.wait_for()`, not `signal.alarm()`
- `ExecutionError` follows the same pattern as `ProviderError` (simple exception with message)
- Container labels must include `grandline.user_id` and `grandline.managed=true` for tracking
- Factory only supports `"gvisor"` backend in v1 — no subprocess fallback yet
- gVisor runtime name is configurable — dev environments may not have `runsc` installed

## Edge Cases

- `create()` when Docker daemon is not running → `ExecutionError` with clear message
- `create()` when image doesn't exist locally → aiodocker pulls it (may be slow first time)
- `execute()` with timeout of 0 or negative → schema validation rejects (min=1)
- `execute()` when container was killed externally → `ExecutionError`
- `execute()` with empty command → let container handle it (will fail with exit code)
- `execute()` exceeds timeout → `timed_out=True`, stdout/stderr may be partial
- `destroy()` on already-destroyed container → handle gracefully, no error
- `status()` on non-existent container → `ExecutionError`
- `get_or_create_sandbox()` when tracked sandbox was killed externally → detect via status check, recreate
- `cleanup_all()` with some containers already removed → log and continue
- `files` dict with nested paths (e.g., `"src/main.py"`) → tar archive preserves directory structure
- `files` dict with `../` traversal paths → rejected by `_validate_file_path()` before tar creation
- `files` dict with absolute paths (e.g., `/etc/passwd`) → rejected by `_validate_file_path()`
- `files` dict with file exceeding `MAX_FILE_SIZE` (1 MiB) → rejected before tar creation
- Invalid memory limit suffix (e.g., `"256x"`) → `_parse_memory` raises `ValueError`
- Empty memory limit string → `_parse_memory` raises `ValueError`
- Non-numeric memory value (e.g., `"abcm"`) → `_parse_memory` raises `ValueError`
- Memory limit exceeded by running process → container OOM-kills the process, captured in exit code

## Test Plan

### tests/test_execution_schemas.py
- `test_execution_request_defaults` — default working_dir, timeout, empty env/files
- `test_execution_request_custom_values` — all fields set
- `test_execution_request_timeout_range` — rejects timeout < 1 or > 300
- `test_execution_result_fields` — all fields present
- `test_sandbox_status_fields` — all fields present
- `test_sandbox_status_state_accepts_valid_values` — "running", "idle", "destroyed" accepted
- `test_sandbox_status_state_rejects_invalid_value` — "unknown" → ValidationError

### tests/test_execution_backend.py (mocked aiodocker)
- `test_create_sets_gvisor_runtime` — container config includes runtime=runsc
- `test_create_sets_resource_limits` — memory, cpu_quota, cpu_period in HostConfig
- `test_create_disables_network` — NetworkMode=none when network disabled
- `test_create_sets_readonly_rootfs` — ReadonlyRootfs=True with tmpfs mounts
- `test_create_labels_include_user_id` — grandline.user_id label set
- `test_create_starts_container` — container.start() called
- `test_execute_captures_output` — stdout and stderr returned
- `test_execute_captures_exit_code` — non-zero exit code preserved
- `test_execute_respects_timeout` — asyncio.TimeoutError sets timed_out=True
- `test_execute_writes_files` — put_archive called with correct tar data
- `test_execute_sets_environment` — env vars passed to exec_create
- `test_execute_tracks_duration` — duration_seconds > 0
- `test_destroy_removes_container` — kill + delete called
- `test_destroy_handles_already_removed` — DockerError caught gracefully
- `test_status_maps_running` — Docker "running" → SandboxStatus "running"
- `test_status_maps_created_to_idle` — Docker "created" → "idle"
- `test_status_not_found_raises` — missing container → ExecutionError
- `test_parse_memory_megabytes` — "256m" → 268435456
- `test_parse_memory_gigabytes` — "1g" → 1073741824
- `test_parse_memory_invalid_suffix_raises` — "256x" → ValueError
- `test_parse_memory_empty_raises` — "" → ValueError
- `test_parse_memory_non_numeric_raises` — "abcm" → ValueError
- `test_build_tar_rejects_path_traversal` — "../etc/passwd" → ExecutionError
- `test_build_tar_rejects_absolute_path` — "/etc/passwd" → ExecutionError
- `test_build_tar_rejects_file_too_large` — exceeds MAX_FILE_SIZE → ExecutionError
- `test_build_tar_accepts_nested_path` — "src/main.py" → valid tar bytes

### tests/test_execution_service.py (mocked backend)
- `test_run_creates_sandbox_and_executes` — happy path
- `test_run_reuses_existing_sandbox` — second call uses same sandbox
- `test_get_or_create_detects_dead_sandbox` — recreates if status check fails
- `test_destroy_sandbox_calls_backend` — delegates to backend.destroy()
- `test_destroy_sandbox_not_found_raises` — no sandbox for user
- `test_cleanup_all_destroys_all` — all tracked sandboxes destroyed
- `test_cleanup_all_continues_on_error` — one failure doesn't block others

### tests/test_execution_factory.py
- `test_creates_gvisor_backend` — "gvisor" → GVisorContainerBackend
- `test_raises_for_unknown_backend` — "unknown" → ValueError

### tests/test_execution_api.py (mocked service)
- `test_execute_returns_result` — POST returns ExecutionResult
- `test_execute_sets_user_from_auth` — user_id from token, not body
- `test_sandbox_status_returns_status` — GET returns SandboxStatus
- `test_sandbox_status_not_found` — 404 when no sandbox
- `test_destroy_sandbox_204` — DELETE returns 204
- `test_destroy_sandbox_not_found` — 404 when no sandbox
- `test_execute_unauthorized_401` — no token → 401
- `test_execute_invalid_path_returns_400` — path traversal error → 400 INVALID_REQUEST
- `test_execute_file_too_large_returns_400` — file size error → 400 INVALID_REQUEST
