# Prompt: DialPanel UI — claude_code options, editable fallback chains, Sea Chest connection status (Phase C2)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-C2-dial-panel-ui.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: The deck's `DialPanel` (today: edits role→provider/model via
`PUT /voyages/{id}/dial-config`, shows fallback chains READ-ONLY, watches per-provider
rate-limit headroom), **C1** (`role_mapping[role]` may carry a per-role `max_turns`
int 1–10 for `claude_code`; the backend resolver tolerates the extra key — `role_mapping`
is JSONB), and **Phase 0a Sea Chest** (`GET /api/v1/sea-chest` → `CredentialStatus[]`;
`DELETE /api/v1/sea-chest/{kind}` → 204; **the API never returns a secret**).
**Project type**: Frontend (Next.js App Router + React + TS strict + Tailwind + TanStack Query)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. The
Observation Deck's Details-drawer **Dial** tab (`DialPanel`) is where a voyage's Dial
System config is viewed and edited. Today it edits only role→provider/model and shows
fallback chains read-only.

This is **C2** of the Dial Config workstream (PLAN-deck-capabilities.md). It surfaces the
C1 backend (`claude_code` `max_turns`), makes fallback chains **editable**, and adds a
**Sea Chest connection status** indicator (is `claude_code` / `github` connected, with a
Disconnect action). The actual **connect** flows — device-code `claude login` (C0) and
GitHub OAuth (A3) — are LATER phases; C2 shows **status + Disconnect** and a disabled
"Connect (coming soon)" affordance, **not** the connect flow itself. **Never render a
secret** — the Sea Chest API does not return one.

## Task

1. **Types + API helpers** (`src/frontend/lib/dial.ts`):
   - Extend `RoleProviderConfig` to `{ provider: string; model: string; max_turns?: number }`.
   - Add a `CredentialStatus` type (`{kind: "claude_code"|"github"; connected: boolean;
     label: string|null; created_at: string; last_used_at: string|null}`) and Sea Chest
     api helpers in `src/frontend/lib/seaChest.ts`: `getSeaChest()`
     (`GET /sea-chest` → `CredentialStatus[]`) and `disconnectCredential(kind)`
     (`DELETE /sea-chest/{kind}` → 204). NEVER a secret field anywhere.

2. **`useSeaChest` hook** (`src/frontend/hooks/useSeaChest.ts`) — React Query over
   `getSeaChest()` (`queryKey: ["sea-chest"]`), so the status section gets loading/error
   states and the Disconnect mutation can invalidate it.

3. **`max_turns` control** in `DialPanel`: when `draft[role].provider === "claude_code"`,
   render a small number input (1–10, optional/clearable) bound to `draft[role].max_turns`
   via `setRole(role, { max_turns })`. Non-`claude_code` rows are unchanged. Saved as part
   of `role_mapping` (the existing save path). A stray `max_turns` must NOT trip the
   existing "every role needs provider+model" guard.

4. **Editable fallback chains** in `DialPanel`: a per-role editor for
   `fallback_chain[role]` — add an entry (provider dropdown from `DIAL_PROVIDERS` +
   optional model text), remove an entry. Maintain a `fallbackDraft` state seeded from
   `config.fallback_chain`; normalize entries to the object form `{provider, model?}`.
   Save via `updateDialConfig(voyageId, { fallback_chain })` (saved together with
   `role_mapping` by the same Save button so the dirty/save UX stays coherent). Keep
   `fallbackLabel` for compact display.

5. **Sea Chest connection status** section (a `CredentialStatusRow` subcomponent): show
   `claude_code` and `github` as **Connected** (with `label`, e.g. "device-login" /
   "token …abcd") or **Not connected** from `useSeaChest`. A **Disconnect** button calls
   `disconnectCredential(kind)` + invalidates `["sea-chest"]`. A **Connect** affordance is
   present but disabled, labeled "coming soon". Loading/error/empty states. NEVER a secret.

6. **Tests** (Vitest + RTL, mock `apiFetch`/hooks):
   - `DialPanel.test.tsx`: `max_turns` appears only for `claude_code` rows and round-trips
     into the saved `role_mapping`; fallback add/remove edits + saves `fallback_chain`;
     the Sea Chest section renders Connected/Not-connected from mocked data and Disconnect
     calls the DELETE; existing role/provider/model + rate-limit behavior still works.
   - `useSeaChest.test.ts`: URL + returns statuses.

## Output format

- TS strict, `interface` props, NO `any`, Tailwind only (deck nautical dark theme,
  matching existing `DialPanel` styling), React Query for server state,
  loading/error/empty states on every async surface. New artifacts only under
  `src/frontend/` and the named pdd files.
- TDD: failing tests first, then implement to green.

## Constraints

- **No backend change**, **no new dependency**. `max_turns` rides inside `role_mapping`
  (C1 backend tolerates it). Fallback chains save through the existing
  `updateDialConfig(... { fallback_chain })` path.
- **Never render a secret** — the Sea Chest API doesn't return one; only `label`,
  `connected`, timestamps.
- The **connect flow is NOT built here** — C2 is status + Disconnect + a disabled
  "coming soon" Connect affordance (device-login is C0, GitHub OAuth is A3).
- Keep all existing `DialPanel` behavior (role/provider/model editing, the save guard,
  the rate-limit headroom display).
- Do NOT break existing tests. No git.

## Edge Cases

- A `claude_code` row with no `max_turns` → blank input, saves no `max_turns` key (or
  omits it); switching a row away from `claude_code` drops the control.
- `max_turns` present but provider not `claude_code` → control hidden; the stray key must
  not block the provider+model save guard.
- `fallback_chain` is `null`/absent → editor starts empty; adding an entry creates the
  role's array.
- Sea Chest: not connected → "Not connected" + disabled Connect; connected → label +
  Disconnect; loading/error states distinct.
- The Disconnect DELETE failing → surfaces an error, does not crash the panel.
