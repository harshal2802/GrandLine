# Prompt: Den Den Mushi (Message Bus)

**File**: pdd/prompts/features/den-den-mushi/grandline-05-message-bus.md
**Created**: 2026-04-05
**Depends on**: Phase 1 (Redis), Phase 3 (Database Models & Pydantic Schemas)
**Project type**: Backend (FastAPI + Redis Streams)

## Context

GrandLine is a One Piece-themed multi-agent orchestration platform. Phases 1-4 delivered Docker infrastructure, database models (Voyage, CrewAction, etc.), Pydantic schemas, and JWT auth. Redis is running and used for refresh token storage. The `CrewRole` enum exists with: captain, navigator, doctor, shipwright, helmsman.

The Den Den Mushi is the inter-agent communication backbone. In One Piece, Den Den Mushi are snail-based communication devices — here they represent the typed event bus that lets crew agents publish and receive events during a voyage.

## Task

Implement a Redis Streams-based message bus system with:

1. **Event Schemas** (`app/den_den_mushi/events.py`):
   - `DenDenMushiEvent` base model with `event_id`, `event_type` (Literal discriminator), `voyage_id`, `timestamp`, `source_role`, `payload`
   - 7 concrete event types: `VoyagePlanCreatedEvent`, `PoneglyphDraftedEvent`, `HealthCheckWrittenEvent`, `CodeGeneratedEvent`, `ValidationPassedEvent`, `DeploymentCompletedEvent`, `ProviderSwitchedEvent`
   - `parse_event()` using Pydantic v2 discriminated union via TypeAdapter

2. **DenDenMushi Class** (`app/den_den_mushi/mushi.py`):
   - `publish(stream, event)` — serialize event as JSON, xadd to stream
   - `read(stream, group, consumer, count, block_ms)` — xreadgroup, deserialize events
   - `ack(stream, group, *msg_ids)` — xack processed messages
   - `ensure_group(stream, group)` — XGROUP CREATE with MKSTREAM, idempotent
   - `replay(stream, start_id, count)` — xrange for catch-up reads
   - `claim_stale(stream, group, consumer, min_idle_ms, count)` — xautoclaim idle messages
   - `send_to_dead_letter(original_stream, msg_id, event_data, error, retry_count)` — xadd to dead letter stream
   - `trim(stream, maxlen, approximate)` — xtrim

3. **Handler Registry** (`app/den_den_mushi/handlers.py`):
   - `HandlerRegistry` class with `on(event_type, handler)` and `handlers_for(event_type)`
   - `consume_loop(mushi, stream, role, consumer_id, registry)` — async loop that reads, dispatches, acks, retries, dead-letters

4. **Constants** (`app/den_den_mushi/constants.py`):
   - Stream key helpers: `stream_key(voyage_id)` → `grandline:events:{voyage_id}`
   - `group_name(role)` → `crew:{role}`
   - `BROADCAST_STREAM`, `DEAD_LETTER_STREAM`, `MAX_RETRIES`, `BLOCK_MS`

5. **FastAPI Integration**:
   - Lifespan handler in `main.py` with Redis ConnectionPool + DenDenMushi singleton on `app.state`
   - `get_den_den_mushi` dependency in `dependencies.py`

## Input

- Existing `CrewRole` enum at `src/backend/app/models/enums.py`
- Existing config at `src/backend/app/core/config.py` (has `redis_url`)
- Existing `main.py` app factory at `src/backend/app/main.py`
- Existing dependencies at `src/backend/app/api/v1/dependencies.py`

## Output format

- Python files following existing conventions (async, type-annotated, Pydantic v2)
- New `den_den_mushi/` package under `src/backend/app/`
- Unit tests with mocked Redis (AsyncMock) + integration tests with real Redis
- All new files under `src/backend/app/` and `src/backend/tests/`

## Constraints

- Use existing `redis==5.1.1` package (supports Redis Streams natively)
- No new dependencies
- Events serialized as single JSON `data` field per stream entry
- Per-voyage streams + broadcast stream for system events
- Dead letter after MAX_RETRIES (3) failed deliveries
- Consumer groups lazy-created with MKSTREAM + BUSYGROUP catch
- Error isolation: one bad handler cannot crash the consumer loop
- Integration tests marked with `@pytest.mark.integration`
