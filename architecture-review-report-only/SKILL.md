---
name: architecture-review-report-only
description: >-
  当前免费版副本：Review a codebase's architecture with deterministic scanning, independent
  per-module quality scores, evidence-backed findings, and a retained Markdown
  audit history. Use for 架构审查, coupling analysis, code-quality scores,
  staleness checks, or incremental refreshes. This
  copy is the explicit free user-facing edition and provides the Chinese report
  dashboard plus the free module-map projection.
  Do not invoke it for standalone single-module repairs or merely because ordinary
  website or game files changed.
---

# 架构审查 Skill — 免费开源版

> **版本定位：免费开源版。** 面向用户提供中文结论仪表盘与免费模块图；
> 不提供方案选择、本机 AI 桥接、规划执行或修复进度。默认架构审计入口是
> `architecture-review-plus`；它提供独立的 Plus 修复能力。

This free, report-focused edition preserves the architecture audit contract and
immutable version lifecycle while producing a Chinese dashboard and module map.
It contains no source-repair entry point.

## Outputs

`<project>/.codemap/modules.json` is the mutable source of truth. Each functional
module records paths, dependencies, coupling, LoC, content hash, score, grade,
tags, and evidence-backed findings. The generated report is
`<project>/.codemap/codemap.md` by default. Retained versions live under
`<project>/.codemap/versions/audit-vNNNN/` and contain the state, report,
standard, source snapshot, delta, manifest, and semantic receipt.

## When To Use

`software-engineering` remains the generic engineering entrypoint. Enter this
skill only for an explicit architecture review, an app/website/game milestone or
release review, a coupling/maintainability request, or a high-impact boundary
that focused verification cannot safely cover. Ordinary prototypes, small
features, and localized fixes stay outside this skill.

单模块修复不触发本 Skill，且本 Skill 不调用规划器、执行器或任何本机 Agent。

`client/plus_client.py` 是独立的可选 Plus 连接器，不属于免费审计流程；它不会上传源码，
也不会携带 Plus Skill、方案算法或服务端密钥。

For a triggered website/game review:

1. Run `scripts/version.py status --root <project>`.
2. Run a full `init` workflow when there is no prior state/version; otherwise
   refresh changed modules and affected consumers.
3. Run `scripts/maintainability_gate.py` after every scored audit.
4. Publish an immutable version and run `scripts/version.py verify --root <project>`.
5. Open the post-audit dashboard with `scripts/version.py publish --open-dashboard` (or run
   `scripts/dashboard.py --open` after an existing audit).
6. Open the generated Chinese dashboard or module map for the user.

Read [reference/VERSIONING.md](reference/VERSIONING.md) for retention and drift
rules. A no-delta review does not allocate a version.

## Workflow Rules

- Read [reference/STANDARDS.md](reference/STANDARDS.md) and
  [reference/DATA_MODEL.md](reference/DATA_MODEL.md) before scoring.
- Every module score comes from an independent audit result against the fixed
  rubric. Never batch-copy scores or grade inline in the main thread.
- Scripts are deterministic. `scan.py` owns LoC, hashes, and freshness;
  `apply_audit.py` owns audit facts; `render.py` only projects state to Markdown.
- Hand-edit only decomposition fields in `modules.json`; audit facts enter via
  `apply_audit.py` and its semantic contract.
- Treat missing evidence as unknown or failure. Never weaken the rubric, hide a
  finding, or claim project-wide maintainability from a scoped pass.
- `.codemap/` is excluded from the audited source set. Do not delete or rewrite
  retained versions.

## Commands

All scripts use Python 3 stdlib only. `SKILL_DIR` is this skill directory.

```text
python SKILL_DIR/scripts/scan.py --root <project> --state <state> --write
python SKILL_DIR/scripts/query.py --state <state> --max-grade C --format ids
python SKILL_DIR/scripts/apply_audit.py --state <state> --id <id> --json '<result>'
python SKILL_DIR/scripts/render.py --state <state> --out-md <report>
python SKILL_DIR/scripts/version.py status --root <project>
python SKILL_DIR/scripts/version.py publish --root <project>
python SKILL_DIR/scripts/version.py publish --root <project> --open-dashboard
python SKILL_DIR/scripts/version.py verify --root <project>
python SKILL_DIR/scripts/version.py rollback --root <project> --to audit-vNNNN --reason "..."
```

`dashboard.py` creates static Chinese pages: `audit-dashboard.html` shows the
overall score and three largest current problems; `codemap.html` provides module
search, filters, details and dependency highlighting, with a return link to the
dashboard. The pages contain no repair plans, network endpoint, bridge request,
progress window or floating ball. Publishing and rollback update only audit
artifacts and metadata.

## Targeted Queries

Use `query.py` instead of loading a large state file just to choose work:

```text
python SKILL_DIR/scripts/query.py --state <state> --max-grade D --format paths
python SKILL_DIR/scripts/query.py --state <state> --tag glue --format findings
python SKILL_DIR/scripts/query.py --state <state> --needs-audit --format ids
```

Filters combine with AND semantics. Supported formats are `ids`, `paths`,
`findings`, `table`, `json`, and `count`.

## Boundaries

Use `architecture-review-plus` for the default architecture audit and optional repair
workflow. This free copy is only selected explicitly when a read-only dashboard and
module-map workflow is wanted.
