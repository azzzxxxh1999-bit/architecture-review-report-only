"""Fail-closed maintainability claims for architecture-review.

SCOPED_PASSED closes an authorized audit/remediation scope. It never certifies the
whole project. PROJECT_MAINTAINABLE requires a retained FULL audit plus fresh global
audit facts and current engineering-safeguard evidence.

Stdlib only; Python 3.9+.
"""

import argparse
import glob
import json
import os
import sys


DEFAULT_STANDARD = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "reference", "standard.json"))
CRITICAL_COUPLING = {"core", "high"}


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def emit(result):
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


def failure(code, message, **details):
    item = {"code": code, "message": message}
    item.update(details)
    return item


def gate_map(values):
    parsed = {}
    for raw in values or []:
        if ":" not in raw:
            continue
        key, value = raw.rsplit(":", 1)
        parsed[key.strip()] = value.strip().lower()
    return parsed


def resolve_state(root, state_arg):
    if state_arg:
        return os.path.abspath(state_arg)
    return os.path.join(root, ".codemap", "modules.json")


def effective_standard(state_path, explicit_path=None):
    base = read_json(DEFAULT_STANDARD)
    override_path = (os.path.abspath(explicit_path) if explicit_path else
                     os.path.join(os.path.dirname(state_path), "standard.json"))
    if not os.path.isfile(override_path) or os.path.samefile(override_path, DEFAULT_STANDARD):
        return base
    override = read_json(override_path)
    merged = dict(base)
    merged.update(override)
    base_claims = base.get("maintainabilityClaims") or {}
    override_claims = override.get("maintainabilityClaims") or {}
    hardened_claims = {}
    for claim_name in ("scoped", "project"):
        baseline = dict(base_claims.get(claim_name) or {})
        custom = dict(override_claims.get(claim_name) or {})
        claim = {**baseline, **custom}
        claim["passingStatus"] = baseline.get("passingStatus")
        claim["failingStatus"] = baseline.get("failingStatus")
        claim["minimumScore"] = max(int(baseline.get("minimumScore", 75)),
                                    int(custom.get("minimumScore", 0)))
        claim["criticalMinimumScore"] = max(
            int(baseline.get("criticalMinimumScore", 80)),
            int(custom.get("criticalMinimumScore", 0)))
        for key in ("requiredGates", "forbiddenDimensionStatuses", "unfinishedTags"):
            values = list(baseline.get(key) or [])
            for item in custom.get(key) or []:
                if item not in values:
                    values.append(item)
            claim[key] = values
        hardened_claims[claim_name] = claim
    merged["maintainabilityClaims"] = hardened_claims
    return merged


def active_manifest(root, state):
    version = (state.get("auditVersion") or {}).get("version")
    index_path = os.path.join(root, ".codemap", "versions", "index.json")
    if not version and os.path.isfile(index_path):
        version = read_json(index_path).get("activeVersion")
    if not version:
        return None, None
    path = os.path.join(root, ".codemap", "versions", version, "manifest.json")
    if not os.path.isfile(path):
        return version, None
    return version, read_json(path)


def has_ci_config(root):
    candidates = [
        os.path.join(root, ".gitlab-ci.yml"),
        os.path.join(root, "azure-pipelines.yml"),
        os.path.join(root, "Jenkinsfile"),
    ]
    if any(os.path.isfile(path) for path in candidates):
        return True
    workflows = os.path.join(root, ".github", "workflows")
    return bool(glob.glob(os.path.join(workflows, "*.yml"))
                or glob.glob(os.path.join(workflows, "*.yaml")))


def critical_ids(state):
    spine = set(state.get("spine") or [])
    return {
        module.get("id") for module in state.get("modules") or []
        if module.get("coupling") in CRITICAL_COUPLING or module.get("id") in spine
    }


def evaluate_modules(modules, critical, cfg, failures, project_claim):
    minimum = int(cfg.get("minimumScore", 75))
    critical_minimum = int(cfg.get("criticalMinimumScore", 80))
    unfinished = set(cfg.get("unfinishedTags") or [])
    for module in modules:
        module_id = module.get("id") or "<missing-id>"
        score = module.get("score")
        content_hash = module.get("contentHash")
        audited_hash = module.get("auditedHash")
        if not isinstance(score, int) or isinstance(score, bool):
            failures.append(failure("MODULE_UNAUDITED", "module has no valid score",
                                    moduleId=module_id))
        elif score < minimum:
            failures.append(failure("MODULE_BELOW_FLOOR", "module is below the hard floor",
                                    moduleId=module_id, score=score, required=minimum))
        if module_id in critical and isinstance(score, int) and score < critical_minimum:
            failures.append(failure("CRITICAL_MODULE_BELOW_TARGET",
                                    "core/high/spine module is below the healthy target",
                                    moduleId=module_id, score=score,
                                    required=critical_minimum))
        if not content_hash or audited_hash != content_hash:
            failures.append(failure("MODULE_STALE", "module audit does not match current content",
                                    moduleId=module_id))
        findings = module.get("findings") or []
        for finding_item in findings:
            severity = finding_item.get("sev")
            if severity == "HIGH":
                failures.append(failure("HIGH_FINDING", "HIGH finding is unresolved",
                                        moduleId=module_id,
                                        location=finding_item.get("loc", "")))
            if project_claim and module_id in critical and severity == "MED":
                failures.append(failure("CRITICAL_MED_FINDING",
                                        "core/high/spine module still has a MED finding",
                                        moduleId=module_id,
                                        location=finding_item.get("loc", "")))
        if project_claim and unfinished.intersection(module.get("tags") or []):
            if any(item.get("sev") in {"HIGH", "MED"} for item in findings):
                failures.append(failure("FORMAL_RUNTIME_UNFINISHED",
                                        "unfinished formal runtime remains wired",
                                        moduleId=module_id,
                                        tags=sorted(unfinished.intersection(
                                            module.get("tags") or []))))


def evaluate(args):
    root = os.path.abspath(args.root)
    state_path = resolve_state(root, args.state)
    if not os.path.isfile(state_path):
        return {"claim": args.claim, "passed": False,
                "status": "PROJECT_REWORK_REQUIRED" if args.claim == "project"
                else "SCOPED_REWORK_REQUIRED",
                "projectClaimAllowed": False,
                "failures": [failure("STATE_MISSING", "modules.json is missing",
                                     path=state_path)]}
    state = read_json(state_path)
    standard = effective_standard(state_path, args.standard)
    cfg = (standard.get("maintainabilityClaims") or {}).get(args.claim) or {}
    default_status = ("PROJECT_MAINTAINABLE" if args.claim == "project"
                      else "SCOPED_PASSED")
    fail_status = ("PROJECT_REWORK_REQUIRED" if args.claim == "project"
                   else "SCOPED_REWORK_REQUIRED")
    pass_status = cfg.get("passingStatus", default_status)
    fail_status = cfg.get("failingStatus", fail_status)
    failures = []
    module_by_id = {item.get("id"): item for item in state.get("modules") or []}
    critical = critical_ids(state)
    version, manifest = active_manifest(root, state)

    if args.claim == "scoped":
        requested = list(dict.fromkeys(args.scope or []))
        if not requested:
            failures.append(failure("SCOPE_REQUIRED", "scoped claim requires --scope"))
        unknown = [item for item in requested if item not in module_by_id]
        for module_id in unknown:
            failures.append(failure("SCOPE_MODULE_UNKNOWN", "scope module is unknown",
                                    moduleId=module_id))
        modules = [module_by_id[item] for item in requested if item in module_by_id]
        evaluate_modules(modules, critical, cfg, failures, project_claim=False)
        if not manifest:
            failures.append(failure("RETAINED_AUDIT_MISSING",
                                    "active retained audit manifest is missing",
                                    version=version))
            manifest_gates = {}
        else:
            retained_scope = set(manifest.get("scope") or [])
            for module_id in requested:
                if manifest.get("mode") != "full" and module_id not in retained_scope:
                    failures.append(failure("SCOPE_NOT_RETAINED",
                                            "module is not covered by the active audit scope",
                                            moduleId=module_id, version=version))
            manifest_gates = gate_map(manifest.get("validationGates") or [])
        supplied_gates = gate_map(args.gate)
        evidence_gates = {**manifest_gates, **supplied_gates}
        for required in cfg.get("requiredGates") or []:
            if evidence_gates.get(required) != "pass":
                failures.append(failure("REQUIRED_GATE_NOT_PASSED",
                                        "required scoped evidence gate is not pass",
                                        gate=required,
                                        observed=evidence_gates.get(required, "missing")))
    else:
        modules = list(module_by_id.values())
        evaluate_modules(modules, critical, cfg, failures, project_claim=True)
        audit_version = state.get("auditVersion") or {}
        if audit_version.get("mode") != "full":
            failures.append(failure("FULL_AUDIT_REQUIRED",
                                    "project claim requires the active working audit to be FULL",
                                    observed=audit_version.get("mode", "missing")))
        if not manifest:
            failures.append(failure("RETAINED_AUDIT_MISSING",
                                    "active retained FULL audit manifest is missing",
                                    version=version))
            manifest_gates = {}
        else:
            if manifest.get("mode") != "full" or not manifest.get("auditComplete"):
                failures.append(failure("RETAINED_FULL_AUDIT_REQUIRED",
                                        "active retained audit is not a completed FULL audit",
                                        version=version, observed=manifest.get("mode")))
            manifest_gates = gate_map(manifest.get("validationGates") or [])
        for required in cfg.get("requiredGates") or []:
            if manifest_gates.get(required) != "pass":
                failures.append(failure("REQUIRED_GATE_NOT_PASSED",
                                        "required project evidence gate is not retained as pass",
                                        gate=required,
                                        observed=manifest_gates.get(required, "missing")))
        forbidden = set(cfg.get("forbiddenDimensionStatuses") or ["risk", "unknown"])
        dimensions = state.get("architectureDimensions") or []
        expected_dimensions = {item.get("id") for item in
                               standard.get("architectureDimensions") or []}
        observed_dimensions = {item.get("id") for item in dimensions}
        for missing in sorted(expected_dimensions - observed_dimensions):
            failures.append(failure("DIMENSION_MISSING",
                                    "architecture dimension is missing", dimension=missing))
        for dimension in dimensions:
            if dimension.get("status") in forbidden:
                failures.append(failure("DIMENSION_NOT_CLEARED",
                                        "architecture dimension is not cleared",
                                        dimension=dimension.get("id"),
                                        observed=dimension.get("status")))
        if not os.path.isdir(os.path.join(root, ".git")):
            failures.append(failure("GIT_MISSING", "project has no Git repository"))
        if not has_ci_config(root):
            failures.append(failure("CI_CONFIG_MISSING",
                                    "project has no recognized CI workflow configuration"))

    passed = not failures
    return {
        "claim": args.claim,
        "passed": passed,
        "status": pass_status if passed else fail_status,
        "projectClaimAllowed": passed and args.claim == "project",
        "auditVersion": version,
        "evaluatedModules": [item.get("id") for item in modules],
        "criticalModules": sorted(item for item in critical if item),
        "failureCount": len(failures),
        "failures": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--state")
    parser.add_argument("--standard")
    parser.add_argument("--claim", choices=("scoped", "project"), required=True)
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--gate", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        return emit(evaluate(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "claim": args.claim,
            "passed": False,
            "status": "PROJECT_REWORK_REQUIRED" if args.claim == "project"
            else "SCOPED_REWORK_REQUIRED",
            "projectClaimAllowed": False,
            "failureCount": 1,
            "failures": [failure("GATE_INPUT_INVALID", str(exc))],
        }
        return emit(result)


if __name__ == "__main__":
    sys.exit(main())
