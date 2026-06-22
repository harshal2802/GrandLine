# Fix: claude_code provider can't drive voyages (CLI agent ignores the role prompt)

**File**: pdd/prompts/fixes/claude-code-completion-contract.md
**Created**: 2026-06-19
**Project type**: backend (FastAPI + LangGraph multi-agent)

## Context

Running a real voyage with every crew role dialed to the `claude_code`
provider fails immediately at PLANNING. Two distinct failure modes were
observed and reproduced across many runs against the local `claude` CLI
(v2.1.170, model alias `sonnet` → `claude-sonnet-4-6`):

1. **Tool-use under `--max-turns 1`.** The CLI is an *agentic coding tool*,
   not a text-completion API. Given a task that mentions producing files, the
   model reaches for the **Write** tool. Under `--max-turns 1` the tool call is
   denied and the run ends `subtype=error_max_turns`, `is_error=true`,
   exit code 1 with empty stderr. The adapter surfaces this as
   `ProviderError("Claude Code CLI exited with code 1: ")` →
   `RuntimeError: All providers exhausted for role captain`.

2. **Role prompt ignored.** The adapter passes each crew role's instructions
   via `--append-system-prompt`
   ([claude_code.py](src/backend/app/dial_system/adapters/claude_code.py)).
   The CLI's built-in agent system prompt reliably **overrides** the appended
   prompt: instead of the required structured JSON
   (Captain → `{"phases":[...]}`, Shipwright → `{"files":[...]}`), the model
   returns prose, ```python code, or a JSON representation of the *file*
   (`{"filename","content"}`) — none of which the crew parsers
   ([captain_graph.validate](src/backend/app/crew/captain_graph.py),
   [shipwright_graph.generate](src/backend/app/crew/shipwright_graph.py))
   accept. Result: `PLAN_PARSE_FAILED: Expecting value: line 1 column 1`.

Every crew role expects a single JSON object back (the Shipwright wraps
generated source as a string inside the `content` field — it never writes
files itself). `strip_fences`
([crew/utils.py](src/backend/app/crew/utils.py)) only strips one
```` ``` ```` block, so preamble or wrong-schema output is fatal.

### What was measured

A reproduction harness ran the real CLI with the actual `CAPTAIN_SYSTEM_PROMPT`
and `SHIPWRIGHT_SYSTEM_PROMPT`:

| Recipe | Captain (want `phases`) | Shipwright (want `files`) |
|---|---|---|
| `--append-system-prompt` (current) | 0/5 (tool-use / wrong schema) | — |
| `--tools ""` + extra `--append-system-prompt` contract | 0/5 (wrong schema) | 1/3 |
| **Fold role prompt into the user turn + `--tools ""`** | **5/5** | **3/3** |

The CLI weights the **user turn** far more than appended system prompts.
Folding the role instructions into the prompt body, disabling tools, and
adding a short response-format reminder makes the CLI behave as the
completion endpoint the Dial System expects.

## Locked decisions

- **Fold system → user turn.** `_build_prompt` returns the system
  instructions prepended to the conversation body and `system=None`. Stop
  relying on `--append-system-prompt` to carry the role contract.
- **Disable tools.** `_command` always appends `--tools ""` so the model has
  no tools to reach for and answers with text. (Verified: the empty-string
  arg disables all tools; `--disallowedTools` does **not** — the model still
  attempts Write and hits max-turns.)
- **Add a response-format reminder** at the end of the folded prompt: no
  tools, no preamble, no fences, return exactly what the instructions ask
  for; when asked for code, put it in the requested JSON field, never write a
  file. Only added when a system prompt is present (pure single-user / multi-
  turn calls pass through unchanged).
- **Keep `--max-turns` default at 1.** With tools disabled, one turn is a
  clean completion; no need to raise it.
- **Adapter-only change.** Do NOT touch crew prompts, the Dial router,
  guards, or the pipeline graph. The other providers (`anthropic`, `openai`,
  `ollama`) are unaffected — they never used `_build_prompt`/`_command`.
- **Decision log**: append an entry to
  [pdd/context/decisions.md](pdd/context/decisions.md).

## Deliverables

### 1. `app/dial_system/adapters/claude_code.py`

- Add a module-level `_RESPONSE_CONTRACT` string (the reminder above).
- Rewrite `_build_prompt(messages)`:
  - Build the conversation body exactly as today (single user → passthrough;
    multi-turn → `Human:/Assistant:` transcript).
  - If there are **no** system messages → return `(body, None)` (unchanged).
  - If there **are** system messages → return
    `(f"{system}\n\n=== INPUT ===\n{body}{_RESPONSE_CONTRACT}", None)`.
- In `_command(output_format, system)`: append `["--tools", ""]` after the
  `--max-turns`/`--verbose` block and before `--append-system-prompt`/
  `extra_args`. Leave the `if system:` branch in place (harmless; never fires
  now that `_build_prompt` returns `system=None`) so the signature and any
  direct callers keep working.

### 2. Tests: `tests/test_dial_claude_code_adapter.py`

- `test_single_user_message_passes_through` — unchanged (no system → `"Hello"`,
  `system is None`).
- `test_multi_turn_rendered_as_transcript` — unchanged (no system).
- Replace `test_system_messages_extracted` with
  `test_system_message_folded_into_user_turn`: assert `system is None`, and
  that the returned prompt contains `"Be brief."`, the `=== INPUT ===` marker,
  `"Hello"`, and the response-format reminder.
- Update `test_complete_builds_expected_command`:
  - assert `--append-system-prompt` is **not** in `cmd`,
  - assert `--tools` is in `cmd` and the token after it is `""`,
  - assert the folded prompt reached the process: `proc.communicate_input`
    decodes to a string containing both `"Be brief."` and `"Hello"`,
  - keep the `extra_args` ordering assertion (`cmd[-2:] == ["--permission-mode","plan"]`).

### 3. `pdd/context/decisions.md`

Append a decision entry (date 2026-06-19) recording the fold-into-user-turn +
`--tools ""` contract and why `--append-system-prompt` was abandoned for this
provider.

## Test plan

- [ ] `pytest tests/test_dial_claude_code_adapter.py -q` — green.
- [ ] `pytest -q` — full suite green (no regressions).
- [ ] `ruff check app/ tests/` clean; `ruff format` applied.
- [ ] Manual: start a voyage with all roles dialed to `claude_code`
      (`GRANDLINE_DIAL_DEFAULT_PROVIDER=claude_code`, model `sonnet`,
      `GRANDLINE_EXECUTION_GVISOR_RUNTIME=crun`,
      `GRANDLINE_EXECUTION_IMAGE=localhost/grandline-sandbox:py313`) and watch
      it reach PLANNING → PDD → TDD → BUILDING → REVIEWING → DEPLOYING →
      COMPLETED via the SSE stream.

## Constraints

- **Adapter-only.** No changes to crew prompts, dial router, guards, graph,
  or other providers.
- **No new env knobs.** The behavior is intrinsic to the `claude_code`
  adapter (the CLI is always an agent; it always needs this treatment).
- **`extra_args` still honored** and still appended last, so operators can add
  `--permission-mode`, `--add-dir`, etc.
- **No commit or PR until the user signs off.**

## References

- Adapter: [app/dial_system/adapters/claude_code.py](src/backend/app/dial_system/adapters/claude_code.py)
- Dial gateway prompt (original): [pdd/prompts/features/dial-system/grandline-06-llm-gateway.md](pdd/prompts/features/dial-system/grandline-06-llm-gateway.md)
- Crew parsers that require JSON:
  [captain_graph.py](src/backend/app/crew/captain_graph.py),
  [shipwright_graph.py](src/backend/app/crew/shipwright_graph.py),
  [crew/utils.py strip_fences](src/backend/app/crew/utils.py)
- Provider factory: [app/dial_system/factory.py](src/backend/app/dial_system/factory.py)
- Adapter tests: [tests/test_dial_claude_code_adapter.py](src/backend/tests/test_dial_claude_code_adapter.py)
- README provider table (`claude_code`): [README.md](README.md)
