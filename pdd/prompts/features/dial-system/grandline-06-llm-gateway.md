# Prompt: Dial System (LLM Gateway)

**File**: pdd/prompts/features/dial-system/grandline-06-llm-gateway.md
**Created**: 2026-04-05
**Depends on**: Phase 3 (DialConfig model + schema), Phase 5 (Den Den Mushi events)
**Project type**: Backend (FastAPI + LLM SDKs)

## Context

GrandLine is a One Piece-themed multi-agent orchestration platform. Phases 1-5 delivered Docker infrastructure, database models, JWT auth, and the Den Den Mushi message bus. The `DialConfig` model stores per-voyage provider/model mappings as JSONB. The `ProviderSwitchedEvent` is already defined in the Den Den Mushi event system.

In One Piece, Dials are shell-shaped devices from Skypiea that store and release different types of energy. Here, the Dial System is the LLM gateway that routes, buffers, and relays AI provider calls — each crew role can be configured to use a different provider/model combination, with automatic failover when limits are hit.

## Task

Implement a provider-agnostic LLM gateway with config-driven routing per crew role:

1. **Provider Adapters** (`app/dial_system/adapters/`):
   - `base.py` — `ProviderAdapter` ABC with `complete(messages, **kwargs) -> CompletionResult`, `stream(messages, **kwargs) -> AsyncIterator[str]`, `check_rate_limit() -> RateLimitStatus`
   - `anthropic.py` — Anthropic adapter using `anthropic` SDK
   - `openai.py` — OpenAI adapter using `openai` SDK
   - `ollama.py` — Ollama adapter using HTTP calls to local Ollama server
   - All adapters return a unified `CompletionResult` response shape

2. **Rate Limit Tracker** (`app/dial_system/rate_limiter.py`):
   - Track token counts and request counts per provider using Redis
   - `RateLimitStatus` with `is_limited`, `remaining_tokens`, `remaining_requests`, `reset_at`
   - Sliding window counter using Redis sorted sets

3. **DialSystemRouter** (`app/dial_system/router.py`):
   - `route(role, messages, **kwargs)` — look up provider for role from config, call adapter
   - `stream(role, messages, **kwargs)` — same but returns SSE token stream
   - Config-driven mapping: reads from `DialConfig` DB model per voyage
   - Failover chain: primary -> fallback -> park (raises if all exhausted)
   - Publishes `ProviderSwitchedEvent` via Den Den Mushi on failover

4. **Schemas** (`app/schemas/dial_system.py`):
   - `CompletionRequest` — messages, role, voyage_id, model overrides
   - `CompletionResult` — content, provider, model, usage (tokens)
   - `RateLimitStatus` — is_limited, remaining_tokens, remaining_requests, reset_at
   - `ProviderConfig` — provider name, model, api_key reference, max_tokens

5. **REST API** (`app/api/v1/dial.py`):
   - `GET /api/v1/voyages/{voyage_id}/dial-config` — get current config
   - `PUT /api/v1/voyages/{voyage_id}/dial-config` — update config (takes effect on next call)

6. **FastAPI Integration**:
   - Add `get_dial_router` dependency in `dependencies.py`
   - Provider API keys via Settings (GRANDLINE_ANTHROPIC_API_KEY, GRANDLINE_OPENAI_API_KEY, GRANDLINE_OLLAMA_BASE_URL)

## Input

- Existing `DialConfig` model at `src/backend/app/models/dial_config.py` (JSONB role_mapping + fallback_chain)
- Existing `DialConfigCreate/Update/Read` schemas at `src/backend/app/schemas/dial_config.py`
- Existing `ProviderSwitchedEvent` at `src/backend/app/den_den_mushi/events.py`
- Existing `DenDenMushi` class at `src/backend/app/den_den_mushi/mushi.py`
- Existing `CrewRole` enum: captain, navigator, doctor, shipwright, helmsman
- Existing `Settings` at `src/backend/app/core/config.py` (pydantic-settings, GRANDLINE_ prefix)

## Output format

- Python files following existing conventions (async, type-annotated, Pydantic v2)
- New `dial_system/` package under `src/backend/app/`
- Adapters under `dial_system/adapters/` subpackage
- Unit tests with mocked provider SDKs (AsyncMock) + integration tests with real Ollama (if available)
- All new files under `src/backend/app/` and `src/backend/tests/`

## Constraints

- Add `anthropic>=0.40.0` and `openai>=1.50.0` to requirements.txt
- Ollama adapter uses `httpx` (already a dependency) — no extra SDK needed
- Provider API keys stored in environment, never in DB or code
- `role_mapping` JSONB shape: `{"captain": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}, ...}`
- `fallback_chain` JSONB shape: `{"captain": ["openai", "ollama"], ...}`
- Rate limits tracked in Redis with TTL-based sliding windows
- SSE streaming uses `text/event-stream` content type
- All providers must return the same `CompletionResult` shape
- Failover is transparent to the caller — same interface, different backend
- Integration tests marked with `@pytest.mark.integration`
- No global adapter instances — adapters created per-request from config
