# Plan: Execution Service — Containerized Sandbox (Phase 8)

**Issue**: #9
**Branch**: `feat/issue-9-execution-service`
**Depends on**: Phase 1 (Docker), Phase 3 (models)

---

## Problem

Crew agents (Shipwrights, Doctor, Helmsman) generate and execute untrusted code. This code must never run on the host — it needs a security boundary with resource limits, filesystem isolation, and network restrictions. The Execution Service is that boundary.

The architecture decision mandates a swappable `ExecutionBackend` interface so the sandbox implementation can evolve (gVisor → Firecracker → Wasm) without changing the calling code.

## What exists already

| Artifact | Location | Status |
|---|---|---|
| Docker infrastructure | `src/infra/docker/docker-compose.yml` | Done — api, frontend, db, redis |
| `CrewAction` model | `src/backend/app/models/crew_action.py` | Done — logs agent actions |
| `CrewRole` enum | `src/backend/app/models/enums.py` | Done — captain, navigator, doctor, shipwright, helmsman |
| `ProviderAdapter` ABC pattern | `src/backend/app/dial_system/adapters/base.py` | Done — good reference for the `ExecutionBackend` ABC pattern |
| Settings (pydantic-settings) | `src/backend/app/core/config.py` | Done — GRANDLINE_ prefix |

## What needs to be built

### Phase 1: Data models — ExecutionRequest/Result schemas

**File**: `src/backend/app/schemas/execution.py`

Pydantic schemas for the execution boundary:

- `ExecutionRequest`:
  - `command: str` — the shell command to execute
  - `working_dir: str = "/workspace"` — working directory inside the container
  - `timeout_seconds: int = 30` — max execution time
  - `environment: dict[str, str] = {}` — environment variables to inject
  - `files: dict[str, str] = {}` — file path → content to write before execution
  - `user_id: uuid.UUID` — for per-user isolation
  - `voyage_id: uuid.UUID` — for tracking

- `ExecutionResult`:
  - `exit_code: int`
  - `stdout: str`
  - `stderr: str`
  - `timed_out: bool`
  - `duration_seconds: float`
  - `sandbox_id: str` — container/sandbox identifier for logging

- `SandboxStatus`:
  - `sandbox_id: str`
  - `state: str` — "running", "idle", "destroyed"
  - `user_id: uuid.UUID`
  - `created_at: datetime`

### Phase 2: ExecutionBackend ABC

**File**: `src/backend/app/execution/__init__.py` (package)
**File**: `src/backend/app/execution/backend.py`

Abstract base class defining the sandbox contract:

- `create(user_id: UUID) -> str` — provision a sandbox, return sandbox_id
- `execute(sandbox_id: str, request: ExecutionRequest) -> ExecutionResult` — run code in sandbox
- `destroy(sandbox_id: str) -> None` — tear down the sandbox
- `status(sandbox_id: str) -> SandboxStatus` — query sandbox state

Plus `ExecutionError` exception for sandbox failures (same pattern as `ProviderError`).

### Phase 3: GVisorContainerBackend

**File**: `src/backend/app/execution/gvisor_backend.py`

Docker + gVisor implementation of `ExecutionBackend`:

- `create()`:
  - Pull/use a base image (e.g., `python:3.13-slim`)
  - Create container with `runtime="runsc"` (gVisor)
  - Resource limits: `mem_limit`, `cpu_quota`, `cpu_period`
  - Network disabled: `network_disabled=True`
  - Read-only root filesystem with writable `/workspace` tmpfs
  - Label with `user_id` for per-user tracking
  - Start the container in idle state (e.g., `tail -f /dev/null`)

- `execute()`:
  - Write `request.files` into the container's `/workspace` via `put_archive()`
  - Set environment variables from `request.environment`
  - Run `request.command` via `exec_create()` + `exec_start()`
  - Apply timeout — kill container exec if exceeded, set `timed_out=True`
  - Capture stdout, stderr, exit_code
  - Return `ExecutionResult`

- `destroy()`:
  - Stop and remove the container
  - Handle already-stopped/removed gracefully

- `status()`:
  - Inspect container state via Docker API
  - Map Docker states to SandboxStatus

Uses `aiodocker` (async Docker SDK) for non-blocking container operations.

### Phase 4: ExecutionService (public API)

**File**: `src/backend/app/services/execution_service.py`

The facade that crew agents call. Manages sandbox lifecycle:

- `run(request: ExecutionRequest) -> ExecutionResult`:
  - Get or create a sandbox for the user (pool management)
  - Call `backend.execute()`
  - Log the execution as a `CrewAction` (optional, for Ship's Log)
  - Return the result

- `get_or_create_sandbox(user_id: UUID) -> str`:
  - Check if user already has an active sandbox
  - If not, call `backend.create(user_id)`
  - Track in an in-memory dict `_sandboxes: dict[UUID, str]`

- `destroy_sandbox(user_id: UUID) -> None`:
  - Call `backend.destroy()` and remove from tracking

- `cleanup_all() -> None`:
  - Destroy all tracked sandboxes (for shutdown/restart)

Constructor takes the `ExecutionBackend` instance (dependency injection).

### Phase 5: Backend factory + config

**File**: `src/backend/app/execution/factory.py`

- `create_backend(settings: Settings) -> ExecutionBackend`:
  - Read `settings.execution_backend` (default: `"gvisor"`)
  - `"gvisor"` → `GVisorContainerBackend(settings)`
  - Future: `"subprocess"` → `SubprocessBackend(settings)` (for dev/testing)
  - Raise `ValueError` for unknown backend

**File**: `src/backend/app/core/config.py` — Add:
- `execution_backend: str = "gvisor"`
- `execution_image: str = "python:3.13-slim"`
- `execution_memory_limit: str = "256m"`
- `execution_cpu_quota: int = 50000` (50% of one core)
- `execution_cpu_period: int = 100000`
- `execution_default_timeout: int = 30`
- `execution_network_enabled: bool = False`
- `execution_gvisor_runtime: str = "runsc"`

### Phase 6: REST API endpoints

**File**: `src/backend/app/api/v1/execution.py`

- `POST /api/v1/voyages/{voyage_id}/execute` — Run code in sandbox
  - Body: `ExecutionRequest` (command, files, timeout, etc.)
  - Returns: `ExecutionResult`
  - Requires auth + voyage ownership
  - Sets `user_id` from authenticated user (not from request body)

- `GET /api/v1/sandbox/status` — Get current user's sandbox status
  - Returns: `SandboxStatus` or 404 if no active sandbox

- `DELETE /api/v1/sandbox` — Destroy current user's sandbox
  - Returns: 204 No Content

Wire into `src/backend/app/api/v1/router.py`.

---

## Implementation order

```
Phase 1 (schemas)           — ExecutionRequest, ExecutionResult, SandboxStatus
Phase 2 (backend ABC)       — ExecutionBackend interface + ExecutionError
Phase 5 (config)            — execution settings in config.py
Phase 3 (gVisor backend)    — GVisorContainerBackend using aiodocker
Phase 4 (service)           — ExecutionService facade with sandbox pooling
Phase 5b (factory)          — create_backend() factory function
Phase 6 (API)               — REST endpoints
```

Schemas and ABC first (no dependencies), then config, then the gVisor implementation, then the service and API layers.

## Testing strategy (TDD)

This is a high-risk security component. Testing needs two layers:

### Unit tests (mocked Docker — run in CI)
1. **`tests/test_execution_schemas.py`** — Schema validation for request/result
2. **`tests/test_execution_backend.py`** — GVisorContainerBackend with mocked aiodocker client
   - Tests that create() sets correct container config (runtime, limits, network)
   - Tests that execute() handles timeout, captures output
   - Tests that destroy() handles already-removed containers
3. **`tests/test_execution_service.py`** — ExecutionService with mocked backend
   - Tests sandbox pool management (get_or_create, destroy, cleanup)
   - Tests that run() delegates to backend correctly
4. **`tests/test_execution_factory.py`** — Factory creates correct backend from config
5. **`tests/test_execution_api.py`** — API endpoints with mocked service

### Integration tests (real Docker — run locally only)
6. **`tests/test_execution_integration.py`** — Marked `@pytest.mark.integration`
   - Verifies actual container creation and code execution
   - Verifies network isolation
   - Verifies filesystem isolation
   - Verifies timeout enforcement
   - These require Docker daemon running locally

## Dependencies

- `aiodocker>=0.23.0` — async Docker SDK (add to `requirements.txt`)
- Docker daemon running locally (for integration tests and actual usage)
- gVisor `runsc` runtime installed on Docker host (for production — falls back gracefully if missing)

## Out of scope

- Git integration inside containers (Phase 9)
- Per-agent branches and PR workflow (Phase 9)
- Automatic container scaling (Phase 19 — Kubernetes)
- WebSocket streaming of execution output (Phase 16 — Observation Deck)
- Container image caching/warming strategies

## Key design decisions

1. **aiodocker over docker-py**: Async-first — matches FastAPI's async model. docker-py is sync and would require `run_in_executor()` wrappers everywhere.

2. **Per-user sandboxes, not per-execution**: Creating a container per command is too slow (~1s). Instead, each user gets a long-lived container that handles multiple executions. Destroyed on explicit request or timeout.

3. **gVisor runtime is configurable**: In development without gVisor installed, the backend falls back to default Docker runtime but logs a warning. Tests mock the Docker API so they don't need gVisor.

4. **Network disabled by default**: Agents shouldn't be able to exfiltrate data or reach internal services. Network access can be opted-in per-execution via config if needed (e.g., for `pip install`).

5. **Swappable backend**: The `ExecutionBackend` ABC means we can add `SubprocessBackend` for quick local dev, `FirecrackerBackend` for micro-VMs, or `WasmBackend` for lightweight isolation — all without touching `ExecutionService` or any crew agent code.

## Risk: security

This is the highest-risk component in the platform. Key mitigations:
- gVisor intercepts syscalls at the kernel level — even if code escapes the container namespace, gVisor's Sentry blocks dangerous syscalls
- Network disabled prevents callback/exfiltration attacks
- Memory limits prevent DoS via memory exhaustion
- Timeout prevents DoS via infinite loops
- Read-only root filesystem prevents persistent modifications
- Per-user isolation prevents cross-user contamination
- `/workspace` is a tmpfs — destroyed with the container, no disk persistence
