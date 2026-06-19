---
name: pdd-skill
description: >-
  Trigger when the user mentions PDD, wants to scaffold an AI-assisted project,
  write context or prompt files, improve prompts, or review AI-generated output.
  Also trigger for: "structure my AI project", "organize my prompts", or
  "review this AI code" -- even without the term PDD.
---

# Prompt Driven Development (PDD) Skill

This skill turns Claude into a PDD partner — helping users structure, operate, and improve AI-assisted development projects.

**Nine core workflows:**
<!-- GENERATED:claude-workflow-overview:start -->
1. **Scaffold** — set up a new project folder structure
2. **Init** — add PDD to an existing project (auto-detects stack and conventions)
3. **Context** — write or update context files (`project.md`, `conventions.md`, `decisions.md`)
4. **Research** — explore a problem space, evaluate approaches, and decide what to build
5. **Plan** — decompose a feature into phases and a prompt chain strategy
6. **Prompts** — generate well-structured feature prompts
7. **Update** — improve or refactor an existing prompt
8. **Review** — verify and review AI-generated output before committing (includes automated quality checks)
9. **Eval** — run prompt evaluations and track quality over time
<!-- GENERATED:claude-workflow-overview:end -->

<!-- GENERATED:claude-quick-path:start -->
**Quick path**: For simple features, you only need **Context -> Prompts -> Review**. Research, Plan, and Eval add value for complex or critical features but are not required for every task. Use **Init** instead of Scaffold when adding PDD to a project that already has code.
<!-- GENERATED:claude-quick-path:end -->

---

## Step 0: Identify what the user needs

<!-- GENERATED:claude-routing-table:start -->
| If the user says... | Use workflow |
|---|---|
| "Start a new PDD project", "Set up folder structure", "How do I get started?" | -> **Scaffold**: run `/project:pdd-scaffold` |
| "Add PDD to my project", "Initialize PDD here", "Set up PDD in this repo" | -> **Init**: run `/project:pdd-init` |
| "Help me write my project.md", "What should my context file say?" | -> **Context**: run `/project:pdd-context` |
| "Is there a library for this?", "Does something already do this?", "What should I build?", "Help me think through this", "I'm not sure what approach to take" | -> **Research**: run `/project:pdd-research` |
| "Plan this feature", "How should I break this down?" | -> **Plan**: run `/project:pdd-plan` |
| "Write a prompt for this feature", "Help me prompt this" | -> **Prompts**: run `/project:pdd-prompts` |
| "This prompt isn't working", "Can you improve this prompt?" | -> **Update**: run `/project:pdd-update` |
| "Check this code", "Run the quality checks", "Is this ready to commit?", "Review this output", pastes code without instructions | -> **Review**: run `/project:pdd-review` |
| "How is my prompt performing?", "Run the eval", "Track prompt quality" | -> **Eval**: run `/project:pdd-eval` |
| "What's set up?", "What's missing?", "Show me the project health" | -> **Status**: run `/project:pdd-status` |
| "What commands are there?", "Help me with PDD", "What can you do?", "How does PDD work?" | -> **Help**: run `/project:pdd-help` |
<!-- GENERATED:claude-routing-table:end -->
| Vague or unclear | → Ask: *"Are you starting a new project, working on a feature prompt, or reviewing something the AI generated?"* |

**If context files don't exist yet:** Don't block the user. Proceed with the requested workflow and suggest context files afterward.

### Returning to an existing PDD project

When context files already exist, check freshness first: *"Has anything changed since your context files were last updated?"* If yes → run `/project:pdd-context` before proceeding.

### Workflow transitions

After completing any workflow, suggest the natural next step:

<!-- GENERATED:claude-workflow-transitions:start -->
| Just finished | Suggest next |
|---|---|
| **Scaffold** | -> Context: *"Structure is ready. Want to write `pdd/context/project.md`?"* |
| **Init** | -> Context: *"PDD structure is ready. Run `/project:pdd-context` to fill in your context files; I'll use what I detected as a starting point."* |
| **Context** | -> Research or Plan: *"Context is set. Before writing prompts, want to research the problem space or plan the implementation?"* |
| **Research** - adopt/extend/compose | -> Help install/configure, or create a prompt adapting the solution |
| **Research** - build | -> Plan: *"Nothing existing fits. Let's plan the implementation."* |
| **Plan** | -> Prompts: *"Plan is set. Ready to write the first prompt? Start with Phase 1."* |
| **Prompts** | -> Run the prompt 2 to 3 times, then -> Review: *"Run this prompt, then `/project:pdd-review` to verify and review the output."* For critical prompts, create a Level 1 eval first. |
| **Update** | -> Re-run the prompt, then -> Review: *"Try the updated prompt and run `/project:pdd-review` on the output."* |
| **Review** - issues found | -> Fix code, or -> Update if the prompt needs work |
| **Review** - looks good | -> Commit both prompt and output. -> Eval: *"Consider running `/project:pdd-eval` to track this prompt's quality over time."* |
| **Eval** - passes | -> Level up the eval if 5 or more runs, or continue to next feature |
| **Eval** - fails | -> Update: *"These criteria failed. Fix the prompt first."* |
<!-- GENERATED:claude-workflow-transitions:end -->

---

## General Principles

<!-- GENERATED:claude-principles:start -->
- **One prompt, one job.** Split if multiple concerns.
- **Commit prompts alongside outputs.** The prompt is part of the codebase.
- **Update context after every significant decision.** Stale context degrades future prompts.
- **Timebox experiments.** Name with a date prefix (`YYYY-MM-DD-`). After one week: promote to `pdd/prompts/features/` if it worked, delete if it didn't.
- **Never commit unreviewed output.** Treat it like a PR.
- **Context must reflect reality.** Aspirational `project.md` actively misleads.
<!-- GENERATED:claude-principles:end -->

---

## Common Situations

**"I don't know where to start"** → Ask if they have a project in mind, then Scaffold + Context or define the project first.

**"This is too complicated"** → Start with just `pdd/context/project.md`. Everything else can come later.

**"I'm mid-project and things are messy"** → Init to add PDD structure, then write context files for what exists now. Apply full workflow to new work only.

**"My team doesn't know about PDD"** → Start with `pdd/context/` layer — reads as plain docs, no workflow change required.

**"The prompt didn't work at all"** → Update. Diagnose before rewriting.

**"Is this code ready to commit?"** → Review. Runs automated checks first, then detailed review.

**"How reliable is this prompt?"** → Eval. Track pass rates across runs.

**"Can you just do it for me?"** → Yes — but explain each step so the user learns the pattern.
