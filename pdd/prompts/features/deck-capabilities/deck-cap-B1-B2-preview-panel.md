# Prompt: Preview panel — live logs + embedded running app (Phases B1 + B2)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-B1-B2-preview-panel.md
**Created**: 2026-06-22
**Depends on**: B0 (preview backend — runs the app in the Cabin, exposes preview API + logs tail)
**Project type**: Full-stack (FastAPI SSE + Next.js deck view)

## Context

B0 made "preview" real: the crew's built app runs as a long-running process inside the
user's Cabin, with `POST/GET/DELETE /api/v1/voyages/{id}/preview` + a `GET .../preview/logs`
tail. B1 + B2 surface that in the deck: **B1** streams the running app's logs live, and **B2**
embeds the running app in an iframe with start/stop controls. (B3 — an interactive PTY terminal
— is the next and final phase.)

## Task

### B1 — live log streaming (backend)
- `GET /api/v1/voyages/{id}/preview/logs/stream` (owner-scoped) — a `StreamingResponse`
  (`text/event-stream`) that polls `PreviewService.logs(user_id, tail=...)` on a short interval
  and emits only the NEW delta as `data: <line>\n\n` (longest-common-prefix anchor so a rotated
  tail re-syncs). Self-terminates on client disconnect (`request.is_disconnected()`), when the
  preview is absent, or at a hard iteration cap. Mirrors the pipeline SSE shape. App stdout/stderr
  only — never a secret.

### B1 + B2 — the panel (frontend)
- `lib/preview.ts` — `PreviewInfo`/`PreviewStatus` + `startPreview`/`getPreview`/`stopPreview`.
- `hooks/usePreview.ts` — React Query status (404 → `null` empty) + start/stop mutations.
- `hooks/usePreviewLogs.ts` — consumes the SSE stream via `fetch` + `ReadableStream` (EventSource
  can't set `Authorization`, so a fetch-reader carries the bearer token), ring-buffered,
  follow/pause, aborts on unmount.
- `components/observation-deck/PreviewPanel.tsx` — Start/Stop controls; when running, a
  **sandboxed** iframe (`sandbox="allow-scripts allow-same-origin allow-forms allow-popups"`) of
  `PreviewInfo.url` + "open in new tab" + a live logs pane; loading/error/empty/no-voyage states;
  active voyage from the store.
- `app/app/preview/page.tsx` + a `Preview` entry in `DeckShell` `TABS`.
- `next.config.mjs` — add CSP `frame-src 'self' http://localhost:* http://127.0.0.1:* https:` so
  the iframe loads the Cabin-run app.

## Output format
- Backend SSE mirrors `pipeline.py`'s `stream_events`; owner-scoped; no secret in the stream.
- Frontend: TS strict, `interface` props, Tailwind, React Query; the iframe is sandboxed; the SSE
  reader cleans up on unmount.
- Tests: pytest (SSE delta emission, owner-scoping, no-preview/disconnect close — mocked service)
  and Vitest (panel start→iframe+logs→stop, empty/error; the two hooks).

## Constraints
- No new dependency, no migration. Sandbox the iframe. Clean up the SSE reader on unmount.
- The SSE poll reads the process-local preview registry (v1 single-worker); multi-worker needs a
  Redis-backed lifecycle (noted).

## Edge Cases
- No preview running → empty state + Start button.
- Preview stopped while streaming → stream closes; panel returns to empty.
- Rotated/truncated log tail → longest-common-prefix anchor re-syncs the delta.
- Client navigates away → `is_disconnected()` / `AbortController` tears the stream down.
- Iframe app errors → sandbox contains it; "open in new tab" as a fallback.
