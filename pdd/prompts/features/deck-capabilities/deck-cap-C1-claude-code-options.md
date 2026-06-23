# Prompt: Per-role Claude Code options in the dial config (Phase C1)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-C1-claude-code-options.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: The Dial System (Phase 6 — `ProviderAdapter` ABC, `create_adapter`,
`build_router_from_config`, `DialConfig{role_mapping, fallback_chain}` JSONB), the
Claude Code adapter (`app/dial_system/adapters/claude_code.py` — `ClaudeCodeAdapter`
with a `max_turns` knob, default sourced from `Settings.claude_code_max_turns`), and
the `ShipwrightRoleConfig` / `resolve_shipwright_max_concurrency` precedent
(`app/schemas/dial_config.py`) that carries a safe per-role knob inside `role_mapping`.
**Project type**: Backend (FastAPI + Pydantic v2)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. Each
crew role maps to a provider + model through the Dial System's `DialConfig`. The
`claude_code` provider runs completions through the Claude Code CLI (`claude -p`); its
behavioral knob `max_turns` is currently sourced ONLY from the global env setting
`Settings.claude_code_max_turns`, so every voyage and every role shares one value.

This is the first slice of the Dial Config workstream's per-role options
(PLAN-deck-capabilities.md, Phase C1). It mirrors the existing
`ShipwrightRoleConfig.max_concurrency` precedent exactly: a small, strict Pydantic
sub-schema carried INSIDE the role's `role_mapping` entry, plus a defensive resolver
that tolerates any malformed shape. It is a **safe behavioral knob only** —
host/auth knobs (`cli_path`, `workspace`, `extra_args`, tokens) stay env-level and
are NOT exposed per-role. The DialPanel UI for this is a later phase (C2); per-user
Claude Code credentials are C0 — both out of scope here.

## Task

Let a voyage set `max_turns` PER ROLE for the `claude_code` provider, inside that
role's `role_mapping` entry, resolved by the factory at adapter-construction time:

1. **Schema** (`app/schemas/dial_config.py`, directly beside `ShipwrightRoleConfig`) —
   `class ClaudeCodeRoleConfig(BaseModel)` with `model_config = ConfigDict(strict=True)`
   and a single `max_turns: int | None = Field(default=None, ge=1, le=10)`. (Only
   `max_turns` for now; leave room to add further safe knobs later.)

2. **Resolver** (`app/schemas/dial_config.py`) —
   `def resolve_claude_code_role_config(role_cfg: dict[str, Any] | None) -> ClaudeCodeRoleConfig`.
   Given ONE role's raw mapping entry (e.g.
   `{"provider": "claude_code", "model": "sonnet", "max_turns": 2}`), validate just the
   claude-code fields and return the config; on any non-dict / `ValidationError`, log a
   warning and return `ClaudeCodeRoleConfig()` (all-None defaults). Mirror
   `resolve_shipwright_max_concurrency`'s defensiveness. Sibling keys like
   `provider`/`model` must NOT break it — validate a filtered subset of the known
   claude-code fields so strict mode never rejects the extra keys.

3. **Factory plumbing** (`app/dial_system/factory.py`) —
   - Give `create_adapter` an optional per-role options param
     `role_cfg: dict[str, Any] | None = None` (default None so existing callers/tests
     are unaffected).
   - In the `claude_code`/`claude-code` branch, resolve
     `max_turns = resolve_claude_code_role_config(role_cfg).max_turns or settings.claude_code_max_turns`
     and pass it to `ClaudeCodeAdapter(..., max_turns=max_turns, ...)`. Keep
     `cli_path`/`timeout_seconds`/`workspace`/`extra_args` sourced from `settings`
     (unchanged — host/auth stays env-level).
   - In `build_router_from_config`, pass the role's raw mapping entry as `role_cfg`
     to `create_adapter` (primary role only; fallback entries are unchanged).

## Input

- `app/schemas/dial_config.py` — `ShipwrightRoleConfig` (`model_config =
  ConfigDict(strict=True)`, `max_concurrency: int | None = Field(default=None, ge=1,
  le=10)`) and `resolve_shipwright_max_concurrency(role_mapping)` (returns default on
  any missing/non-dict/invalid shape, logs a warning). Copy this shape exactly.
- `app/dial_system/adapters/claude_code.py` — `ClaudeCodeAdapter.__init__(self, model,
  cli_path="claude", timeout_seconds=300, max_turns=1, workspace=None, extra_args="")`.
- `app/dial_system/factory.py` — `create_adapter(provider, model, settings)` (claude_code
  branch) and `build_router_from_config(config, settings, mushi, rate_limiter)` (reads
  `mapping[role]`, calls `create_adapter`).
- `app/core/config.py` — `Settings.claude_code_max_turns` (env default to fall back to).
- Tests `tests/test_dial_config_schemas.py`, `tests/test_dial_factory.py` — mirror
  their style (no DB; plain Pydantic + mocked Settings).

## Output format

- Type-annotated Python following existing conventions: Pydantic v2, classes PascalCase,
  functions snake_case, One Piece themed naming. New artifacts only under
  `src/backend/app/`, `src/backend/tests/`, and the named pdd files.
- TDD: failing tests first, then implement to green. Tests in
  `tests/test_dial_config_schemas.py` (or a new `tests/test_claude_code_role_config.py`)
  and `tests/test_dial_factory.py`, no DB.

## Constraints

- Mirror the `ShipwrightRoleConfig` / `resolve_shipwright_max_concurrency` precedent
  exactly (strict schema + defensive resolver that returns defaults on any bad shape).
- `max_turns` is the ONLY per-role knob. Host/auth knobs (`cli_path`, `workspace`,
  `extra_args`, tokens) stay env-level — do NOT expose them per-role.
- `create_adapter`'s new `role_cfg` is optional (default None) so existing callers and
  tests are unaffected; non-`claude_code` providers ignore it.
- Resolver tolerates extra sibling keys (`provider`/`model`) — validate a filtered
  subset, never reject on them.
- Do NOT break existing tests — ADD new ones. No secrets. No git.

## Edge Cases

- `role_cfg` is None / not a dict / missing `max_turns` → resolver returns all-None
  defaults; factory falls back to `settings.claude_code_max_turns`.
- `max_turns` out of range (`0`, `11`, negative) or wrong type (`"2"`) → `ValidationError`
  inside the resolver → warning logged → all-None defaults → env fallback.
- `max_turns` valid (1–10) → that value reaches `ClaudeCodeAdapter._max_turns`.
- Sibling `provider`/`model` keys present alongside `max_turns` → tolerated, do not break
  resolution.
- Non-`claude_code` providers (anthropic/openai/ollama) → `role_cfg` ignored, behavior
  unchanged.
