# Architecture Review Report Only（副本·免费版）

这是面向用户的免费开源只读版。默认架构审计入口为 `architecture-review-plus`；
本目录只在用户明确选择免费版时使用。

This skill audits functional modules, records independent 0–100 quality scores,
and emits an evidence-backed Markdown report with immutable audit versions.

It is a report-focused free copy: retained audit versions remain Markdown-only,
while the Chinese dashboard opens the free module map. The four-lens shell and
eight-dimension evidence screen are omitted; module search, filters, details, and
dependency highlighting remain. It has no repair plan or bridge.

## Quick start

\`\`\`text
python scripts/scan.py --root <project> --state <project>/.codemap/modules.json --write
python scripts/render.py --state <project>/.codemap/modules.json --out-md <project>/.codemap/codemap.md
python scripts/version.py status --root <project>
python scripts/version.py publish --root <project>
python scripts/version.py verify --root <project>
python scripts/dashboard.py --root <project> --state <project>/.codemap/modules.json --out-html <project>/.codemap/audit-dashboard.html --open
\`\`\`

Read SKILL.md, reference/STANDARDS.md, and reference/DATA_MODEL.md before
running a scored audit.
