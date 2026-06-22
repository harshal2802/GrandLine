# PDD Reference: Compiler / Language Tooling

> **Last reviewed**: 2026-03

Use this file to enrich Workflows 2, 3, and 5 for compiler and language tooling projects — compilers, interpreters, transpilers, linters, formatters, LSP servers, and other language infrastructure.

---

## Additional Context Questions (Workflow 2)

Ask these after the base questions in `project.md`:

- What are you building (compiler, interpreter, transpiler, linter, formatter, LSP server)?
- Source language being processed (existing language or new DSL)?
- Target (machine code, bytecode, another language, AST-only)?
- Implementation language (Rust, OCaml, Haskell, TypeScript, Go, C)?
- Parser approach (hand-written recursive descent, parser combinator, PEG, parser generator)?
- Type system (none, simple, Hindley-Milner, dependent types)?
- Is incremental parsing/analysis needed (for IDE integration)?
- LSP support planned?
- What error reporting quality is expected (bare minimum vs Elm/Rust-level diagnostics)?

### Extended `pdd/context/project.md` sections for compiler / language tooling

```markdown
## Pipeline Stages
- Stages: (lex → parse → desugar → type-check → optimize → emit — which subset)
- Source language: (existing language, subset, or new DSL)
- Target: (machine code via LLVM/Cranelift, bytecode, another language, AST-only for tooling)
- Entry points: (file, REPL, stdin, LSP)

## AST / IR Design
- AST node types: (expression, statement, declaration, pattern, type — enumerate top-level kinds)
- IR levels: (AST → HIR → MIR → LIR, or AST-only — how many lowerings)
- Node identity: (arena-allocated with IDs, tree of owned nodes, reference-counted)
- Visitor/traversal pattern: (visitor trait, fold, manual match, zipper)
- Mutability: (immutable AST with transformations returning new trees, or mutable in-place)

## Source Location Tracking
- Span representation: (byte offsets, line:column pairs, interned file + offset range)
- Span storage: (inline in AST nodes, side table keyed by node ID, both)
- Source maps: (generated for transpiler output? format — v3 source maps, DWARF, custom)
- Multi-file support: (how spans reference files — file ID, path, interned string)

## Type System
- Type system kind: (none, simple type checking, Hindley-Milner inference, bidirectional, dependent)
- Type representation: (enum of types, interned type IDs, structural or nominal)
- Inference approach: (unification, constraint solving, local inference only)
- Generics/polymorphism: (parametric, ad-hoc/traits, both, none)
- Error reporting: (expected vs found, type mismatch context, suggestion for fixes)

## Error Recovery Strategy
- Lexer recovery: (skip to next valid token, insert synthetic token, best-effort tokenize)
- Parser recovery: (synchronize on statement boundaries, panic mode, error productions)
- Type checker recovery: (infer error type, continue checking other expressions, skip dependent checks)
- Goal: (report multiple errors per file, not just the first one)
- Error message format: (snippet with underline, primary + secondary labels, fix suggestions)

## Incremental Compilation
- Incremental unit: (file, function, expression, statement)
- Cache strategy: (salsa/query-based, file-level memoization, manual dependency tracking)
- Invalidation: (what triggers recomputation — file change, type change, signature change)
- IDE integration: (cancel in-flight computation on new edit, prioritize open file)

## LSP Capabilities
- Diagnostics: (real-time error reporting, warning levels)
- Completion: (keyword, identifier, type-aware, snippet)
- Hover: (type information, documentation, signature)
- Go-to-definition: (cross-file, cross-module)
- Find references: (identifier, type, trait implementation)
- Rename: (scoped, cross-file, preview changes)
- Code actions: (quick fixes, refactors)
- Formatting: (full document, range, on-type)

## Test Corpus Structure
- Valid programs: (one file per language feature, combinatorial edge cases)
- Invalid programs: (one per error kind, expected error message or code)
- Edge cases: (deeply nested, empty input, Unicode, maximum token length, pathological inputs)
- Snapshot testing: (AST snapshots, error message snapshots, output snapshots)
- Conformance: (external test suite if processing an existing language)
```

---

## Conventions Starter (Workflow 2)

```markdown
# Compiler / Language Tooling Conventions

## Pipeline Architecture
- Each pipeline stage is a pure function: input IR in, output IR out — no global mutable state
- Stages are independently testable — test the lexer without the parser, the parser without the type checker
- Errors are collected, not thrown — every stage returns results + diagnostics, never panics on invalid input
- Source spans flow through the entire pipeline — every AST node, every IR node, every diagnostic has a span

## Parsing
- Hand-written recursive descent unless there's a strong reason for a generator — it's easier to debug and gives better error messages
- Error recovery is not optional — the parser must produce a partial AST and report multiple errors per file
- Never panic or crash on any input — fuzz the parser from day one
- Operator precedence via Pratt parsing — don't nest recursive descent calls for precedence levels
- Tokenizer is separate from parser — tokens carry spans, parser consumes tokens

## AST Design
- AST nodes are data, not behavior — keep traversal and transformation separate from node definitions
- Every node carries a source span — no exceptions, no "unknown" spans in production
- Use typed enums/variants for node kinds — not stringly-typed or generic "Node" with a kind field
- Arena allocation for nodes when performance matters — avoid deep tree ownership hierarchies
- AST is immutable after construction — transformations produce new trees (or new arenas)

## Type System
- Types are interned (deduplicated) — compare by ID, not by structure
- Type errors show expected vs found with source context — not just "type mismatch"
- Inference variables are scoped and resolved — no dangling unification variables escape the checker
- Unknown/error types propagate without cascading errors — one mistake shouldn't produce 50 diagnostics
- Type-level operations are total — no infinite loops in type normalization or unification

## Error Reporting
- Errors are user-facing documentation — write them like you're helping someone fix their code
- Every error has a primary span (underlined), optional secondary spans (labeled), and an optional fix suggestion
- Error messages never expose internal compiler state (node IDs, IR details, stack traces)
- Warnings are only emitted for things the user can and should fix — no noise
- Error codes are stable and documented — users and tools can reference them

## Incremental and IDE Integration
- Parsing and analysis must support cancellation — an edit invalidates in-flight work
- Cache/memoize at natural boundaries (file, function, top-level item) — avoid recomputing the world on every keystroke
- LSP responses target < 200ms for diagnostics on typical files — measure and optimize
- Separate "fast path" (syntax-only, for highlighting and basic errors) from "slow path" (full type checking)

## Testing
- Snapshot tests for AST output, error messages, and codegen output — review diffs, not just pass/fail
- Every error path has a test — if the compiler can produce an error, there's a test that triggers it
- Fuzz testing for the lexer and parser — any input must not crash, regardless of validity
- Property-based tests where applicable — parse(pretty_print(ast)) == ast
- Test corpus is organized by language feature, not by compiler phase
```

---

## Common Feature Prompt Patterns (Workflow 3)

### New language feature (lexer through codegen)

```markdown
# Prompt: <FeatureName> language feature

## Task
Implement the <feature> (e.g., pattern matching, string interpolation, async/await) from lexer through codegen.

## Syntax
- Grammar: <EBNF or informal description of the new syntax>
- Examples: <3-5 examples of valid usage>
- Invalid cases: <2-3 examples that should produce specific errors>
- Interaction with existing features: <how this composes with existing syntax>

## Lexer Changes
- New tokens: <list new token kinds, if any>
- Tokenization edge cases: <ambiguities, context-sensitive lexing>

## Parser Changes
- New AST nodes: <node types, fields, span tracking>
- Precedence and associativity: <where this fits in the expression hierarchy>
- Error recovery: <how to recover from malformed <feature> syntax>
- Error messages: <expected messages for common mistakes>

## Type Checker Changes (if applicable)
- Type rules: <how types are checked or inferred for this feature>
- New type constructs: <if any — new types, constraints, or bounds>
- Error messages: <type errors specific to this feature>

## Codegen / Lowering (if applicable)
- Target representation: <how this feature lowers to the target IR or output>
- Desugaring: <if this feature is syntactic sugar — what it desugars to>

## Constraints
- Source spans must be accurate on all new AST nodes
- Error recovery must allow continued parsing after a malformed <feature>
- No regressions on existing test corpus
- Must handle edge cases: empty bodies, nested usage, interaction with <existing feature>

## Output format
- Token definitions (if new)
- AST node types
- Parser implementation with error recovery
- Type checking rules (if applicable)
- Codegen/lowering (if applicable)
- Test cases: valid inputs, invalid inputs with expected errors, edge cases
- Snapshot updates for affected tests
```

### LSP capability

```markdown
# Prompt: LSP <Capability> support

## Task
Implement LSP <capability> (e.g., completion, hover, go-to-definition, rename, code actions) for the language server.

## Capability Design
- Trigger: <what user action triggers this — cursor position, keystroke, explicit request>
- Scope: <what language constructs this applies to — identifiers, types, imports, keywords>
- Data needed: <what analysis results are required — resolved names, types, scopes>

## Behavior
- Response content: <what the LSP returns — completion items, hover markdown, location, edits>
- Sorting/filtering: <how results are ranked or filtered — by scope, by type, by relevance>
- Edge cases: <cursor in comment, cursor in string literal, incomplete expression, error recovery AST>

## Performance
- Target latency: <e.g., < 100ms for completions, < 200ms for diagnostics>
- Caching: <what can be cached between requests — scope resolution, type info>
- Cancellation: <how to handle a new request arriving before the current one completes>

## Constraints
- Must work on files with errors — use error recovery AST, not just valid programs
- Must not block on full type checking if only syntax info is needed
- Must handle multi-file projects (cross-file references)
- Response format must conform to LSP specification exactly

## Output format
- LSP handler implementation
- Analysis/query functions the handler depends on
- Integration with incremental compilation cache
- Tests: valid programs, programs with errors, edge cases, multi-file scenarios
- Manual test instructions for VS Code (or target editor)
```

### Error reporting improvement

```markdown
# Prompt: Improve error reporting for <ErrorKind>

## Task
Improve the diagnostic quality for <error kind> (e.g., type mismatches, unresolved names, syntax errors) to match Elm/Rust-level helpfulness.

## Current State
- Current error message: <paste the current output>
- What's wrong with it: <too terse, no context, wrong span, cascading errors>

## Target Quality
- Primary message: <one-line summary — what went wrong>
- Primary span: <underline the exact source location>
- Secondary labels: <additional context — "expected type defined here", "first used here">
- Help text: <actionable suggestion — "did you mean X?", "try adding Y">
- Error code: <stable code for documentation reference>

## Implementation
- Diagnostic construction: <where in the pipeline this error is produced>
- Data needed: <what additional context is needed — expected type, candidate names, declaration site>
- Cascading prevention: <how to suppress downstream errors caused by this one>

## Constraints
- Must not regress other error messages
- Spans must point to the correct source locations
- Suggestions must be syntactically valid if applied
- Error code must be stable across compiler versions

## Output format
- Updated diagnostic construction
- Snapshot test updates showing the new error output
- Tests: trigger the error in various contexts, verify span accuracy, verify suggestion validity
```

---

## Review Checklist (Workflow 5)

Apply in addition to the universal review dimensions:

**Parsing correctness**
- [ ] Parses all valid inputs in the test corpus correctly?
- [ ] Produces a partial AST (not a crash) on all invalid inputs?
- [ ] Error recovery allows continued parsing — reports multiple errors per file?
- [ ] No panics or stack overflows on any input (including deeply nested, empty, and pathological)?
- [ ] Tokenizer handles Unicode identifiers, escape sequences, and string edge cases?
- [ ] Operator precedence and associativity are correct?

**AST and IR quality**
- [ ] Every AST node carries an accurate source span?
- [ ] AST round-trips correctly (pretty-print → re-parse → same AST)?
- [ ] Node types are specific (typed enums), not generic or stringly-typed?
- [ ] Visitor/traversal pattern is consistent across all node kinds?
- [ ] No unnecessary allocations or deep cloning in tree transformations?

**Type system** (if applicable)
- [ ] Type checker accepts all valid programs in the corpus?
- [ ] Type checker rejects all invalid programs with clear, located error messages?
- [ ] Type errors show expected vs found with source context?
- [ ] Error types propagate without cascading diagnostics?
- [ ] Inference variables are fully resolved — no dangling unification variables?
- [ ] Type-level operations terminate (no infinite loops in normalization)?

**Error reporting**
- [ ] Every error has a primary span pointing to the correct source location?
- [ ] Error messages are user-helpful — no internal compiler state exposed?
- [ ] Fix suggestions (if any) are syntactically valid when applied?
- [ ] Warning-level diagnostics are actionable — no noise?
- [ ] Error codes are stable and documented?

**Incremental and performance** (if applicable)
- [ ] Incremental re-parse/re-check is faster than full reprocessing?
- [ ] LSP diagnostics appear in < 200ms for typical files?
- [ ] In-flight computation is cancellable on new edits?
- [ ] Memory usage scales linearly (not quadratically) with input size?
- [ ] No performance regression on the benchmark corpus?

**LSP integration** (if applicable)
- [ ] LSP responses conform to the specification exactly?
- [ ] Capabilities work on files with errors (error recovery AST)?
- [ ] Cross-file features work (go-to-definition, find references)?
- [ ] Completions are relevant and properly sorted/filtered?
- [ ] Rename handles all references across files?

**Testing**
- [ ] Every new language feature has valid and invalid test cases?
- [ ] Every error path is covered by at least one test?
- [ ] Snapshot tests updated and reviewed (AST output, error messages, codegen)?
- [ ] Fuzz testing covers the lexer and parser?
- [ ] Property-based tests where applicable (parse ∘ pretty-print = identity)?
