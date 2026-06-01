# Poneglyph: User Intervention System (Phase 17)

**Issue**: #18 · **Depends on**: #16 (pipeline control), #17 (Observation Deck)

> PDD note: authored manually following the `/pdd-skill:pdd-prompts` workflow
> (the plugin is not installed in this execution environment).

## Goal

Give the fleet admiral live control over a voyage from the Observation Deck:
pause, resume, inject context, redirect a phase, cancel — every intervention
logged durably to the Ship's Log.

## What already existed (Phase 15)

`PipelineService.pause/resume/cancel` + REST `POST /voyages/{id}/{pause,resume,cancel}`
already flip status, record a CrewAction, and publish `crew_action_recorded`.

## Deliverables (this phase)

### Backend
- `CrewActionType.CONTEXT_INJECTED`, `CrewActionType.PHASE_REDIRECTED` (P8 taxonomy extension).
- `PipelineService.inject(voyage, context, phase_number=None)` — durable
  CrewAction + event; rejects terminal voyages (`VOYAGE_TERMINAL`).
- `PipelineService.redirect(voyage, phase_number, instruction)` — resets the
  targeted phase to PENDING so a resume re-builds it; durable CrewAction +
  event; rejects terminal voyages.
- `POST /voyages/{id}/inject` and `POST /voyages/{id}/redirect`
  (`InjectContextRequest`, `RedirectPhaseRequest`, `InterventionResponse`).

### Frontend
- `lib/intervention.ts` — pause/resume/cancel/inject/redirect over `apiFetch` (P4).
- `components/observation-deck/InterventionControls.tsx` — header control bar:
  Pause/Resume toggle, Inject (modal), Cancel (destructive confirmation).
  Hidden on terminal voyages; invalidates status + crew-actions on success.
- Wired into the deck header per active voyage.

## Tests
- Service: inject/redirect record correct action_type + details; terminal
  rejection; redirect resets phase_status.
- API: inject/redirect return crew_action_id; PipelineError → HTTP.

Intervention history surfaces automatically in the Ship's Log (CONTEXT_INJECTED
/ PHASE_REDIRECTED / PIPELINE_PAUSED/RESUMED/CANCELLED rows).
