# PDD Reference: CLI / Developer Tools

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for command-line tools and developer utilities (standalone CLIs, multi-subcommand tools, REPL shells, code generators, and similar programs invoked from a terminal).

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- What language and runtime? (Rust, Go, Node.js, Python, Bash, etc.)
- Argument parsing library? (clap, cobra, yargs, argparse, built-in getopts)
- Is this interactive, non-interactive (piped), or both?
- Target platforms? (macOS, Linux, Windows, all)
- Distribution method? (Homebrew, npm global, cargo install, standalone binary, apt/yum, go install)
- Does it have subcommands (git-style) or is it single-purpose?
- Does it read/write config files? If so, where? (XDG, `~/.toolrc`, platform-specific)
- Plugin or extension system?
- Shell completions needed? (bash, zsh, fish)
- Does it need to work when piped (`tool | grep`, `tool | jq`)?

### Extended `pdd/context/project.md` sections for CLI tools

```markdown
## Command Structure
- Single command or subcommand tree:
- Top-level flags (global options):
- Subcommands (if any): <name — one-line description, for each>

## Arguments and Flags
- Argument parsing library:
- Flag conventions: (GNU long opts, POSIX short opts, both)
- Required vs optional arguments:

## Config
- Config file location: (XDG_CONFIG_HOME, ~/.toolrc, platform-specific)
- Config format: (TOML, YAML, JSON, INI)
- Environment variable overrides: (naming convention, e.g. TOOL_*)
- Precedence order: (flags > env vars > config file > defaults)

## Output
- Human-readable output format:
- Machine-readable output: (JSON, CSV, TSV, none)
- Verbosity levels: (--quiet, default, --verbose, --debug)
- Color strategy: (auto-detect TTY, --color=always/never/auto)

## Distribution
- Installation method:
- Target platforms:
- Update mechanism: (self-update, package manager, manual)
- Shell completion targets: (bash, zsh, fish)
- Man page or built-in help:
```

---

## Conventions Starter (Workflow 2)

```markdown
# CLI Conventions

## Command Interface
- Follow platform conventions: GNU long opts (--flag), POSIX short opts (-f)
- Required arguments are positional; optional behavior is controlled by flags
- Every flag has a long form; common flags also have short forms (-v/--verbose, -h/--help, -q/--quiet)
- --help and --version always work and produce correct output

## Output
- Human-readable output goes to stdout; errors and warnings go to stderr
- No color codes when stdout is not a TTY (respect NO_COLOR env var and --color flag)
- Support --json or structured output mode for machine consumption
- Progress indicators go to stderr so they don't pollute piped output

## Exit Codes
- 0: success
- 1: general runtime error
- 2: usage error (bad arguments, missing required flags)
- Use distinct non-zero codes for distinct failure categories when useful

## Signals and Interrupts
- Handle SIGINT (Ctrl+C) gracefully — clean up temp files, release locks
- Handle SIGTERM for graceful shutdown in containerized environments
- No partial writes — use atomic file operations (write to temp, then rename)

## Config Files
- Respect XDG_CONFIG_HOME on Linux, ~/Library/Application Support on macOS, %APPDATA% on Windows
- Environment variables override config file values; flags override both
- Document every config key in --help or a dedicated config subcommand

## Error Messages
- Include what went wrong, why, and what to do next
- Reference the flag or config key that controls the behavior
- Suggest --help or a specific subcommand when usage is wrong

## Testing
- Test both interactive (TTY) and piped (non-TTY) behavior
- Test exit codes for success, failure, and usage error cases
- Test signal handling (SIGINT cleanup)
- Test cross-platform path handling if targeting multiple OSes
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New subcommand

```markdown
# Prompt: <subcommand-name>

## Task
Add a new subcommand `<tool> <subcommand>` that <does what>.

## Arguments
- Positional: <name — description, for each>
- Flags: <--flag (-f) — description and default, for each>

## Behavior
- <core behavior>
- <edge cases: missing input, invalid values, permission errors>
- Output format: <what stdout looks like, human and --json>
- Exit codes: <0 for success, specific codes for known failures>

## Constraints
- Must work when piped (no interactive prompts unless --interactive is passed)
- Errors to stderr with actionable message
- Respect global flags (--quiet, --verbose, --color)
- Add shell completion hints for the new subcommand and its flags
- Add help text following existing subcommand style

## Output format
- Implementation file(s)
- Unit tests covering happy path, invalid input, and piped usage
- Updated help text and shell completions
```

### Config file support

```markdown
# Prompt: Add config file support

## Task
Add support for reading configuration from <path> in <format> format.

## Config keys
- <key: type — description and default, for each>

## Precedence
1. CLI flags (highest)
2. Environment variables (TOOL_KEY_NAME)
3. Config file
4. Built-in defaults (lowest)

## Constraints
- Create config file on first run with commented defaults (or via `<tool> config init`)
- Validate all config values on load — fail fast with clear error on invalid values
- Support --config <path> to override default config location
- Document every key in --help output or `<tool> config list`

## Output format
- Config loading module
- Config init / list subcommands (if applicable)
- Tests covering: missing file (use defaults), invalid values (clear error), precedence order
```

### Output formatting and piping

```markdown
# Prompt: Add structured output support

## Task
Add --json flag (and/or --format=json|table|csv) to `<tool> <subcommand>` so output works in pipelines.

## Behavior
- Default (TTY): human-readable table/list with colors
- Default (piped / non-TTY): human-readable without colors
- --json: JSON to stdout, one object or array
- --format: explicit format selection overriding auto-detection

## Constraints
- Progress indicators and status messages go to stderr only
- JSON output must be valid — no trailing commas, no mixed stdout
- Respect NO_COLOR env var and --color=always/never/auto
- Exit code is the same regardless of output format
- Column alignment and truncation for table format in narrow terminals

## Output format
- Output formatting module
- Tests: TTY vs non-TTY detection, --json validity, piped usage with head/jq
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Command interface**
- [ ] --help output is complete and follows platform conventions?
- [ ] --version prints correct version and exits 0?
- [ ] Unknown flags produce a clear error and suggest --help?
- [ ] Required arguments validated before any work begins?
- [ ] Flag names consistent with existing commands (no --verbose vs --debug inconsistency)?

**Output and piping**
- [ ] Works correctly when piped (`tool | head`, `tool | jq`, `tool | grep`)?
- [ ] No color codes when output is not a TTY?
- [ ] Respects NO_COLOR environment variable?
- [ ] Errors and progress go to stderr, data goes to stdout?
- [ ] --json output is valid JSON?

**Exit codes and signals**
- [ ] Exit 0 on success, non-zero on failure?
- [ ] Exit 2 on usage error (bad arguments)?
- [ ] Handles SIGINT gracefully — no partial writes, temp files cleaned up?
- [ ] Handles SIGTERM for graceful shutdown?

**Config and environment**
- [ ] Config file location respects platform conventions (XDG / Library / AppData)?
- [ ] Environment variable overrides work correctly?
- [ ] Precedence order correct (flags > env > config > defaults)?
- [ ] Invalid config values produce clear error on startup?

**Cross-platform**
- [ ] Path separators handled correctly (no hardcoded `/` on Windows)?
- [ ] Shell escaping safe across bash, zsh, fish, PowerShell?
- [ ] No platform-specific APIs without feature detection or conditional imports?

**Distribution and help**
- [ ] Shell completions work for bash, zsh, and fish?
- [ ] Man page or equivalent long-form help generated?
- [ ] Installation instructions tested on target platforms?
- [ ] --help text includes examples for common use cases?
