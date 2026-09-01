# Architecture review report-only instructions

## Edition status

This directory is the **explicit free read-only copy**. The default user-facing
architecture audit entrypoint is `architecture-review-plus`.

This repository contains the Markdown-only sibling of the full
architecture-review skill.

- modules.json is the source of truth; scripts/render.py generates only the
  Markdown report.
- Scores, grades, tags, findings, and audited hashes enter through
  scripts/apply_audit.py and the shared semantic contract.
- Every score requires an independent audit against reference/STANDARDS.md.
- Keep auditor, test-author, fixer, and acceptance/verifier roles separate.
- .codemap/ is excluded from source scanning. Retained audit versions are
  immutable and must not be removed or overwritten.
- This sibling has no interactive map or dependency graph viewer. dashboard.py
  may generate the conclusion dashboard and open it in the browser.
- The dashboard is beginner-facing: show only the architecture score, three confirmed
  problems and three likely follow-on problems. It has no repair plans or AI handoff.
- `client/` is an optional Plus connector only. It uploads allow-listed audit metadata,
  never Plus core files or source code, and invokes the user's own local Agent.

The free copy owns its read-only renderer and module-map projection; users must
explicitly request it instead of the default Plus workflow.
