# Markdown audit versioning

This report-only skill retains the same immutable audit lifecycle as the full
architecture-review skill. Its only browser artifact is an optional conclusion
dashboard; it never stores a module-map or dependency-graph viewer.

## Layout

    <project>/.codemap/
    ├─ modules.json
    ├─ standard.json                 optional project override
    ├─ config.json                   optional preferences
├─ codemap.md                    mutable Markdown report
├─ audit-dashboard.html          optional local conclusion dashboard
    └─ versions/
       ├─ index.json
       └─ audit-vNNNN/
          ├─ modules.json
          ├─ codemap.md
          ├─ standard.json
          ├─ source-snapshot.json
          ├─ delta.json
          ├─ semantic-receipt.json
          └─ manifest.json

Never overwrite a retained version. A short-lived .codemap/version.lock
serializes publishers and is removed only by its owning process.

## Triggers and modes

Retain a version after an explicit architecture review, milestone/release
review, or high-impact boundary review. Ordinary source edits do not publish by
themselves. The first retained audit is full; later changes are incremental or
expanded_incremental when affected consumers require it. status returns
NO_DELTA/UP_TO_DATE without allocating a version when no source or audit fact
changed.

## Acceptance

Before publish, run scan.py --write, validate all audit facts through the shared
AuditContract, and ensure no module is stale or empty. publish writes the
Markdown report into a staging directory, records hashes for every artifact,
creates a semantic receipt, and atomically promotes the version and working
state. verify checks the hash chain, source snapshot, semantic receipt, and that
the working state and Markdown report match the active version.

rollback restores only a verified retained state, standard/config, and Markdown
report. It never deletes history. Missing semantic receipts are accepted only
for independently validated legacy v1 records.

The dashboard is regenerated from current state with `dashboard.py`; it is a
local, disposable projection and is excluded from source fingerprints.

## Source snapshot

Product source is fingerprinted while excluding .codemap/, VCS metadata,
dependencies, build output, caches, and sensitive credentials. Changes are
mapped to modules using their declared path globs and expanded to direct
consumers for incremental scope. Unmapped changes are reported and never
silently ignored.
