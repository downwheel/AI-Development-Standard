"""Version-pinned cooperative workflow. Read operations never start transactions.

Human decisions are caller-supplied provenance, not identity authentication.
All persistent writes use Journal.transaction; artifact bodies are immutable blobs.
"""
from __future__ import annotations

import copy
import difflib
import json
import threading
from datetime import datetime, timedelta, timezone

from .common import emit, encoded, fail, identifier, now, safe_relative, scan_secrets, sha256, uid

KINDS = ("discovery-context", "requirements", "system-design", "unit-spec", "test-plan", "review-report")
EVIDENCE_KINDS = ("implementation-receipt", "verification-report")
PRODUCERS = dict(zip(KINDS, ("dev-discover", "dev-requirements", "dev-system-design", "dev-unit-design", "dev-test-design", "dev-review")))
SKILLS = tuple(PRODUCERS.values()) + ("dev-implement", "dev-verify", "dev-restore")
NOTICE = "Cooperative local workflow: user decisions are caller-supplied and not authenticated; same-account files/tools are not isolated."
STAGE_STATUS = {"succeeded": "completed", "no_change": "completed", "failed": "failed", "blocked": "waiting_tool",
                "interrupted": "failed", "waiting_input": "waiting_input", "waiting_tool": "waiting_tool", "cancelled": "cancelled"}


def string(maximum=1000):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def obj(properties, required=None, additional=False):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": additional}


def array(items, minimum=0, maximum=100):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


ID = {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,95}$", "minLength": 1, "maxLength": 96}
REF = obj({"artifact_id": ID, "revision_id": ID, "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}})
REFS = array(REF, maximum=100)
HEAD = obj({"revision_id": {"type": ["string", "null"]}, "generation": {"type": "integer", "minimum": 0}})
CHECK = obj({"check_id": ID, "argv": array(string(4000), 1, 100), "cwd": string(512),
             "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300}, "required": {"type": "boolean"},
             "expected_exit": {"type": "integer", "enum": [0]}, "case_ids": array(ID, 1), "expected": string(10000), "oracle": string(10000),
             "evidence_mode": {"type": "string", "enum": ["command-exit", "case-results"]},
             "parser": {"type": "string", "enum": ["exit-code", "team-json"]}},
            ["check_id", "argv", "cwd", "timeout_seconds", "required", "expected_exit", "case_ids", "expected", "oracle"])
PAYLOADS = {
    "discovery-context": obj({}, [], True),
    "requirements": obj({"requirements": array(obj({"id": ID, "description": string(10000), "case_ids": array(ID, 1)}, additional=True), 1)}, ["requirements"], True),
    "system-design": obj({"requirement_ids": array(ID, 1)}, ["requirement_ids"], True),
    "unit-spec": obj({"requirement_ids": array(ID, 1), "case_ids": array(ID, 1)}, ["requirement_ids", "case_ids"], True),
    "test-plan": obj({"unit_ref": REF, "checks": array(CHECK, 1)}, ["unit_ref", "checks"], True),
    "review-report": obj({}, [], True),
    "implementation-receipt": obj({}, [], True),
    "verification-report": obj({}, [], True),
}
SCHEMAS = {
    "create_run": obj({"run_id": ID, "workspace_id": ID, "goal": string(10000)}, ["run_id", "workspace_id", "goal"]),
    "start_stage": obj({"run_id": ID, "skill": {"type": "string", "enum": list(SKILLS)}, "owner": ID, "input_refs": REFS,
                         "unit_id": ID, "reason": string(5000)}, ["run_id", "skill", "owner", "input_refs"]),
    "finish_stage": obj({"stage_run_id": ID, "owner": ID, "status": {"type": "string", "enum": list(STAGE_STATUS)},
                          "output_refs": REFS, "notes": string(10000)}, ["stage_run_id", "owner", "status"]),
    "resume_stage": obj({"stage_run_id": ID, "owner": ID}),
    "publish_artifact": obj({"run_id": ID, "stage_run_id": ID, "owner": ID, "artifact_id": ID, "kind": {"type": "string", "enum": list(KINDS)},
                              "unit_id": ID, "payload": {"type": "object"}, "report": string(200000), "input_refs": REFS,
                              "accept": {"type": "boolean"}, "expected_head": HEAD},
                             ["run_id", "stage_run_id", "owner", "artifact_id", "kind", "payload", "report", "input_refs"]),
    "accept_artifact": obj({"ref": REF, "expected_head": HEAD}),
    "get_artifact": obj({"ref": REF}),
    "list_artifacts": obj({"run_id": ID, "kind": {"type": "string", "enum": list(KINDS + EVIDENCE_KINDS)}, "unit_id": ID}, ["run_id"]),
    "diff_artifacts": obj({"before": REF, "after": REF}),
    "create_review": obj({"run_id": ID, "gate": {"type": "string", "enum": ["A", "B"]}, "unit_id": ID, "input_refs": REFS}, ["run_id", "gate", "input_refs"]),
    "record_decision": obj({"review_id": ID, "decision": {"type": "string", "enum": ["approved", "rejected", "changes_requested"]},
                             "user_message": string(10000), "source": string(4000)}),
    "record_change": obj({"run_id": ID, "unit_ids": array(ID), "user_message": string(10000), "source": string(4000)}),
    "resolve_change": obj({"change_id": ID, "status": {"type": "string", "enum": ["contract_resolved", "cancelled"]},
                            "target_refs": REFS, "user_message": string(10000), "source": string(4000)}, ["change_id", "status"]),
    "workflow_status": obj({"run_id": ID}),
    "acquire_lease": obj({"run_id": ID, "unit_id": ID, "stage_run_id": ID, "owner": ID,
                           "ttl_seconds": {"type": "integer", "minimum": 1, "maximum": 3600}}, ["run_id", "unit_id", "stage_run_id", "owner"]),
    "release_lease": obj({"lease_id": ID, "owner": ID}),
}
READ_ONLY = {"get_artifact", "list_artifacts", "diff_artifacts", "workflow_status"}
for _operation, _schema in SCHEMAS.items():
    if _operation not in READ_ONLY:
        _schema["properties"]["request_id"] = ID


def validate(value, schema, location="input"):
    """Small strict validator for the schema subset exported by this module."""
    import re
    declared = schema.get("type")
    types = declared if isinstance(declared, list) else [declared]
    matches = {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
               "integer": type(value) is int, "boolean": type(value) is bool, "null": value is None}
    if declared and not any(matches.get(t, False) for t in types):
        fail("invalid_input", f"{location}: invalid type")
    if "enum" in schema and value not in schema["enum"]:
        fail("invalid_input", f"{location}: unsupported value")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                fail("invalid_input", f"{location}: missing {required}")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            fail("invalid_input", f"{location}: unknown fields")
        for key, child in value.items():
            if key in properties:
                validate(child, properties[key], f"{location}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 1000000):
            fail("invalid_input", f"{location}: invalid list size")
        for i, child in enumerate(value):
            validate(child, schema.get("items", {}), f"{location}[{i}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1000000):
            fail("invalid_input", f"{location}: invalid string length")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            fail("invalid_input", f"{location}: invalid format")
    if type(value) is int and (value < schema.get("minimum", value) or value > schema.get("maximum", value)):
        fail("invalid_input", f"{location}: out of bounds")


def slot(run_id, artifact_id):
    return run_id + "/" + artifact_id


def _unique(values, label):
    if len(values) != len(set(values)):
        fail("duplicate_id", f"Duplicate {label}")


class Workflow:
    def __init__(self, journal):
        self.journal = journal
        self._local = threading.local()

    @staticmethod
    def operations():
        return copy.deepcopy(SCHEMAS)

    def execute(self, operation, params):
        if operation not in SCHEMAS:
            fail("unknown_operation", "Unknown workflow operation")
        validate(params, SCHEMAS[operation])
        try:
            raw = encoded(params)
        except (ValueError, TypeError):
            fail("invalid_input", "Input must be finite JSON")
        if len(raw) > 2 * 1024 * 1024:
            fail("input_too_large", "Workflow input exceeds 2 MiB")
        scan_secrets(raw)
        if operation in READ_ONLY:
            return self._operate(self.journal.read(), operation, copy.deepcopy(params))
        request = copy.deepcopy(params)
        request_id = request.pop("request_id", None)
        fingerprint = sha256(encoded({"operation": operation, "params": request}))
        def transaction(state):
            run_id = self._operation_run_id(state, operation, request)
            if run_id in state.get("runs", {}):
                self._require_runtime(state, run_id)
            key = "workflow/" + request_id if request_id else None
            cached = state.get("requests", {}).get(key) if key else None
            if cached:
                if cached["fingerprint"] != fingerprint:
                    fail("request_conflict", "Request ID was already used with different input")
                return copy.deepcopy(cached["result"])
            result = self._operate(state, operation, request)
            if key:
                state.setdefault("requests", {})[key] = {"fingerprint": fingerprint, "result": copy.deepcopy(result), "at": now()}
            return result
        return self.journal.transaction(transaction)

    def _operation_run_id(self, state, operation, params):
        if params.get("run_id"):
            return params["run_id"]
        for field, table in (("stage_run_id", "stages"), ("review_id", "reviews"), ("change_id", "changes"), ("lease_id", "leases")):
            if params.get(field):
                return state.get(table, {}).get(params[field], {}).get("run_id")
        if params.get("ref"):
            return self._load(state, params["ref"])["manifest"]["run_id"]
        return None

    def _require_runtime(self, state, run_id):
        from .registry import runtime_release
        run = self._run(state, run_id)
        pinned = run.get("standard_release") or state.get("project", {}).get("standard_release")
        if not pinned:
            fail("run_release_unknown", "Run has no runtime provenance; inspect it read-only and use explicit migration")
        current = runtime_release()
        if pinned != current:
            fail("release_mismatch", f"Run requires release {pinned}; current runtime is {current}. Resume with the pinned release or explicitly migrate; no state was changed.")
        return pinned

    def _run(self, state, run_id):
        run = state.get("runs", {}).get(run_id)
        if not run:
            fail("unknown_run", "Run is not registered")
        return run

    def _load(self, state, ref):
        validate(ref, REF, "artifact_ref")
        entry = state.get("artifacts", {}).get(ref["revision_id"])
        if not entry or entry["ref"] != ref:
            fail("artifact_mismatch", "Artifact reference does not match immutable revision")
        if getattr(self._local, "state", None) is not state:
            self._local.state, self._local.artifacts = state, {}
        if ref["revision_id"] in self._local.artifacts:
            return self._local.artifacts[ref["revision_id"]]
        raw = self.journal.get_blob(entry["manifest_oid"])
        if sha256(raw) != ref["sha256"]:
            fail("artifact_integrity", "Artifact manifest hash mismatch")
        try:
            manifest = json.loads(raw)
            payload_raw = self.journal.get_blob(manifest["payload_oid"])
            report_raw = self.journal.get_blob(manifest["report_oid"])
            if sha256(payload_raw) != manifest["payload_sha256"] or sha256(report_raw) != manifest["report_sha256"]:
                fail("artifact_integrity", "Artifact body hash mismatch")
            payload, report = json.loads(payload_raw), report_raw.decode("utf-8")
            validate(payload, PAYLOADS[manifest["kind"]], "payload")
        except (KeyError, ValueError, UnicodeError):
            fail("artifact_integrity", "Artifact contains invalid data")
        loaded = {"manifest": manifest, "payload": payload, "report": report, "ref": copy.deepcopy(ref)}
        self._local.artifacts[ref["revision_id"]] = loaded
        return loaded

    def load_artifact(self, ref):
        return copy.deepcopy(self._load(self.journal.read(), ref))

    def store_evidence_artifact(self, state, *, artifact_id, kind, run_id, unit_id, payload, report, input_refs, stage_run_id=None):
        """Trusted execution integration, called inside its existing transaction.

        Not a public operation: callers cannot submit test results through MCP.
        The execution module must validate actual runner/source results first.
        """
        if kind not in EVIDENCE_KINDS:
            fail("invalid_kind", "Execution evidence helper accepts receipt/report kinds only")
        identifier(artifact_id); self._run(state, run_id)
        validate(payload, PAYLOADS[kind]); validate(input_refs, REFS)
        self._require_refs(state, input_refs, run_id, fresh=False)
        stage = None
        if stage_run_id is not None:
            stage = state.get("stages", {}).get(stage_run_id)
            required_skill = "dev-implement" if kind == "implementation-receipt" else "dev-verify"
            if (not stage or stage["run_id"] != run_id or stage.get("unit_id") != unit_id or stage["skill"] != required_skill
                    or stage["status"] != "running"):
                fail("scope_mismatch", "Execution artifact must belong to its running producer stage")
        payload_raw, report_raw = encoded(payload), report.encode("utf-8")
        scan_secrets(payload_raw); scan_secrets(report_raw)
        head = self._head(state, run_id, artifact_id)
        manifest = {"schema_version": 2, "artifact_id": artifact_id, "revision_id": uid("rev"), "kind": kind, "run_id": run_id,
                    "unit_id": unit_id, "stage_run_id": stage_run_id, "created_at": now(), "input_refs": input_refs,
                    "supersedes": head["revision_id"], "payload_oid": self.journal.put_blob(payload_raw), "payload_sha256": sha256(payload_raw),
                    "report_oid": self.journal.put_blob(report_raw), "report_sha256": sha256(report_raw)}
        raw = encoded(manifest)
        ref = {"artifact_id": artifact_id, "revision_id": manifest["revision_id"], "sha256": sha256(raw)}
        state.setdefault("artifacts", {})[ref["revision_id"]] = {"ref": ref, "manifest_oid": self.journal.put_blob(raw)}
        state.setdefault("heads", {})[slot(run_id, artifact_id)] = {"revision_id": ref["revision_id"], "generation": head["generation"] + 1}
        if stage is not None:
            stage.setdefault("output_refs", []).append(ref)
        emit(state, "execution_artifact_recorded", {"ref": ref, "kind": kind})
        return {"ref": ref, "manifest": manifest}

    def _head(self, state, run_id, artifact_id):
        return state.get("heads", {}).get(slot(run_id, artifact_id), {"revision_id": None, "generation": 0})

    def _fresh(self, state, ref, seen=None):
        seen = set() if seen is None else seen
        if ref["revision_id"] in seen:
            return []
        seen.add(ref["revision_id"])
        loaded = self._load(state, ref)
        manifest = loaded["manifest"]
        head = self._head(state, manifest["run_id"], ref["artifact_id"])
        issues = [] if head["revision_id"] == ref["revision_id"] else [ref["revision_id"] + ": not accepted head"]
        for dependency in manifest["input_refs"]:
            issues.extend(self._fresh(state, dependency, seen))
        return issues

    def _require_refs(self, state, refs, run_id, fresh=True):
        _unique([r["revision_id"] for r in refs], "artifact reference")
        loaded = [self._load(state, ref) for ref in refs]
        if any(a["manifest"]["run_id"] != run_id for a in loaded):
            fail("scope_mismatch", "Artifact belongs to a different run")
        if fresh:
            issues = [issue for ref in refs for issue in self._fresh(state, ref)]
            if issues:
                fail("stale_input", "; ".join(issues))
        return loaded

    @staticmethod
    def _one(loaded, kind):
        selected = [a for a in loaded if a["manifest"]["kind"] == kind]
        if len(selected) != 1:
            fail("missing_input", f"Exactly one {kind} artifact is required")
        return selected[0]

    def _require_dependency(self, loaded, dependency):
        if dependency["ref"] not in loaded["manifest"]["input_refs"]:
            fail("pin_mismatch", "Artifact dependency does not pin the supplied input")

    def _validate_payload(self, state, kind, payload, loaded, unit_id):
        validate(payload, PAYLOADS[kind], "payload")
        if kind == "requirements":
            self._one(loaded, "discovery-context")
            requirements = payload["requirements"]
            _unique([r["id"] for r in requirements], "requirement")
            _unique([c for r in requirements for c in r["case_ids"]], "case")
        elif kind == "system-design":
            req = self._one(loaded, "requirements")
            context = self._one(loaded, "discovery-context")
            self._require_dependency(req, context)
            expected = {r["id"] for r in req["payload"]["requirements"]}
            if set(payload["requirement_ids"]) != expected:
                fail("missing_coverage", "System must cover every requirement")
            _unique(payload["requirement_ids"], "requirement")
        elif kind == "unit-spec":
            if not unit_id:
                fail("invalid_scope", "unit-spec requires unit_id")
            system = self._one(loaded, "system-design")
            req_inputs = [self._load(state, ref) for ref in system["manifest"]["input_refs"]]
            req = self._one(req_inputs, "requirements")
            requirements = {r["id"]: set(r["case_ids"]) for r in req["payload"]["requirements"]}
            if not set(payload["requirement_ids"]) <= set(requirements):
                fail("missing_coverage", "Unit refers to unknown requirements")
            cases = set().union(*(requirements[r] for r in payload["requirement_ids"]))
            if not set(payload["case_ids"]) <= cases:
                fail("missing_coverage", "Unit cases lack requirement provenance")
            _unique(payload["requirement_ids"], "requirement")
            _unique(payload["case_ids"], "case")
        elif kind == "test-plan":
            unit = self._one(loaded, "unit-spec")
            if not unit_id or unit["manifest"].get("unit_id") != unit_id or payload["unit_ref"] != unit["ref"]:
                fail("pin_mismatch", "Test plan must pin the exact unit revision and scope")
            _unique([c["check_id"] for c in payload["checks"]], "check")
            required = set()
            for check in payload["checks"]:
                safe_relative(check["cwd"])
                mode, parser = check.get("evidence_mode", "case-results"), check.get("parser", "team-json")
                if (mode, parser) not in {("case-results", "team-json"), ("command-exit", "exit-code")}:
                    fail("invalid_check_parser", "Evidence mode and parser must be an approved supported pair")
                if mode == "command-exit" and not {"evidence_mode", "parser"} <= set(check):
                    fail("invalid_check_parser", "Command-exit evidence requires explicit evidence_mode and parser")
                _unique(check["case_ids"], "case")
                if not set(check["case_ids"]) <= set(unit["payload"]["case_ids"]):
                    fail("missing_coverage", "Check refers to an unknown unit case")
                if check["required"]:
                    required.update(check["case_ids"])
            if required != set(unit["payload"]["case_ids"]):
                fail("missing_coverage", "Required checks must cover every unit case")

    def _approved_a(self, state, run_id):
        candidates = [r for r in state.get("reviews", {}).values() if r["run_id"] == run_id and r["gate"] == "A"]
        for review in sorted(candidates, key=lambda r: (r["created_at"], r["review_id"]), reverse=True):
            if self._review_approved(state, review):
                return review
        fail("gate_a_required", "A fresh Gate A user decision is required")

    def _review_approved(self, state, review):
        decision = state.get("decisions", {}).get(review.get("decision_id"))
        if not decision or decision["decision"] != "approved" or self._review_issues(state, review):
            return False
        for newer in state.get("reviews", {}).values():
            if (newer["run_id"] == review["run_id"] and newer["gate"] == review["gate"] and newer.get("unit_id") == review.get("unit_id")
                    and newer.get("decision_id") and (newer["created_at"], newer["review_id"]) > (review["created_at"], review["review_id"])
                    and not self._review_issues(state, newer)):
                return False
        return True

    def _review_issues(self, state, review):
        issues = [issue for ref in review["input_refs"] for issue in self._fresh(state, ref)]
        if review["gate"] == "B":
            parent = state.get("reviews", {}).get(review.get("gate_a_review_id"))
            if not parent or not self._review_approved(state, parent):
                issues.append("Gate A is not currently approved")
        return issues

    def _basis(self, state, run_id, unit_id, check_changes=True):
        run = self._run(state, run_id)
        self._require_runtime(state, run_id)
        gate_a = self._approved_a(state, run_id)
        for review in sorted(state.get("reviews", {}).values(), key=lambda r: (r["created_at"], r["review_id"]), reverse=True):
            if review["run_id"] != run_id or review["gate"] != "B" or review.get("unit_id") != unit_id:
                continue
            if review.get("gate_a_review_id") != gate_a["review_id"] or not self._review_approved(state, review):
                continue
            loaded = self._require_refs(state, review["input_refs"], run_id)
            unit, test = self._one(loaded, "unit-spec"), self._one(loaded, "test-plan")
            if check_changes:
                for change in state.get("changes", {}).values():
                    if change["run_id"] != run_id or (change["unit_ids"] and unit_id not in change["unit_ids"]):
                        continue
                    if change["status"] == "requested":
                        fail("change_pending", "Requested change blocks the previous contract")
                    if change["status"] == "contract_resolved":
                        targets = change.get("target_refs", [])
                        if unit["ref"] not in targets or test["ref"] not in targets or any(self._fresh(state, r) for r in targets):
                            fail("change_target_mismatch", "Resolved change does not match the implementation contract")
            return {"review_id": review["review_id"], "unit_ref": unit["ref"], "test_ref": test["ref"],
                    "gate_a_review_id": gate_a["review_id"], "workspace_id": run["workspace_id"]}
        fail("gate_b_required", "A fresh composite Gate B user decision is required")

    def implementation_basis(self, run_id, unit_id):
        identifier(run_id); identifier(unit_id)
        return self._basis(self.journal.read(), run_id, unit_id)

    def _stage(self, state, stage_id, owner, running=True):
        stage = state.get("stages", {}).get(stage_id)
        if not stage:
            fail("unknown_stage", "Stage does not exist")
        if stage["owner"] != owner:
            fail("owner_mismatch", "Stage belongs to another cooperative owner")
        if running and stage["status"] != "running":
            fail("stage_not_running", "Stage is not running")
        return stage

    def _stage_preconditions(self, state, run_id, skill, refs, unit_id):
        loaded = self._require_refs(state, refs, run_id)
        requirements = {"dev-requirements": "discovery-context", "dev-system-design": "requirements", "dev-unit-design": "system-design",
                        "dev-test-design": "unit-spec"}
        if skill in requirements:
            self._one(loaded, requirements[skill])
        if skill in {"dev-unit-design", "dev-test-design"}:
            self._approved_a(state, run_id)
            if not unit_id:
                fail("invalid_scope", "Unit stage requires unit_id")
        if skill in {"dev-implement", "dev-verify"}:
            if not unit_id:
                fail("invalid_scope", "Implementation/verification requires unit_id")
            basis = self._basis(state, run_id, unit_id)
            if basis["unit_ref"] not in refs or basis["test_ref"] not in refs:
                fail("pin_mismatch", "Stage inputs must include approved unit and test plan")

    def _accept(self, state, ref, expected):
        loaded = self._load(state, ref)
        manifest = loaded["manifest"]
        if manifest["kind"] not in KINDS:
            fail("invalid_kind", "Execution receipt heads are managed by the execution module")
        self._require_refs(state, manifest["input_refs"], manifest["run_id"])
        key = slot(manifest["run_id"], ref["artifact_id"])
        current = self._head(state, manifest["run_id"], ref["artifact_id"])
        if current["revision_id"] != expected["revision_id"] or current["generation"] != expected["generation"]:
            fail("head_conflict", "Accepted head changed; candidate was preserved")
        if current["revision_id"] == ref["revision_id"]:
            return copy.deepcopy(current)
        if state["artifacts"][ref["revision_id"]].get("accepted_generation") is not None:
            fail("superseded_revision", "A superseded accepted revision cannot be restored as head; publish a new revision")
        head = {"revision_id": ref["revision_id"], "generation": current["generation"] + 1}
        state.setdefault("heads", {})[key] = head
        state["artifacts"][ref["revision_id"]]["accepted_generation"] = head["generation"]
        emit(state, "artifact_accepted", {"ref": ref, "previous": current})
        return copy.deepcopy(head)

    def _operate(self, state, operation, p):
        if operation == "create_run":
            if p["workspace_id"] not in state.get("workspaces", {}):
                fail("unknown_workspace", "Workspace is not registered")
            if p["run_id"] in state.get("runs", {}):
                existing = state["runs"][p["run_id"]]
                if all(existing.get(k) == v for k, v in p.items()):
                    return copy.deepcopy(existing)
                fail("run_exists", "Run already exists with different input")
            from .registry import runtime_release
            run = {**p, "standard_release": runtime_release(), "created_at": now()}
            state.setdefault("runs", {})[p["run_id"]] = run
            emit(state, "run_created", run)
            return copy.deepcopy(run)
        if operation == "get_artifact":
            return self._load(state, p["ref"])
        if operation == "list_artifacts":
            self._run(state, p["run_id"])
            result = []
            for item in state.get("artifacts", {}).values():
                loaded = self._load(state, item["ref"])
                m = loaded["manifest"]
                if m["run_id"] == p["run_id"] and ("kind" not in p or m["kind"] == p["kind"]) and ("unit_id" not in p or m.get("unit_id") == p["unit_id"]):
                    result.append({"ref": loaded["ref"], "kind": m["kind"], "unit_id": m.get("unit_id"),
                                   "head": self._head(state, m["run_id"], loaded["ref"]["artifact_id"]), "freshness_issues": self._fresh(state, loaded["ref"])})
            return {"artifacts": result}
        if operation == "diff_artifacts":
            a, b = self._load(state, p["before"]), self._load(state, p["after"])
            if a["ref"]["artifact_id"] != b["ref"]["artifact_id"] or a["manifest"]["run_id"] != b["manifest"]["run_id"]:
                fail("scope_mismatch", "Diff requires revisions of one logical artifact")
            return {"before": p["before"], "after": p["after"], "report_diff": "".join(difflib.unified_diff(a["report"].splitlines(True), b["report"].splitlines(True))),
                    "payload_changed": a["payload"] != b["payload"]}
        if operation == "workflow_status":
            run = self._run(state, p["run_id"])
            reviews = [{"review_id": r["review_id"], "gate": r["gate"], "unit_id": r.get("unit_id"), "approved": self._review_approved(state, r),
                        "freshness_issues": self._review_issues(state, r)} for r in state.get("reviews", {}).values() if r["run_id"] == p["run_id"]]
            return {"run": copy.deepcopy(run), "projection": {"reviews": reviews, "heads": {k: copy.deepcopy(v) for k, v in state.get("heads", {}).items() if k.startswith(p["run_id"] + "/")},
                    "changes": [copy.deepcopy(c) for c in state.get("changes", {}).values() if c["run_id"] == p["run_id"]],
                    "stages": [copy.deepcopy(s) for s in state.get("stages", {}).values() if s["run_id"] == p["run_id"]],
                    "recorded_applied": {k: v for k, v in state.get("applied", {}).items() if k.startswith(p["run_id"] + "/")},
                    "recorded_verification": [{k: copy.deepcopy(v.get(k)) for k in ("campaign_id", "implementation_id", "unit_id", "outcome", "test_ref")}
                                              for v in state.get("verification", {}).values() if v.get("run_id") == p["run_id"]],
                    "source_freshness": "not_observed; use execution.get_verification"}, "security_notice": NOTICE}
        if operation == "start_stage":
            self._run(state, p["run_id"])
            self._stage_preconditions(state, p["run_id"], p["skill"], p["input_refs"], p.get("unit_id"))
            stage = {**p, "stage_run_id": uid("stage"), "standard_release": self._require_runtime(state, p["run_id"]),
                     "status": "running", "stage_run_status": "running", "outcome": None, "started_at": now(), "output_refs": []}
            state.setdefault("stages", {})[stage["stage_run_id"]] = stage
            emit(state, "stage_started", stage)
            return copy.deepcopy(stage)
        if operation == "finish_stage":
            stage = self._stage(state, p["stage_run_id"], p["owner"])
            outputs = p.get("output_refs", stage["output_refs"])
            self._require_refs(state, outputs, stage["run_id"], fresh=False)
            if any(r not in stage["output_refs"] for r in outputs):
                fail("scope_mismatch", "Output was not produced by this stage")
            stage.update({"status": p["status"], "outcome": p["status"], "stage_run_status": STAGE_STATUS[p["status"]],
                          "finished_at": now(), "output_refs": outputs, "notes": p.get("notes", "")})
            emit(state, "stage_finished", {"stage_run_id": stage["stage_run_id"], "status": stage["status"]})
            return copy.deepcopy(stage)
        if operation == "resume_stage":
            stage = self._stage(state, p["stage_run_id"], p["owner"], False)
            if stage["status"] not in {"interrupted", "blocked", "waiting_input", "waiting_tool"}:
                fail("invalid_transition", "Only interrupted or blocked stages may resume")
            self._stage_preconditions(state, stage["run_id"], stage["skill"], stage["input_refs"], stage.get("unit_id"))
            stage.update({"status": "running", "stage_run_status": "running", "outcome": None, "resumed_at": now()})
            emit(state, "stage_resumed", {"stage_run_id": stage["stage_run_id"], "owner": p["owner"]})
            return copy.deepcopy(stage)
        if operation == "publish_artifact":
            self._run(state, p["run_id"])
            stage = self._stage(state, p["stage_run_id"], p["owner"])
            if stage["run_id"] != p["run_id"] or stage["skill"] != PRODUCERS[p["kind"]] or stage.get("unit_id") != p.get("unit_id"):
                fail("scope_mismatch", "Artifact does not match its producing stage")
            if p["input_refs"] != stage["input_refs"]:
                fail("pin_mismatch", "Artifact inputs must exactly match stage pins")
            self._stage_preconditions(state, p["run_id"], stage["skill"], p["input_refs"], p.get("unit_id"))
            loaded = self._require_refs(state, p["input_refs"], p["run_id"])
            self._validate_payload(state, p["kind"], p["payload"], loaded, p.get("unit_id"))
            head = self._head(state, p["run_id"], p["artifact_id"])
            if head["revision_id"]:
                previous = self._load(state, state["artifacts"][head["revision_id"]]["ref"])
                if previous["manifest"]["kind"] != p["kind"] or previous["manifest"].get("unit_id") != p.get("unit_id"):
                    fail("scope_mismatch", "Logical artifact cannot change kind or unit")
            payload_raw, report_raw = encoded(p["payload"]), p["report"].encode("utf-8")
            manifest = {"schema_version": 2, "artifact_id": p["artifact_id"], "revision_id": uid("rev"), "kind": p["kind"], "run_id": p["run_id"],
                        "unit_id": p.get("unit_id"), "stage_run_id": p["stage_run_id"], "created_at": now(), "input_refs": p["input_refs"],
                        "supersedes": head["revision_id"], "payload_oid": self.journal.put_blob(payload_raw), "payload_sha256": sha256(payload_raw),
                        "report_oid": self.journal.put_blob(report_raw), "report_sha256": sha256(report_raw)}
            raw = encoded(manifest)
            ref = {"artifact_id": p["artifact_id"], "revision_id": manifest["revision_id"], "sha256": sha256(raw)}
            state.setdefault("artifacts", {})[ref["revision_id"]] = {"ref": ref, "manifest_oid": self.journal.put_blob(raw)}
            stage["output_refs"].append(ref)
            emit(state, "artifact_published", {"ref": ref, "accepted": p.get("accept", False)})
            accepted = None
            if p.get("accept", False):
                if "expected_head" not in p:
                    fail("invalid_input", "Accepting requires expected_head")
                accepted = self._accept(state, ref, p["expected_head"])
            return {"ref": ref, "manifest": manifest, "head": accepted, "status": "accepted" if accepted else "candidate"}
        if operation == "accept_artifact":
            return {"ref": p["ref"], "head": self._accept(state, p["ref"], p["expected_head"]), "status": "accepted"}
        if operation == "create_review":
            self._run(state, p["run_id"])
            loaded = self._require_refs(state, p["input_refs"], p["run_id"])
            gate_a = None
            if p["gate"] == "A":
                if p.get("unit_id"):
                    fail("invalid_scope", "Gate A does not accept unit_id")
                context = self._one(loaded, "discovery-context")
                req, system = self._one(loaded, "requirements"), self._one(loaded, "system-design")
                self._require_dependency(req, context); self._require_dependency(system, context); self._require_dependency(system, req)
            else:
                if not p.get("unit_id"):
                    fail("invalid_scope", "Gate B requires unit_id")
                gate_a = self._approved_a(state, p["run_id"])
                unit, test = self._one(loaded, "unit-spec"), self._one(loaded, "test-plan")
                if unit["manifest"]["unit_id"] != p["unit_id"] or test["manifest"]["unit_id"] != p["unit_id"] or test["payload"]["unit_ref"] != unit["ref"]:
                    fail("pin_mismatch", "Gate B unit/test plan scope and pins must match")
                self._require_dependency(test, unit)
                system = self._one([self._load(state, r) for r in gate_a["input_refs"]], "system-design")
                self._require_dependency(unit, system)
            review = {**p, "review_id": uid("review"), "created_at": now(), "gate_a_review_id": gate_a["review_id"] if gate_a else None}
            review["bundle_sha256"] = sha256(encoded({"gate": p["gate"], "run_id": p["run_id"], "unit_id": p.get("unit_id"), "input_refs": p["input_refs"], "gate_a_review_id": review["gate_a_review_id"]}))
            state.setdefault("reviews", {})[review["review_id"]] = review
            emit(state, "review_created", {"review_id": review["review_id"], "bundle_sha256": review["bundle_sha256"]})
            return copy.deepcopy(review)
        if operation == "record_decision":
            review = state.get("reviews", {}).get(p["review_id"])
            if not review:
                fail("unknown_review", "Review is not registered")
            if self._review_issues(state, review):
                fail("stale_review", "Presented review is no longer fresh")
            if review.get("decision_id"):
                old = state["decisions"][review["decision_id"]]
                if all(old[k] == p[k] for k in p):
                    return copy.deepcopy(old)
                fail("decision_exists", "Decision is immutable; present a new review")
            decision = {**p, "decision_id": uid("decision"), "bundle_sha256": review["bundle_sha256"], "recorded_at": now(), "provenance": "caller-supplied; not authenticated"}
            state.setdefault("decisions", {})[decision["decision_id"]] = decision
            review["decision_id"] = decision["decision_id"]
            emit(state, "decision_recorded", decision)
            return copy.deepcopy(decision)
        if operation == "record_change":
            self._run(state, p["run_id"])
            _unique(p["unit_ids"], "unit")
            change = {**p, "change_id": uid("change"), "status": "requested", "created_at": now(), "target_refs": []}
            state.setdefault("changes", {})[change["change_id"]] = change
            emit(state, "change_requested", change)
            return copy.deepcopy(change)
        if operation == "resolve_change":
            change = state.get("changes", {}).get(p["change_id"])
            if not change:
                fail("unknown_change", "Change is not registered")
            if change["status"] not in {"requested", "contract_resolved"}:
                fail("invalid_transition", "Change is already terminal")
            if p["status"] == "cancelled":
                if not p.get("user_message") or not p.get("source"):
                    fail("user_decision_required", "Cancellation requires actual user message and source")
                change.update({"status": "cancelled", "cancellation": {"user_message": p["user_message"], "source": p["source"], "at": now()}})
            else:
                refs = p.get("target_refs", [])
                self._require_refs(state, refs, change["run_id"])
                units = change["unit_ids"] or sorted({self._load(state, r)["manifest"].get("unit_id") for r in refs if self._load(state, r)["manifest"].get("unit_id")})
                if not units:
                    fail("missing_target", "Resolved change requires approved target units")
                for unit_id in units:
                    basis = self._basis(state, change["run_id"], unit_id, False)
                    if basis["unit_ref"] not in refs or basis["test_ref"] not in refs:
                        fail("missing_target", "Change targets must include approved unit and test plan")
                change.update({"status": "contract_resolved", "target_refs": refs, "resolved_unit_ids": units, "resolved_at": now()})
            emit(state, "change_resolved", {"change_id": change["change_id"], "status": change["status"], "target_refs": change["target_refs"]})
            return copy.deepcopy(change)
        if operation == "acquire_lease":
            run = self._run(state, p["run_id"])
            stage = self._stage(state, p["stage_run_id"], p["owner"])
            if stage["run_id"] != p["run_id"] or stage.get("unit_id") != p["unit_id"] or stage["skill"] not in {"dev-implement", "dev-verify"}:
                fail("scope_mismatch", "Workspace lease must belong to its running implementation/verification stage")
            self._basis(state, p["run_id"], p["unit_id"])
            current = datetime.now(timezone.utc)
            for lease in state.get("leases", {}).values():
                if lease["workspace_id"] == run["workspace_id"] and not lease.get("released_at"):
                    if lease["owner"] == p["owner"] and lease["stage_run_id"] == p["stage_run_id"]:
                        return copy.deepcopy(lease)
                    fail("lease_conflict", "Workspace has another cooperative writer")
            lease = {**p, "lease_id": uid("lease"), "workspace_id": run["workspace_id"], "acquired_at": now(), "expires_at": (current + timedelta(seconds=p.get("ttl_seconds", 300))).isoformat()}
            state.setdefault("leases", {})[lease["lease_id"]] = lease
            emit(state, "lease_acquired", lease)
            return copy.deepcopy(lease)
        if operation == "release_lease":
            lease = state.get("leases", {}).get(p["lease_id"])
            if not lease:
                fail("unknown_lease", "Lease is not registered")
            if lease["owner"] != p["owner"]:
                fail("owner_mismatch", "Lease belongs to another cooperative owner")
            if not lease.get("released_at"):
                lease["released_at"] = now()
                emit(state, "lease_released", {"lease_id": lease["lease_id"], "owner": p["owner"]})
            return copy.deepcopy(lease)
        fail("unknown_operation", "Unknown workflow operation")
