# Scaffold

## Purpose

Set up a brand new PDD project structure for a project that does not have an established repo layout yet.

Scaffold is for true greenfield work. It creates the PDD structure, establishes the default source layout, and prepares the repo for the first `context` pass.

## Use When

- The user is starting from scratch.
- They want folders, starter context stubs, and a clean workflow entrypoint.
- There is no established repository structure to preserve.

## Inputs

- Project name if one is available.
- High-level project type or stack, if already known.

## Step 1: Gather The Setup Inputs

Confirm:

- project name
- source directory name, defaulting to `src/`
- high-level project type if already known

If the user already has a populated project directory or repository, route them to `init` instead.

## Step 2: Create The Base Structure

Create every folder and file shown in this layout. The source directory defaults to `src/` unless the user chose a different source directory name in Step 1.

```text
<project-name>/
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
  <source-dir>/
  README.md
```

On macOS/Linux, use commands like:

```bash
mkdir -p pdd/{prompts/{features,templates,experiments},context,evals/{baselines,scripts}} src
touch pdd/context/project.md pdd/context/conventions.md pdd/context/decisions.md README.md
```

If the user chose a source directory name other than `src/`, replace `src` in the command with that name.

Initialize git only if the directory is not already a repository.

Adapt shell commands to the user's platform when needed.

## Step 3: Explain The Structure

Make it clear what each major folder is for:

- `pdd/prompts/features/` for stable feature prompts
- `pdd/prompts/templates/` for reusable patterns
- `pdd/prompts/experiments/` for time-boxed exploratory prompts
- `pdd/context/` for durable project context
- source directory for reviewed output and hand-written code
- `pdd/evals/` for prompt-quality checks

## Step 4: Guardrails

- do not overwrite existing files silently
- if `pdd/context/project.md` already exists, stop and confirm before replacing anything
- if the user already has a repo or meaningful source structure, prefer `init`

## Produces

- PDD folder structure under `pdd/`
- source directory, defaulting to `src/`
- starter context files
- project `README.md`
- a natural handoff to the context workflow

## Edge Cases

- **User already has a repo**: route to `init`
- **User wants a non-`src` source dir**: honor it consistently
- **User is unsure about project type**: scaffold first and refine during `context`

## Default Next Step

Move to `context` and fill in `pdd/context/project.md`, `conventions.md`, and `decisions.md`.
