# Prompt: Vivre Card (State Checkpointing)

**File**: pdd/prompts/features/vivre-card/grandline-07-state-checkpointing.md
**Created**: 2026-04-06
**Updated**: 2026-04-06
**Depends on**: Phase 3 (VivreCard model + schema), Phase 5 (Den Den Mushi events), Phase 6 (Dial System router)
**Project type**: Backend (FastAPI + PostgreSQL JSONB)

## Context

GrandLine is a One Piece-themed multi-agent orchestration platform. Phases 1-6 delivered Docker infrastructure, database models, JWT auth, the Den Den Mushi message bus, and the Dial System LLM gateway with failover.

In One Piece, a Vivre Card is a paper made from a person's fingernail that tracks their life force — if they're alive, the card points toward them; if they're dying, it burns away. Here, Vivre Cards are state checkpoints that track an agent's progress. If the agent crashes, migrates to a different provider, or pauses, the system restores from the last Vivre Card — no work is lost.

The `VivreCard` SQLAlchemy model and basic Pydantic schemas already exist. This phase builds the service layer, REST API, event integration, state diffing, and cleanup policy on top of that foundation.

## Task

Implement the Vivre Card state checkpointing system with TDD (tests first, then implementation):

1. **Extended Schemas** (`app/schemas/vivre_card.py`):
   - Keep existing `VivreCardCreate` and `VivreCardRead`
   - Add `VivreCardList` — paginated response:
     - `items: list[VivreCardRead]`
     - `total: int`
     - `limit: int`
     - `offset: int`
   - Add `VivreCardDiff` — diff result between two checkpoints:
     - `card_a_id: uuid.UUID`
     - `card_b_id: uuid.UUID`
     - `added: dict[str, Any]` — keys present in B but not A
     - `removed: dict[str, Any]` — keys present in A but not B
     - `changed: dict[str, dict[str, Any]]` — keys in both but with different values, each entry has `{"before": ..., "after": ...}`
   - Add `VivreCardRestore` — restore response:
     - `card_id: uuid.UUID`
     - `voyage_id: uuid.UUID`
     - `crew_member: str`
     - `state_data: dict[str, Any]`
     - `checkpoint_reason: str`
     - `restored_at: datetime`
   - Add `CleanupResult`:
     - `deleted_count: int`
     - `kept_count: int`
     - `voyage_id: uuid.UUID`

2. **CheckpointCreatedEvent** (`app/den_den_mushi/events.py`):
   - Add `CheckpointCreatedEvent(DenDenMushiEvent)`:
     - `event_type: Literal["checkpoint_created"] = "checkpoint_created"`
     - Payload should contain: `card_id` (str, UUID as string), `crew_member` (str), `reason` (str)
   - Add `CheckpointCreatedEvent` to the `AnyEvent` union type
   - Update the `_event_adapter` TypeAdapter to include it

3. **VivreCardService** (`app/services/vivre_card_service.py`):
   - Module-level async functions (matching `auth_service.py` pattern — no class needed):
   
   - `checkpoint(session, voyage_id, crew_member, state_data, reason) -> VivreCard`:
     - Create a new VivreCard record
     - Commit and refresh
     - Return the created model instance
   
   - `restore(session, card_id) -> VivreCard`:
     - Fetch a VivreCard by ID
     - Raise `VivreCardError("CARD_NOT_FOUND", "Vivre Card not found", 404)` if not found
     - Return the model instance (caller decides what to do with state_data)
   
   - `list_cards(session, voyage_id, crew_member=None, limit=20, offset=0) -> tuple[list[VivreCard], int]`:
     - Query vivre_cards filtered by voyage_id
     - Optionally filter by crew_member if provided
     - Order by created_at DESC (most recent first)
     - Return (items, total_count) for pagination
   
   - `diff(session, card_id_a, card_id_b) -> dict`:
     - Fetch both cards (raise VivreCardError if either not found)
     - Compute a shallow diff of `state_data` JSONB:
       - `added`: keys in B's state_data not in A's
       - `removed`: keys in A's state_data not in B's
       - `changed`: keys in both where values differ — `{"before": a_val, "after": b_val}`
     - Return the diff dict
   
   - `cleanup(session, voyage_id, keep_last_n=10) -> tuple[int, int]`:
     - For EACH crew_member that has cards in this voyage:
       - Find all cards ordered by created_at DESC
       - Keep the most recent `keep_last_n`
       - Delete the rest
     - Return (deleted_count, kept_count)
   
   - `VivreCardError` exception class (same pattern as `AuthError`):
     - `code: str`, `message: str`, `status_code: int`

4. **REST API** (`app/api/v1/vivre_cards.py`):
   - Router prefix: `/voyages/{voyage_id}/vivre-cards`, tags: `["vivre-cards"]`
   - All endpoints require auth (`get_current_user`) and voyage ownership (`get_authorized_voyage`)
   
   - `GET /voyages/{voyage_id}/vivre-cards` → `VivreCardList`:
     - Query params: `crew_member: CrewRole | None = None`, `limit: int = 20`, `offset: int = 0`
     - Calls `list_cards()`
   
   - `POST /voyages/{voyage_id}/vivre-cards` → `VivreCardRead` (status 201):
     - Body: `VivreCardCreate` (crew_member, state_data, checkpoint_reason)
     - Calls `checkpoint()`
     - Publishes `CheckpointCreatedEvent` via Den Den Mushi after successful creation
     - Stream key: use `stream_key(voyage_id)` from den_den_mushi constants
   
   - `GET /voyages/{voyage_id}/vivre-cards/{card_id}` → `VivreCardRead`:
     - Calls `restore()` (same DB lookup, just returns the card)
     - 404 if not found
   
   - `GET /voyages/{voyage_id}/vivre-cards/{card_id}/diff` → `VivreCardDiff`:
     - Query param: `compare_to: uuid.UUID` (required)
     - Calls `diff(card_id, compare_to)`
     - 404 if either card not found
   
   - `POST /voyages/{voyage_id}/vivre-cards/{card_id}/restore` → `VivreCardRestore`:
     - Calls `restore()`
     - Returns state_data with a `restored_at` timestamp
     - 404 if not found
   
   - `DELETE /voyages/{voyage_id}/vivre-cards/cleanup` → `CleanupResult`:
     - Query param: `keep_last_n: int = 10`
     - Calls `cleanup()`
   
   - All `VivreCardError` exceptions caught and converted to HTTPException with standard error shape: `{"error": {"code": "...", "message": "..."}}`
   
   - Wire into `app/api/v1/router.py`: add `vivre_cards_router` to `v1_router`

5. **Config Settings** (`app/core/config.py`):
   - Add `vivre_card_checkpoint_interval_seconds: int = 300` (5 minutes default)
   - Add `vivre_card_cleanup_keep_last_n: int = 10`
   - These are read by future agent execution phases; exposed in config now for consistency

6. **Dial System Pre-Failover Hook** (`app/dial_system/router.py`):
   - Add optional `on_provider_switch` callback to `DialSystemRouter.__init__()`:
     - Type: `Callable[[CrewRole, str], Awaitable[None]] | None = None`
   - In `route()`: when failover occurs (before publishing `ProviderSwitchedEvent`), call `await self._on_provider_switch(role, new_provider)` if the callback is set
   - In `stream()`: same — call the hook before failover streaming begins
   - This is the integration point where the agent execution layer (future phase) will wire `VivreCardService.checkpoint()` with reason `"failover"`

## Input

- Existing `VivreCard` model at `src/backend/app/models/vivre_card.py` — id (UUID), voyage_id (FK), crew_member (str), state_data (JSONB), checkpoint_reason (str), created_at (datetime)
- Existing `VivreCardCreate` / `VivreCardRead` at `src/backend/app/schemas/vivre_card.py`
- Existing `CheckpointReason` enum: interval, failover, pause, migration
- Existing `CrewRole` enum: captain, navigator, doctor, shipwright, helmsman
- Existing `DenDenMushi` at `src/backend/app/den_den_mushi/mushi.py` — `publish(stream, event)`
- Existing `stream_key()` at `src/backend/app/den_den_mushi/constants.py`
- Existing `DialSystemRouter` at `src/backend/app/dial_system/router.py`
- Existing `get_authorized_voyage` dependency at `src/backend/app/api/v1/dependencies.py`
- Existing `AuthError` pattern at `src/backend/app/services/auth_service.py`

## Output format

- Python files following existing conventions (async, type-annotated, Pydantic v2)
- Service functions at module level (no class — matching auth_service.py pattern)
- Unit tests with in-memory SQLite or mocked sessions
- Tests written BEFORE implementation (TDD)
- All new files under `src/backend/app/` and `src/backend/tests/`

## Constraints

- Service takes `AsyncSession` as first parameter (dependency injection)
- Service does NOT publish events — the API layer publishes after successful service calls
- State diff is shallow (top-level keys only) — deep nested diff is over-engineering for v1
- Cleanup operates per-crew-member within a voyage (each crew member keeps their own N most recent)
- All endpoints nested under `/voyages/{voyage_id}/` to enforce voyage ownership
- `VivreCardError` follows the same pattern as `AuthError` (code, message, status_code)
- No raw SQL — use SQLAlchemy ORM queries
- Consistent error shape: `{"error": {"code": "...", "message": "..."}}`
- The `on_provider_switch` hook on DialSystemRouter is optional and backward-compatible (existing tests must still pass)

## Edge Cases

- `restore()` with non-existent card_id → `VivreCardError("CARD_NOT_FOUND", ..., 404)`
- `diff()` where one or both cards don't exist → `VivreCardError("CARD_NOT_FOUND", ..., 404)`
- `diff()` where both cards have identical state_data → all three diff dicts are empty
- `cleanup()` on a voyage with no cards → returns (0, 0)
- `cleanup()` with `keep_last_n` >= total cards for a crew member → nothing deleted for that member
- `list_cards()` with offset beyond total → returns empty list, total still reflects actual count
- `state_data` with nested dicts — diff only compares top-level keys, nested changes show full before/after value
- `checkpoint_reason` must be a valid `CheckpointReason` enum value (validated by Pydantic schema)
- `crew_member` must be a valid `CrewRole` enum value (validated by Pydantic schema)
- Empty `state_data` (`{}`) is valid — an agent with no state is still checkpointable
- `on_provider_switch` hook that raises — should not prevent failover from completing (catch and log)
- Multiple concurrent checkpoints for same crew_member — each gets its own card, no conflict

## Test Plan

### tests/test_vivre_card_service.py
- `test_checkpoint_creates_card` — happy path, verify all fields persisted
- `test_checkpoint_stores_jsonb_state` — complex nested state round-trips correctly
- `test_restore_returns_card` — fetch by ID, verify state_data matches
- `test_restore_not_found_raises` — non-existent ID raises VivreCardError
- `test_list_cards_by_voyage` — returns cards for correct voyage only
- `test_list_cards_filter_by_crew_member` — filtering works
- `test_list_cards_pagination` — limit/offset respected, total accurate
- `test_list_cards_ordered_by_created_at_desc` — most recent first
- `test_diff_added_keys` — key in B not in A shows as added
- `test_diff_removed_keys` — key in A not in B shows as removed
- `test_diff_changed_keys` — same key, different value shows before/after
- `test_diff_identical_states` — empty diff result
- `test_diff_card_not_found` — raises VivreCardError
- `test_cleanup_deletes_old_cards` — keeps N most recent per crew member
- `test_cleanup_no_cards` — returns (0, 0)
- `test_cleanup_per_crew_member` — each crew member's cards cleaned independently

### tests/test_vivre_card_api.py
- `test_create_checkpoint_201` — POST returns created card
- `test_create_checkpoint_publishes_event` — CheckpointCreatedEvent published via Den Den Mushi
- `test_list_checkpoints` — GET returns paginated list
- `test_list_checkpoints_filter_crew` — crew_member query param works
- `test_get_checkpoint_by_id` — GET single card
- `test_get_checkpoint_not_found_404` — non-existent card
- `test_diff_checkpoints` — GET diff endpoint
- `test_restore_checkpoint` — POST restore returns state_data + restored_at
- `test_cleanup_checkpoints` — DELETE cleanup returns counts
- `test_unauthorized_401` — no token → 401
- `test_wrong_voyage_404` — other user's voyage → 404

### tests/test_vivre_card_events.py
- `test_checkpoint_created_event_serializes` — model_dump_json round-trips
- `test_checkpoint_created_event_parses` — parse_event recognizes it
- `test_checkpoint_created_event_in_any_event` — discriminator works

### tests/test_dial_router_hook.py
- `test_on_provider_switch_called_on_failover` — hook fires when primary fails
- `test_on_provider_switch_called_on_stream_failover` — hook fires during stream failover
- `test_on_provider_switch_not_called_when_primary_succeeds` — no hook call on success
- `test_on_provider_switch_none_is_safe` — no callback set, no crash
- `test_on_provider_switch_error_does_not_block_failover` — hook exception is caught and logged
