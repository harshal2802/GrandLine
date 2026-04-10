# Plan: Vivre Card — State Checkpointing (Phase 7)

**Issue**: #8
**Branch**: `feat/issue-8-vivre-card`
**Depends on**: Phase 3 (VivreCard model), Phase 5 (Den Den Mushi), Phase 6 (Dial System)

---

## Problem

Agents need to survive failures. When a provider goes down, the Dial System fails over — but without a recent checkpoint, the agent loses its in-progress work. Vivre Cards serialize agent state to PostgreSQL JSONB so the system can resume from any checkpoint. This is the "no work lost" guarantee.

## What exists already

| Artifact | Location | Status |
|---|---|---|
| `VivreCard` SQLAlchemy model | `src/backend/app/models/vivre_card.py` | Done — has id, voyage_id, crew_member, state_data (JSONB), checkpoint_reason, created_at |
| `VivreCardCreate` / `VivreCardRead` schemas | `src/backend/app/schemas/vivre_card.py` | Done — uses `CrewRole` and `CheckpointReason` enums |
| `CheckpointReason` enum | `src/backend/app/models/enums.py` | Done — interval, failover, pause, migration |
| `CrewRole` enum | `src/backend/app/models/enums.py` | Done — captain, navigator, doctor, shipwright, helmsman |
| Den Den Mushi (message bus) | `src/backend/app/den_den_mushi/` | Done — publish, read, ack, consumer groups |
| Dial System (LLM gateway) | `src/backend/app/dial_system/` | Done — failover router, provider adapters |
| `ProviderSwitchedEvent` | `src/backend/app/den_den_mushi/events.py` | Done — published on failover |

## What needs to be built

### Phase 1: VivreCardService (core business logic)

**File**: `src/backend/app/services/vivre_card_service.py`

The service layer that handles all checkpoint operations:

- **`checkpoint(session, voyage_id, crew_member, state_data, reason)`** — Creates a new Vivre Card. Serializes agent state to JSONB. Returns the created card.
- **`restore(session, card_id)`** — Loads a checkpoint by ID. Returns the deserialized state. Raises if not found.
- **`list_cards(session, voyage_id, crew_member?, limit?, offset?)`** — Lists checkpoints for a voyage, optionally filtered by crew member. Ordered by created_at desc.
- **`diff(session, card_id_a, card_id_b)`** — Computes a JSON diff between two checkpoints. Returns added/removed/changed keys with before/after values.
- **`cleanup(session, voyage_id, keep_last_n)`** — Deletes old checkpoints per crew member, keeping the N most recent. Returns count of deleted cards.

**Design decisions**:
- Service takes `AsyncSession` as parameter (dependency injection, consistent with auth_service pattern)
- No direct Redis dependency — Den Den Mushi events are published by the caller (API layer or scheduler), not the service
- State diff uses recursive dict comparison (not a library) — agent state is flat-to-moderately-nested JSONB

### Phase 2: Den Den Mushi integration (events)

**Files**: 
- `src/backend/app/den_den_mushi/events.py` — Add `CheckpointCreatedEvent`
- Update `AnyEvent` union and discriminator

New event: `CheckpointCreatedEvent` with `event_type: "checkpoint_created"`, published after every successful checkpoint. Payload contains `card_id`, `crew_member`, `reason`.

### Phase 3: REST API endpoints

**File**: `src/backend/app/api/v1/vivre_cards.py`

Endpoints:
- `GET /api/v1/voyages/{voyage_id}/vivre-cards` — List checkpoints for a voyage. Query params: `crew_member` (optional filter), `limit` (default 20), `offset` (default 0). Requires auth + voyage ownership.
- `POST /api/v1/voyages/{voyage_id}/vivre-cards` — Create a checkpoint manually. Body: `VivreCardCreate` (crew_member, state_data, checkpoint_reason). Publishes `CheckpointCreatedEvent` via Den Den Mushi. Requires auth + voyage ownership.
- `GET /api/v1/voyages/{voyage_id}/vivre-cards/{card_id}` — Get a single checkpoint by ID.
- `GET /api/v1/voyages/{voyage_id}/vivre-cards/{card_id}/diff?compare_to={other_id}` — Diff two checkpoints.
- `POST /api/v1/voyages/{voyage_id}/vivre-cards/{card_id}/restore` — Restore from a checkpoint. Returns the state data and marks intent (actual agent resume is out of scope — that's the agent execution layer).
- `DELETE /api/v1/voyages/{voyage_id}/vivre-cards/cleanup` — Run cleanup policy. Query param: `keep_last_n` (default 5).

**Dependencies**: Reuse `get_authorized_voyage` from existing dependencies. Add `get_vivre_card_service` dependency.

**Wire into router**: Add `vivre_cards_router` to `src/backend/app/api/v1/router.py`.

### Phase 4: Schemas (request/response)

**File**: `src/backend/app/schemas/vivre_card.py` — Extend existing schemas:

- `VivreCardList` — Paginated response with items + total count
- `VivreCardDiff` — Diff result with added/removed/changed fields
- `VivreCardRestore` — Restore response with card_id + state_data
- `CleanupResult` — Count of deleted checkpoints

### Phase 5: Config for automatic checkpointing

**File**: `src/backend/app/core/config.py` — Add:
- `vivre_card_checkpoint_interval_seconds: int = 300` (5 min default)
- `vivre_card_cleanup_keep_last_n: int = 10`

These settings are used by the future agent execution loop (Phase 9+) to trigger interval-based checkpoints. The API also exposes manual checkpointing for immediate use.

### Phase 6: Dial System integration hook

The Dial System's `DialSystemRouter` already publishes `ProviderSwitchedEvent` on failover. The integration point is:

- Add a `pre_failover_hook` callback to `DialSystemRouter` that callers can set
- When the Dial System is about to switch providers, it calls the hook (if set) before the switch
- In the agent execution layer (future phase), this hook will call `VivreCardService.checkpoint()` with reason `failover`

For now in Phase 7, we add the hook mechanism to the router. The actual wiring happens when agents are built (Phase 11+).

**File**: `src/backend/app/dial_system/router.py` — Add optional `on_provider_switch` callback parameter.

---

## Implementation order

```
Phase 4 (schemas)          — extend VivreCard schemas
Phase 2 (events)           — add CheckpointCreatedEvent
Phase 1 (service)          — VivreCardService core logic
Phase 3 (API)              — REST endpoints
Phase 5 (config)           — checkpoint interval + cleanup settings
Phase 6 (Dial hook)        — pre-failover callback on DialSystemRouter
```

Schemas and events first (no dependencies), then service (depends on schemas), then API (depends on service + events), then config and Dial hook (independent).

## Testing strategy (TDD)

Tests written BEFORE implementation, following Doctor-first convention:

1. **`tests/test_vivre_card_service.py`** — Unit tests for checkpoint, restore, list, diff, cleanup
2. **`tests/test_vivre_card_api.py`** — Integration tests for all REST endpoints (auth, ownership, 404s, validation)
3. **`tests/test_vivre_card_events.py`** — Event serialization/deserialization for CheckpointCreatedEvent
4. **`tests/test_dial_router_hook.py`** — Test that the pre-failover hook fires before provider switch

## Out of scope

- Automatic interval-based checkpoint scheduling (needs agent execution loop — Phase 9+)
- Actual agent state restoration and resume (needs agent definitions — Phase 11+)
- WebSocket notifications for checkpoint events (needs Observation Deck — Phase 16)

## Risk: serialization of arbitrary state

Agent state shapes vary per crew member. The `state_data` JSONB field is flexible, but:
- All state must be JSON-serializable (no datetime objects, no custom classes without serialization)
- The service should validate that `state_data` round-trips correctly (serialize → deserialize → equal)
- Diff logic must handle nested dicts and lists gracefully
