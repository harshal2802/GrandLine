# Update an Existing Prompt

This is the Claude adapter for the shared `Update` workflow in `core/workflows/update.md`. Keep shared workflow behavior aligned there; this file exists to preserve Claude-specific command wording and `$ARGUMENTS` handling.

**User input**: $ARGUMENTS

## Purpose

Improve a prompt that is underperforming instead of immediately rewriting it from scratch.

Default to diagnosis before replacement. Most weak prompts need a few targeted fixes, not a full rewrite.

## Use When

- The prompt produces wrong output.
- The results are inconsistent, incomplete, or too broad.
- The user can describe what went wrong.
- The prompt worked once but is no longer reliable enough to trust.

## Inputs

- the existing prompt
- observed failure mode
- desired behavior

## Step 1: Identify The Root Cause

Ask for the prompt and the resulting output if they are not already available.

Use this symptom table to guide the diagnosis:

| Symptom | Likely cause | Fix |
|---|---|---|
| Output is too generic | Missing context | Add project or tech context |
| Output ignores constraints | Constraints are vague or buried | Move constraints higher and make them explicit |
| Output does too many things | Task is too broad | Split into multiple prompts |
| Output format is wrong | Format is underspecified | Add an explicit output format section |
| Output drifts across runs | Prompt is ambiguous | Add concrete examples or tighter language |
| Output contradicts conventions | No conventions reference | Pull in `pdd/context/conventions.md` |

If possible, run the prompt 2 to 3 times:

- **Consistent errors** usually mean the prompt is wrong
- **Inconsistent output** usually means the prompt is ambiguous
- **Correct but unusable output** usually means the format or scope is wrong

## Step 2: Apply Targeted Fixes

Prefer the smallest effective change:

- add missing context
- elevate buried constraints
- add a concrete example
- narrow the task
- split one overloaded prompt into smaller prompts

Only recommend a full rewrite when more than half the prompt needs to change.

## Step 3: Show What Changed

Do not just hand back a replacement prompt. Explain what changed and why.

Where possible, show a before/after diff of the key sections so the user can learn from the change.

## Produces

- a revised prompt
- clearer scope or constraints
- a recommendation for how to re-run and verify it

## Step 4: Verify And Version

- suggest re-running the updated prompt 2 to 3 times
- recommend reviewing the new output with `/project:pdd-review`
- keep version history clear so the team knows what was fixed

If the old prompt is effectively abandoned, move it to `pdd/prompts/experiments/` with a date prefix instead of silently losing that history.

## When To Start Fresh

Start from scratch only when the prompt is fundamentally the wrong shape for the job. In that case, route back to `/project:pdd-prompts` and preserve the old prompt as an experiment or historical reference.

## Default Next Step

Re-run the prompt, then move to `/project:pdd-review` on the resulting output.
