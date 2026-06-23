# Prompt: Interactive terminal — a PTY in the user's Cabin over a bidirectional WS (Phase B3)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-B3-terminal.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Phase 0b (**the Cabin** — `CabinBackend`/`CabinService`, `NullCabinBackend`
default, `GVisorCabinBackend` opt-in with a LAZY `aiodocker` import), Phase B0 (the Cabin
runs the crew's app), the **bidirectional-WS foundation** reserved by Phase 17 and the deck
WS auth/close-code conventions in `app/api/v1/observation_deck.py`
(`_ws_credentials`, `grandline-bearer` subprotocol, close `1008`/`1003`/`1000`), Auth (Phase
4 — `decode_token`, `get_current_user`, `get_authorized_voyage`, default-deny middleware),
and `Settings` (`GRANDLINE_` env prefix). `aiodocker` MUST stay a LAZY import (never
module-top) so app startup + the test suite never need Docker.

**Project type**: Backend (FastAPI + Pydantic v2 + SQLAlchemy async) + Frontend (Next.js/React/TS)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. The **Live App**
workstream (PLAN-deck-capabilities.md, Workstream B = B0 → B1 → B2 → B3) lets a user run the
app the crew built. B0 made preview real (run the app in the user's Cabin), B1 streamed its
logs, B2 embedded it in an iframe. **B3** is the final phase: a **real interactive shell into
the user's Cabin**, shown in the deck via `xterm.js`, bridged over a **bidirectional
WebSocket**. The existing deck WS (`/voyages/{id}/events`) is server→client only; B3 ADDS
inbound frame handling on a NEW endpoint.

This is the **largest attack surface in the epic** — interactive arbitrary command execution —
so it gets its own security review. The mitigation is that everything runs INSIDE the
already-isolated gVisor Cabin (kernel-filtered syscalls, deny-by-default egress, per-user,
bounded by the Cabin's hard max lifetime + reaper). There is no host access.

## SECURITY REVIEW (NON-NEGOTIABLE — this phase's dedicated gate)

- **Owner-scoped, always.** The terminal ONLY ever attaches to the **requesting user's own
  Cabin**. The WS resolves the voyage with the same owner check as every deck endpoint
  (`Voyage.user_id == user.id`) and keys the Cabin on the authenticated user's id — there is
  NO path to another user's Cabin or shell.
- **Authenticated WS.** Auth rides the existing `grandline-bearer` subprotocol
  (`Sec-WebSocket-Protocol: grandline-bearer, <jwt>`) or the `access_token` cookie — never the
  URL. A missing/invalid/expired token → **close `1008`** (policy). Not found / not owned →
  **close `1003`** (unsupported data). We accept-then-close so the browser surfaces the code.
- **Arbitrary commands, but ONLY inside the gVisor Cabin.** The PTY is an `aiodocker` exec with
  `tty=True` + stdin attached, inside the persistent per-user container: kernel-filtered
  syscalls (runsc), deny-by-default egress (the Cabin's allow-list), CPU/mem quotas, readonly
  rootfs + tmpfs, and the Cabin's **hard max lifetime + idle reaper**. No host process is ever
  spawned. The blast radius is exactly the Cabin's blast radius.
- **No secret is logged.** PTY bytes are passed through verbatim to the client and never logged;
  the terminal never injects or echoes a materialized secret, and exceptions never carry frame
  contents. `CabinTerminal` exposes no secret field.
- **Bounded teardown.** The PTY session is torn down on disconnect, Cabin destroy, error, or an
  **idle timeout** (`terminal_idle_timeout_seconds`, default 600s) — both pump tasks are
  cancelled and `terminal.close()` is called in a `finally`. No orphan exec streams.
- **Lazy `aiodocker`.** Extending `GVisorCabinBackend` must NOT import `aiodocker` at module
  top; absent → a clear `CabinError("BACKEND_UNAVAILABLE")`, never an opaque `ImportError`.

## Locked design decisions

- **PTY lives in the Cabin contract.** Extend `CabinBackend` (+ Null + gVisor) with
  `async open_terminal(user_id, *, cols=80, rows=24) -> CabinTerminal`. `CabinTerminal` is a
  small async handle: `read() -> bytes` (PTY output), `write(data: bytes)` (stdin),
  `resize(cols, rows)`, `close()`. NO secret field.
- **Null backend = a deterministic in-memory terminal.** Echoes input back and emits a canned
  prompt, so the full WS bridge is testable with NO container (the CI default). `read()` blocks
  until there is output (an `asyncio.Queue`), so the output-pump task behaves like a real PTY.
- **gVisor backend = a real PTY** via `aiodocker` exec (`Tty=True`, `AttachStdin=True`), lazy
  import; clean `CabinError` if absent. Bounded by the Cabin; egress unchanged.
- **Bidirectional WS** in a NEW `app/api/v1/terminal.py`. One task pumps PTY output → client
  (`{"type":"output","data":<str>}`); another reads client frames
  (`{"type":"input","data":<str>}` → `terminal.write`; `{"type":"resize","cols","rows"}` →
  `terminal.resize`). The two tasks race; whichever finishes first tears the other down.
- **Process-local, v1 single-worker** — like the Cabin registry; a per-connection terminal, no
  cross-request registry needed (the WS owns its terminal for its lifetime).

## Task

### Backend
1. **Cabin contract** (`app/cabin/backend.py`): add `CabinTerminal` (ABC) with async
   `read`/`write`/`resize`/`close`, and `async open_terminal(user_id, *, cols=80, rows=24) ->
   CabinTerminal` on `CabinBackend`.
2. **Null backend** (`app/cabin/null_backend.py`): `_NullCabinTerminal` — a queue-backed echo
   terminal that emits a canned prompt on open and echoes each `write` back as output. Raises
   `CabinError` if the user has no Cabin.
3. **gVisor backend** (`app/cabin/gvisor_backend.py`): real PTY exec (lazy `aiodocker`,
   `Tty=True` + `AttachStdin=True`); a `_GVisorCabinTerminal` wrapping the exec stream;
   `resize` best-effort; `close` shuts the stream. `CabinError` if `aiodocker` absent.
4. **`CabinService.open_terminal(user_id, session, *, cols, rows)`** — ensure the Cabin, then
   `backend.open_terminal`; touch `last_active`.
5. **Bidirectional terminal WS** `app/api/v1/terminal.py`: `WS /api/v1/voyages/{id}/terminal`.
   Auth via the shared `_ws_credentials`/`_authenticate_ws_token` helpers (reuse from
   `observation_deck`), owner-scope the voyage (`1003` if not owned), `open_terminal` on the
   user's Cabin, then bridge with two tasks + idle timeout; tear down both + the terminal in a
   `finally`. Register the router in `router.py`.
6. **Settings**: `terminal_enabled: bool = True`, `terminal_idle_timeout_seconds: int = 600`.

### Frontend
7. **`@xterm/xterm` + `@xterm/addon-fit`** dependency. `components/observation-deck/TerminalPanel.tsx`
   mounts an `xterm` `Terminal`, opens `new WebSocket(${WS}/voyages/${id}/terminal,
   ["grandline-bearer", token])`, pipes xterm `onData` → `{"type":"input",...}`, WS `output` →
   `term.write`, `FitAddon` + a resize observer → `{"type":"resize",...}`. Connect/disconnect
   status; clean teardown on unmount. Mount as a **Terminal** section in the Preview view.
8. **`hooks/useCabinTerminal.ts`** — encapsulates the WS lifecycle (connect, frames, teardown).

### Tests + Docs
9. Backend `tests/test_terminal_ws.py` — auth reject `1008`, owner-scope reject `1003`, an
   input frame reaches `terminal.write` + PTY output reaches the client, resize forwarded, clean
   close (Null terminal + mocked WS, mirroring `test_observation_deck_ws.py`).
   `tests/test_cabin_backend.py` — Null `open_terminal` echo + gVisor lazy-import guard.
10. Frontend `TerminalPanel.test.tsx` — mounts, connects (mock WS), forwards input, writes
    output to the term (mock xterm), resizes, tears down on unmount.
11. Docs: prepend a dated `decisions.md` B3 entry (security posture) + a `project.md`
    current-state line; note the **deck-capabilities epic is complete**.

## Output format

- Type-annotated Python, async, Pydantic v2, classes PascalCase, functions snake_case, One
  Piece themed naming ("Cabin", "terminal"). New backend artifacts only under
  `src/backend/app/` + `src/backend/tests/`; new frontend artifacts under `src/frontend/`.
- TS strict, `interface` props, NO `any`, Tailwind, clean WS + xterm teardown on unmount.
- TDD: failing tests first, then implement to green. Null backend / mocked WS / mocked xterm —
  no Docker, no Postgres, no real socket.

## Constraints

- Extend the Cabin contract (ABC + Null + gVisor) for the PTY; do NOT touch the pipeline.
- Lazy `aiodocker` import inside methods; missing lib → clean `CabinError`.
- Owner-scoped + authenticated WS; secrets never logged. `@xterm/xterm` + `@xterm/addon-fit`
  are the ONLY new deps. No migration. Do NOT break existing tests. No git.

## Edge Cases

- Bad/missing token → `1008`; never reaches `open_terminal`.
- Voyage not owned / not found → `1003`.
- Client disconnect mid-session → both pump tasks cancelled, `terminal.close()` called once.
- Idle past `terminal_idle_timeout_seconds` with no I/O → session torn down (`1000`).
- Malformed inbound frame (not JSON / unknown type) → ignored, the session stays up.
- gVisor `open_terminal` with `aiodocker` absent → `CabinError("BACKEND_UNAVAILABLE")`, never
  an opaque `ImportError`; importing the module never imports `aiodocker`.
- No secret ever appears in a frame, a log line, or an exception message — only PTY bytes.
