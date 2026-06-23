# Prompt: The Sea Chest — encrypted per-user credential vault (Phase 0a)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-0a-sea-chest.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Auth (Phase 4 — `get_current_user`, default-deny middleware), the
`User` model, `Settings` (`GRANDLINE_` env prefix), and the
`validate_production_settings` posture in `app/main.py` (refuse insecure defaults
outside debug). `cryptography.fernet.Fernet` is available.
**Project type**: Backend (FastAPI + Pydantic v2 + SQLAlchemy async)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. Today
all provider credentials are deployment-level env vars (`anthropic_api_key`,
`github_api_token`, the Claude Code CLI's own login). The next foundation is
**per-user** credentials: each user connects their own Claude Code and GitHub
credentials, and later phases run the crew with *their* secrets.

The **Sea Chest** is that vault. In One Piece a sea chest is where a pirate locks
away their most precious possessions. Here it is a per-user, encrypted-at-rest
credential store. This phase is **storage + crypto + API only** — there is no
Cabin (per-user container) yet. Later phases consume *decrypted* secrets INTERNALLY
(the Cabin/adapters: A3 per-user GitHub, C0 device-login Claude Code) — never the
browser.

PLAN reference: PLAN-deck-capabilities.md, Phase 0 = Cabin + Sea Chest. This is the
**Sea Chest** half; the Cabin is a sibling, out of scope here.

## Security requirements (NON-NEGOTIABLE)

- **Ciphertext only at rest.** The `user_credentials` table stores ONLY the encrypted
  secret (`ciphertext` BYTEA) plus non-secret metadata (`kind`, `label`, timestamps).
  There is NEVER a plaintext secret column.
- **Key from env, never in code/DB.** The encryption key derives from
  `Settings.seachest_key` (env `GRANDLINE_SEACHEST_KEY`). In `debug` mode, if it is
  unset, derive a STABLE dev key (so local dev works) and log a WARNING. In non-debug
  mode, if it is unset, raise a clear error the first time encryption is needed —
  mirroring `validate_production_settings`'s fail-closed posture.
- **API never returns secrets.** Status endpoints return
  `{kind, connected, label?, created_at, last_used_at}` — NEVER the secret or the
  ciphertext. Decryption (`reveal`) is an INTERNAL service method only, documented as
  not-for-API; it exists for the Cabin/adapters in later phases.
- **Never log secrets.** No secret (plaintext or ciphertext) in any log line or
  exception message. The `label` is a non-secret hint only (e.g. last-4 of a token,
  or "device-login").
- **Per-user isolation.** Every operation is owner-scoped by `user_id` — a user can
  only touch their own credentials. Unique `(user_id, kind)`: one credential per kind
  per user (connecting again replaces).

## Task

1. **Crypto helper** (`app/core/seachest_crypto.py`) — derive a valid Fernet key from
   `settings.seachest_key` (an arbitrary string → SHA-256 → `urlsafe_b64encode` = a
   32-byte urlsafe-base64 key; accept the value as-is if it is already a valid Fernet
   key). `encrypt(plaintext: str) -> bytes` / `decrypt(token: bytes) -> str`. Missing
   key: debug → derive a stable dev key + warn; non-debug → raise `SeaChestKeyError`.
   Pure + unit-testable; no DB, no secret in any message.
2. **Model** `app/models/user_credential.py` — `UserCredential` (`user_credentials`):
   `id` UUID pk; `user_id` UUID FK→users.id indexed NOT NULL; `kind` String(32) NOT
   NULL; `ciphertext` LargeBinary NOT NULL; `label` String(255) nullable; `created_at`
   /`updated_at` tz-aware; `last_used_at` tz-aware nullable. Unique `(user_id, kind)`.
   Register in `models/__init__.py`. Migration `down_revision='b8d4f2a6c1e3'`.
3. **Schemas** `app/schemas/sea_chest.py` —
   `SeaChestConnectRequest{kind: Literal["claude_code","github"], secret: str, label: str|None}`
   and `CredentialStatus{kind, connected: bool, label, created_at, last_used_at}` (NO
   secret field anywhere).
4. **Service** `app/services/sea_chest_service.py` — `SeaChestService(session, settings)`
   + `SeaChestError(code, message)`: `store`, `reveal` (INTERNAL only), `status`,
   `status_for`, `delete`, `reader(session)`. Owner-scoped throughout.
5. **API** `app/api/v1/sea_chest.py` (kebab `/api/v1/sea-chest`, default-deny via
   `get_current_user`): `GET /sea-chest`, `PUT /sea-chest/{kind}`, `DELETE
   /sea-chest/{kind}` (204). Register in `router.py`.
6. **Settings**: `seachest_key: str | None = None` (env `GRANDLINE_SEACHEST_KEY`).

## Output format

- Type-annotated Python, async, Pydantic v2, classes PascalCase, functions
  snake_case, One Piece themed naming. New artifacts only under `src/backend/app/`,
  `src/backend/tests/`, and the named pdd files.
- TDD: failing tests first, then implement to green. Mocked sessions
  (`AsyncMock`/`MagicMock`), no Postgres.

## Constraints

- Mirror the Log Book / Standing Orders trios (owner-scoped CRUD, `Error(code, message)`,
  `reader()`, `add`→`flush`→`commit`→`refresh`).
- Migration `down_revision` MUST be `'b8d4f2a6c1e3'`; pick a UNIQUE 12-hex revision id.
- No secrets in code/logs. Do NOT break existing tests. No git.

## Edge Cases

- `seachest_key` unset + debug → stable derived dev key + warning; encrypt/decrypt work.
- `seachest_key` unset + non-debug → `SeaChestKeyError` raised on first encryption need.
- `seachest_key` is an arbitrary string (not a Fernet key) → derived deterministically.
- `seachest_key` is already a valid 32-byte urlsafe-base64 Fernet key → accepted as-is.
- `store` on an existing `(user_id, kind)` → replaces ciphertext + label (upsert).
- `reveal`/`status_for` for a kind the user hasn't connected → `None`.
- A foreign user can never read/replace/delete another user's credential (owner-scoped).
- `CredentialStatus` / any API response body NEVER contains the secret or ciphertext.
