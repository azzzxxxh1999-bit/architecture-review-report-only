# Audit Standard (canonical)

This is the fixed rubric. Every module audit must follow it verbatim so scores are
comparable across modules, runs, and projects. Do not improvise scoring.

## Scoring rubric (0–100) → grade

| Score | Grade | Meaning |
|------:|:-----:|---------|
| 90–100 | A | Clean, well-scoped, idiomatic. No material smells. |
| 75–89 | B | Minor issues: a documented shim, mild bloat, a localized cast. |
| 60–74 | C | Notable hacks/fallbacks, real bloat, or duplication that has a clear owner. |
| 40–59 | D | Significant legacy/stubs/duplication, or a dual-format/protocol violation. |
| 0–39 | F | Broken, fake output, or an unfinished feature wired in as if done. |

Be rigorous and evidence-based, not generous. A module with one HIGH finding rarely
scores above 60; with only LOW findings it usually scores 80+.

## Machine-enforced semantic invariants

`scripts/audit_contract.py` is the single executable owner of this rubric's hard
semantics. `apply_audit.py`, publish preflight and retained-history verification must call
that shared contract rather than reimplementing checks. At minimum it enforces:

- `score` is a real integer from 0 through 100 (a boolean is not a score), and `grade`
  exactly matches the table above;
- every tag exists in the effective standard; `clean` is exclusive, has no findings,
  and is incompatible with a materially low score;
- every negative tag has concrete finding evidence, and each finding has a valid
  severity, location and non-empty explanation;
- `auditedHash` identifies the exact current `contentHash` at publish time;
- a publishable audit has the complete module/dependency graph, exactly eight canonical
  dimensions, exactly four lenses, and the evidence required by this standard.

A project `standard.json` may add valid taxonomy tags and descriptions, but it cannot
remove these invariants. A semantic failure is a hard rejection: no partial mutation,
version allocation or retained promotion is allowed.

## Maintainability claim invariants

Module grades and project maintainability are different contracts. The executable owner
of claim wording is `scripts/maintainability_gate.py`, configured by
`maintainabilityClaims` in the effective standard.

- A DELTA or named module scope may return `SCOPED_PASSED`, never
  `PROJECT_MAINTAINABLE`. `SCOPED_PASSED` always carries
  `projectClaimAllowed=false`.
- The scoped hard floor is 75. Core/high/spine modules in scope have an 80 hard target,
  not a recommendation. Scoped evidence must retain `focused-tests:pass`,
  `independent-acceptance:pass`, and `architecture-scope:pass`.
- A project claim requires the active retained audit mode to be `full`, every module to
  be fresh and at least 75, core/high/spine modules to be at least 80 with no `MED`, no
  `HIGH` anywhere, no material unfinished runtime, and no `risk`/`unknown` dimension.
- Project evidence must retain `build-parse:pass`, `critical-regression:pass`,
  `false-green:pass`, and `ci:pass`; Git and a recognized CI configuration must exist.
- Missing, stale, skipped, ignored, or unretained evidence is failure. An average score,
  a green local module, or a DELTA pass cannot compensate for one failed hard condition.

The only whole-project passing status is `PROJECT_MAINTAINABLE`; every failed or
incomplete whole-project evaluation is `PROJECT_REWORK_REQUIRED`.

A project `.codemap/standard.json` may add required gates, forbidden statuses, unfinished
tags, or raise score thresholds. It cannot rename passing/failing statuses, remove a
default requirement, or lower either score threshold; the gate merges project settings
over the defaults monotonically and keeps the stricter value.

## Smell taxonomy (the `tags`)

Use these exact tag strings. `clean` is the only positive tag; the rest are negative
Findings are grouped by severity and counted in the Markdown report.

- `monkeypatch` — runtime mutation of another module / stdlib / vendor; `setattr` on
  foreign objects; `sys.modules` / `sys.meta_path` surgery; reassigning store actions.
- `fallback` — "try the real thing, then fake/degrade"; chained `a || b || c` /
  `a ?? b` defaults that hide which value is real.
- `silent-except` / `silent-catch` — `except: pass`, bare `except`, empty `catch {}`
  that swallow errors with no log/signal.
- `legacy` — deprecated/back-compat shims, retired vocabulary, dead-but-shipped code,
  parallel "old + new" code paths kept side by side.
- `dual-format` — accepting both snake_case and camelCase (or two payload shapes) for
  the same field; the classic `display_name || displayName` patch.
- `stub` / `placeholder` — `NotImplemented`, `TODO: implement`, dead buttons, demo
  scripts, hardcoded sample data presented as real.
- `fake-output` — returns random/canned/hardcoded results where real computation is implied.
- `duplication` — logic copy-pasted from a sibling or that an existing shared
  abstraction already covers.
- `bloat` / `god-component` — oversized file/function; many responsibilities in one unit.
- `glue` — thin, valueless pass-through / boilerplate forwarding: rows of one-line
  wrappers that only forward args to another layer (e.g. dozens of `send({type:...})`
  methods), an adapter that copies a payload field-for-field without transforming, a
  store/function that only re-exports or delegates to another. The indirection earns
  nothing. Distinct from `bloat` (size) and `duplication` (copy-paste): glue is about
  forwarding that adds no value.
- `any-escape` — `as any`, `@ts-ignore`, untyped boundaries used to bypass the type system.
- `over-fit` — hardcoded to one case where a small generalization was expected.
- `clean` — no material issues.

### The taxonomy is language-agnostic — recognize the per-language form

The tags name *behaviors*, not syntax. Map each to whatever the target language does:

| tag | Python | TS / JS | C# / .NET | Rust | C / C++ |
|---|---|---|---|---|---|
| `any-escape` | `# type: ignore`, `Any` | `as any`, `@ts-ignore`, `!` | `dynamic`, `object` casts, `#nullable disable` | `unsafe`, `transmute`, blanket `.unwrap()` | `void*`, `reinterpret_cast`, C-style casts |
| `silent-except` | `except: pass` | empty `catch {}` | `catch (Exception) {}` | `let _ = x;`, `.ok()`, `unwrap_or_default` to hide | empty `catch`, ignored return codes / `errno` |
| `monkeypatch` | `setattr`, `sys.modules` | prototype patching, global override | reflection / Harmony patching | macro / `static mut` hacks | `#define` overrides, weak-symbol swap |
| `dual-format` | `a or b` (snake/camel) | `a ?? b`, `a \|\| b` | nullable + alias props | `Option` chains for two shapes | overloads accepting two layouts |
| `fallback` | try real then stub | `try/catch` → canned data | `try/catch` fallback | `unwrap_or(fakeDefault)` | `#ifdef` to fake impl |

`legacy`, `stub`, `fake-output`, `bloat`, `god-component`, `duplication`, `glue`,
`over-fit` are the same idea in every language. Build / test / generated files are out of
audit scope — the module `paths` globs plus `scan.py` excludes handle that across stacks
(`target/`, `bin/`, `obj/`, `node_modules/`, `__pycache__/`, `dist/`, …).

Judgement rules:
- A *documented, bounded* compat shim that deliberately refuses to silently coerce is
  `legacy` at most LOW — do not over-penalize disciplined shims.
- A fallback that is a real security control or numeric guard (e.g. identity matrix on
  singular input, stripping untrusted shaders) is **not** a smell.
- Native-dependency gating that *raises or returns an error* when a lib is missing is
  correct; only `fake-output` if it silently returns fabricated data.
- A `*Placeholder` name is not automatically a stub — read it; it may be a finished
  read-only widget.
- A *single* thin delegator, or a genuine boundary normalizer that converts/validates
  once, is fine — not `glue`. Flag `glue` only when pass-through wrappers **proliferate**
  (many near-identical forwarders that should be collapsed, generated, or replaced by a
  generic dispatch) or an adapter forwards with no transformation. Usually MED when it
  proliferates, LOW for a one-off.

## Severity (each finding)

- `HIGH` — wrong/dangerous/fake, a protocol or security issue, or a god-file that is a
  genuine maintenance hazard.
- `MED` — a real smell a maintainer should fix: a live dual-format patch, an un-migrated
  duplicate, an unfinished-but-wired path.
- `LOW` — a documented shim, a cosmetic cast, benign bloat. Worth noting, not urgent.

Always cite `file:line` and quote/paraphrase the offending snippet. Never report a
grep hit as a problem without reading the surrounding code.

## Four-lens / eight-dimension architecture classification

Module quality scores and architecture-dimension results are related but not
interchangeable. A clean module can still participate in a bad dependency direction;
a low-scoring leaf need not create a system-wide boundary risk. Keep the existing
per-module scoring protocol unchanged, then synthesize these eight evidence-backed
architecture dimensions:

| Lens | Dimension | Judge this | Typical evidence |
|---|---|---|---|
| 分 | `responsibility` | one coherent reason to change; no God Object | responsibilities, public surface, file/class size, unrelated change reasons |
| 分 | `boundary` | UI, combat, persistence, and data do not write through each other | cross-layer writes, internal-state access, global-singleton calls |
| 连 | `contract` | stable interfaces, events, DTOs/snapshots, contract tests | typed APIs, signals/events, Dictionary/has_method/dynamic dispatch |
| 连 | `dependency` | no cycles, reversed layers, or uncontrolled blast radius | dependency edges, fan-in/out, cycles, lower-to-upper dependencies |
| 变 | `data_logic` | new content uses data through one stable extension point | catalog/resource coverage, hardcoded branches, registration sites |
| 变 | `composition_state` | complex behavior is composed and stateful, not condition sprawl | state machines, components, strategies, branch complexity, inheritance depth |
| 变 | `evolution` | old data upgrades through stable IDs and real migrations | schema version, migration steps, compatibility reads, transactions, rollback |
| 保 | `safeguards` | regressions can be detected, traced, and recovered | tests, Git, CI, docs, retained audits, snapshots, backups, rollback proof |

Dimension status is one of `good`, `warning`, `risk`, `unknown`:

- `good`: current evidence supports a healthy boundary.
- `warning`: localized coupling or evolution cost exists but is not yet systemic.
- `risk`: evidence shows cross-domain ownership, uncontrolled dependency, unsafe
  migration, or materially weak recovery.
- `unknown`: the dimension was not checked, evidence is insufficient, or tooling cannot
  decide. Unknown is never treated as good.

Do not create a dimension score from the number of findings. Leave `score: null` unless
the project's `standard.json` defines a repeatable dimension rubric. Every `warning` or
`risk` needs at least one current evidence item and a primary dimension. The same evidence
may be referenced elsewhere, but it must not be counted twice. A missing cycle, a tests
folder, a schema version, or a large file is not by itself proof of health or failure.

## Independent-subagent protocol (REQUIRED)

Every module's score MUST be produced by a separate sub-task, never inline in the main
thread, and never reused across modules. The default is one sub-task per module, run in
parallel. **Token-saving exception:** several *small, low-risk* modules (≤ ~150 LoC, or
low-coupling leaves) MAY share one sub-task **only if** it audits each independently and
returns a separate, evidence-backed result per module (this is not batch-scoring — it is
several independent audits sharing one context to amortize overhead). Core / high-coupling
/ large modules always get their own sub-task. The audit is a constrained read-and-grade
task, so run these sub-tasks on the **cheapest capable model**; the strict `apply_audit.py`
validation plus this rubric catch weak output. Reserve the top model for decomposition,
theme synthesis, and fixes.

### Subagent prompt template

> You are auditing CODE QUALITY of ONE functional module for an architecture audit.
> Module: **{label}** (`{id}`). Files: {paths}. Project root: {root}.
>
> Read EFFICIENTLY — do not read whole large files. First grep the smell markers below
> across {paths}; skim each file's structure (sizes, top-level defs); then READ ONLY the
> flagged regions plus enough context to judge them (never flag a grep hit you haven't
> read). For a big file, the line count + a few representative excerpts are usually enough
> to score bloat/god-component. Judge it against this rubric:
> {paste the "Scoring rubric", "Smell taxonomy", "Severity" sections above}
>
> Hunt specifically for: monkeypatch / stdlib mutation, fallback chains & silent
> excepts, legacy/deprecated/back-compat shims, dual-format (snake||camel) handling,
> stubs / fake output / unfinished-but-wired code, bloat/god-files, duplication of
> logic that exists elsewhere, thin valueless glue (proliferating pass-through wrappers
> / no-op adapters), and over-fitting. Also state whether the module is appropriately
> generic.
>
> Return ONLY this JSON (no prose):
> {"score": <0-100>, "grade": "<A|B|C|D|F>",
>  "tags": ["<from the taxonomy>", ...],
>  "findings": [{"sev":"HIGH|MED|LOW","loc":"file:line","text":"concrete issue + evidence"}, ...]}
> If clean, use tags ["clean"] and findings []. Be rigorous, not generous.

Use `schema` on the Agent call to force that JSON shape when available. Then feed each
result to `scripts/apply_audit.py --id <id> --json '<result>'`.

## Test-author protocol (the `test` command + the baseline step of `fix`)

A dedicated **test-author subagent** generates tests for a module. It is separate from
the auditor, fixer, and verifier.

- **Detect, don't invent.** Find the repo's test framework and location from existing
  tests near the module (pytest / jest / vitest / go test / …); match their style and
  placement. Never introduce a new framework or harness.
- **characterization mode** (default before a fix): capture the module's CURRENT
  observable behavior — inputs→outputs, side effects, payload shapes — as assertions of
  "same as today", not "correct". Target the public surface; don't pin private internals.
  Use snapshot/golden tests only where the repo already does.
- **coverage mode**: cover the public API and the specific behaviors named in the
  module's `findings`. Aim for meaningful branches, not line count.
- **Must be GREEN on the current, unmodified code before returning.** If a test you want
  to write fails because of a real bug, FLAG it as a finding — do not assert the buggy
  output as if it were the desired behavior.
- Tests are real, committed source (the regression net); never delete or weaken them to
  move a number.
- Return JSON: `{"framework":"...","files":["..."],"locked":"<behaviors locked>",
  "gaps":"<what is still uncovered>","flagged":[{"sev":"...","loc":"...","text":"..."}]}`.

## Acceptance / regression gate (the gate in `fix`)

An **acceptance/verifier subagent**, independent of the fixer, proves a fix introduced no
regression. It does NOT score quality — pass/fail only.

- Re-run the EXACT baseline test set captured before the fix (same commands), plus the
  narrowest build/typecheck for the touched area.
- **PASS iff** every test that was green before is green after, AND no new build / type /
  lint errors appeared. A baseline-green test that is now failing, errored, skipped,
  deleted, or flaky counts as a regression → FAIL (you cannot remove a test to pass).
- New tests the fixer may have added are ignored (and the fixer should not add any).
- Return JSON: `{"pass": <bool>, "ran": "<commands>",
  "regressions": [{"test":"...","was":"pass","now":"fail|error|missing","evidence":"..."}],
  "evidence": "<short summary>"}`.
- **Gate rule:** no PASS → no re-audit and no rendered score improvement. Report the
  failure with evidence; revert or hand back to the fixer.

## Cross-cutting themes

After all modules are scored, the orchestrator (main thread) writes 4–7
`reportThemes` into `modules.json` — patterns seen across modules (e.g. "dual-format
recurs in N handlers", "duplication between X and Y", "stub backend wired live"). Each
is `[headline, body]`. These are synthesis, not per-module scoring, so the main thread
writes them.
