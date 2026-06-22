# Research Before Building

This is the Claude adapter for the shared `Research` workflow in `core/workflows/research.md`. Keep shared workflow behavior aligned there; this file exists to preserve Claude-specific command wording and `$ARGUMENTS` handling.

**User input**: $ARGUMENTS

## Purpose

Explore the problem space before implementation so the team can adopt, extend, compose, or build with intention.

Research exists to prevent waste. Do not jump straight from "I want feature X" to implementation prompts when the real question is still "what problem are we solving, and what already exists?"

## Use When

- The user is unsure which approach to take.
- Existing tools or libraries may already solve the problem.
- The feature is expensive or risky enough to justify pre-work.
- The team needs a build-vs-adopt decision with explicit tradeoffs.

## Inputs

- Problem statement
- constraints
- success criteria
- any candidate tools or approaches already under consideration

## Step 1: Clarify The Problem

Ask conversationally:

- What problem are you trying to solve?
- Who encounters this problem and when?
- What happens today without this?
- What does success look like?

If the user already has a clear, narrow need, skip most of the discovery and move directly to scanning for solutions.

## Step 2: Surface Constraints

Capture the constraints that shape the decision:

- performance or scale requirements
- security, privacy, or compliance requirements
- integration points with the existing codebase
- timeline or effort budget
- things that are explicitly out of scope

These notes should be reusable later in `/project:pdd-plan`, `/project:pdd-prompts`, and `/project:pdd-review`.

## Step 3: Scan For Existing Solutions

Check these sources in order:

1. Existing codebase
2. Prompt history and templates
3. Package or tool ecosystem
4. MCP servers or external capabilities
5. Framework built-ins

Look for solutions that are current, maintained, and compatible with the project constraints.

## Step 4: Evaluate The Approaches

Use these four buckets:

| Approach | When to use | Example |
|---|---|---|
| **Adopt** | An existing tool already fits | Use zod for validation |
| **Extend** | Something close exists but needs small customization | Fork a template, add constraints |
| **Compose** | Several existing pieces fit together well | Wrap two tools behind one local interface |
| **Build** | Nothing fits, or constraints rule out the existing options | Implement a custom solution |

Present findings in a durable format:

```markdown
## Research: <problem being solved>

### Problem
<1-2 sentence problem statement>

### Key constraints
- <constraint>

### Options evaluated
#### Option 1: <name> (Adopt / Extend / Compose / Build)
**What**: ...
**Pros**: ...
**Cons**: ...
**Effort**: Low | Medium | High

### Recommendation
<which approach and why>
```

## Produces

- an option set
- tradeoff analysis
- a recommendation
- explicit reasoning for build vs adopt decisions
- reusable notes for later workflows

## Step 5: Decide And Proceed

- **Adopt**: help install, configure, or integrate it
- **Extend**: move to `/project:pdd-prompts` with adaptation guidance
- **Compose**: move to `/project:pdd-plan` or `/project:pdd-prompts` depending on complexity
- **Build**: move to `/project:pdd-plan` for multi-step work, or `/project:pdd-prompts` if the task is still small and clear

Record the decision and rejected alternatives in `pdd/context/decisions.md`.

If the findings will matter later, save the full summary in `pdd/context/research/<topic>.md`.

## Edge Cases

- **User already knows what to build**: skip most discovery and do a fast solution scan
- **User wants to build anyway**: respect the choice, but log the rejected alternatives
- **Multiple good options**: present the comparison clearly and let the user decide
- **No existing solutions**: confirm the scan was thorough, then proceed to `/project:pdd-plan`
- **Problem is too vague**: narrow it to one use case or user story before researching broadly

## Default Next Step

If the recommendation is to build, move to `/project:pdd-plan`. If the research settles a small change directly, move to `/project:pdd-prompts`.
