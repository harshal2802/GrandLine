# Review

## Purpose

Treat AI-generated output like a PR by verifying correctness, identifying regressions, and calling out missing tests or checks.

Review should combine objective verification with judgment. The goal is not just "does it run?" but "is this safe, understandable, and worth committing?"

## Use When

- The AI generated code, docs, config, or another artifact that may be committed.
- The user asks if something is ready to commit.
- The team needs a quick risk assessment before merging or shipping.

## Inputs

- generated output
- relevant files or diffs
- expected behavior

## Before Reviewing

- Read `pdd/context/project.md` if it exists for project standards and stack context.
- Read `pdd/context/conventions.md` if it exists for style and architectural rules.
- If no context exists, ask what the output was supposed to do and note that future reviews will be stronger with context files.

If the user pastes code without explaining the goal, ask what they prompted and what they expected.

Load the matching project-type reference file to apply the right checklist for that domain.

## Phase 1: Verification

Run the relevant checks in order. Skip checks that do not apply to the project.

| Check | What it checks |
|---|---|
| **Build** | Code compiles or builds without errors |
| **Type check** | Static type checks pass, if applicable |
| **Lint** | No new lint violations |
| **Test** | Existing tests pass and new code has adequate coverage |
| **Security** | No hardcoded secrets, obvious injection risks, or dependency red flags |

If a verification step fails, surface it clearly before spending time on lower-priority polish.

## Phase 2: Subjective Review

Evaluate the output from four angles:

### 1. Correctness

Does it do what was requested? Are there obvious bugs, broken flows, or missing edge-case handling?

### 2. Project Fit

Does it match the documented stack, conventions, and prior decisions?

### 3. Maintainability

Will a teammate understand this later? Is the structure clear? Are there anti-patterns or unnecessary complexity?

### 4. Prompt Signal

What does this output say about the prompt quality? Should the next fix happen in code, in the prompt, or both?

Then apply the project-type review checklist from the relevant reference file.

## Issue Severity

Tag findings with a severity level:

| Severity | Meaning | Action |
|---|---|---|
| **Blocking** | Broken, insecure, or violates a hard constraint | Must fix before committing |
| **Should fix** | Missing edge case, wrong pattern, or convention violation | Fix before or soon after committing |
| **Consider** | Optional improvement or low-risk polish | Fix if time allows |

## Produces

- review findings
- verification results
- fix guidance or a commit-ready recommendation

## Output Format

Structure the review like this:

1. **Verification** — pass/fail per relevant check
2. **What's good** — specific strengths
3. **Issues** — ordered by severity, highest risk first
4. **Suggestions** — optional improvements
5. **Prompt feedback** — how to improve the prompt that generated the output
6. **Next step** — one clear action

## Edge Cases

- **Mostly good**: say so clearly and recommend commit after any small fixes
- **Fundamentally wrong**: name the root cause and route to `update`
- **Very large output**: focus on the highest-risk areas and explicitly note what was not reviewed
- **User disagrees**: explain once, stay concrete, and let them decide
- **First review of a new prompt**: suggest capturing an eval checklist in `pdd/evals/`

## Default Next Step

If issues are found, iterate on code or prompts. If the output is solid, commit it and consider `eval`.
