# Run Prompt Evaluations

This is the Claude adapter for the shared `Eval` workflow in `core/workflows/eval.md`. Keep shared workflow behavior aligned there; this file exists to preserve Claude-specific command wording and `$ARGUMENTS` handling.

**User input**: $ARGUMENTS

## Purpose

Track prompt quality over time with explicit criteria instead of relying on memory or one successful run.

An eval turns "this felt good once" into something measurable. It gives the team a repeatable signal for prompt reliability and helps catch drift early.

## Use When

- A prompt matters enough to measure repeatedly.
- The team wants a baseline or regression signal.
- A once-good prompt has started to drift.
- The team wants confidence before reusing or promoting a prompt.

## Inputs

- prompt under test
- expected outputs or acceptance criteria
- baseline artifacts when available

## Step 1: Identify What To Evaluate

If the user names a prompt, evaluate that one.

Otherwise, prefer prompts that are:

- high-impact
- used often
- not yet covered by an eval
- suspected of drifting

## Step 2: Check For An Existing Eval

Look in `pdd/evals/` for a matching eval file, usually named `<prompt-name>-eval.md`.

If none exists, create a Level 1 manual checklist like:

```markdown
# Eval: <prompt name>
**Prompt**: pdd/prompts/features/<area>/<prompt-file>.md
**Created**: <date>
**Level**: 1 — Manual checklist

## Criteria
- [ ] Output compiles / runs without errors
- [ ] Matches the specified output format
- [ ] Handles the listed edge cases
- [ ] Follows project conventions
- [ ] No hallucinated imports, APIs, or functions
- [ ] Integrates with existing code without conflicts

## Type-specific criteria
<add checks from the project type reference file>

## Run log

| Run | Date | Result | Notes |
|---|---|---|---|
| 1 | <date> | <pass/fail> | <what happened> |
```

## Step 3: Run The Evaluation

Use the latest prompt output or ask the user to run the prompt if no output is available.

For each evaluation run:

1. check every criterion
2. mark pass or fail
3. log the run
4. summarize the overall result

## Pass-Rate Tracking

After 3 or more runs, track useful signals such as:

- **pass@1**: passes on the first try
- **pass@3**: passes at least once within three tries

## Step 4: Level Up When Ready

| Current level | Trigger to level up | Action |
|---|---|---|
| **Level 1** | 5+ runs of the same prompt | Save a known-good baseline |
| **Level 2** | Stable, frequently used prompt | Add scripted validation |

### Level 2

Save a known-good output under `pdd/evals/baselines/` and compare future outputs against it.

### Level 3

For mature prompts, add validation scripts under `pdd/evals/scripts/`.

## Produces

- evaluation notes or files under `pdd/evals/`
- pass/fail signals
- follow-up recommendations when quality drops

## Reporting

Use a compact report that includes:

- eval level
- run number and date
- pass/fail result
- criteria results
- pass-rate summary when enough runs exist
- recommendation

## Edge Cases

- **No prompt output available**: ask the user to run it first, or run it if possible
- **No eval exists yet**: create Level 1 and perform the first run
- **All prompts already have evals**: report coverage and suggest the least recently evaluated prompt
- **Criteria are outdated**: update the eval to match what quality now means for that prompt

## Default Next Step

If the eval fails, move to `/project:pdd-update`. If it passes consistently, keep the prompt in active use.
