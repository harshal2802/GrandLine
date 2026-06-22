# PDD Help

> **Version**: v1.4.0-3-gf83deb4

Quick reference for all PDD commands, workflow order, and usage guidance.

**User input**: $ARGUMENTS

## If the user passed an argument

If `$ARGUMENTS` names a specific command (e.g., "context", "pdd-context", "review"), show detailed help for that command only:

- **What it does** — one-paragraph description
- **When to use it** — the situation that calls for this workflow
- **Inputs it expects** — what the user should provide or have ready
- **What it produces** — the output artifact(s)
- **Typical next step** — what command usually follows

Use the command table and routing guide below to compose the answer. Give the user just what they asked about — don't dump the full help.

## If no argument was provided

Show the full quick reference below.

---

### Quick start

<!-- GENERATED:claude-help-quick-start:start -->
> **Quick start**: For most features, you only need three commands: **Context -> Prompts -> Review**. Add Research, Plan, and Eval for complex or critical features.
<!-- GENERATED:claude-help-quick-start:end -->

### All commands

<!-- GENERATED:claude-help-command-groups:start -->
**Getting started**

| Command | What it does |
|---|---|
| `/project:pdd-help` | Show the available workflows, when to use them, and the typical sequence. |
| `/project:pdd-scaffold` | Set up a new PDD project with folders, context stubs, and starter guidance. |
| `/project:pdd-init` | Add PDD structure to an existing repository and infer a starting context. |
| `/project:pdd-status` | Check what PDD artifacts exist, what is stale, and what to do next. |

**Building features**

| Command | What it does |
|---|---|
| `/project:pdd-context` | Write or update the persistent project context files that future prompts depend on. |
| `/project:pdd-research` | Explore the problem space, evaluate options, and decide what to build. |
| `/project:pdd-plan` | Break a feature into phases and decide the prompt chain strategy before coding. |
| `/project:pdd-prompts` | Generate focused feature prompts and place them in the right PDD folder. |
| `/project:pdd-update` | Diagnose and improve a prompt that is producing weak or incorrect output. |

**Quality**

| Command | What it does |
|---|---|
| `/project:pdd-review` | Verify and review AI-generated output before it is committed. |
| `/project:pdd-eval` | Track prompt quality over time with repeatable evaluation criteria. |
<!-- GENERATED:claude-help-command-groups:end -->

### "What should I use?"

<!-- GENERATED:claude-help-scenarios:start -->
| I want to... | Use |
|---|---|
| Start a brand new project | `pdd-scaffold` -> `pdd-context` |
| Add PDD to an existing codebase | `pdd-init` -> `pdd-context` |
| Build a new feature (complex) | `pdd-context` -> `pdd-research` -> `pdd-plan` -> `pdd-prompts` -> `pdd-review` |
| Build a new feature (simple) | `pdd-context` -> `pdd-prompts` -> `pdd-review` |
| Fix a prompt that isn't working | `pdd-update` |
| Check if my project setup is complete | `pdd-status` |
| Track prompt quality over time | `pdd-eval` |
<!-- GENERATED:claude-help-scenarios:end -->

### Per-command detail

Use this table when the user asks about a specific command.

<!-- GENERATED:claude-help-command-detail:start -->
| Command | When to use | Inputs | Produces | Next step |
|---|---|---|---|---|
| `pdd-scaffold` | Starting a brand new project from scratch | Project name (optional) | Folder structure with context stubs | `pdd-context` |
| `pdd-init` | Adding PDD to a project that already has code | Existing project directory | PDD folders plus auto-detected context | `pdd-context` |
| `pdd-context` | Before writing prompts, or when the project changes | Answers to context questions | `pdd/context/project.md`, `conventions.md`, `decisions.md` | `pdd-research` or `pdd-prompts` |
| `pdd-research` | Before building to clarify the problem and evaluate approaches | Problem description or feature idea | Research summary plus approach recommendation | `pdd-plan` or `pdd-prompts` |
| `pdd-plan` | When a feature spans multiple files, modules, or phases | Feature description plus context files | Phased implementation plan with prompt chain strategy | `pdd-prompts` |
| `pdd-prompts` | When you're ready to write the actual feature prompt | Feature description plus context files | Prompt file(s) in `pdd/prompts/features/` | Run the prompt, then `pdd-review` |
| `pdd-update` | When a prompt isn't producing good results | The failing prompt plus what went wrong | Updated prompt file | Run the prompt again, then `pdd-review` |
| `pdd-review` | When AI generated code and you want to verify it | Generated code, pasted or in files | Quality report plus fix suggestions | Commit or iterate |
| `pdd-eval` | After committing, to track prompt reliability | Prompt file plus expected outcomes | Eval results in `pdd/evals/` | Update the prompt if quality drops |
| `pdd-status` | When you want to check project health | None | Status report with suggestions | Whatever the report recommends |
| `pdd-help` | When you want to see available commands | Command name (optional) | This reference | Whatever workflow fits |
<!-- GENERATED:claude-help-command-detail:end -->
