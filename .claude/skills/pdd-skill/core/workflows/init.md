# Init

## Purpose

Add PDD structure to an existing repository without pretending the project is starting fresh.

Init should preserve reality. It adds the PDD layer to an existing codebase, detects what already exists, and hands off into `context` with a truthful starting point.

## Use When

- The codebase already exists.
- The user wants to introduce PDD incrementally.
- The repo already has source layout, tooling, and conventions worth detecting instead of recreating.

## Inputs

- Existing repository layout
- detectable stack and conventions
- any known constraints the AI should follow

## Step 1: Confirm This Is An Existing Project

Check for signs of an established codebase:

- git repository
- source files
- dependency manifests
- existing build or lint configuration

If the directory looks empty or brand new, route to `scaffold` instead.

## Step 2: Guard Against Overwrite

If `pdd/` already exists, do not overwrite it silently. Confirm whether the user wants to fill in missing pieces or stop.

## Step 3: Detect The Project Shape

Infer:

- project type
- tech stack
- likely source directories
- existing conventions from linting and formatting config

If multiple project types match, surface that and ask the user to confirm the primary type instead of guessing.

## Step 4: Create Only The PDD Layer

Create just the `pdd/` structure:

```text
pdd/
  prompts/
    features/
    templates/
    experiments/
  context/
    project.md
    conventions.md
    decisions.md
  evals/
    baselines/
    scripts/
```

Do not create a new source directory, do not create a new project root, and do not initialize git.

## Step 5: Present A Detection Summary

Summarize:

- inferred project type
- detected languages and frameworks
- likely source directories
- notable conventions from tool configs
- what was created under `pdd/`

Ask the user to confirm what is correct and what needs adjustment before moving on.

## Produces

- PDD folders added to the repo
- an initial understanding of the project shape
- a handoff into context refinement

## Rules

- never create a new project directory
- never run `git init`
- never modify source directories during init
- never overwrite existing `pdd/` files without explicit confirmation
- if detection is uncertain, say so

## Edge Cases

- **Multiple project types match**: surface all likely matches and ask for confirmation
- **Monorepo**: initialize the root thoughtfully and note likely sub-project boundaries
- **Existing partial PDD setup**: fill in gaps instead of pretending the project is uninitialized

## Default Next Step

Move to `context` and write what is true today, not what the team hopes to build later.
