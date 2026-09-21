"""Synthetic workflow fixtures only: no real user approval or product changes."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from harness.common import HarnessError, encoded, sha256
from harness.workflow import Workflow, KINDS, PAYLOADS, SCHEMAS, slot


class MemoryJournal:
    """Transactional fake tests core without a Git executable or product IO."""
    def __init__(self):
        self.state = {"schema_version": 2, "project": {"project_id": "fixture-only"}, "workspaces": {"work": {"root": "SYNTHETIC-UNUSED"}},
                      **{k: {} for k in ("runs", "stages", "artifacts", "heads", "reviews", "decisions", "changes", "implementations", "verification", "snapshots", "leases", "requests")}, "events": []}
        self.blobs = {}
        self.writes = 0

    def read(self):
        return copy.deepcopy(self.state)

    def transaction(self, callback):
        candidate = self.read()
        result = callback(candidate)
        self.state = candidate
        self.writes += 1
        return result

    def put_blob(self, raw):
        oid = sha256(raw)
        self.blobs[oid] = raw
        return oid

    def get_blob(self, oid):
        return self.blobs[oid]


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.journal = MemoryJournal()
        self.workflow = Workflow(self.journal)
        self.call("create_run", run_id="run", workspace_id="work", goal="SYNTHETIC FIXTURE ONLY")

    def call(self, operation, **params):
        return self.workflow.execute(operation, params)

    def assertCode(self, code, operation, **params):
        before = encoded(self.journal.state)
        with self.assertRaises(HarnessError) as caught:
            self.call(operation, **params)
        self.assertEqual(code, caught.exception.code)
        self.assertEqual(before, encoded(self.journal.state), "Failed transaction changed state")

    def publish(self, kind, payload, refs=None, unit=None, accept=True, artifact_id=None, report=None):
        names = dict(zip(KINDS, ("dev-discover", "dev-requirements", "dev-system-design", "dev-unit-design", "dev-test-design", "dev-review")))
        params = dict(run_id="run", skill=names[kind], owner="fixture-owner", input_refs=refs or [])
        if unit:
            params["unit_id"] = unit
        stage = self.call("start_stage", **params)
        aid = artifact_id or kind
        head = copy.deepcopy(self.journal.read()["heads"].get(slot("run", aid), {"revision_id": None, "generation": 0}))
        args = dict(run_id="run", stage_run_id=stage["stage_run_id"], owner="fixture-owner", artifact_id=aid, kind=kind,
                    payload=payload, report=report or "# SYNTHETIC FIXTURE\n\nNot user approval.", input_refs=refs or [], accept=accept, expected_head=head)
        if unit:
            args["unit_id"] = unit
        output = self.call("publish_artifact", **args)
        self.call("finish_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner", status="succeeded")
        return output["ref"]

    def approve(self, review):
        return self.call("record_decision", review_id=review["review_id"], decision="approved",
                         user_message="SYNTHETIC TEST FIXTURE: approved", source="isolated test fixture; never a user decision")

    def system(self):
        context = self.publish("discovery-context", {"facts": ["SYNTHETIC FIXTURE"]})
        req = self.publish("requirements", {"requirements": [{"id": "req-1", "description": "Fixture behavior", "case_ids": ["case-1", "case-2"]}]}, [context])
        system = self.publish("system-design", {"requirement_ids": ["req-1"]}, [context, req])
        review = self.call("create_review", run_id="run", gate="A", input_refs=[context, req, system])
        self.approve(review)
        return context, req, system, review

    def unit(self):
        context, req, system, gate_a = self.system()
        unit = self.publish("unit-spec", {"requirement_ids": ["req-1"], "case_ids": ["case-1", "case-2"]}, [system], "ui-1")
        payload = {"unit_ref": unit, "checks": [{"check_id": "check-1", "argv": ["python", "--version"], "cwd": ".", "timeout_seconds": 30,
                   "required": True, "expected_exit": 0, "case_ids": ["case-1", "case-2"], "expected": "Fixture expected output", "oracle": "Fixture independent specification"}]}
        test = self.publish("test-plan", payload, [unit], "ui-1")
        gate_b = self.call("create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=[unit, test])
        self.approve(gate_b)
        return context, req, system, unit, test, gate_a, gate_b

    def test_exact_basis_and_artifact_bytes(self):
        _, _, _, unit, test, gate_a, gate_b = self.unit()
        basis = self.workflow.implementation_basis("run", "ui-1")
        self.assertEqual({"review_id": gate_b["review_id"], "unit_ref": unit, "test_ref": test, "gate_a_review_id": gate_a["review_id"], "workspace_id": "work"}, basis)
        self.assertEqual(unit, self.workflow.load_artifact(test)["payload"]["unit_ref"])

    def test_candidate_does_not_replace_head_or_approval(self):
        _, _, system, unit, _, _, _ = self.unit()
        candidate = self.publish("unit-spec", {"requirement_ids": ["req-1"], "case_ids": ["case-1"]}, [system], "ui-1", False)
        self.assertNotEqual(unit, candidate)
        self.assertEqual(unit, self.workflow.implementation_basis("run", "ui-1")["unit_ref"])

    def test_head_cas_keeps_losing_candidate(self):
        first = self.publish("discovery-context", {"facts": ["a"]})
        candidate = self.publish("discovery-context", {"facts": ["b"]}, accept=False)
        third = self.publish("discovery-context", {"facts": ["c"]})
        self.assertCode("head_conflict", "accept_artifact", ref=candidate, expected_head={"revision_id": first["revision_id"], "generation": 1})
        self.assertEqual(candidate, self.workflow.load_artifact(candidate)["ref"])
        self.assertEqual(third["revision_id"], self.journal.state["heads"]["run/discovery-context"]["revision_id"])

    def test_accept_invalidates_dependency_without_deleting_old_records(self):
        _, _, system, unit, test, _, gate_b = self.unit()
        replacement = self.publish("unit-spec", {"requirement_ids": ["req-1"], "case_ids": ["case-1"]}, [system], "ui-1")
        with self.assertRaises(HarnessError) as exc:
            self.workflow.implementation_basis("run", "ui-1")
        self.assertEqual("gate_b_required", exc.exception.code)
        self.assertIn(gate_b["review_id"], self.journal.state["reviews"])
        self.assertEqual(unit, self.workflow.load_artifact(test)["payload"]["unit_ref"])
        self.assertNotEqual(unit, replacement)

    def test_gate_a_cannot_be_skipped(self):
        context = self.publish("discovery-context", {"facts": []})
        self.assertCode("missing_input", "start_stage", run_id="run", skill="dev-unit-design", owner="fixture-owner", input_refs=[context], unit_id="ui-1")

    def test_gate_a_requires_context_and_matching_system_inputs(self):
        context, req, system, _ = self.system()
        self.assertCode("missing_input", "create_review", run_id="run", gate="A", input_refs=[req, system])

    def test_gate_b_rejects_mismatched_unit_plan(self):
        _, _, system, unit, test, _, _ = self.unit()
        replacement = self.publish("unit-spec", {"requirement_ids": ["req-1"], "case_ids": ["case-1"]}, [system], "ui-1")
        self.assertCode("stale_input", "create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=[replacement, test])

    def test_decision_is_idempotent_and_immutable(self):
        _, _, _, review = self.system()
        decision = self.approve(review)
        self.assertEqual(review["review_id"], decision["review_id"])
        self.assertIn("not authenticated", decision["provenance"])
        self.assertCode("decision_exists", "record_decision", review_id=review["review_id"], decision="rejected", user_message="SYNTHETIC reject", source="fixture")

    def test_old_review_cannot_approve_new_context(self):
        _, _, _, review = self.system()
        self.publish("discovery-context", {"facts": ["new"]})
        self.assertCode("stale_review", "record_decision", review_id=review["review_id"], decision="approved", user_message="SYNTHETIC", source="fixture")

    def test_change_blocks_then_resolved_contract_can_implement(self):
        _, _, _, unit, test, _, _ = self.unit()
        change = self.call("record_change", run_id="run", unit_ids=["ui-1"], user_message="SYNTHETIC change intent", source="fixture")
        with self.assertRaises(HarnessError) as exc:
            self.workflow.implementation_basis("run", "ui-1")
        self.assertEqual("change_pending", exc.exception.code)
        resolved = self.call("resolve_change", change_id=change["change_id"], status="contract_resolved", target_refs=[unit, test])
        self.assertEqual("contract_resolved", resolved["status"])
        self.assertEqual(unit, self.workflow.implementation_basis("run", "ui-1")["unit_ref"])

    def test_change_cancellation_requires_user_provenance(self):
        change = self.call("record_change", run_id="run", unit_ids=[], user_message="SYNTHETIC", source="fixture")
        self.assertCode("user_decision_required", "resolve_change", change_id=change["change_id"], status="cancelled")
        self.assertEqual("cancelled", self.call("resolve_change", change_id=change["change_id"], status="cancelled", user_message="SYNTHETIC cancel", source="fixture")["status"])

    def test_caller_cannot_fulfill_change(self):
        self.assertCode("invalid_input", "resolve_change", change_id="absent", status="fulfilled")

    def test_stage_owner_and_resume_validation(self):
        stage = self.call("start_stage", run_id="run", skill="dev-discover", owner="fixture-owner", input_refs=[])
        self.assertCode("owner_mismatch", "finish_stage", stage_run_id=stage["stage_run_id"], owner="other-owner", status="interrupted")
        self.call("finish_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner", status="interrupted")
        self.assertCode("owner_mismatch", "resume_stage", stage_run_id=stage["stage_run_id"], owner="other-owner")
        self.assertEqual("running", self.call("resume_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner")["status"])

    def test_completed_stage_cannot_resume(self):
        stage = self.call("start_stage", run_id="run", skill="dev-discover", owner="fixture-owner", input_refs=[])
        self.call("finish_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner", status="no_change")
        self.assertCode("invalid_transition", "resume_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner")

    def test_workspace_lease_owner_and_conflict(self):
        _, _, _, unit, test, _, _ = self.unit()
        a = self.call("start_stage", run_id="run", skill="dev-implement", owner="one", unit_id="ui-1", input_refs=[unit, test])
        b = self.call("start_stage", run_id="run", skill="dev-verify", owner="two", unit_id="ui-1", input_refs=[unit, test])
        lease = self.call("acquire_lease", run_id="run", unit_id="ui-1", stage_run_id=a["stage_run_id"], owner="one")
        self.assertCode("lease_conflict", "acquire_lease", run_id="run", unit_id="ui-1", stage_run_id=b["stage_run_id"], owner="two")
        self.assertCode("owner_mismatch", "release_lease", lease_id=lease["lease_id"], owner="two")
        self.call("release_lease", lease_id=lease["lease_id"], owner="one")
        self.assertEqual("two", self.call("acquire_lease", run_id="run", unit_id="ui-1", stage_run_id=b["stage_run_id"], owner="two")["owner"])

    def test_read_operations_do_not_write(self):
        _, _, _, unit, test, _, _ = self.unit()
        before, count = encoded(self.journal.state), self.journal.writes
        self.call("workflow_status", run_id="run")
        self.call("list_artifacts", run_id="run")
        self.call("get_artifact", ref=test)
        self.call("diff_artifacts", before=unit, after=unit)
        self.workflow.implementation_basis("run", "ui-1")
        self.assertEqual(before, encoded(self.journal.state))
        self.assertEqual(count, self.journal.writes)

    def test_exact_sha_and_blob_integrity(self):
        context = self.publish("discovery-context", {"facts": []})
        bad = {**context, "sha256": "0" * 64}
        self.assertCode("artifact_mismatch", "get_artifact", ref=bad)
        oid = self.journal.state["artifacts"][context["revision_id"]]["manifest_oid"]
        self.journal.blobs[oid] = b"{}"
        self.assertCode("artifact_integrity", "get_artifact", ref=context)

    def test_test_plan_required_coverage_and_cwd(self):
        _, _, system, _ = self.system()
        unit = self.publish("unit-spec", {"requirement_ids": ["req-1"], "case_ids": ["case-1", "case-2"]}, [system], "ui-1")
        stage = self.call("start_stage", run_id="run", skill="dev-test-design", owner="fixture-owner", input_refs=[unit], unit_id="ui-1")
        check = {"check_id": "check-1", "argv": ["python"], "cwd": ".", "timeout_seconds": 1, "required": True, "expected_exit": 0,
                 "case_ids": ["case-1"], "expected": "fixture", "oracle": "independent fixture"}
        args = dict(run_id="run", stage_run_id=stage["stage_run_id"], owner="fixture-owner", artifact_id="test-plan", kind="test-plan", unit_id="ui-1", report="# fixture", input_refs=[unit])
        self.assertCode("missing_coverage", "publish_artifact", **args, payload={"unit_ref": unit, "checks": [check]})
        check.update(cwd="../escape", case_ids=["case-1", "case-2"])
        self.assertCode("invalid_path", "publish_artifact", **args, payload={"unit_ref": unit, "checks": [check]})

    def test_strict_schema_rejects_boolean_timeout_and_unknown_input(self):
        self.assertCode("invalid_input", "create_run", run_id="new", workspace_id="work", goal="fixture", approve=True)
        self.assertCode("invalid_input", "acquire_lease", run_id="run", unit_id="ui-1", stage_run_id="stage", owner="owner", ttl_seconds=True)

    def test_evidence_parser_contract_defaults_and_explicit_command_exit(self):
        _, _, system, _ = self.system()
        unit = self.publish("unit-spec", {"requirement_ids": ["req-1"], "case_ids": ["case-1", "case-2"]}, [system], "ui-1")
        base = {"check_id": "check-1", "argv": ["python", "--version"], "cwd": ".", "timeout_seconds": 1, "required": True, "expected_exit": 0,
                "case_ids": ["case-1", "case-2"], "expected": "SYNTHETIC explicit command condition", "oracle": "SYNTHETIC specification"}
        stage = self.call("start_stage", run_id="run", skill="dev-test-design", owner="fixture-owner", unit_id="ui-1", input_refs=[unit])
        params = dict(run_id="run", stage_run_id=stage["stage_run_id"], owner="fixture-owner", artifact_id="plan", kind="test-plan", unit_id="ui-1", report="# fixture", input_refs=[unit])
        for altered in ({"evidence_mode": "command-exit"}, {"parser": "exit-code"}, {"evidence_mode": "case-results", "parser": "exit-code"}):
            self.assertCode("invalid_check_parser", "publish_artifact", **params, payload={"unit_ref": unit, "checks": [{**base, **altered}]})
        self.assertCode("invalid_input", "publish_artifact", **params, payload={"unit_ref": unit, "checks": [{**base, "parser": "junit"}]})
        self.assertCode("invalid_input", "publish_artifact", **params, payload={"unit_ref": unit, "checks": [{**base, "case_map": {}}]})
        result = self.call("publish_artifact", **params, payload={"unit_ref": unit, "checks": [{**base, "evidence_mode": "command-exit", "parser": "exit-code"}]})
        self.assertEqual("exit-code", self.workflow.load_artifact(result["ref"])["payload"]["checks"][0]["parser"])

    def test_contract_files_equal_runtime_schema(self):
        base = Path(__file__).resolve().parents[1] / "contracts"
        self.assertEqual(SCHEMAS, json.loads((base / "workflow-operations.json").read_text(encoding="utf-8")))
        self.assertEqual(PAYLOADS, json.loads((base / "artifact-payloads.json").read_text(encoding="utf-8")))

    def test_retry_start_stage_does_not_duplicate_and_changed_input_conflicts(self):
        params = dict(run_id="run", skill="dev-discover", owner="fixture-owner", input_refs=[], request_id="request-one")
        first = self.call("start_stage", **params)
        count = len(self.journal.state["events"])
        self.assertEqual(first, self.call("start_stage", **params))
        self.assertEqual(count, len(self.journal.state["events"]))
        self.assertEqual(1, len(self.journal.state["stages"]))
        self.assertCode("request_conflict", "start_stage", **{**params, "reason": "different request"})

    def test_different_runtime_cannot_resume_or_mutate_existing_run(self):
        stage = self.call("start_stage", run_id="run", skill="dev-discover", owner="fixture-owner", input_refs=[])
        self.call("finish_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner", status="interrupted")
        with patch("harness.registry.runtime_release", return_value="newer-runtime"):
            self.assertCode("release_mismatch", "resume_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner")
            self.assertCode("release_mismatch", "start_stage", run_id="run", skill="dev-discover", owner="fixture-owner", input_refs=[])
            self.assertCode("release_mismatch", "record_change", run_id="run", unit_ids=[], user_message="SYNTHETIC", source="fixture")
            status = self.call("workflow_status", run_id="run")
            self.assertEqual(stage["standard_release"], status["run"]["standard_release"])

    def test_same_project_new_run_can_pin_new_runtime_without_migrating_old_run(self):
        old = copy.deepcopy(self.journal.state["runs"]["run"])
        with patch("harness.registry.runtime_release", return_value="newer-runtime"):
            new = self.call("create_run", run_id="new-run", workspace_id="work", goal="SYNTHETIC new run")
            self.assertEqual("newer-runtime", new["standard_release"])
        self.assertEqual(old, self.journal.state["runs"]["run"])

    def test_implementation_basis_is_release_pinned(self):
        self.unit()
        with patch("harness.registry.runtime_release", return_value="newer-runtime"):
            with self.assertRaises(HarnessError) as caught:
                self.workflow.implementation_basis("run", "ui-1")
            self.assertEqual("release_mismatch", caught.exception.code)

    def test_legacy_run_without_pin_uses_original_project_release_not_current(self):
        self.journal.state["runs"]["run"].pop("standard_release")
        self.journal.state["project"]["standard_release"] = "old-project-runtime"
        with patch("harness.registry.runtime_release", return_value="newer-runtime"):
            self.assertCode("release_mismatch", "start_stage", run_id="run", skill="dev-discover", owner="fixture-owner", input_refs=[])
        self.assertNotIn("standard_release", self.journal.state["runs"]["run"])

    def test_same_create_run_is_idempotent_without_request_id(self):
        before = encoded(self.journal.state)
        self.call("create_run", run_id="run", workspace_id="work", goal="SYNTHETIC FIXTURE ONLY")
        self.assertEqual(before, encoded(self.journal.state))
        self.assertCode("run_exists", "create_run", run_id="run", workspace_id="work", goal="different")

    def test_retry_publish_and_accept_keeps_one_revision(self):
        stage = self.call("start_stage", run_id="run", skill="dev-discover", owner="fixture-owner", input_refs=[])
        params = dict(run_id="run", stage_run_id=stage["stage_run_id"], owner="fixture-owner", artifact_id="context", kind="discovery-context",
                      payload={"facts": []}, report="# SYNTHETIC", input_refs=[], accept=True,
                      expected_head={"revision_id": None, "generation": 0}, request_id="publish-one")
        first = self.call("publish_artifact", **params)
        self.assertEqual(first, self.call("publish_artifact", **params))
        self.assertEqual(1, len(self.journal.state["artifacts"]))

    def test_stage_lifecycle_projection_separate_from_outcome(self):
        stage = self.call("start_stage", run_id="run", skill="dev-discover", owner="fixture-owner", input_refs=[])
        output = self.call("finish_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner", status="succeeded")
        self.assertEqual("completed", output["stage_run_status"])
        self.assertEqual("succeeded", output["outcome"])

    def test_expired_lease_never_proves_previous_writer_stopped(self):
        _, _, _, unit, test, _, _ = self.unit()
        a = self.call("start_stage", run_id="run", skill="dev-implement", owner="one", unit_id="ui-1", input_refs=[unit, test])
        b = self.call("start_stage", run_id="run", skill="dev-verify", owner="two", unit_id="ui-1", input_refs=[unit, test])
        lease = self.call("acquire_lease", run_id="run", unit_id="ui-1", stage_run_id=a["stage_run_id"], owner="one")
        self.journal.state["leases"][lease["lease_id"]]["expires_at"] = "2000-01-01T00:00:00+00:00"
        self.assertCode("lease_conflict", "acquire_lease", run_id="run", unit_id="ui-1", stage_run_id=b["stage_run_id"], owner="two")

    def test_rejected_new_review_does_not_fall_back_to_old_approval(self):
        _, _, _, unit, test, _, _ = self.unit()
        later = self.call("create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=[unit, test])
        self.call("record_decision", review_id=later["review_id"], decision="rejected", user_message="SYNTHETIC new rejection", source="fixture")
        # Git JSON serialization sorts keys; ordering must never depend on UUID order.
        self.journal.state = json.loads(encoded(self.journal.state))
        with self.assertRaises(HarnessError) as exc:
            self.workflow.implementation_basis("run", "ui-1")
        self.assertEqual("gate_b_required", exc.exception.code)

    def test_superseded_head_cannot_resurrect_old_user_approval(self):
        first = self.publish("discovery-context", {"facts": ["a"]})
        second = self.publish("discovery-context", {"facts": ["b"]})
        self.assertCode("superseded_revision", "accept_artifact", ref=first,
                        expected_head={"revision_id": second["revision_id"], "generation": 2})

    def test_execution_artifacts_are_readable_but_not_publicly_forgeable(self):
        _, _, _, unit, test, _, _ = self.unit()
        output = self.journal.transaction(lambda state: self.workflow.store_evidence_artifact(state,
            artifact_id="verification-fixture", kind="verification-report", run_id="run", unit_id="ui-1",
            payload={"outcome": "SYNTHETIC RUNNER FIXTURE"}, report="# Synthetic runner evidence", input_refs=[unit, test]))
        self.assertEqual("SYNTHETIC RUNNER FIXTURE", self.workflow.load_artifact(output["ref"])["payload"]["outcome"])
        stage = self.call("start_stage", run_id="run", skill="dev-review", owner="fixture-owner", input_refs=[unit, test])
        self.assertCode("invalid_input", "publish_artifact", run_id="run", stage_run_id=stage["stage_run_id"], owner="fixture-owner",
                        artifact_id="forged", kind="verification-report", payload={"outcome": "passed"}, report="# forged", input_refs=[unit, test])
        head = self.journal.read()["heads"]["run/verification-fixture"]
        self.assertCode("invalid_kind", "accept_artifact", ref=output["ref"], expected_head=head)

    def test_publishing_after_gate_rejection_rechecks_stage_preconditions(self):
        context, req, system, _ = self.system()
        stage = self.call("start_stage", run_id="run", skill="dev-unit-design", owner="fixture-owner", input_refs=[system], unit_id="ui-1")
        later = self.call("create_review", run_id="run", gate="A", input_refs=[context, req, system])
        self.call("record_decision", review_id=later["review_id"], decision="rejected", user_message="SYNTHETIC rejected", source="fixture")
        self.assertCode("gate_a_required", "publish_artifact", run_id="run", stage_run_id=stage["stage_run_id"], owner="fixture-owner",
                        artifact_id="unit", kind="unit-spec", unit_id="ui-1", payload={"requirement_ids": ["req-1"], "case_ids": ["case-1"]},
                        report="# SYNTHETIC", input_refs=[system])

    def test_execution_receipt_can_finish_its_producing_stage(self):
        _, _, _, unit, test, _, _ = self.unit()
        stage = self.call("start_stage", run_id="run", skill="dev-implement", owner="fixture-owner", unit_id="ui-1", input_refs=[unit, test])
        output = self.journal.transaction(lambda state: self.workflow.store_evidence_artifact(state,
            artifact_id="implementation-fixture", kind="implementation-receipt", run_id="run", unit_id="ui-1",
            payload={"outcome": "SYNTHETIC FIXTURE"}, report="# Fixture applied receipt", input_refs=[unit, test], stage_run_id=stage["stage_run_id"]))
        finished = self.call("finish_stage", stage_run_id=stage["stage_run_id"], owner="fixture-owner", status="succeeded", output_refs=[output["ref"]])
        self.assertEqual([output["ref"]], finished["output_refs"])
        self.assertEqual("completed", finished["stage_run_status"])

    def test_execution_receipt_cannot_claim_a_different_stage_kind(self):
        _, _, _, unit, test, _, _ = self.unit()
        stage = self.call("start_stage", run_id="run", skill="dev-verify", owner="fixture-owner", unit_id="ui-1", input_refs=[unit, test])
        before = encoded(self.journal.state)
        with self.assertRaises(HarnessError) as caught:
            self.journal.transaction(lambda state: self.workflow.store_evidence_artifact(state,
                artifact_id="implementation-fixture", kind="implementation-receipt", run_id="run", unit_id="ui-1", payload={}, report="# Fixture",
                input_refs=[unit, test], stage_run_id=stage["stage_run_id"]))
        self.assertEqual("scope_mismatch", caught.exception.code)
        self.assertEqual(before, encoded(self.journal.state))

    def test_real_journal_roundtrip_preserves_gates_and_readonly_tip(self):
        from harness.history import Journal
        with tempfile.TemporaryDirectory(prefix="harness-workflow-fixture-") as directory:
            root = Path(directory)
            workspace = root / "product"
            workspace.mkdir()
            initial = MemoryJournal().state
            initial["workspaces"]["work"]["root"] = str(workspace)
            journal = Journal(root / "private" / "history.git")
            journal.initialize(initial)
            self.journal, self.workflow = journal, Workflow(journal)
            self.call("create_run", run_id="run", workspace_id="work", goal="SYNTHETIC FIXTURE ONLY")
            _, _, _, unit, _, _, _ = self.unit()
            before = journal._tip()
            self.assertEqual(unit, self.workflow.implementation_basis("run", "ui-1")["unit_ref"])
            self.call("workflow_status", run_id="run")
            self.assertEqual(before, journal._tip())
            self.assertEqual([], list(workspace.iterdir()))


if __name__ == "__main__":
    unittest.main()
