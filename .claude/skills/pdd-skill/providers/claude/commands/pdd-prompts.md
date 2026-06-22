# Generate a Feature Prompt

This is the Claude adapter for the shared `Prompts` workflow in `core/workflows/prompts.md`. Keep shared workflow behavior aligned there; this file exists to preserve Claude-specific command wording and `$ARGUMENTS` handling.

**User input**: $ARGUMENTS

## Purpose

Create focused, versionable prompt artifacts that ask the AI to do one job well.

Prompts should be durable project artifacts, not one-off chat messages. Each prompt should have a single job, a clear file path, and a reviewable output expectation.

## Use When

- The team is ready to implement a planned change.
- Context is already in place or good enough to proceed.
- A feature is small enough to prompt directly or already decomposed into clear phases.

## Inputs

- feature description
- current context files
- plan or research notes if they exist

## Step 1: Load Context

Read the relevant project context first. If `pdd/context/project.md` exists, use it. Pull in conventions and decisions if they affect the requested feature.

Load the matching project-type reference file for prompt patterns, common feature concerns, and type-specific expectations.

If context is missing, continue but note that a later `/project:pdd-context` pass would improve prompt quality.

## Step 2: Decompose If Needed

Watch for work that should be split before writing prompts:

- multiple unrelated outputs
- backend and frontend bundled together
- implementation plus tests plus refactor all in one ask

If the task is too broad, split it into smaller prompts before writing anything.

## Step 3: Gather Task Details

Ask for the details needed to make the prompt precise:

- what the feature does
- inputs and expected outputs
- constraints and edge cases
- surrounding code or modules it must fit into

## Step 4: Write The Prompt

Before writing from scratch, check whether an existing template in `pdd/prompts/templates/` already fits.

Use a structure like:

```markdown
# Prompt: <feature name>
**File**: pdd/prompts/features/<area>/<feature-name>.md
**Created**: <date>
**Project type**: <detected type>

## Context
<relevant context>

## Task
<single, clear instruction>

## Input
<what the AI is working with>

## Output format
<what should be returned>

## Constraints
- <constraint>

## Examples (optional but recommended)
Input: <example>
Output: <example>
```

Save prompts under `pdd/prompts/features/<area>/`, `pdd/prompts/templates/`, or `pdd/prompts/experiments/` depending on maturity and reuse.

## Prompt Chaining

For multi-step features with dependencies:

- number prompts in order
- include dependencies between steps
- review each step before running the next

If one step fails, fix it and re-run downstream steps as needed instead of restarting the entire chain.

## Produces

- prompt files under `pdd/prompts/features/`, `templates/`, or `experiments/`
- clear run instructions and expected review follow-up

## Edge Cases

- **Vague goal**: break it into a feature list first
- **Prompt keeps failing**: route to `/project:pdd-update`
- **Exploratory work**: save to `pdd/prompts/experiments/` with a date prefix
- **Recurring structure**: extract a reusable template

## Default Storage Guidance

- stable implementation work -> `pdd/prompts/features/`
- repeated pattern -> `pdd/prompts/templates/`
- exploratory or uncertain work -> `pdd/prompts/experiments/`

## Default Next Step

Run the prompt, inspect the output, and move to `/project:pdd-review` before committing anything.
