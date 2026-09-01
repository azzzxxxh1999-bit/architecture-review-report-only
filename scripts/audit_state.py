#!/usr/bin/env python3
"""Controlled, optimistic and atomic writer for mutable modules.json state."""

import copy
import datetime
import hashlib
import json
import os
import tempfile
import uuid
import sys

from audit_contract import AuditContractError, ContractIssue


def _sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


class AuditStateRepository:
    """The only audit-result writer; no generic path setter is intentionally exposed."""

    def __init__(self, state_path, contract):
        self.state_path = os.path.abspath(state_path)
        self.contract = contract
        self.lock_path = self.state_path + ".audit-state.lock"

    def load_working_state(self, validate=True):
        try:
            with open(self.state_path, "rb") as handle:
                raw = handle.read()
            state = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise AuditContractError(ContractIssue(
                "STATE_READ_FAILED", self.state_path, "cannot read working state: " + str(exc)))
        if validate:
            self.contract.validate_working_state(state)
        return {"state": state, "expectedFingerprint": _sha256_bytes(raw)}

    def apply_module_result(self, module_id, result, revision="", expected_fingerprint=None):
        loaded = self.load_working_state()
        if expected_fingerprint is not None and expected_fingerprint != loaded["expectedFingerprint"]:
            raise AuditContractError(ContractIssue(
                "STATE_BASELINE_MISMATCH", self.state_path,
                "expected state fingerprint does not match current state"))
        state = copy.deepcopy(loaded["state"])
        module = next((item for item in state.get("modules", [])
                       if isinstance(item, dict) and item.get("id") == module_id), None)
        if module is None:
            raise AuditContractError(ContractIssue(
                "MODULE_ID_NOT_FOUND", "modules", "module id not found: " + str(module_id)))
        normalized = self.contract.normalize_audit_result(result)
        module.update(normalized)
        module["auditedHash"] = module.get("contentHash", "")
        module["auditedAt"] = datetime.datetime.now().strftime("%Y-%m-%d")
        module["auditedRev"] = revision
        self.contract.validate_module_result(
            module, "modules[{}]".format(module_id), True, require_fresh_hash=True)
        self.contract.validate_working_state(state)
        receipt = self.commit(state, loaded["expectedFingerprint"])
        receipt.update({
            "moduleId": module_id,
            "score": normalized["score"],
            "grade": normalized["grade"],
            "findings": len(normalized["findings"]),
            "tags": normalized["tags"],
        })
        return receipt

    def commit(self, candidate, expected_fingerprint):
        self.contract.validate_working_state(candidate)
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        token = str(uuid.uuid4())
        try:
            with open(self.lock_path, "x", encoding="utf-8") as handle:
                json.dump({"token": token, "pid": os.getpid()}, handle)
        except FileExistsError:
            raise AuditContractError(ContractIssue(
                "STATE_WRITER_LOCKED", self.lock_path,
                "another audit state writer holds the lock"))
        except OSError as exc:
            raise AuditContractError(ContractIssue(
                "STATE_LOCK_FAILED", self.lock_path,
                "cannot create audit state writer lock: " + str(exc)))

        temp_path = None
        try:
            try:
                with open(self.state_path, "rb") as handle:
                    current_raw = handle.read()
            except OSError as exc:
                raise AuditContractError(ContractIssue(
                    "STATE_READ_FAILED", self.state_path, "cannot re-read state: " + str(exc)))
            current_fingerprint = _sha256_bytes(current_raw)
            if current_fingerprint != expected_fingerprint:
                raise AuditContractError(ContractIssue(
                    "STATE_BASELINE_MISMATCH", self.state_path,
                    "working state changed after it was loaded"))

            fd, temp_path = tempfile.mkstemp(
                prefix=".tmp-audit-state-", suffix=".json",
                dir=os.path.dirname(self.state_path),
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(candidate, handle, ensure_ascii=False, indent=1)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            with open(temp_path, "rb") as handle:
                written_raw = handle.read()
            parsed = json.loads(written_raw.decode("utf-8"))
            self.contract.validate_working_state(parsed)
            os.replace(temp_path, self.state_path)
            temp_path = None
            return {
                "status": "COMMITTED",
                "previousFingerprint": expected_fingerprint,
                "stateFingerprint": _sha256_bytes(written_raw),
            }
        except AuditContractError:
            raise
        except (OSError, UnicodeError, ValueError) as exc:
            raise AuditContractError(ContractIssue(
                "STATE_COMMIT_FAILED", self.state_path,
                "atomic state commit failed: " + str(exc)))
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError as exc:
                    print("audit-state: warning - could not clean temporary file: {}".format(exc),
                          file=sys.stderr)
            try:
                with open(self.lock_path, encoding="utf-8") as handle:
                    lock = json.load(handle)
                if lock.get("token") == token:
                    os.unlink(self.lock_path)
            except (OSError, ValueError, TypeError) as exc:
                print("audit-state: warning - could not clean audit lock: {}".format(exc),
                      file=sys.stderr)
