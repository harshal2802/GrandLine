# Poneglyph: Observation Deck — Frontend Foundation (Phase 16.1)

**Issue**: #17 · **PLAN**: [PLAN-observation-deck.md](PLAN-observation-deck.md) · **Contracts**: P1–P4, P9, P10, P12, P15

> PDD note: authored manually following the `/pdd-skill:pdd-prompts` workflow
> (the plugin is not installed in this execution environment).

## Goal

Ship the protocol backbone the three views ride on: auth bridge, a
transport-agnostic event store, the WS→SSE stream hook, voyage/crew-action
data hooks, the app shell (sidebar + connection chip), and login/register.

## Backend contracts (already merged, Phase 16.0)

- `POST /api/v1/auth/{login,register,refresh}` → `{access_token, refresh_token, token_type}`,
  also sets `access_token` cookie (non-HttpOnly, for the WS handshake).
- `GET /api/v1/auth/me` → `UserRead`.
- `GET /api/v1/voyages?status=active|terminal&cursor=&limit=` → `{items: VoyageListItem[], nextCursor}`.
- `GET /api/v1/voyages/{id}/crew-actions?cursor=&limit=` → `{items: CrewActionRead[], nextCursor}` (DESC).
- `GET /api/v1/voyages/{id}/status` → pipeline status.
- `WS /api/v1/voyages/{id}/events?token=<jwt>` → frames
  `{type:"event", payload:{msg_id, event:{event_id,event_type,voyage_id,timestamp,source_role,payload}}}`.
  Close 1008 = auth; 1003 = not found; 1000 + reason `voyage-terminal` = terminal (P10).
- `GET /api/v1/voyages/{id}/stream` → SSE fallback, same event JSON per `data:` line.

## Deliverables

| File | Responsibility |
|---|---|
| `lib/config.ts` | `API_BASE_URL`, `WS_BASE_URL` from `NEXT_PUBLIC_*`. |
| `lib/types.ts` | `CrewRole`, `VoyageStatus`, `EventEnvelope` (P3), `VoyageListItem`, `CrewActionRead`, `ConnectionState`, `Transport`. |
| `lib/auth/jwt.ts` | `decodeJwt`, `expiresInMs` (client-side `exp`, no verify) (P4). |
| `lib/auth/cookie.ts` | `readCookie(name)` read-only helper. |
| `lib/api.ts` | `apiFetch` — bearer injection from store at call time; 401 → refresh → retry once → fail → redirect `/login?redirect=` (P4). |
| `lib/preferences.ts` | typed, schema-versioned (`__version`) localStorage wrapper. |
| `lib/eventEnvelope.ts` | `normalizeFrame(frame, isReplay)` → `EventEnvelope` (P3). |
| `stores/auth.ts` | Zustand: tokens, user, `login/logout/refresh`, pre-emptive refresh scheduling (P4). |
| `stores/voyage.ts` | Zustand: per-voyage event maps deduped by `event_id`; `connectionState` incl `terminal-idle` (P10); `transport` (P1); `liveEpoch`+`replayMode` (P2); 5000 ring buffer; LRU eviction active+2 (P12); global 15k cap. |
| `hooks/useVoyageStream.ts` | WS first; 3 handshake fails/60s → sticky SSE (P1); replay→live cutover (P2); refresh+reconnect on auth close (P4); terminal-idle on terminal (P10); manual `reconnect()` retries WS first. |
| `hooks/useVoyages.ts` | `GET /voyages` with status filter + cursor (P7); `queryKey` arg (P15). |
| `hooks/useVoyageStatus.ts` | `GET /voyages/{id}/status`. |
| `hooks/useCrewActions.ts` | cursor pagination (P6); reconciliation triggers (P9). |
| `components/observation-deck/ConnectionState.tsx` | state + transport + last-event-ts + manual reconnect. |
| `components/observation-deck/Sidebar.tsx` | voyage list; click sets `?voyage=<id>`. |
| `components/Providers.tsx` | React Query client provider. |
| `app/(app)/layout.tsx` | sidebar + outlet + connection chip. |
| `app/(app)/page.tsx` | redirect → `/app/sea-chart`. |
| `app/login/page.tsx`, `app/register/page.tsx` | auth forms → store → redirect. |

## Tests (vitest + RTL)

- `lib/eventEnvelope.test.ts` — frame→envelope normalization; ms timestamp.
- `stores/voyage.test.ts` — dedupe by `event_id` (P3); order `(ts,msg_id)` (P3);
  replay→live cutover + `isReplay` snapshot (P2); LRU keeps active+2 (P12); 15k cap (P12);
  terminal-idle stops reconnect (P10).
- `stores/auth.test.ts` — login populates; logout clears; pre-emptive refresh schedule (P4).
- `lib/api.test.ts` — bearer injected; 401→refresh→retry; refresh-fail→redirect (P4).
- `hooks/useVoyageStream.test.ts` — 3 WS fails → SSE (P1); replay skips side effects; manual reconnect retries WS first.
- `lib/jwt.test.ts` — `expiresInMs` from `exp`.
