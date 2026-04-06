# Eval: Dial System (LLM Gateway)

**Prompt**: `pdd/prompts/features/dial-system/grandline-06-llm-gateway.md`
**Level**: 1 (Checklist)
**Created**: 2026-04-05

## Criteria

### C1: Provider Adapter ABC
- [x] `ProviderAdapter` ABC exists with `complete()`, `stream()`, `check_rate_limit()`
- [x] `ProviderError` exception defined in `base.py`

### C2: Anthropic Adapter
- [x] Catches `RateLimitError` → sets `_rate_limited`, re-raises as `ProviderError`
- [x] Catches `APIError` → re-raises as `ProviderError`
- [x] `complete()` returns `CompletionResult` with `TokenUsage`
- [x] `stream()` yields text tokens from streaming events
- [x] `check_rate_limit()` returns `RateLimitStatus`

### C3: OpenAI Adapter
- [x] Same error handling pattern as Anthropic (RateLimitError, APIError)
- [x] `complete()` returns `CompletionResult` with `TokenUsage`
- [x] `stream()` yields text tokens from streaming chunks
- [x] `check_rate_limit()` returns `RateLimitStatus`

### C4: Ollama Adapter
- [x] Uses `httpx` for HTTP calls (no extra SDK)
- [x] Raises `ProviderError` on non-200 HTTP status
- [x] Catches `httpx.HTTPError` for connection errors
- [x] `check_rate_limit()` always returns `is_limited=False`
- [x] `stream()` parses NDJSON lines

### C5: Rate Limiter
- [x] Redis sliding window using sorted sets
- [x] `record_usage(provider, tokens)` stores entries
- [x] `check(provider)` returns `RateLimitStatus` with token/request counts
- [x] `cleanup(provider)` removes expired entries

### C6: Adapter Factory
- [x] `create_adapter()` creates correct adapter for each provider string
- [x] Raises `ValueError` for unknown provider
- [x] `build_router_from_config()` reads JSONB config and wires router
- [x] Handles missing `provider`/`model` keys with `ValueError`
- [x] Handles `None` fallback chain gracefully

### C7: Router — route()
- [x] Checks rate limit before calling primary
- [x] On `ProviderError`, tries fallback chain
- [x] Calls `record_usage()` after success (when rate_limiter provided)
- [x] Publishes `ProviderSwitchedEvent` on failover
- [x] Raises `RuntimeError("All providers exhausted")` when all fail
- [x] No event published when primary succeeds

### C8: Router — stream()
- [x] Same failover logic as `route()` (rate limit check → primary → fallbacks)
- [x] Publishes `ProviderSwitchedEvent` on failover
- [x] Yields tokens from successful provider

### C9: Schemas
- [x] `CompletionRequest` has `messages`, `role`, `voyage_id`, `max_tokens`, `temperature`, `extra`
- [x] `CompletionResult` has `content`, `provider`, `model`, `usage`
- [x] `TokenUsage` has `prompt_tokens`, `completion_tokens`, `total_tokens`
- [x] `RateLimitStatus` has `is_limited`, `remaining_tokens`, `remaining_requests`, `reset_at`
- [x] `ProviderConfig` has `provider`, `model`, `max_tokens`

### C10: REST API
- [x] `GET /{voyage_id}/dial-config` returns config
- [x] `PUT /{voyage_id}/dial-config` updates config
- [x] `POST /{voyage_id}/completions` runs completion
- [x] `POST /{voyage_id}/completions/stream` returns SSE with `text/event-stream`
- [x] SSE format: `data: {token}\n\n`

### C11: FastAPI Integration
- [x] `get_dial_router` dependency fetches config, creates rate limiter, builds router
- [x] 404 when no config found
- [x] Settings has `anthropic_api_key`, `openai_api_key`, `ollama_base_url`
- [x] Dial router registered in `v1_router`

### C12: Constraints
- [x] `anthropic>=0.40.0` and `openai>=1.50.0` in requirements.txt
- [x] API keys in env, never in DB
- [x] Failover in both `route()` and `stream()`
- [x] No global adapter instances

### C13: Quality Gates
- [x] All tests pass (pytest) — 37/37 dial system tests, 163/163 total
- [x] Type-safe (mypy clean) — 0 errors in 46 files
- [x] Lint-clean (ruff) — all checks passed

## Run Log

| Run | Date | Pass | Fail | Notes |
|-----|------|------|------|-------|
| 1   | 2026-04-05 | 48/48 | 0 | All criteria pass. 37 dial tests, mypy clean, ruff clean. |
