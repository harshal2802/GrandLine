# Implementation Plan: PandaOS-Inspired Features

**Created**: 2026-06-22
**Complexity**: High
**Estimated prompts**: 6 (one Poneglyph per feature, shipped as a stacked PR series)

## Summary

A competitive review of [PandaOS](https://pandaos.ai/) — a local AI workstation
whose pitch is "AI agents operate your whole dev stack, not just write code" —
surfaced six capabilities worth adapting into GrandLine's crewed, observable
pipeline model. PandaOS's desktop shell, embedded browser, and plugin surface are
orthogonal to GrandLine and deliberately **not** adopted. What we adapt are the
ideas about **memory, triggers, verification, and closing the loop** — each of
which makes GrandLine's "disciplined crew, observable and interventable, PDD/TDD
as the Log Pose" story stronger rather than diluting it.

These ship as a **linear stack of six PRs**, dependency-ordered. Each PR carries
its own Poneglyph, health checks (TDD), implementation, docs, and a
`decisions.md` entry — the Log Pose applies to our own features too.

## PandaOS → GrandLine mapping

| PandaOS capability | GrandLine adaptation | One Piece name |
|---|---|---|
| Local knowledge graph ("never re-explain your stack") | Cross-voyage memory the Captain recalls when planning | **Log Book** |
| Saved workflows / agent setups | Reusable voyage presets (dial config + plan skeleton + context) | **Standing Orders** |
| Pull context from Gmail/GitHub; start work from an email | Chart a course from a GitHub issue / webhook | **Message in a Bottle** |
| Draft a reply to the reporter confirming the fix | Post a voyage summary back to the originating channel | **Return Bottle** |
| Test in browser to verify the fix | Doctor runs a browser health check, screenshots to Ship's Log | **Bedside Browser** |
| Switch context without losing terminal/browser/agent state | Lossless per-voyage deck state + voyage switcher | **Fleet Switcher** |

## Dependency graph

```
Phase 19 (Log Book) ──────────┐
Phase 20 (Standing Orders) ────┤  (independent of each other; stacked for clean shared-file edits)
Phase 21 (Message in a Bottle) ─→ Phase 22 (Return Bottle)   [22 needs 21's voyage origin metadata]
Phase 23 (Bedside Browser) ────┐
Phase 24 (Fleet Switcher) ─────┘  (frontend; consumes existing deck)
```

Stacked PR order (each based on the previous branch):
1. **PR1 — Log Book** · branch `claude/panda-os-features-review-czwvv0` · base `main`
2. **PR2 — Standing Orders** · branch `claude/panda-os/02-standing-orders`
3. **PR3 — Message in a Bottle** · branch `claude/panda-os/03-message-in-a-bottle`
4. **PR4 — Return Bottle** · branch `claude/panda-os/04-return-bottle`
5. **PR5 — Bedside Browser** · branch `claude/panda-os/05-bedside-browser`
6. **PR6 — Fleet Switcher** · branch `claude/panda-os/06-fleet-switcher`

## Phases

### Phase 19: Log Book — cross-voyage memory
**Produces**: A per-repo memory store the Captain recalls at planning time, so the
crew never re-explains the stack across voyages.
**Adapts**: PandaOS local knowledge graph.
**Poneglyph**: `pdd/prompts/features/panda-os/grandline-19-log-book.md`
**Backend seam**: `CaptainService.chart_course` recalls Log Book context for
`voyage.target_repo` and injects it into the planning prompt; learnings are
recorded via API and (optionally) a pipeline-completion hook.

### Phase 20: Standing Orders — voyage templates / presets
**Produces**: Named, reusable bundles of dial config + plan skeleton + injected
context, so recurring task shapes ("bugfix voyage", "dep-bump voyage") chart
faster.
**Adapts**: PandaOS saved workflows.
**Poneglyph**: `pdd/prompts/features/panda-os/grandline-20-standing-orders.md`

### Phase 21: Message in a Bottle — external triggers
**Produces**: Chart a course from a GitHub issue / signed webhook. Records voyage
**origin** metadata (channel, repo, issue number) for the return trip.
**Adapts**: PandaOS "pull context from Gmail/GitHub; start from an email".
**Poneglyph**: `pdd/prompts/features/panda-os/grandline-21-message-in-a-bottle.md`

### Phase 22: Return Bottle — close the loop
**Produces**: On voyage completion, post a summary back to the originating channel
(e.g. a GitHub issue comment) using the Phase 21 origin metadata.
**Adapts**: PandaOS "draft a reply to the reporter".
**Depends on**: Phase 21 (origin metadata).
**Poneglyph**: `pdd/prompts/features/panda-os/grandline-22-return-bottle.md`

### Phase 23: Bedside Browser — browser-in-the-loop verification
**Produces**: A Doctor health-check mode that drives a headless browser inside the
Execution sandbox and surfaces screenshots in the Ship's Log — "tests pass AND the
page renders".
**Adapts**: PandaOS "test in browser to verify".
**Poneglyph**: `pdd/prompts/features/panda-os/grandline-23-bedside-browser.md`

### Phase 24: Fleet Switcher — multi-voyage deck
**Produces**: Lossless per-voyage Observation Deck state (active view, filters,
scroll) plus a quick voyage switcher, so a fleet admiral hops between concurrent
voyages without losing context.
**Adapts**: PandaOS state-preserving context switch.
**Poneglyph**: `pdd/prompts/features/panda-os/grandline-24-fleet-switcher.md`

## Constraints (apply to every phase)
- The Log Pose holds: Poneglyph first, health checks (TDD) before implementation.
- One Piece terminology throughout code, API labels, and docs.
- No secrets in code; webhook secrets and provider keys via environment only.
- All new backend artifacts under `src/backend/app/`, tests under
  `src/backend/tests/`; schema changes via a new Alembic revision chained to the
  current head.
- Default-deny security posture; signed/verified inbound webhooks only.
- Update `pdd/context/decisions.md` and `pdd/context/project.md` in the same PR;
  refresh `docs/` where the feature is user-visible.

## Decisions needed
- None blocking. Each phase records its own non-obvious choices in `decisions.md`.
