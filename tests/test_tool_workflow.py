"""SYNTHETIC tool-policy integration fixtures; no provider calls or user decisions."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness.api import API
from harness.common import encoded
from harness.workflow import PRODUCERS, Workflow, slot
from tests import test_execution as execution_fixtures
from tests import test_workflow as workflow_fixtures


def capability_plan(unit="ui-1", **modes):
    return [{"capability": capability, "mode": modes.get(capability, "not_applicable"),
             "reason": "SYNTHETIC applicability for isolated contract test", "unit_ids": [unit] if capability in modes else []}
            for capability in ("ui_design", "library_docs", "browser", "database")]


def documentation_observation():
    return {"capability": "library_docs", "provider": "context7", "tool": "context7.resolve-library-id + query-docs",
            "status": "success", "observed_at": "2026-09-21T09:00:00+00:00", "target": "SYNTHETIC-library@1",
            "summary": "SYNTHETIC recorded version decision; no network request", "source_refs": ["https://example.test/docs"],
            "result": {"library": "SYNTHETIC-library", "version": "1", "library_id": "/synthetic/library/v1",
                       "version_checked": True, "sources": [{"url": "https://example.test/docs", "title": "SYNTHETIC reference"}]}}


def local_fallback():
    return {"capability": "ui_design", "provider": "local-design", "tool": "local HTML and Markdown authoring",
            "status": "fallback", "observed_at": "2026-09-21T09:00:00+00:00", "target": "SYNTHETIC UI unit",
            "summary": "SYNTHETIC local design after provider failure; no external writes", "source_refs": ["https://example.test/synthetic-ui"],
            "result": {"report_markdown": "# SYNTHETIC UI\nButton, loading state, and keyboard focus.", "layout_content": "<main><button>SYNTHETIC</button></main>"},
            "failure": {"code": "quota_exceeded", "tool": "figma.use_figma", "detail": "SYNTHETIC quota response fixture"}}


def browser_check(case_ids=None, script="SYNTHETIC-never-executed.py", marker=None):
    return {"check_id": "browser-check", "argv": [sys.executable, script] + ([str(marker)] if marker else []), "cwd": ".",
            "timeout_seconds": 15, "required": True, "expected_exit": 0, "case_ids": case_ids or ["case-1"],
            "expected": "SYNTHETIC fixed invariant and structured evidence", "oracle": "Independent synthetic case specification",
            "runner": {"kind": "project-runner", "evidence": [{"evidence_id": "browser-evidence", "path": "browser.json", "format": "json", "required": True, "max_bytes": 50000}]}}


def browser_binding():
    return [{"capability": "browser", "check_id": "browser-check", "evidence_id": "browser-evidence"}]


def synthetic_browser_observation():
    return {"capability": "browser", "provider": "playwright", "tool": "playwright.page.click",
            "status": "success", "observed_at": "2026-09-21T09:00:00+00:00", "target": "SYNTHETIC isolated application",
            "summary": "SYNTHETIC contract fixture only; no real browser session was opened",
            "source_refs": ["http://127.0.0.1:41234/synthetic"],
            "result": {"url": "http://127.0.0.1:41234/synthetic", "engine": "chromium", "browser_session": "SYNTHETIC-session",
                       "connection_mode": "live", "interaction_count": 1,
                       "checks": [{"name": "SYNTHETIC identity", "expected": "5", "observed": "5", "passed": True}]}}


def synthetic_database_observation(target):
    return {"capability": "database", "provider": "team-sqlserver", "tool": "observe_database",
            "status": "success", "observed_at": "2026-09-21T09:00:00+00:00", "target": target,
            "summary": "SYNTHETIC catalog fixture; no database connection", "source_refs": ["https://example.test/synthetic-catalog"],
            "result": {"engine": "sqlserver", "target_ref": target, "connection_mode": "live", "observation_kind": "catalog",
                       "read_only": True, "rows_observed": 0, "objects": [],
                       "checks": [{"name": "SYNTHETIC empty catalog", "expected": "0", "observed": "0", "passed": True}]}}


class ToolWorkflowTests(unittest.TestCase):
    """Exercise the public workflow boundary without inventing external success."""

    call = workflow_fixtures.WorkflowTest.call
    assertCode = workflow_fixtures.WorkflowTest.assertCode
    approve = workflow_fixtures.WorkflowTest.approve

    def setUp(self):
        self.journal = workflow_fixtures.MemoryJournal()
        self.workflow = Workflow(self.journal)
        self.call("create_run", run_id="run", workspace_id="work", goal="SYNTHETIC tool-policy fixture only")

    def publish_args(self, kind, payload, refs=None, unit=None, artifact_id=None):
        refs = refs or []
        params = {"run_id": "run", "skill": PRODUCERS[kind], "owner": "fixture-owner", "input_refs": refs}
        if unit:
            params["unit_id"] = unit
        stage = self.call("start_stage", **params)
        aid = artifact_id or kind
        args = {"run_id": "run", "stage_run_id": stage["stage_run_id"], "owner": "fixture-owner", "artifact_id": aid,
                "kind": kind, "payload": copy.deepcopy(payload), "report": "# SYNTHETIC ISOLATED FIXTURE\n\nNot user approval or a real provider result.",
                "input_refs": refs, "accept": True,
                "expected_head": copy.deepcopy(self.journal.read()["heads"].get(slot("run", aid), {"revision_id": None, "generation": 0}))}
        if unit:
            args["unit_id"] = unit
        return args

    def publish(self, kind, payload, refs=None, unit=None, artifact_id=None):
        args = self.publish_args(kind, payload, refs, unit, artifact_id)
        result = self.call("publish_artifact", **args)
        self.call("finish_stage", stage_run_id=args["stage_run_id"], owner="fixture-owner", status="succeeded", output_refs=[result["ref"]])
        return result["ref"]

    def requirements(self):
        context = self.publish("discovery-context", {"facts": ["SYNTHETIC fixture, no external account"]})
        requirement = self.publish("requirements", {"requirements": [{"id": "req-1", "description": "SYNTHETIC behavior", "case_ids": ["case-1"]}]}, [context])
        return context, requirement

    @staticmethod
    def system_payload():
        return {"requirement_ids": ["req-1"], "units": [{"unit_id": "ui-1", "title": "SYNTHETIC source unit", "required": True,
                "depends_on": [], "requirement_ids": ["req-1"], "case_ids": ["case-1"]}]}

    def system(self, plan, observations=None):
        context, requirement = self.requirements()
        system = self.publish("system-design", {**self.system_payload(), "tool_plan": plan, "tool_observations": observations or []}, [context, requirement])
        review = self.call("create_review", run_id="run", gate="A", input_refs=[context, requirement, system])
        self.approve(review)
        return context, requirement, system, review

    def unit(self, system, observations=None, checks=None, bindings=None):
        unit = self.publish("unit-spec", {"requirement_ids": ["req-1"], "case_ids": ["case-1"],
                            "environment": {"required": False, "reason": "SYNTHETIC source-only fixture"},
                            "database": {"required": False, "reason": "SYNTHETIC no database"},
                            "tool_observations": observations or []}, [system], "ui-1")
        test = self.publish("test-plan", {"unit_ref": unit, "checks": checks or [browser_check()], "tool_checks": bindings or []}, [unit], "ui-1")
        scope = self.publish("scope-manifest", {"run_id": "run", "workspace_id": "work", "unit_id": "ui-1", "unit_ref": unit,
                             "requirement_ids": ["req-1"], "mode": "observe", "reason": "SYNTHETIC observation only",
                             "source_baseline": {"sha256": "0" * 64}, "files": [], "db_objects": []}, [system, unit], "ui-1")
        return unit, test, scope

    def test_missing_plan_cannot_be_published_for_new_run(self):
        context, requirement = self.requirements()
        args = self.publish_args("system-design", self.system_payload(), [context, requirement])
        self.assertCode("tool_plan_required", "publish_artifact", **args)

    def test_plan_cannot_assign_unknown_unit(self):
        context, requirement = self.requirements()
        plan = capability_plan(unit="not-in-system", library_docs="required")
        args = self.publish_args("system-design", {**self.system_payload(), "tool_plan": plan}, [context, requirement])
        self.assertCode("invalid_tool_plan", "publish_artifact", **args)

    def test_artifact_source_must_exist_and_be_pinned_in_stage_inputs(self):
        context, requirement = self.requirements()
        unpinned = self.publish("discovery-context", {"facts": ["SYNTHETIC unpinned reference"]}, artifact_id="auxiliary-context")
        docs = documentation_observation()
        payload = {**self.system_payload(), "tool_plan": capability_plan(library_docs="required"), "tool_observations": [docs]}
        args = self.publish_args("system-design", payload, [context, requirement])
        args["payload"]["tool_observations"][0]["source_refs"] = ["artifact:nonexistent/nonexistent/" + "0" * 64]
        self.assertCode("artifact_mismatch", "publish_artifact", **args)
        args["payload"]["tool_observations"][0]["source_refs"] = ["artifact:{artifact_id}/{revision_id}/{sha256}".format(**unpinned)]
        self.assertCode("pin_mismatch", "publish_artifact", **args)
        args["payload"]["tool_observations"][0]["source_refs"] = ["artifact:{artifact_id}/{revision_id}/{sha256}".format(**context)]
        published = self.call("publish_artifact", **args)
        self.assertEqual("accepted", published["status"])

    def test_database_evidence_cannot_pass_gate_b_without_pinned_target(self):
        _, _, system, _ = self.system(capability_plan(database="required"))
        bindings = [{"capability": "database", "check_id": "browser-check", "evidence_id": "browser-evidence"}]
        refs = self.unit(system, [synthetic_database_observation("SYNTHETIC-unpinned-database")], bindings=bindings)
        self.assertCode("tool_database_target_required", "create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=list(refs))

    def test_database_observation_of_other_target_cannot_pass_gate_b(self):
        _, _, system, _ = self.system(capability_plan(database="required"))
        unit = self.publish("unit-spec", {"requirement_ids": ["req-1"], "case_ids": ["case-1"],
                            "environment": {"required": True}, "database": {"required": False, "reason": "SYNTHETIC catalog read only"},
                            "tool_observations": [synthetic_database_observation("SYNTHETIC-other-database")]}, [system], "ui-1")
        environment = self.publish("environment-contract", {"unit_ref": unit, "profile_id": "synthetic-profile", "profile_revision": "SYNTHETIC-profile-v1",
                                   "target_revision": "SYNTHETIC-target-v1", "roles": ["read"], "probe_receipt_id": "synthetic-probe",
                                   "target_ref": "SYNTHETIC-approved-database"}, [unit], "ui-1")
        check = browser_check()
        check.update(environment_ref=environment, role="read")
        test = self.publish("test-plan", {"unit_ref": unit, "checks": [check],
                            "tool_checks": [{"capability": "database", "check_id": "browser-check", "evidence_id": "browser-evidence"}]}, [unit, environment], "ui-1")
        scope = self.publish("scope-manifest", {"run_id": "run", "workspace_id": "work", "unit_id": "ui-1", "unit_ref": unit,
                             "requirement_ids": ["req-1"], "mode": "observe", "reason": "SYNTHETIC catalog observation",
                             "source_baseline": {"sha256": "0" * 64}, "files": [], "db_objects": [], "environment_refs": [environment]},
                             [system, unit, environment], "ui-1")
        self.assertCode("tool_database_target_mismatch", "create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=[unit, test, scope, environment])

    def test_gate_a_requires_documentation_before_approval(self):
        context, requirement = self.requirements()
        system = self.publish("system-design", {**self.system_payload(), "tool_plan": capability_plan(library_docs="required")}, [context, requirement])
        self.assertCode("tool_evidence_required", "create_review", run_id="run", gate="A", input_refs=[context, requirement, system])
        self.assertEqual({}, self.journal.read()["reviews"])

    def test_gate_a_documentation_appears_in_exact_review(self):
        _, _, _, review = self.system(capability_plan(library_docs="required"), [documentation_observation()])
        self.assertIn("context7.resolve-library-id + query-docs", review["presentation"])
        self.assertIn("SYNTHETIC-library@1", review["presentation"])
        self.assertTrue(review["presentation_sha256"])

    def test_required_figma_rejects_local_quota_fallback_at_gate_b(self):
        _, _, system, _ = self.system(capability_plan(ui_design="required", browser="required"))
        refs = self.unit(system, [local_fallback()], bindings=browser_binding())
        self.assertCode("tool_evidence_required", "create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=list(refs))

    def test_preferred_figma_allows_concrete_fallback_and_presents_failure(self):
        _, _, system, _ = self.system(capability_plan(ui_design="preferred", browser="required"))
        refs = self.unit(system, [local_fallback()], bindings=browser_binding())
        review = self.call("create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=list(refs))
        self.assertIn("quota_exceeded", review["presentation"])
        self.assertIn("local-design", review["presentation"])
        self.assertNotIn("decision_id", review, "Generating a valid review must not fabricate user approval")

    def test_browser_required_check_bindings_cannot_be_missing_or_optional(self):
        _, _, system, _ = self.system(capability_plan(browser="required"))
        refs = self.unit(system)
        self.assertCode("tool_check_required", "create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=list(refs))
        check = browser_check()
        check["runner"]["evidence"][0]["required"] = False
        test = self.publish("test-plan", {"unit_ref": refs[0], "checks": [check], "tool_checks": browser_binding()}, [refs[0]], "ui-1")
        self.assertCode("invalid_tool_check", "create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=[refs[0], test, refs[2]])

    def test_browser_binding_cannot_point_to_unrelated_check(self):
        _, _, system, _ = self.system(capability_plan(browser="required"))
        binding = browser_binding()
        binding[0]["check_id"] = "absent-check"
        refs = self.unit(system, bindings=binding)
        self.assertCode("invalid_tool_check", "create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=list(refs))

    def test_revised_system_evidence_invalidates_old_unit_and_old_gate_a(self):
        context, requirement, system, old_review = self.system(capability_plan(library_docs="required"), [documentation_observation()])
        refs = self.unit(system, [documentation_observation()])
        docs = documentation_observation()
        docs["result"]["version"] = "2"
        replacement = self.publish("system-design", {**self.system_payload(), "tool_plan": capability_plan(library_docs="required"), "tool_observations": [docs]}, [context, requirement])
        self.assertNotEqual(system, replacement)
        self.assertCode("stale_review", "record_decision", review_id=old_review["review_id"], decision="approved", user_message="SYNTHETIC retry", source="isolated fixture")
        self.assertCode("stale_input", "create_review", run_id="run", gate="B", unit_id="ui-1", input_refs=list(refs))

    def test_new_run_pins_tool_policy_without_caller_override(self):
        self.assertEqual("1", self.journal.read()["runs"]["run"]["tool_policy_version"])
        self.assertCode("invalid_input", "create_run", run_id="other", workspace_id="work", goal="SYNTHETIC cannot disable policy", tool_policy_version=None)

    def test_legacy_run_without_policy_stays_read_only_and_can_review_original_design(self):
        self.journal.state["runs"]["run"].pop("tool_policy_version")
        context, requirement = self.requirements()
        system = self.publish("system-design", self.system_payload(), [context, requirement])
        review = self.call("create_review", run_id="run", gate="A", input_refs=[context, requirement, system])
        self.approve(review)
        before, writes = encoded(self.journal.state), self.journal.writes
        self.call("workflow_status", run_id="run")
        self.call("list_artifacts", run_id="run")
        self.call("get_artifact", ref=system)
        self.call("evaluate_completion", run_id="run")
        self.assertEqual(before, encoded(self.journal.state))
        self.assertEqual(writes, self.journal.writes)
        self.assertNotIn("tool_policy_version", self.journal.read()["runs"]["run"])


class ToolRunnerWorkflowTests(unittest.TestCase):
    """Run real Python/Git against synthetic evidence; this is not a browser test."""

    def test_actual_runner_requires_attached_current_build_and_attempt_evidence(self):
        with tempfile.TemporaryDirectory(prefix="SYNTHETIC-tool-workflow-") as directory:
            base = Path(directory)
            product = base / "product"
            product.mkdir()
            marker = base / "SYNTHETIC-mode"
            marker.write_text("missing", encoding="utf-8")
            script = product / "check.py"
            observation_json = repr(json.dumps(synthetic_browser_observation()))
            script.write_text(
                "# SYNTHETIC runner integration fixture; no external provider operations.\n"
                "import json, os, sys\nfrom pathlib import Path\n"
                "assert 2 + 3 == 5\n"
                "mode = Path(sys.argv[1]).read_text(encoding='utf-8')\n"
                f"observation = json.loads({observation_json})\n"
                "if mode != 'missing':\n"
                "    evidence = {'tool_policy_version':'1','capability':'browser','build_id':os.environ['HARNESS_BUILD_ID'],"
                "'run_id':os.environ['HARNESS_RUN_ID'],'observation':observation}\n"
                "    if mode == 'wrong-build': evidence['build_id'] = '0' * 64\n"
                "    if mode == 'wrong-attempt': evidence['run_id'] = 'synthetic-previous-attempt'\n"
                "    Path(os.environ['HARNESS_EVIDENCE_DIR'], 'browser.json').write_text(json.dumps(evidence), encoding='utf-8')\n"
                "print('HARNESS_CASE_RESULTS=' + json.dumps({'cases':[{'case_id':'case-1','status':'passed'},"
                "{'case_id':'case-2','status':'passed'}]}))\n", encoding="utf-8")
            api = API(base / "private", Path(__file__).resolve().parents[1])
            project_id, call = execution_fixtures.approved_fixture(
                api, product, marker,
                checks=[browser_check(["case-1", "case-2"], str(script), marker)],
                tool_plan=capability_plan(unit="unit-1", browser="required"), tool_checks=browser_binding())
            session = call("begin_implementation", run_id="fixture-run", unit_id="unit-1", owner="fixture-owner", request_id="synthetic-observe")
            implementation = call("finish_implementation", session_id=session["session_id"], owner="fixture-owner",
                                  summary="SYNTHETIC unchanged source observation", outcome="completed")
            self.assertEqual("completed", implementation["outcome"])
            observed = {}
            for mode in ("missing", "valid", "wrong-build", "wrong-attempt", "valid-again"):
                with self.subTest(mode=mode):
                    marker.write_text(mode, encoding="utf-8")
                    campaign = call("run_checks", implementation_id=implementation["implementation_id"],
                                    owner="fixture-owner", request_id="synthetic-" + mode)
                    observed[mode] = campaign
                    if mode.startswith("valid"):
                        self.assertEqual("passed", campaign["outcome"], campaign)
                        self.assertEqual("browser", campaign["tool_evidence"][0]["capability"])
                        self.assertTrue(call("evaluate_completion", run_id="fixture-run")["eligible_complete"])
                    else:
                        self.assertEqual("blocked", campaign["outcome"], campaign)
                        self.assertFalse(call("evaluate_completion", run_id="fixture-run")["eligible_complete"])
                        if mode.startswith("wrong"):
                            self.assertEqual("tool_evidence_stale", campaign["tool_evidence_error"])
            self.assertEqual("blocked", observed["missing"]["check_results"]["browser-check"]["result"])
            self.assertNotEqual(observed["valid"]["campaign_id"], observed["valid-again"]["campaign_id"])
            journal = api.registry.journal(project_id)
            before = encoded(journal.read())
            self.assertTrue(call("evaluate_completion", run_id="fixture-run")["eligible_complete"])
            self.assertEqual(before, encoded(journal.read()), "Completion projection must remain read-only")
            (product / "SYNTHETIC-drift.txt").write_text("SYNTHETIC concurrent source change", encoding="utf-8")
            evaluation = call("evaluate_completion", run_id="fixture-run")
            self.assertFalse(evaluation["eligible_complete"])
            self.assertIn("unit-1:source_changed", evaluation["blockers"])
            self.assertFalse((product / ".git").exists(), "Personal evidence Git must stay outside the product")
            self.assertTrue(journal.fsck()["ok"])


if __name__ == "__main__":
    unittest.main()
