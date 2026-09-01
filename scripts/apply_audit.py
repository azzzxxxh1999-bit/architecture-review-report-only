#!/usr/bin/env python3
"""apply_audit.py — validate + merge one subagent's audit result into modules.json.

A module audit is produced by an INDEPENDENT subagent (see reference/STANDARDS.md) and
returned as a small JSON object:

    {"score": 72, "grade": "C",
     "tags": ["duplication","legacy"],
     "findings": [{"sev":"HIGH","loc":"path/file.py:120","text":"..."}, ...]}

This script REJECTS bad audits before they pollute the state.  The checks are owned by
``audit_contract.py`` and reused by publish/verify, so a direct edit cannot bypass the
same semantics later in the trust chain. It checks:
  * score in 0..100 and grade in A..F;
  * grade matches the score band (rubric: 90+ A, 75+ B, 60+ C, 40+ D, else F);
  * every tag is in the effective standard (standard.json next to the state, else the
    skill default) — including any custom tags the project added;
  * `clean` does not coexist with any other tag, and requires score >= 75;
  * a module with problem tags has at least one finding (file:line evidence);
  * every finding has a non-empty sev/loc/text.

On success it writes score/grade/tags/findings and stamps `auditedHash` = current
`contentHash` (run scan.py --write FIRST), plus `auditedAt` / `auditedRev`.

Accepts the result inline (--json '...'), from a file (--json-file path), or stdin.
Writes are optimistic, locked and atomic through ``AuditStateRepository``. Stdlib only.
"""
import argparse
import json
import os
import sys

from audit_contract import AuditContract, AuditContractError, format_contract_error
from audit_state import AuditStateRepository


def effective_standard_path(state_path):
    project = os.path.join(os.path.dirname(os.path.abspath(state_path)), "standard.json")
    if os.path.isfile(project):
        return project
    return os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "reference", "standard.json"))


def fail(msg):
    sys.exit("apply_audit: REJECTED — " + msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--id", required=True, help="module id to update")
    ap.add_argument("--json", help="audit result as an inline JSON string")
    ap.add_argument("--json-file", help="audit result JSON file")
    ap.add_argument("--rev", default="", help="git rev being audited (optional)")
    args = ap.parse_args()

    try:
        if args.json_file:
            with open(args.json_file, encoding="utf-8") as handle:
                result = json.load(handle)
        elif args.json:
            result = json.loads(args.json)
        else:
            result = json.load(sys.stdin)
        contract = AuditContract.from_path(effective_standard_path(args.state))
        receipt = AuditStateRepository(args.state, contract).apply_module_result(
            args.id, result, revision=args.rev)
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, AuditContractError):
            fail(format_contract_error(exc))
        fail(str(exc))
    print("applied: {}  score={} grade={} findings={} tags={}".format(
        receipt["moduleId"], receipt["score"], receipt["grade"],
        receipt["findings"], receipt["tags"]))


if __name__ == "__main__":
    main()
