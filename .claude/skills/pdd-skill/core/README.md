# PDD Core

This directory is the canonical home for provider-agnostic PDD content.

## Ownership

- `workflows/` defines the shared workflow intent, expected inputs, outputs, and next-step guidance.
- `references/` contains project-type reference files shared across providers.
- `examples/` contains example PDD project layouts and prompt artifacts.
- `metadata/` contains structured workflow/provider metadata used by verification and future generation tooling.

## Provider Boundary

Provider-specific packaging lives under `providers/`:

- `providers/claude/`
- `providers/copilot/`
- `providers/codex/`

Only `.claude-plugin/` (Claude plugin discovery) and `plugins/pdd-skill` (Codex marketplace) remain as root-level symlinks. All other legacy compatibility links have been removed.
