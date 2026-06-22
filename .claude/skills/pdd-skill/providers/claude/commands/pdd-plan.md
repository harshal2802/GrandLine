# Plan Before Prompting

This is the Claude adapter for the shared `Plan` workflow in `core/workflows/plan.md`. Keep shared workflow behavior aligned there; this file exists to preserve Claude-specific command wording and `$ARGUMENTS` handling.

**User input**: $ARGUMENTS

## Purpose

Break a feature into phases and decide the prompt-chain strategy before generating implementation prompts.

Planning prevents oversized prompts, hidden dependencies, and accidental architecture decisions. The goal is to make implementation sequencing explicit before code generation begins.

## Use When

- The feature spans multiple files, layers, or phases.
- A single prompt would mix too many concerns.
- The team needs sequencing before coding.
- The work has enough ambiguity or risk that a prompt chain should be designed intentionally.

## Inputs

- feature goal
- current context files
- research results if available

## Step 1: Load Context

Read `pdd/context/project.md`, `conventions.md`, and `decisions.md` if they exist. Scan existing prompts in `pdd/prompts/features/` to see what already exists.

Load the matching project-type reference file to pick the right decomposition patterns for the stack.

If context is missing, proceed carefully but flag that as a planning risk.

## Step 2: Understand The Feature

Ask conversationally:

- What are you trying to build?
- What does "done" look like?
- What already exists that this connects to?
- What unknowns or decisions are still open?

## Step 3: Decompose Into Phases

Break the feature into ordered phases. Each phase should produce one concrete, testable artifact and map to exactly one prompt.

Use a structure like:

```markdown
# Implementation Plan: <feature name>
**Created**: <date>
**Complexity**: Low | Medium | High
**Estimated prompts**: <count>

## Summary
<2-3 sentence overview of the approach>

## Phases

### Phase 1: <name>
**Produces**: <concrete artifact>
**Depends on**: nothing | Phase N | existing code
**Risk**: Low | Medium | High — <why>
**Prompt**: `pdd/prompts/features/<area>/<feature>-01-<phase>.md`

### Phase 2: <name>
...

## Risks & Unknowns
- <anything that needs investigation or a decision before proceeding>

## Decisions Needed
- <architectural choices to log in decisions.md>
```

## Step 4: Review The Plan

Before writing prompts, check whether:

- the decomposition feels right
- any phases should start as experiments
- any decisions should be resolved first

Do not rush into prompts if the phase boundaries or dependencies are still unclear.

## Produces

- phased implementation outline
- prompt-chain order
- checkpoints for review and validation

## Step 5: Save The Plan

Save the plan to `pdd/prompts/features/<area>/PLAN-<feature-name>.md` so it becomes the reference for the prompt chain.

## Edge Cases

- **Trivial feature**: skip planning and go directly to `/project:pdd-prompts`
- **Unknowns dominate**: suggest an experiment prompt first
- **Plan changes mid-implementation**: update the plan file and adjust remaining prompts
- **Multiple unrelated features**: create separate plans instead of combining them

## Default Next Step

Move to `/project:pdd-prompts` and generate the first focused implementation prompt.
