# Write PDD Context Files

This is the Claude adapter for the shared `Context` workflow in `core/workflows/context.md`. Keep shared workflow behavior aligned there; this file exists to preserve Claude-specific command wording and `$ARGUMENTS` handling.

**User input**: $ARGUMENTS

## Purpose

Write or update the persistent project context layer so future prompts are grounded in real project constraints.

**Write what is true, not what you hope will be true.** Stale or aspirational context makes every later prompt worse.

## Use When

- Context files do not exist yet.
- The stack, constraints, or architectural decisions have changed.
- The user wants better prompt quality and consistency.
- You need to refresh context after research, planning, or a major implementation decision.

## Inputs

- What the project is
- who it is for
- the tech stack
- quality expectations
- hard constraints and anti-patterns
- current implementation state

## Detect Project Type First

Load the matching project-type reference file from `references/` to get type-specific questions, conventions, and templates. Provider adapters may translate these paths into provider-specific syntax, but the underlying reference files should stay aligned.

| Type | Signals | Reference |
|---|---|---|
| Frontend / UI | React, Vue, Angular, Svelte, CSS, Tailwind | `references/frontend.md` |
| Backend / API | Node, FastAPI, Django, Rails, REST, GraphQL, gRPC, databases | `references/backend.md` |
| Mobile | iOS, Android, Swift, Kotlin, React Native, Flutter, Expo | `references/mobile.md` |
| Data / ML / AI | Python, Jupyter, pandas, PyTorch, scikit-learn, pipelines | `references/data-ml.md` |
| DevOps / Infra | Terraform, Docker, Kubernetes, CI/CD, AWS, GCP, Azure | `references/devops.md` |
| Full-stack | Frontend + backend, Next.js, Nuxt, SvelteKit | `references/fullstack.md` + `references/frontend.md` + `references/backend.md` |
| Library / Package | npm package, PyPI library, crate, gem, Go module, SDK | `references/library.md` (+ domain flavor if applicable) |
| CLI / Developer Tools | CLI app, terminal tool, code generator, REPL, arg parsing, subcommands | `references/cli-devtools.md` |
| Embedded / IoT | MCU, RTOS, bare-metal, Arduino, ESP32, STM32, Zephyr, FreeRTOS, firmware | `references/embedded-iot.md` |
| Game Development | Unity, Unreal, Godot, Bevy, game engine, ECS, frame budget | `references/game-dev.md` |
| Blockchain / Smart Contracts | Solidity, Vyper, Rust/Anchor, Hardhat, Foundry, EVM, Solana, DeFi | `references/blockchain.md` |
| Security / Pentesting Tools | Scanner, fuzzer, exploit framework, SIEM, detection rules, pentest | `references/security.md` |
| API Platform / SDK | Public API, developer platform, OpenAPI, SDK generation, rate limiting, webhooks | `references/api-platform.md` |
| Desktop / Native GUI | Tauri, Electron, Flutter desktop, SwiftUI macOS, Qt, .NET MAUI, WPF | `references/desktop-gui.md` |
| Compiler / Language Tooling | Compiler, interpreter, transpiler, linter, formatter, LSP server, parser, AST | `references/compiler-lang.md` |
| Robotics / ROS | ROS, ROS2, robot, drone, autonomous vehicle, URDF, Gazebo, MoveIt, Nav2 | `references/robotics.md` |

**Full-stack merge priority**: When `fullstack.md`, `frontend.md`, and `backend.md` are loaded together, `fullstack.md` conventions take precedence where they overlap. Fall through to the frontend or backend reference only for concerns `fullstack.md` does not address.

**Library is composable**: A project can be both a library and a domain type. When combined, `library.md` takes precedence for API surface, versioning, and distribution; the domain flavor takes precedence for implementation patterns.

If the project spans multiple types, load all relevant references. When conventions conflict, surface the conflict and record the decision in `pdd/context/decisions.md`.

## Produces

- `pdd/context/project.md`
- `pdd/context/conventions.md`
- `pdd/context/decisions.md`

## If Creating New Context Files

Ask these questions conversationally, not as a single long form:

1. What are you building, and who is it for?
2. What's the tech stack?
3. What does good output look like?
4. What should the AI never do or suggest?
5. What's already been built?

Then ask any type-specific questions from the matching reference file.

### `pdd/context/project.md`

Use this as the shared base template:

```markdown
# Project: <name>

## What we're building
<1-2 sentence description>

## Who it's for
<target users or stakeholders>

## Tech stack
- Language:
- Framework:
- Database:
- Deployment:

## What good output looks like
<quality bar, style expectations, standards>

## Constraints (what the AI should never do or suggest)
- <constraint>

## Current state
<what's already built, or "Starting from scratch">
```

Extend it with type-specific sections from the relevant reference file.

### `pdd/context/conventions.md`

Ask whether the user has code style preferences or patterns the AI should always follow.

Capture naming, file structure, error handling, testing expectations, and persistent AI instructions. Even a short draft is useful; the file can grow over time.

### `pdd/context/decisions.md`

Record important architectural decisions using a durable format:

```markdown
## Decision: <short title>
**Date**: <approximate>
**What was decided**: <the decision>
**Why**: <rationale>
**Don't suggest**: <alternatives to avoid>
```

## If Updating Existing Context Files

1. Read the existing files first.
2. Ask what changed: stack, decisions, constraints, or current state.
3. Update only stale sections instead of rewriting everything.
4. Add `**Last updated**: <date>` to modified files.
5. If the codebase is available, compare what the context claims with what actually exists.

## Edge Cases

- **Monorepo**: keep a root `pdd/context/project.md` for the system, plus sub-project context where needed.
- **Team project**: prioritize `conventions.md` and pull from existing linters or style guides when possible.
- **Context too long**: split deeper material into `architecture.md` or another supporting doc once the overview becomes hard to scan.
- **Partial info**: draft with placeholders rather than leaving the project without context.

## Default Next Step

For simple work, move to `/project:pdd-prompts`. For higher-risk or ambiguous work, move to `/project:pdd-research` or `/project:pdd-plan`. Provider adapters should suggest the provider-specific command or workflow name that matches that transition.
