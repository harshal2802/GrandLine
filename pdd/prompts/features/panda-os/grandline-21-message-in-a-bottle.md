# Prompt: Message in a Bottle (external triggers)

**File**: pdd/prompts/features/panda-os/grandline-21-message-in-a-bottle.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Phase 1-3 (Voyage + DialConfig models/schemas), Phase 10 (voyage-creation contract in `voyages.py` that seeds a default `DialConfig`), the current Alembic head `f6a1b2c3d4e5` (Phase 20 Standing Orders)
**Project type**: Backend (FastAPI + SQLAlchemy + Pydantic v2)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. A
competitive review of PandaOS surfaced its flagship demo: work starts from an
external signal — an email or a GitHub issue — not from a human typing a task into
a box. GrandLine voyages today only start from a user-typed task (`POST /voyages`).

In One Piece, a **Message in a Bottle** drifts in from the sea carrying word of
someone who needs help. Here, a Message in a Bottle is an **inbound, signed
webhook** that charts a course from a GitHub issue. The webhook is **HMAC-verified**
(not Bearer-authed) — it is the single deliberate relaxation of the default-deny
posture, allowlisted by exact path and gated by signature instead.

A triggered voyage records **origin metadata** — how it was triggered (channel,
repo, issue number, issue url, sender) — on the voyage itself, as a new `origin`
JSONB column. This is the canonical record of provenance and is the **key seam**
Phase 22 ("Return Bottle") consumes to reply back to the originating issue. A
manually-charted voyage leaves `origin` NULL.

The trigger has **no webhook identity** — GitHub doesn't carry a GrandLine user.
The owning user is resolved from configuration (`trigger_default_user_email`), so
operators decide which account owns triggered voyages.

## Task

Implement Message in a Bottle as a model column + settings + schema + service +
API, signature-verified and default-deny-respecting throughout:

1. **Voyage origin column** (`app/models/voyage.py`) — add
   `origin: Mapped[dict | None]` JSONB nullable to `Voyage` (records how the voyage
   was triggered; NULL for manually-charted voyages). No other voyage changes.

2. **Migration** (`alembic/versions/<rev>_voyage_origin_and_triggers.py`) — add the
   `origin` JSONB nullable column to `voyages`; `down_revision='f6a1b2c3d4e5'`.

3. **Settings** (`app/core/config.py`) — `github_webhook_secret: str | None`
   (env `GRANDLINE_GITHUB_WEBHOOK_SECRET`), `trigger_default_user_email: str | None`
   (env `GRANDLINE_TRIGGER_DEFAULT_USER_EMAIL`), `trigger_label: str = "grandline"`
   (env `GRANDLINE_TRIGGER_LABEL`). No secrets committed — env only.

4. **Schemas** (`app/schemas/trigger.py`) — a minimal Pydantic v2 subset of the
   GitHub `issues` webhook payload, nested models with `extra="ignore"` so unknown
   fields don't break parsing: `action`; `issue` (`number`, `title`, `body?`,
   `html_url`, `labels: list[{name}]`); `repository` (`full_name`, `clone_url`);
   `sender` (`login`). Plus `TriggerResult` (`status: "charted"|"ignored"`,
   `voyage_id?`, `reason?`).

5. **Service** (`app/services/trigger_service.py`) — `TriggerService(session)` with
   `TriggerError(code, message)`:
   - `verify_github_signature(raw_body, signature_header, secret) -> bool` — a
     module-level/static function (unit-testable in isolation). HMAC-SHA256 over the
     raw body, compared **constant-time** (`hmac.compare_digest`) against the
     `sha256=` hex digest in `X-Hub-Signature-256`. `secret is None` -> `False` (we
     never accept unverified payloads). Malformed/missing header -> `False`.
   - `resolve_trigger_user() -> User` — look up `settings.trigger_default_user_email`;
     raise `TriggerError("TRIGGER_USER_UNCONFIGURED")` if unset,
     `TriggerError("TRIGGER_USER_NOT_FOUND")` if no such user.
   - `should_trigger(payload) -> bool` — `action in {"opened","labeled"}` AND the
     configured `trigger_label` is present on the issue's labels. Otherwise ignore.
   - `ingest_github_issue(payload, user) -> Voyage` — create a `CHARTED` voyage
     (`title` = issue title truncated to 255, `description` = issue body,
     `target_repo` = `repository.clone_url or full_name`), seed
     `_default_dial_config` (reused from `voyages.py` — identical to a manual chart),
     and set `origin = {"type": "github_issue", "repo": full_name, "issue_number": n,
     "issue_url": html_url, "issue_title": title, "sender": login,
     "received_at": <iso8601 UTC>}`. Commit atomically (add voyage -> flush -> add
     dial config -> commit -> refresh).
   - `reader(session)` classmethod for call-site consistency.

6. **API** (`app/api/v1/triggers.py`) — `POST /api/v1/triggers/github`:
   - Read the RAW body (`await request.body()`) BEFORE parsing JSON.
   - Verify the signature against `settings.github_webhook_secret`; on failure (or an
     unconfigured secret) return **401** `{"error":{"code":"INVALID_SIGNATURE",...}}`.
   - Parse the body; if `should_trigger` is `False` -> 200 `TriggerResult(status=
     "ignored", reason=...)`.
   - Resolve the trigger user; map `TriggerError` codes to 422
     (`TRIGGER_USER_UNCONFIGURED`) / 503 (`TRIGGER_USER_NOT_FOUND`) with the standard
     `{"error":{...}}` shape. On success -> 201 `TriggerResult(status="charted",
     voyage_id=...)`.
   - Register the router in `app/api/v1/router.py`. **Add
     `/api/v1/triggers/github` to `PUBLIC_PATHS`** in `app/core/middleware.py` with a
     comment noting it is HMAC-verified, not Bearer-authed.

## Input

- Voyage-creation contract at `src/backend/app/api/v1/voyages.py`
  (`_default_dial_config`, the `Voyage` + default `DialConfig` seeding flow).
- `Voyage` model at `src/backend/app/models/voyage.py` (add `origin`).
- `User` model at `src/backend/app/models/user.py` (resolve owning user by email).
- `DefaultDenyMiddleware` + `PUBLIC_PATHS` at `src/backend/app/core/middleware.py`.
- `Settings` at `src/backend/app/core/config.py` (`GRANDLINE_` env prefix).
- Current Alembic head `f6a1b2c3d4e5` (Phase 20 Standing Orders).
- Test patterns: `tests/test_standing_order_*.py`, `tests/test_voyages_api.py`,
  `tests/test_models.py` (mocked `AsyncSession`, direct endpoint-function calls,
  dep/settings overrides — no live Postgres).

## Output format

- Python files following existing conventions (async, fully type-annotated,
  Pydantic v2). One Piece terminology ("Message in a Bottle") in
  docstrings/comments/labels.
- New files only under `src/backend/app/` and `src/backend/tests/` (plus the PDD
  Poneglyph and `pdd/context/` doc updates).
- Unit tests mock `AsyncSession` with `unittest.mock`; API tests call the endpoint
  functions directly with mocked services and patched settings (no Postgres).

## Constraints

- Strictly typed, async, Pydantic v2 — no `Any` abuse.
- **No secrets in code** — the webhook secret and trigger user come from env only.
- **Default-deny holds.** The ONLY relaxation is the single allowlisted path
  `/api/v1/triggers/github`, protected by HMAC. Unconfigured secret == reject (401).
- Signature comparison is **constant-time** (`hmac.compare_digest`); we never accept
  an unverified payload.
- The raw request body is read BEFORE JSON parsing — the signature is over the exact
  bytes GitHub signed, not a re-serialized model.
- A triggered voyage's `DialConfig` reuses `voyages._default_dial_config` — a
  triggered voyage is configured identically to a manual one (one source of truth).
- `origin` is the canonical trigger record (Phase 22 reads it); a manually-charted
  voyage leaves it NULL.
- Migration `down_revision` MUST be `'f6a1b2c3d4e5'` (unique 12-hex revision id).

## Edge Cases

- Valid signature, `issues.opened` with the trigger label -> 201 `charted`, voyage
  has the exact `origin` dict + a default dial config.
- Tampered body / wrong signature / missing or malformed `X-Hub-Signature-256` ->
  401 `INVALID_SIGNATURE`, no voyage created.
- `github_webhook_secret` unset -> 401 (never accept unverified), even for a
  well-formed payload.
- `action` not in `{opened, labeled}` (e.g. `closed`, `edited`) -> 200 `ignored`.
- Trigger label absent from the issue -> 200 `ignored`.
- `trigger_default_user_email` unset -> 422 `TRIGGER_USER_UNCONFIGURED`.
- No user with that email -> 503 `TRIGGER_USER_NOT_FOUND`.
- Unknown/extra payload fields (the real GitHub payload is huge) -> ignored by
  `extra="ignore"`; parsing never breaks on them.
- `issue.title` longer than 255 chars -> truncated to fit `Voyage.title`.
- `issue.body` is `null` -> voyage `description` is `None`.
- `repository.clone_url` present -> used as `target_repo`; else fall back to
  `full_name`.
