# PDD Project Status

Check the health and completeness of the current PDD project setup.

**User input**: $ARGUMENTS

## What to check

Scan the current project directory and report on each layer:

<!-- GENERATED:claude-status-checks:start -->
### 1. Context layer

| Check | How |
|---|---|
| `pdd/context/project.md` exists and is non-empty | Read file, check for filled-in sections |
| `pdd/context/conventions.md` exists and is non-empty | Read file |
| `pdd/context/decisions.md` exists and has entries | Read file, count decisions |
| Context is fresh | Check for `**Last updated**` dates; flag if older than 30 days |

### 2. Prompts layer

| Check | How |
|---|---|
| `pdd/prompts/features/` has prompt files | Glob for `pdd/prompts/features/**/*.md` |
| Prompts follow the template structure | Spot-check for `## Task`, `## Context`, `## Constraints` sections |
| `pdd/prompts/experiments/` has stale entries | Flag any experiment files older than 7 days; suggest "Promote to `pdd/prompts/features/` or delete" |
| Prompt chains are complete | Check numbered sequences for gaps (for example, `-01-` exists but `-02-` is missing) |
| Templates available | Check `pdd/prompts/templates/` for `.template.md` files. If empty but 3 or more feature prompts exist with similar structure, suggest extracting a template. |

### 3. Evals layer

| Check | How |
|---|---|
| `pdd/evals/` has eval files | Glob for `pdd/evals/*.md` |
| Eval coverage | Compare prompts in `pdd/prompts/features/` vs evals; flag prompts without evals |

### 4. Output layer

| Check | How |
|---|---|
| `src/` has committed artifacts | Check if `src/` has files |
| Uncommitted AI output | Check git status for untracked files outside the PDD structure |
<!-- GENERATED:claude-status-checks:end -->

## Output format

<!-- GENERATED:claude-status-output-format:start -->
```text
## PDD Status: <project name>

### Context  [OK / NEEDS ATTENTION]
- project.md: <status>
- conventions.md: <status>
- decisions.md: <status>

### Prompts  [OK / NEEDS ATTENTION]
- Feature prompts: <count> across <areas count> areas
- Experiments: <count> (<stale count> stale)
- Chains: <complete/incomplete>

### Evals  [OK / NEEDS ATTENTION]
- Eval files: <count>
- Coverage: <prompts with evals> / <total prompts>

### Suggestions
- <actionable next step>
- <actionable next step>
```

Keep the output concise. Only flag problems and suggest the single most impactful next action.
<!-- GENERATED:claude-status-output-format:end -->
