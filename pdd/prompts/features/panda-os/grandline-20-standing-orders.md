# Prompt: Standing Orders (reusable voyage templates / presets)

**File**: pdd/prompts/features/panda-os/grandline-20-standing-orders.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Phase 1-3 (Voyage + DialConfig models/schemas), Phase 10 (voyage-creation contract in `voyages.py` that seeds a default `DialConfig`), the current Alembic head `e5f6a1b2c3d4` (Phase 19 Log Book)
**Project type**: Backend (FastAPI + SQLAlchemy + Pydantic v2)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. A
competitive review of PandaOS surfaced its "saved workflows / agent setups" pitch
— recurring task shapes shouldn't be re-configured from scratch every time.

GrandLine's dial config is **per-voyage**: charting a course (`POST /voyages`)
always seeds a fresh default `DialConfig` mapping every crew role to the
deployment default provider/model. Recurring task shapes — "bugfix voyage",
"dep-bump voyage" — re-pick the same repo, the same provider mix, and re-type the
same framing context every time.

In One Piece, a captain leaves **Standing Orders** — durable instructions the crew
follows without being briefed afresh each time. Here, a Standing Order is a
**named, reusable bundle** of `{dial config + optional plan skeleton + injected
context + default target repo}`, owned by a user. Charting *from* a Standing Order
applies the preset's dial config (instead of the default) and its repo/context
defaults, so a recurring task shape charts in one call.

Standing Orders are **per-user presets**, not per-voyage state: they are owned by
`user_id`, name-unique per owner, and never shared across users. Charting from one
produces an ordinary `Voyage` (status `CHARTED`) — the preset is a stamp, not a
live link, so editing the order later never mutates voyages already charted from
it.

## Task

Implement Standing Orders as a standard three-layer backend feature (model →
schema → service → API), owner-scoped throughout:

1. **Model** (`app/models/standing_order.py`) — `StandingOrder`:
   - `id` UUID pk; `user_id` UUID FK -> `users.id`, indexed, NOT NULL (owner);
     `name` `String(255)` NOT NULL; `description` `Text` nullable; `target_repo`
     `String(500)` nullable (default repo for charted voyages); `dial_config`
     JSONB nullable (a `{role_mapping, fallback_chain}` bundle); `plan_skeleton`
     JSONB nullable (optional pre-seeded plan phases); `injected_context` `Text`
     nullable (prepended to the planning task); `created_at` / `updated_at`
     timezone-aware.
   - Unique constraint on `(user_id, name)` so a name is unambiguous per owner.
   - Register in `app/models/__init__.py`.

2. **Migration** (`alembic/versions/<rev>_standing_orders.py`) — create
   `standing_orders`; `down_revision='e5f6a1b2c3d4'`; index on `user_id` and a
   unique constraint on `(user_id, name)`.

3. **Schemas** (`app/schemas/standing_order.py`) — Pydantic v2:
   - `StandingOrderCreate` (`name`, `description?`, `target_repo?`, `dial_config?`,
     `plan_skeleton?`, `injected_context?`), lightly validating the `dial_config`
     bundle shape (`role_mapping` is a dict; `fallback_chain` reuses the existing
     `validate_fallback_chain`).
   - `StandingOrderUpdate` (all fields optional — partial PATCH).
   - `StandingOrderRead` (all fields + `id` + timestamps; `from_attributes=True`).
   - `ChartFromStandingOrderRequest` (`task: str` 10-5000 chars + optional
     `title` / `target_repo` overrides).

4. **Service** (`app/services/standing_order_service.py`) —
   `StandingOrderService(session)` with `StandingOrderError(code, message)`:
   - CRUD: `create`, `get` (owner-scoped — raise `StandingOrderError("NOT_FOUND")`
     if missing or not owned), `list_for_user`, `update`, `delete`.
   - `chart(order, *, task, title=None, target_repo=None) -> Voyage` — create a
     `Voyage` (status `CHARTED`) the same way `voyages.py` does, but seed its
     `DialConfig` from `order.dial_config` when present (else fall back to the same
     default `voyages.py` uses — import/reuse `_default_dial_config`). Use
     `order.target_repo` / `order.name` as repo/title defaults (overridable). If
     `order.injected_context` is set, prepend it to the voyage `description` so the
     framing travels with the voyage. Commit atomically (add voyage → flush → add
     dial config → commit → refresh).
   - `reader(session)` classmethod for call-site consistency.

5. **API** (`app/api/v1/standing_orders.py`) — kebab path
   `/api/v1/standing-orders`, default-deny via `get_current_user`, owner-scoped:
   - `GET /standing-orders` -> `list[StandingOrderRead]`.
   - `POST /standing-orders` -> `StandingOrderRead` (201).
   - `GET /standing-orders/{id}` -> `StandingOrderRead`.
   - `PATCH /standing-orders/{id}` -> `StandingOrderRead`.
   - `DELETE /standing-orders/{id}` -> 204.
   - `POST /standing-orders/{id}/chart` body `ChartFromStandingOrderRequest` ->
     `VoyageRead` (201) — charts a voyage from the preset.
   - Map `StandingOrderError("NOT_FOUND")` -> 404. Register the router in
     `app/api/v1/router.py`.

## Input

- Voyage-creation contract at `src/backend/app/api/v1/voyages.py`
  (`_default_dial_config`, the `Voyage` + default `DialConfig` seeding flow).
- `DialConfig` model at `src/backend/app/models/dial_config.py`
  (`role_mapping` / `fallback_chain` JSONB).
- `validate_fallback_chain` at `src/backend/app/schemas/dial_config.py`.
- `app/api/v1/dependencies.py` (`get_current_user`, `get_db`).
- Current Alembic head `e5f6a1b2c3d4` (Phase 19 Log Book).
- Test patterns: `tests/test_log_book_*.py`, `tests/test_captain_api.py` (mocked
  `AsyncSession` with `unittest.mock`, direct endpoint-function calls, dep
  overrides — no live Postgres).

## Output format

- Python files following existing conventions (async, fully type-annotated,
  Pydantic v2). One Piece terminology ("Standing Orders") in
  docstrings/comments/labels.
- New files only under `src/backend/app/` and `src/backend/tests/` (plus the PDD
  Poneglyph and `pdd/context/` doc updates).
- Unit tests mock `AsyncSession` with `unittest.mock`; API tests call the endpoint
  functions directly with mocked services (no Postgres).

## Constraints

- Strictly typed, async, Pydantic v2 — no `Any` abuse.
- No secrets in code.
- Owner-scoping is non-negotiable: `get`/`update`/`delete`/`chart` operate only on
  orders owned by the requesting user; a foreign or missing id raises
  `StandingOrderError("NOT_FOUND")` -> 404.
- Charting seeds the voyage's `DialConfig` from `order.dial_config` when present,
  otherwise from the SAME default `voyages.py` uses (`_default_dial_config`) — no
  divergence between the two charting paths.
- `injected_context`, when set, is PREPENDED to the voyage `description`
  (`injected_context + "\n\n---\n\n" + description`); it is never silently
  dropped.
- Migration `down_revision` MUST be `'e5f6a1b2c3d4'`; index `user_id`, unique
  `(user_id, name)`.
- Default-deny: every endpoint requires `get_current_user`.

## Edge Cases

- `chart` with `order.dial_config=None` -> voyage gets the default dial config
  (identical to a plain `POST /voyages`).
- `chart` with `order.dial_config` set -> voyage's `DialConfig` carries the
  preset's `role_mapping` / `fallback_chain`.
- `chart` with `injected_context` set but `description`/override empty -> voyage
  description is just the injected context (no dangling separator).
- `chart` with `title`/`target_repo` override -> overrides win over the order's
  `name`/`target_repo` defaults.
- `get`/`update`/`delete`/`chart` on an id owned by another user -> `NOT_FOUND`
  (404), never a 403 that would leak existence.
- Duplicate `(user_id, name)` on create -> DB unique violation surfaces (not
  swallowed); the schema doesn't pre-check.
- `dial_config` with a non-dict `role_mapping` -> `ValidationError` at the schema
  boundary.
- `task` shorter than 10 chars on `/chart` -> 422 at the schema boundary.
- `plan_skeleton` is stored as opaque JSONB in this phase (a pre-seeded plan is a
  noted follow-up; charting does not yet materialize it into a `VoyagePlan`).
