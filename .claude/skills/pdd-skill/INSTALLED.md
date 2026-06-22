# pdd-skill (vendored)

Vendored from **[harshal2802/pdd-skill](https://github.com/harshal2802/pdd-skill) @ v1.5.0**.

Trimmed to the Claude Code surface only — `providers/claude/` (skill, slash
commands, hooks, plugin manifests) and `core/` (shared workflows, references,
metadata). The Copilot/Codex/Antigravity adapters, `docs/`, `tests/`, and build
scripts were removed; `LICENSE` (MIT) is retained.

**Wired via** `.claude/settings.json`:
`providers/claude/skills/pdd/SKILL.md`

**To update:** re-clone upstream at the new tag and re-apply this same trim, or
switch to the plugin route (`/plugin marketplace add harshal2802/pdd-skill`
→ `/plugin install pdd-skill`) for upstream-managed updates.
