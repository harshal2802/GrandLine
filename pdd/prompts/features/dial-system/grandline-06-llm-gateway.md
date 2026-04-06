# Prompt: Dial System (LLM Gateway)

**File**: pdd/prompts/features/dial-system/grandline-06-llm-gateway.md
**Created**: 2026-04-05
**Updated**: 2026-04-05
**Depends on**: Phase 3 (DialConfig model + schema), Phase 5 (Den Den Mushi events)
**Project type**: Backend (FastAPI + LLM SDKs)

## Context

GrandLine is a One Piece-themed multi-agent orchestration platform. Phases 1-5 delivered Docker infrastructure, database models, JWT auth, and the Den Den Mushi message bus. The `DialConfig` model stores per-voyage provider/model mappings as JSONB. The `ProviderSwitchedEvent` is already defined in the Den Den Mushi event system.

In One Piece, Dials are shell-shaped devices from Skypiea that store and release different types of energy. Here, the Dial System is the LLM gateway that routes, buffers, and relays AI provider calls — each crew role can be configured to use a different provider/model combination, with automatic failover when limits are hit.

## Task

Implement a provider-agnostic LLM gateway with config-driven routing per crew role:

1. **Provider Adapters** (`app/dial_system/adapters/`):
   - `base.py` — `ProviderAdapter` ABC with:
     - `complete(request: CompletionRequest) -> CompletionResult`
     - `stream(request: CompletionRequest) -> AsyncIterator[str]`
     - `check_rate_limit() -> RateLimitStatus`
   - `anthropic.py` — Anthropic adapter using `anthropic` SDK
     - Catch `anthropic.RateLimitError` and return `RateLimitStatus(is_limited=True)` from `check_rate_limit()`
     - Catch `anthropic.APIError` in `complete()` and re-raise as a common `ProviderError`
   - `openai.py` — OpenAI adapter using `openai` SDK
     - Catch `openai.RateLimitError` and return `RateLimitStatus(is_limited=True)` from `check_rate_limit()`
     - Catch `openai.APIError` in `complete()` and re-raise as a common `ProviderError`
   - `ollama.py` — Ollama adapter using HTTP calls to local Ollama server
     - Check HTTP response status codes — raise `ProviderError` on non-2xx responses
     - `check_rate_limit()` always returns `is_limited=False` (local, no limits)
   - All adapters return a unified `CompletionResult` response shape
   - `ProviderError` custom exception defined in `base.py` for uniform error handling

2. **Rate Limit Tracker** (`app/dial_system/rate_limiter.py`):
   - Track token counts and request counts per provider using Redis
   - `RateLimitStatus` with `is_limited`, `remaining_tokens`, `remaining_requests`, `reset_at`
   - Sliding window counter using Redis sorted sets
   - `record_usage(provider, tokens)` — called by the router after each successful completion
   - `check(provider) -> RateLimitStatus` — called by the router before attempting a provider
   - `cleanup(provider)` — remove expired window entries

3. **Adapter Factory** (`app/dial_system/factory.py`):
   - `create_adapter(provider: str, model: str, settings: Settings) -> ProviderAdapter`
     - `"anthropic"` → `AnthropicAdapter(AsyncAnthropic(api_key=settings.anthropic_api_key), model)`
     - `"openai"` → `OpenAIAdapter(AsyncOpenAI(api_key=settings.openai_api_key), model)`
     - `"ollama"` → `OllamaAdapter(httpx.AsyncClient(), model, settings.ollama_base_url)`
     - Raise `ValueError` for unknown provider names
   - `build_router_from_config(config: DialConfig, settings: Settings, mushi: DenDenMushi, rate_limiter: RateLimiter) -> DialSystemRouter`
     - Read `config.role_mapping` JSONB → create primary adapter per role
     - Read `config.fallback_chain` JSONB → create fallback adapter lists per role
     - Return a fully wired `DialSystemRouter`
   - No global adapter instances — adapters are created per-request from config

4. **DialSystemRouter** (`app/dial_system/router.py`):
   - `route(role, request) -> CompletionResult`:
     - Check rate limiter before calling primary provider
     - On rate limit or `ProviderError`, try fallback chain in order
     - After each successful completion, call `rate_limiter.record_usage()`
     - Publish `ProviderSwitchedEvent` via Den Den Mushi when failover occurs
     - Raise `RuntimeError("All providers exhausted")` if all fail
   - `stream(role, request) -> AsyncIterator[str]`:
     - Same failover logic as `route()` — check rate limit, try primary, then fallbacks
     - On rate limit or `ProviderError` from primary, failover to next provider's `stream()`
     - Publish `ProviderSwitchedEvent` on failover
   - Constructor takes `role_mapping`, `fallback_chains`, `mushi`, `voyage_id`, `rate_limiter`

5. **Schemas** (`app/schemas/dial_system.py`):
   - `CompletionRequest` — `messages`, `role` (CrewRole), `voyage_id` (UUID), `max_tokens`, `temperature`, `extra`
   - `CompletionResult` — `content`, `provider`, `model`, `usage` (TokenUsage)
   - `TokenUsage` — `prompt_tokens`, `completion_tokens`, `total_tokens`
   - `RateLimitStatus` — `is_limited`, `remaining_tokens`, `remaining_requests`, `reset_at`
   - `ProviderConfig` — `provider` name, `model`, `max_tokens`

6. **REST API** (`app/api/v1/dial.py`):
   - `GET /api/v1/voyages/{voyage_id}/dial-config` — get current config
   - `PUT /api/v1/voyages/{voyage_id}/dial-config` — update config (takes effect on next call)
   - `POST /api/v1/voyages/{voyage_id}/completions` — run a completion through the dial system
     - Request body: `CompletionRequest` (messages, role, max_tokens, temperature)
     - Returns: `CompletionResult`
   - `POST /api/v1/voyages/{voyage_id}/completions/stream` — SSE streaming endpoint
     - Request body: same as completions
     - Returns: `StreamingResponse` with `media_type="text/event-stream"`
     - Each token sent as `data: {token}\n\n`

7. **FastAPI Integration**:
   - `get_dial_router(voyage_id, session, mushi, redis)` dependency in `dependencies.py`:
     - Fetch `DialConfig` from DB by `voyage_id`
     - Create `RateLimiter` from Redis
     - Call `build_router_from_config()` to construct the fully wired router
     - Raise 404 if no config found
   - Provider API keys via Settings: `GRANDLINE_ANTHROPIC_API_KEY`, `GRANDLINE_OPENAI_API_KEY`, `GRANDLINE_OLLAMA_BASE_URL`

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
- SSE streaming uses `text/event-stream` content type with `data: {token}\n\n` format
- All providers must return the same `CompletionResult` shape
- Failover is transparent to the caller — same interface, different backend
- Failover applies to BOTH `route()` and `stream()` — not just route
- Integration tests marked with `@pytest.mark.integration`
- No global adapter instances — adapters created per-request from config via factory
- Ollama adapter must check HTTP status codes and raise on errors
- Provider SDK errors (RateLimitError, APIError) must be caught and handled uniformly

## Edge Cases

- Unknown provider name in `role_mapping` → `ValueError` from factory
- Empty `role_mapping` for a voyage → `ValueError` when routing
- Provider returns empty content → return empty string, don't crash
- Provider SDK raises `RateLimitError` mid-request → catch, mark rate-limited, failover
- All providers in fallback chain rate-limited → `RuntimeError("All providers exhausted")`
- `fallback_chain` is `None` or missing for a role → no fallback, fail immediately after primary
- Ollama server unreachable → `ProviderError`, triggers failover
- Malformed `role_mapping` JSONB (missing "provider" or "model" keys) → `ValueError` from factory
- Config updated via PUT while a request is in-flight → safe, next request picks up new config
- SSE stream client disconnects mid-stream → generator cleanup, no crash
- `CompletionRequest` with empty messages list → let provider SDK handle validation
