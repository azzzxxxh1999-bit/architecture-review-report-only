#!/usr/bin/env python3
"""Shared semantic contract for architecture-review audit state.

The module is deliberately stdlib-only and side-effect free.  It owns the meaning of
module audit results, publishable architecture state, semantic fingerprints, retained
schema compatibility and publish receipts.  Writers and repository verification must
use this module instead of re-implementing the rubric.
"""

import copy
import hashlib
import json
import re


STATE_SCHEMA_VERSION = 1
SEMANTIC_CONTRACT_VERSION = 1
RECEIPT_VERSION = 1

VALID_GRADES = {"A", "B", "C", "D", "F"}
CANONICAL_DIMENSIONS = (
    "responsibility", "boundary", "contract", "dependency", "data_logic",
    "composition_state", "evolution", "safeguards",
)
CANONICAL_LENSES = ("split", "connect", "change", "protect")
VALID_ARCHITECTURE_STATUSES = {"good", "warning", "risk", "unknown"}


def stable_json_hash(value):
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


DEFAULT_RUBRIC = (
    ("A", 90), ("B", 75), ("C", 60), ("D", 40), ("F", 0)
)


def grade_for(score, rubric=None):
    """Return the grade from the effective rubric's lower bounds."""
    bounds = DEFAULT_RUBRIC if rubric is None else rubric
    for grade, lower_bound in sorted(bounds, key=lambda item: item[1], reverse=True):
        if score >= lower_bound:
            return grade
    return "F"


class ContractIssue:
    def __init__(self, code, path, message):
        self.code = str(code)
        self.path = str(path)
        self.message = str(message)

    def as_dict(self):
        return {"code": self.code, "path": self.path, "message": self.message}

    def __str__(self):
        where = " {}".format(self.path) if self.path else ""
        return "[{}]{}: {}".format(self.code, where, self.message)


class AuditContractError(ValueError):
    def __init__(self, issues):
        if isinstance(issues, ContractIssue):
            issues = [issues]
        self.issues = list(issues)[:50]
        super().__init__("; ".join(str(issue) for issue in self.issues))


def _issue(issues, code, path, message):
    if len(issues) < 50:
        issues.append(ContractIssue(code, path, message))


class AuditSchemaRegistry:
    """Current-schema writer plus a read-only v1 retained-state adapter."""

    current_version = STATE_SCHEMA_VERSION
    supported_retained_versions = {1}

    def detect_schema(self, document):
        if not isinstance(document, dict):
            raise AuditContractError(ContractIssue(
                "STATE_NOT_OBJECT", "$", "audit state must be a JSON object"))
        version = document.get("schemaVersion", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise AuditContractError(ContractIssue(
                "SCHEMA_INVALID", "schemaVersion", "schemaVersion must be a positive integer"))
        return version

    def upgrade_working_state(self, document, to_version=STATE_SCHEMA_VERSION):
        source_version = self.detect_schema(document)
        if to_version != self.current_version:
            raise AuditContractError(ContractIssue(
                "SCHEMA_TARGET_UNSUPPORTED", "schemaVersion",
                "unsupported target schemaVersion: {}".format(to_version)))
        if source_version > self.current_version:
            raise AuditContractError(ContractIssue(
                "SCHEMA_FUTURE_UNSUPPORTED", "schemaVersion",
                "future schemaVersion {} is not supported".format(source_version)))
        if source_version != self.current_version:
            raise AuditContractError(ContractIssue(
                "SCHEMA_MIGRATION_MISSING", "schemaVersion",
                "no migration registered from {} to {}".format(
                    source_version, self.current_version)))
        upgraded = copy.deepcopy(document)
        upgraded["schemaVersion"] = self.current_version
        return {
            "document": upgraded,
            "fromVersion": source_version,
            "toVersion": self.current_version,
            "changed": "schemaVersion" not in document,
            "compatibilityStatus": (
                "legacy-v1-adapted" if "schemaVersion" not in document else "current-contract"
            ),
            "irreversibleFields": [],
        }

    def read_retained(self, document):
        version = self.detect_schema(document)
        if version not in self.supported_retained_versions:
            raise AuditContractError(ContractIssue(
                "SCHEMA_RETAINED_UNSUPPORTED", "schemaVersion",
                "retained schemaVersion {} is not supported".format(version)))
        return {
            "document": copy.deepcopy(document),
            "schemaVersion": version,
            "compatibilityStatus": (
                "legacy-contract" if "schemaVersion" not in document else "current-contract"
            ),
        }


class AuditContract:
    def __init__(self, standard):
        self.standard = copy.deepcopy(standard)
        issues = []
        if not isinstance(standard, dict):
            _issue(issues, "STANDARD_NOT_OBJECT", "$", "standard must be a JSON object")
            raise AuditContractError(issues)

        self.rubric = self._parse_rubric(standard.get("rubric"), issues)

        tags = standard.get("tags")
        if not isinstance(tags, list) or not tags:
            _issue(issues, "STANDARD_TAGS_INVALID", "tags", "standard tags must be a non-empty array")
            raise AuditContractError(issues)
        self.tags = {}
        for index, tag in enumerate(tags):
            path = "tags[{}]".format(index)
            if not isinstance(tag, dict) or not isinstance(tag.get("id"), str) or not tag["id"]:
                _issue(issues, "STANDARD_TAG_INVALID", path, "every tag needs a non-empty string id")
                continue
            if tag["id"] in self.tags:
                _issue(issues, "STANDARD_TAG_DUPLICATE", path, "duplicate tag id: " + tag["id"])
                continue
            self.tags[tag["id"]] = copy.deepcopy(tag)
        clean = self.tags.get("clean")
        if not clean or clean.get("bad") is not False:
            _issue(issues, "STANDARD_CLEAN_INVALID", "tags.clean",
                   "standard must define clean as a non-problem tag")

        severities = standard.get("severities")
        if not isinstance(severities, list):
            _issue(issues, "STANDARD_SEVERITIES_INVALID", "severities",
                   "standard severities must be an array")
            self.severities = {"HIGH", "MED", "LOW"}
        else:
            self.severities = {
                str(item.get("key")) for item in severities
                if isinstance(item, dict) and item.get("key")
            }
            if not {"HIGH", "MED", "LOW"}.issubset(self.severities):
                _issue(issues, "STANDARD_SEVERITIES_INCOMPLETE", "severities",
                       "standard must include HIGH, MED and LOW")
        if issues:
            raise AuditContractError(issues)

        semantic_standard = {
            "rubric": standard.get("rubric"),
            "severities": standard.get("severities"),
            "tags": standard.get("tags"),
            "architectureLenses": standard.get("architectureLenses"),
            "architectureDimensions": standard.get("architectureDimensions"),
            "architectureStatuses": standard.get("architectureStatuses"),
        }
        self.standard_fingerprint = stable_json_hash(standard)
        self.contract_fingerprint = stable_json_hash({
            "semanticContractVersion": SEMANTIC_CONTRACT_VERSION,
            "stateSchemaVersion": STATE_SCHEMA_VERSION,
            "semanticStandard": semantic_standard,
            "invariants": [
                "score-grade-match", "known-tags", "clean-exclusive",
                "problem-tags-require-findings", "finding-evidence-required",
                "audited-hash-matches-content", "canonical-four-lens-eight-dimension",
            ],
        })

    @staticmethod
    def _parse_rubric(raw, issues):
        if not isinstance(raw, list) or not raw:
            _issue(issues, "STANDARD_RUBRIC_INVALID", "rubric",
                   "standard rubric must be a non-empty array")
            return list(DEFAULT_RUBRIC)
        bounds = []
        grades = set()
        for index, item in enumerate(raw):
            path = "rubric[{}]".format(index)
            if not isinstance(item, dict):
                _issue(issues, "STANDARD_RUBRIC_ENTRY_INVALID", path,
                       "rubric entries must be objects")
                continue
            grade = item.get("grade")
            if not isinstance(grade, str) or grade.strip().upper() not in VALID_GRADES:
                _issue(issues, "STANDARD_RUBRIC_GRADE_INVALID", path,
                       "rubric grade must be A, B, C, D or F")
                continue
            grade = grade.strip().upper()
            lower = None
            match = re.match(r"\s*(-?\d+)", str(item.get("range", "")))
            if match:
                lower = int(match.group(1))
            if lower is None or not 0 <= lower <= 100:
                _issue(issues, "STANDARD_RUBRIC_RANGE_INVALID", path,
                       "rubric range must start with a score from 0 to 100")
                continue
            if grade in grades:
                _issue(issues, "STANDARD_RUBRIC_DUPLICATE", path,
                       "duplicate rubric grade: " + grade)
                continue
            grades.add(grade)
            bounds.append((grade, lower))
        if grades != VALID_GRADES:
            _issue(issues, "STANDARD_RUBRIC_INCOMPLETE", "rubric",
                   "standard rubric must define exactly A, B, C, D and F")
        return bounds or list(DEFAULT_RUBRIC)

    @classmethod
    def from_path(cls, path):
        with open(path, encoding="utf-8") as handle:
            return cls(json.load(handle))

    def normalize_audit_result(self, result):
        if not isinstance(result, dict):
            raise AuditContractError(ContractIssue(
                "AUDIT_RESULT_NOT_OBJECT", "$", "audit result must be a JSON object"))
        issues = []
        raw_score = result.get("score")
        if isinstance(raw_score, bool):
            score = None
        elif isinstance(raw_score, int):
            score = raw_score
        elif isinstance(raw_score, str) and raw_score.strip().isdigit():
            score = int(raw_score.strip())
        else:
            score = None
        if score is None:
            _issue(issues, "AUDIT_SCORE_TYPE", "score", "score must be an integer")
        elif not 0 <= score <= 100:
            _issue(issues, "AUDIT_SCORE_RANGE", "score",
                   "score out of range 0..100: {}".format(score))

        raw_grade = result.get("grade")
        grade = raw_grade.strip().upper() if isinstance(raw_grade, str) else ""
        if grade not in VALID_GRADES:
            _issue(issues, "AUDIT_GRADE_INVALID", "grade",
                   "grade must be one of A, B, C, D, F")
        elif score is not None and 0 <= score <= 100 and grade != grade_for(score, self.rubric):
            _issue(issues, "AUDIT_GRADE_MISMATCH", "grade",
                   "grade {} doesn't match score {} (rubric grade is {})".format(
                       grade, score, grade_for(score, self.rubric)))

        raw_tags = result.get("tags")
        tags = ["clean"] if raw_tags in (None, []) else raw_tags
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            _issue(issues, "AUDIT_TAGS_TYPE", "tags", "tags must be an array of strings")
            tags = []
        unknown = sorted({tag for tag in tags if tag not in self.tags})
        if unknown:
            _issue(issues, "AUDIT_TAG_UNKNOWN", "tags",
                   "tag(s) not in the standard: " + ", ".join(unknown))
        problem_tags = [
            tag for tag in tags
            if tag in self.tags and self.tags[tag].get("bad") is True
        ]
        if "clean" in tags and len(tags) > 1:
            _issue(issues, "AUDIT_CLEAN_CONFLICT", "tags",
                   "clean cannot coexist with problem tags")
        if "clean" in tags and score is not None and score < 75:
            _issue(issues, "AUDIT_CLEAN_LOW_SCORE", "tags",
                   "clean requires score >= 75")

        raw_findings = result.get("findings") or []
        findings = []
        if not isinstance(raw_findings, list):
            _issue(issues, "AUDIT_FINDINGS_TYPE", "findings",
                   "findings must be an array")
            raw_findings = []
        for index, finding in enumerate(raw_findings):
            path = "findings[{}]".format(index)
            if not isinstance(finding, dict):
                _issue(issues, "AUDIT_FINDING_TYPE", path, "finding must be an object")
                continue
            sev = finding.get("sev")
            sev = sev.strip().upper() if isinstance(sev, str) else ""
            loc = finding.get("loc")
            text = finding.get("text")
            loc = loc.strip() if isinstance(loc, str) else ""
            text = text.strip() if isinstance(text, str) else ""
            if sev not in self.severities:
                _issue(issues, "AUDIT_FINDING_SEVERITY", path + ".sev",
                       "finding severity is not in the effective standard")
            if not loc or not text:
                _issue(issues, "AUDIT_FINDING_EVIDENCE", path,
                       "every finding needs non-empty loc and text")
            if sev in self.severities and loc and text:
                findings.append({"sev": sev, "loc": loc, "text": text})
        if problem_tags and not findings:
            _issue(issues, "AUDIT_PROBLEM_WITHOUT_FINDING", "findings",
                   "a module with problem tags must include file:line evidence")
        if issues:
            raise AuditContractError(issues)
        return {"score": score, "grade": grade, "tags": list(tags), "findings": findings}

    def validate_module_result(self, module, path="module", require_audit=True,
                               require_fresh_hash=True):
        issues = []
        if not isinstance(module, dict):
            raise AuditContractError(ContractIssue(
                "MODULE_NOT_OBJECT", path, "module must be a JSON object"))
        audit_keys = ("score", "grade", "tags", "findings", "auditedHash")
        present = [key for key in audit_keys if key in module]
        if not present and not require_audit:
            return
        if not require_audit and len(present) != len(audit_keys):
            # Working state may be mid-initialization or a legacy partial state.
            # Publication remains strict; scan/apply must be able to finish it.
            return
        if len(present) != len(audit_keys):
            missing = [key for key in audit_keys if key not in module]
            _issue(issues, "AUDIT_RESULT_INCOMPLETE", path,
                   "missing audit fields: " + ", ".join(missing))
        else:
            try:
                self.normalize_audit_result({key: module.get(key) for key in (
                    "score", "grade", "tags", "findings")})
            except AuditContractError as exc:
                for issue in exc.issues:
                    _issue(issues, issue.code, path + "." + issue.path, issue.message)
        content_hash = module.get("contentHash")
        audited_hash = module.get("auditedHash")
        if present or require_audit:
            if not isinstance(content_hash, str) or not content_hash:
                _issue(issues, "AUDIT_CONTENT_HASH_MISSING", path + ".contentHash",
                       "audited modules require a non-empty contentHash")
            if not isinstance(audited_hash, str) or not audited_hash:
                _issue(issues, "AUDIT_HASH_MISSING", path + ".auditedHash",
                       "audited modules require a non-empty auditedHash")
            elif (require_fresh_hash and isinstance(content_hash, str) and content_hash
                  and audited_hash != content_hash):
                _issue(issues, "AUDIT_HASH_MISMATCH", path + ".auditedHash",
                       "auditedHash must match current contentHash")
        if issues:
            raise AuditContractError(issues)

    def validate_working_state(self, state):
        registry = AuditSchemaRegistry()
        registry.upgrade_working_state(state)
        issues = []
        modules = state.get("modules") if isinstance(state, dict) else None
        if not isinstance(modules, list):
            raise AuditContractError(ContractIssue(
                "MODULES_NOT_ARRAY", "modules", "modules must be an array"))
        ids = []
        for index, module in enumerate(modules):
            path = "modules[{}]".format(index)
            if not isinstance(module, dict):
                _issue(issues, "MODULE_NOT_OBJECT", path, "module must be an object")
                continue
            module_id = module.get("id")
            if not isinstance(module_id, str) or not module_id:
                _issue(issues, "MODULE_ID_INVALID", path + ".id",
                       "module id must be a non-empty string")
            else:
                ids.append(module_id)
            try:
                self.validate_module_result(
                    module, path, require_audit=False, require_fresh_hash=False)
            except AuditContractError as exc:
                issues.extend(exc.issues)
        if len(ids) != len(set(ids)):
            _issue(issues, "MODULE_ID_DUPLICATE", "modules",
                   "modules must contain unique ids")
        known = set(ids)
        for index, module in enumerate(modules):
            if not isinstance(module, dict):
                continue
            deps = module.get("deps") or []
            if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
                _issue(issues, "MODULE_DEPS_INVALID", "modules[{}].deps".format(index),
                       "deps must be an array of module ids")
                continue
            unknown = sorted(set(deps) - known)
            if unknown:
                _issue(issues, "MODULE_DEP_UNKNOWN", "modules[{}].deps".format(index),
                       "unknown deps: " + ", ".join(unknown))
        if issues:
            raise AuditContractError(issues)

    def validate_publishable_state(self, state):
        self.validate_working_state(state)
        issues = []
        modules = state.get("modules") or []
        if not modules:
            _issue(issues, "MODULES_EMPTY", "modules",
                   "publishable audits require at least one module")
        for index, module in enumerate(modules):
            try:
                self.validate_module_result(
                    module, "modules[{}]".format(index), require_audit=True)
            except AuditContractError as exc:
                issues.extend(exc.issues)

        known = {module.get("id") for module in modules if isinstance(module, dict)}
        dimensions = state.get("architectureDimensions")
        if not isinstance(dimensions, list):
            _issue(issues, "ARCH_DIMENSIONS_NOT_ARRAY", "architectureDimensions",
                   "architectureDimensions must be an array")
            dimensions = []
        dim_ids = [item.get("id") for item in dimensions if isinstance(item, dict)]
        if len(dimensions) != len(CANONICAL_DIMENSIONS) or set(dim_ids) != set(CANONICAL_DIMENSIONS):
            _issue(issues, "ARCH_DIMENSIONS_INCOMPLETE", "architectureDimensions",
                   "publishable audits require exactly the eight canonical architecture dimensions")
        for index, item in enumerate(dimensions):
            path = "architectureDimensions[{}]".format(index)
            if not isinstance(item, dict) or item.get("id") not in CANONICAL_DIMENSIONS:
                _issue(issues, "ARCH_DIMENSION_INVALID", path,
                       "architecture dimension has an unknown or malformed id")
                continue
            status = item.get("status")
            if status not in VALID_ARCHITECTURE_STATUSES:
                _issue(issues, "ARCH_STATUS_INVALID", path + ".status",
                       "invalid architecture status: {}".format(status))
            score = item.get("score")
            if score is not None and (
                    isinstance(score, bool) or not isinstance(score, (int, float))
                    or not 0 <= score <= 100):
                _issue(issues, "ARCH_SCORE_INVALID", path + ".score",
                       "architecture score must be null or 0..100")
            evidence = item.get("evidence") or []
            if not isinstance(evidence, list):
                _issue(issues, "ARCH_EVIDENCE_NOT_ARRAY", path + ".evidence",
                       "evidence must be an array")
                evidence = []
            for ev_index, evidence_item in enumerate(evidence):
                if isinstance(evidence_item, str):
                    valid_evidence = bool(evidence_item.strip())
                else:
                    valid_evidence = (
                        isinstance(evidence_item, dict)
                        and isinstance(evidence_item.get("description"), str)
                        and bool(evidence_item["description"].strip())
                    )
                if not valid_evidence:
                    _issue(issues, "ARCH_EVIDENCE_INVALID",
                           path + ".evidence[{}]".format(ev_index),
                           "architecture evidence needs a non-empty description")
            if status in {"warning", "risk"} and not evidence:
                _issue(issues, "ARCH_EVIDENCE_REQUIRED", path + ".evidence",
                       "{} architecture dimension requires evidence: {}".format(
                           status, item.get("id")))
            related = item.get("relatedModules") or []
            if (not isinstance(related, list)
                    or any(not isinstance(module_id, str) or module_id not in known
                           for module_id in related)):
                _issue(issues, "ARCH_RELATED_MODULE_UNKNOWN", path + ".relatedModules",
                       "architecture dimension references an unknown module")

        lenses = state.get("architectureLenses")
        if not isinstance(lenses, list):
            _issue(issues, "ARCH_LENSES_NOT_ARRAY", "architectureLenses",
                   "architectureLenses must be an array")
            lenses = []
        lens_ids = [item.get("id") for item in lenses if isinstance(item, dict)]
        if len(lenses) != len(CANONICAL_LENSES) or set(lens_ids) != set(CANONICAL_LENSES):
            _issue(issues, "ARCH_LENSES_INCOMPLETE", "architectureLenses",
                   "publishable audits require exactly the four canonical architecture lenses")
        if issues:
            raise AuditContractError(issues)

    def canonicalize_state(self, state):
        canonical = copy.deepcopy(state)
        canonical.pop("auditVersion", None)
        canonical.pop("auditDelta", None)
        canonical.pop("semanticValidation", None)
        meta = canonical.get("meta")
        if isinstance(meta, dict):
            for key in ("generatedAt", "locLine"):
                meta.pop(key, None)
        for module in canonical.get("modules") or []:
            if isinstance(module, dict):
                module.pop("auditedAt", None)
        for dimension in canonical.get("architectureDimensions") or []:
            if isinstance(dimension, dict):
                dimension.pop("verifiedAt", None)
        canonical["schemaVersion"] = STATE_SCHEMA_VERSION
        return canonical

    def state_fingerprint(self, state):
        return stable_json_hash(self.canonicalize_state(state))

    @staticmethod
    def normalize_gates(gates):
        normalized = []
        for raw in gates or []:
            value = str(raw).strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered.endswith(":fail") or lowered.endswith(":failed"):
                raise AuditContractError(ContractIssue(
                    "PREFLIGHT_GATE_FAILED", "validationGates", "failed gate: " + value))
            normalized.append(value)
        return sorted(set(normalized))

    def build_preflight_receipt(self, state, source_fingerprint, gates, scope,
                                baseline, mode, project_type, created_at):
        self.validate_publishable_state(state)
        normalized_gates = self.normalize_gates(gates)
        normalized_scope = sorted(set(str(item) for item in (scope or [])))
        receipt = {
            "receiptVersion": RECEIPT_VERSION,
            "semanticContractVersion": SEMANTIC_CONTRACT_VERSION,
            "stateSchemaVersion": STATE_SCHEMA_VERSION,
            "compatibilityStatus": "current-contract",
            "semanticValid": True,
            "contractFingerprint": self.contract_fingerprint,
            "standardFingerprint": self.standard_fingerprint,
            "stateFingerprint": self.state_fingerprint(state),
            "sourceFingerprint": str(source_fingerprint),
            "gateFingerprint": stable_json_hash(normalized_gates),
            "scopeFingerprint": stable_json_hash(normalized_scope),
            "validationGates": normalized_gates,
            "scope": normalized_scope,
            "baseline": baseline,
            "mode": mode,
            "projectType": project_type,
            "createdAt": created_at,
            "producer": "architecture-review/version.py",
        }
        receipt["receiptFingerprint"] = stable_json_hash({
            key: value for key, value in receipt.items()
            if key not in {"createdAt", "receiptFingerprint"}
        })
        return receipt

    def validate_preflight_receipt(self, receipt, state, source_fingerprint,
                                   gates, scope, baseline, mode, project_type):
        self.validate_publishable_state(state)
        issues = []
        if not isinstance(receipt, dict):
            raise AuditContractError(ContractIssue(
                "RECEIPT_NOT_OBJECT", "semantic-receipt.json", "receipt must be an object"))
        expected = self.build_preflight_receipt(
            state, source_fingerprint, gates, scope, baseline, mode, project_type,
            receipt.get("createdAt"),
        )
        required = (
            "receiptVersion", "semanticContractVersion", "stateSchemaVersion",
            "compatibilityStatus", "semanticValid", "contractFingerprint", "standardFingerprint",
            "stateFingerprint", "sourceFingerprint", "gateFingerprint",
            "scopeFingerprint", "validationGates", "scope", "baseline", "mode",
            "projectType", "producer", "receiptFingerprint",
        )
        for key in required:
            if receipt.get(key) != expected.get(key):
                _issue(issues, "RECEIPT_MISMATCH", "semantic-receipt.json." + key,
                       "receipt field does not match retained audit state")
        if issues:
            raise AuditContractError(issues)
        return expected


def format_contract_error(error):
    if isinstance(error, AuditContractError):
        return "; ".join(str(issue) for issue in error.issues)
    return str(error)
