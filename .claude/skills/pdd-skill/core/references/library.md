# PDD Reference: Library / Installable Package Projects

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for library and package projects (npm modules, PyPI packages, Rust crates, Go modules, Ruby gems, and similar distributable code).

**This flavor is composable** — a project can be both a library and another type (e.g., a React component library uses this + `frontend.md`). When combining, this file's constraints take precedence for API surface, versioning, and distribution concerns; the domain flavor takes precedence for implementation patterns.

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- What package ecosystem? (npm, PyPI, crates.io, Go modules, Maven, RubyGems, NuGet)
- What language and minimum runtime version do you support?
- Module formats needed? (ESM, CJS, dual, UMD)
- Does it need to work in multiple environments? (Node, browser, Deno, edge runtimes)
- TypeScript / type strategy? (source in TS, generated `.d.ts`, hand-written stubs)
- Who is the target audience? (other library authors, app developers, beginners)
- Monorepo or single package?
- Current versioning stage? (0.x experimental, 1.x stable, pre-release)
- What's your dependency philosophy? (zero-dep, minimal, batteries-included)
- Does it wrap or extend another library? (plugin, adapter, wrapper)

### Extended `pdd/context/project.md` sections for libraries

```markdown
## Public API
- Exported modules / entry points:
- Design principles: (minimal surface, progressive disclosure, etc.)
- Naming conventions for public APIs:

## Distribution
- Package ecosystem:
- Module formats: (ESM / CJS / dual / UMD)
- Supported environments: (Node >= X, browsers, Deno, edge)
- Bundle size budget:

## Versioning
- Current version:
- Versioning policy: (semver — what counts as breaking)
- Deprecation strategy:

## Types
- TypeScript strategy: (source in TS / generated .d.ts / hand-written stubs)
- Type test tool: (tsd, dtslint, expect-type, none)

## Dependencies
- Policy: (zero-dep / minimal / batteries-included)
- Peer dependencies:
- Maximum acceptable install size:
```

---

## Conventions Starter (Workflow 2)

```markdown
# Library Conventions

## Public API
- Every export is a contract — don't export internal helpers
- Prefer named exports over default exports (better tree-shaking, clearer imports)
- Group related exports in subpath entry points (e.g. `my-lib/utils`, `my-lib/types`)
- No side effects on import — importing the package must not execute code or modify globals

## Naming
- Public functions / classes: camelCase / PascalCase matching ecosystem convention
- Internal helpers: prefixed with underscore or in unexported modules
- File names: match the primary export (e.g. `createClient.ts` exports `createClient`)

## Versioning
- Follow semver strictly
- Breaking changes: removing/renaming exports, changing return types, adding required params
- Non-breaking: adding optional params, new exports, bug fixes, performance improvements
- Document every breaking change in CHANGELOG.md with migration instructions

## Dependencies
- Justify every dependency — what it provides vs. its install size and maintenance risk
- Prefer peer dependencies for anything the consumer likely already has
- Never import from a dependency's internal paths (e.g. `lodash/internal/foo`)

## Error handling
- Throw typed errors that consumers can catch programmatically
- Include error codes or classes — not just message strings
- Document all error types in the API reference

## Testing
- Test the public API, not internal implementation details
- Test across supported runtime versions in CI
- Test both ESM and CJS imports if shipping dual format
- Include integration tests that simulate real consumer usage
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New public API function

```markdown
# Prompt: <functionName>

## Task
Create a public API function `<functionName>` that <does what>.

## Signature
- Parameters: <name: type — description, for each>
- Returns: <type — description>
- Throws: <error type — when>

## Behavior
- <core behavior>
- <edge cases: empty input, null, invalid types>

## Constraints
- Zero side effects — must be a pure function (or clearly documented if not)
- No new dependencies
- Must work in [Node / browser / both — match project scope]
- Export from <entry point>
- Include JSDoc / docstring with @param, @returns, @throws, @example

## Output format
- Implementation file
- Type definitions (if separate from source)
- Unit tests covering happy path, edge cases, and error cases
- No test file scaffolding — full passing tests
```

### Breaking change / major version update

```markdown
# Prompt: Migrate <old API> to <new API>

## Task
Replace `<old function/type/export>` with `<new version>` in a backward-incompatible way.

## Changes
- <what changes and why>

## Migration path
- Provide a CHANGELOG entry describing the break
- Provide a migration guide: before/after code examples
- If feasible, provide a codemod or deprecation warning in the current minor version first

## Constraints
- Update all internal usages
- Update type definitions
- Update tests to use new API
- Remove old API completely (no re-export shims)
```

### New subpath entry point

```markdown
# Prompt: Add <subpath> entry point

## Task
Create a new subpath export at `<package-name>/<subpath>` that exposes <what>.

## Exports
- <named exports this entry point provides>

## Constraints
- Update package.json `exports` map
- Ensure tree-shaking works — no shared side-effect modules between entry points
- Add TypeScript types for the subpath
- Test that `import { x } from '<package>/<subpath>'` works in both ESM and CJS
- Document the new entry point in README
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**API surface**
- [ ] Only intended symbols exported? No internal helpers leaking?
- [ ] Naming consistent with existing public API?
- [ ] Backward compatible with current major version? (if not, is this intentional?)
- [ ] JSDoc / docstring present on all public exports?
- [ ] No required parameters added to existing functions?

**Distribution**
- [ ] Package loads correctly via ESM import?
- [ ] Package loads correctly via CJS require? (if dual format)
- [ ] `exports` map in package.json is correct and complete?
- [ ] Type definitions accurate and tested?
- [ ] No side effects on import?
- [ ] Tree-shaking works — unused exports eliminated by bundlers?

**Dependencies**
- [ ] No new dependencies without justification?
- [ ] No imports from dependency internal paths?
- [ ] Peer dependencies declared correctly?
- [ ] Total install size within budget?

**Compatibility**
- [ ] Works across all supported environments (Node versions, browsers)?
- [ ] No environment-specific globals without feature detection (e.g., `window`, `process`)?
- [ ] No Node built-in imports in browser-targeted code?

**Versioning**
- [ ] Version bump matches change type (patch/minor/major)?
- [ ] CHANGELOG updated?
- [ ] Breaking changes documented with migration guide?

**Consumer experience**
- [ ] Error messages actionable — include what went wrong and how to fix it?
- [ ] TypeScript autocomplete works correctly for the new API?
- [ ] README / API docs updated for new or changed exports?
