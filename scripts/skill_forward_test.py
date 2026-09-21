#!/usr/bin/env python3
"""CLI forward-test with synthetic approvals and an isolated web project only.

No account setup, host installation, shared Git changes, or real product edits.
Temporary fixtures are retained for inspection. This does not run a browser.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

STANDARD = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(STANDARD))
SKILLS = ["development-workflow", "dev-discover", "dev-requirements", "dev-system-design",
          "dev-unit-design", "dev-test-design", "dev-review", "dev-implement",
          "dev-verify", "dev-artifacts", "dev-restore"]
OWNER = "synthetic-forward-owner"
RUN = "synthetic-settings-run"
UNIT = "settings-ui"

SETTINGS_JS = """export const defaults = Object.freeze({theme: 'system', pageSize: 20});
export function validateSettings(input) {
  if (!input || !['system', 'light', 'dark'].includes(input.theme))
    throw new RangeError('지원하지 않는 테마입니다.');
  if (!Number.isInteger(input.pageSize) || input.pageSize < 5 || input.pageSize > 100 || input.pageSize % 5)
    throw new RangeError('표시 개수는 5부터 100까지 5 단위로 입력하세요.');
  return {theme: input.theme, pageSize: input.pageSize};
}
export function loadSettings(storage) {
  const raw = storage.getItem('web-settings');
  if (raw === null) return {...defaults};
  try { return validateSettings(JSON.parse(raw)); }
  catch { return {...defaults}; }
}
export function saveSettings(storage, input) {
  const result = validateSettings(input);
  storage.setItem('web-settings', JSON.stringify(result));
  return result;
}
"""

APP_JS = """import {loadSettings, saveSettings} from './settings.js';
const view = document.querySelector('#view');
function render() {
  if (location.hash !== '#settings') {
    view.innerHTML = '<h1>대시보드</h1><p>기존 요약 정보</p>';
    return;
  }
  let values;
  try { values = loadSettings(localStorage); }
  catch { view.innerHTML = '<h1>설정</h1><p role="alert">저장소를 읽을 수 없습니다.</p>'; return; }
  view.innerHTML = '<h1>설정</h1><form><label for="theme">화면 테마</label><select id="theme"><option value="system">시스템</option><option value="light">밝게</option><option value="dark">어둡게</option></select><label for="page-size">표시 개수</label><input id="page-size" type="number" min="5" max="100" step="5" required><button type="submit">저장</button><p id="status" role="status"></p></form>';
  document.querySelector('#theme').value = values.theme;
  document.querySelector('#page-size').value = String(values.pageSize);
  document.querySelector('form').addEventListener('submit', event => {
    event.preventDefault();
    const status = document.querySelector('#status');
    try {
      saveSettings(localStorage, {theme: document.querySelector('#theme').value,
        pageSize: Number(document.querySelector('#page-size').value)});
      status.textContent = '저장했습니다.';
    } catch (error) { status.textContent = error.message; }
  });
}
addEventListener('hashchange', render);
render();
"""

CHECK_JS = """import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {defaults, loadSettings, saveSettings} from '../src/settings.js';
const mode = readFileSync(process.argv[2], 'utf8').trim();
const results = [];
function test(caseId, callback) {
  try { callback(); results.push({case_id: caseId, status: 'passed'}); }
  catch (error) { results.push({case_id: caseId, status: 'failed'}); console.error(caseId + ': ' + error.message); }
}
function memory() {
  const values = new Map();
  return {getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value)};
}
test('case-open', () => {
  assert.match(readFileSync('index.html', 'utf8'), /href="#settings"/);
  assert.match(readFileSync('src/app.js', 'utf8'), /대시보드/);
});
test('case-default', () => assert.deepEqual(loadSettings(memory()), {theme: 'system', pageSize: 20}));
test('case-save', () => {
  const store = memory();
  saveSettings(store, {theme: 'dark', pageSize: 25});
  assert.deepEqual(loadSettings(store), {theme: 'dark', pageSize: 25});
  assert.equal(mode, 'normal', 'Synthetic external fixture forces a new failed attempt');
});
test('case-invalid', () => {
  const store = memory();
  assert.throws(() => saveSettings(store, {theme: 'dark', pageSize: 6}), RangeError);
  assert.equal(store.getItem('web-settings'), null);
  store.setItem('web-settings', '{broken');
  assert.deepEqual(loadSettings(store), defaults);
});
test('case-storage', () => {
  const broken = {getItem: () => null, setItem: () => { throw new Error('quota'); }};
  assert.throws(() => saveSettings(broken, {theme: 'light', pageSize: 10}), /quota/);
});
console.log('HARNESS_CASE_RESULTS=' + JSON.stringify({cases: results}));
process.exitCode = results.every(row => row.status === 'passed') ? 0 : 1;
"""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tree(root):
    return {p.relative_to(root).as_posix(): digest(p.read_bytes())
            for p in root.rglob("*") if p.is_file()}


class Scenario:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="team-skill-forward-")).resolve()
        self.product = self.root / "existing-web"
        self.private = self.root / "private-history"
        self.inputs = self.root / "cli-inputs"
        self.product.mkdir()
        self.inputs.mkdir()
        self.node = shutil.which("node")
        self.git = shutil.which("git")
        if not self.node or not self.git:
            raise RuntimeError("Node.js and Git are required for this isolated scenario.")
        self.sequence = 0
        self.project_id = None
        self.checks = []
        self.commands = []
        self.refs = {}

    def check(self, name, condition, detail):
        self.checks.append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(name + ": " + detail)

    def command(self, argv, cwd=None):
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60)
        if result.returncode:
            raise RuntimeError("Fixture command failed: " + result.stderr[:1000])
        return result.stdout.strip()

    def invoke(self, operation, values=None, error=None, scope=True, describe=False):
        self.sequence += 1
        args = [sys.executable, "-B", "-X", "utf8", str(STANDARD / "team_harness.py"),
                "--state-root", str(self.private), "--standard-root", str(STANDARD)]
        if describe:
            args += ["describe", operation]
        else:
            payload = dict(values or {})
            if scope:
                payload = {"project_id": self.project_id, **payload}
            path = self.inputs / (str(self.sequence) + ".json")
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            args += ["call", operation, "--input-file", str(path)]
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                errors="strict", timeout=60)
        output = json.loads(result.stdout)
        self.commands.append({"operation": operation, "describe": describe,
                              "exit_code": result.returncode, "error": output.get("error") if isinstance(output, dict) else None})
        if error:
            self.check("blocked-" + operation + "-" + error,
                       result.returncode == 2 and output.get("error") == error,
                       "Expected explicit rejection without fabricated approval.")
        elif result.returncode:
            raise RuntimeError(operation + ": " + json.dumps(output, ensure_ascii=False))
        return output

    def state_bytes(self):
        journal = self.private / "projects" / self.project_id / "history.git"
        result = subprocess.run([self.git, "--git-dir", str(journal), "show",
                                 "refs/heads/history:state.json"], capture_output=True, timeout=20)
        if result.returncode:
            raise RuntimeError("Cannot read the isolated journal state.")
        return result.stdout

    def journal_tip(self):
        journal = self.private / "projects" / self.project_id / "history.git"
        return self.command([self.git, "--git-dir", str(journal), "rev-parse", "refs/heads/history"])

    def publish(self, kind, payload, refs, report, unit=None, accept=True, artifact_id=None):
        producer = {"discovery-context": "dev-discover", "requirements": "dev-requirements",
                    "system-design": "dev-system-design", "unit-spec": "dev-unit-design",
                    "test-plan": "dev-test-design", "review-report": "dev-review"}[kind]
        stage_args = {"run_id": RUN, "skill": producer, "owner": OWNER, "input_refs": refs,
                      "request_id": "stage-" + str(self.sequence + 1)}
        if unit:
            stage_args["unit_id"] = unit
        stage = self.invoke("start_stage", stage_args)
        artifact_id = artifact_id or kind
        status = self.invoke("workflow_status", {"run_id": RUN})
        head = status["projection"]["heads"].get(RUN + "/" + artifact_id, {"revision_id": None, "generation": 0})
        values = {"run_id": RUN, "stage_run_id": stage["stage_run_id"], "owner": OWNER,
                  "artifact_id": artifact_id, "kind": kind, "payload": payload, "report": report,
                  "input_refs": refs, "accept": accept, "expected_head": head,
                  "request_id": "publish-" + str(self.sequence + 1)}
        if unit:
            values["unit_id"] = unit
        published = self.invoke("publish_artifact", values)
        self.invoke("finish_stage", {"stage_run_id": stage["stage_run_id"], "owner": OWNER,
                    "status": "succeeded", "output_refs": [published["ref"]]})
        return published["ref"]

    def synthetic_approval(self, review):
        self.invoke("record_decision", {"review_id": review["review_id"], "decision": "approved",
                    "user_message": "SYNTHETIC TEST FIXTURE ONLY: approve this isolated scenario bundle.",
                    "source": "scripts/skill_forward_test.py; not a real user decision"})

    def new_registration_smoke(self):
        target = self.root / "new-empty-web"
        self.check("new-project-target-absent", not target.exists(), "Synthetic new target starts absent.")
        row = self.invoke("project_register", {"project_root": str(target), "name": "SYNTHETIC new empty web", "create_root": True}, scope=False)
        self.invoke("create_run", {"project_id": row["project_id"], "run_id": "synthetic-new-run",
                    "workspace_id": row["workspace_id"], "goal": "SYNTHETIC new project discovery only"}, scope=False)
        stage = self.invoke("start_stage", {"project_id": row["project_id"], "run_id": "synthetic-new-run",
                            "skill": "dev-discover", "owner": OWNER, "input_refs": []}, scope=False)
        self.invoke("finish_stage", {"project_id": row["project_id"], "stage_run_id": stage["stage_run_id"],
                    "owner": OWNER, "status": "no_change", "notes": "SYNTHETIC registration smoke only"}, scope=False)
        self.check("new-project-discovery-starts", stage["skill"] == "dev-discover", "The newly registered directory supports a real discovery StageRun.")
        self.check("new-project-has-no-product-markers", target.is_dir() and list(target.iterdir()) == [],
                   "Only the authorized empty folder was created: no code, .git, or .harness.")
        return {"customer_projects_changed": 0, "synthetic_decisions": 0}

    def run(self):
        skill_hashes = {}
        for name in SKILLS:
            path = STANDARD / "skills" / name / "SKILL.md"
            body = path.read_text(encoding="utf-8")
            runtime = (path.parent / "references" / "runtime.md").read_text(encoding="utf-8")
            self.check("skill-readable-" + name, bool(body and runtime),
                       "Read the actual Skill and packaged execution reference.")
            skill_hashes[name] = digest(body.encode("utf-8"))
        templates = ["artifact-report.md", "ui-unit.md", "test-plan.md", "review-packet.md",
                     "verification-report.md", "restore-preview.md"]
        for name in templates:
            self.check("template-" + name, bool((STANDARD / "templates" / name).read_text(encoding="utf-8")),
                       "Template exists; actual scenario content is authored separately.")

        (self.product / "src").mkdir()
        (self.product / "index.html").write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>기존 웹</title><nav><a href="#home">홈</a></nav><main id="view"></main><script type="module" src="./src/app.js"></script></html>', encoding="utf-8")
        (self.product / "src/app.js").write_text("document.querySelector('#view').innerHTML = '<h1>대시보드</h1><p>기존 요약 정보</p>';\n", encoding="utf-8")
        (self.product / "package.json").write_text('{"name":"synthetic-existing-web","private":true,"type":"module"}\n', encoding="utf-8")
        (self.product / "README.md").write_text("# Fixture existing web\n", encoding="utf-8")
        (self.product / "user-note.txt").write_text("initial fixture note\n", encoding="utf-8")
        self.command([self.git, "init", "--quiet", str(self.product)])
        self.command([self.git, "-C", str(self.product), "add", "index.html", "src/app.js", "package.json", "README.md", "user-note.txt"])
        self.command([self.git, "-C", str(self.product), "-c", "user.name=Synthetic Test", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "Synthetic fixture baseline"])
        (self.product / "user-note.txt").write_text("user staged change must survive\n", encoding="utf-8")
        self.command([self.git, "-C", str(self.product), "add", "user-note.txt"])
        (self.product / "README.md").write_text("# Fixture existing web\nuser unstaged change must survive\n", encoding="utf-8")
        (self.product / "untracked-note.txt").write_text("user untracked file must survive\n", encoding="utf-8")
        (self.product / ".env").write_text("SYNTHETIC_PRIVATE_SETTING=fixture-only\n", encoding="utf-8")
        git_before = tree(self.product / ".git")
        protected = {name: (self.product / name).read_bytes() for name in ["user-note.txt", "README.md", "untracked-note.txt"]}
        product_before = tree(self.product)

        for op in ["project_register", "start_stage", "publish_artifact", "finish_stage", "create_review",
                   "record_decision", "begin_implementation", "run_checks", "get_verification", "render_artifact"]:
            self.invoke(op, describe=True, scope=False)
        self.check("describe-no-state-created", not self.private.exists(), "Schema lookup did not create registry/history.")
        self.new_registration_smoke()
        project = self.invoke("project_register", {"project_root": str(self.product), "name": "SYNTHETIC existing web settings fixture", "create_root": False}, scope=False)
        self.project_id = project["project_id"]
        self.invoke("create_run", {"run_id": RUN, "workspace_id": project["workspace_id"],
                    "goal": "SYNTHETIC FIXTURE: add settings screen to an existing web project; never a customer request."})
        baseline = self.invoke("capture_snapshot", {"workspace_id": project["workspace_id"], "label": "synthetic-before", "request_id": "baseline"})
        self.check("snapshot-excludes-env-and-git",
                   not any(row["path"] == ".env" or row["path"].startswith(".git/") for row in baseline["manifest"]["files"]),
                   "Private configuration and product Git metadata are excluded from source copies.")
        self.check("registration-does-not-edit-product", tree(self.product) == product_before, "Registration/capture preserved product bytes.")

        context = self.publish("discovery-context",
            {"facts": [{"id": "fact-web", "description": "Existing vanilla ES module web project; home navigation and dashboard exist."}],
             "constraints": ["No new runtime dependency or backend", "Preserve staged and unstaged user files"],
             "unknowns": [], "tool_observations": [{"tool": "local-files", "status": "observed"}]},
            [], "# 기존 웹 조사 — 합성 시험\n\n현재 ES module 웹과 대시보드, 사용자 미커밋 변경을 확인했다. Node 기반 독립 검사만 계획하며 브라우저 실동작은 아직 검사하지 않았다.")
        cases = ["case-open", "case-default", "case-save", "case-invalid", "case-storage"]
        requirements = self.publish("requirements",
            {"requirements": [{"id": "req-settings", "description": "Existing web adds local display settings with navigation, defaults, validated persistence, and recoverable storage failures.", "case_ids": cases}],
             "scope": {"included": ["settings navigation", "theme preference value", "page size preference value", "local persistence"], "excluded": ["app-wide theme application", "backend", "authentication", "deployment"]},
             "decisions": [{"source": "synthetic fixture specification", "value": "Local document design; no Figma account required. Theme system/light/dark; page size 5..100 by 5."}]},
            [context], "# 설정 요구 — 합성 시험\n\n설정 진입, 기본값(system/20), 저장/재조회, 잘못된 입력 거절, 저장소 오류 전달을 요구한다. 실제 테마 적용·백엔드·계정·배포는 범위 밖이다. 값과 범위는 합성 fixture 명세이며 실제 사용자 답변이 아니다.")
        system = self.publish("system-design",
            {"requirement_ids": ["req-settings"], "work_units": [{"id": UNIT, "profiles": ["ui"], "description": "Navigation/form and storage contract"}],
             "flows": ["hash navigation -> form -> validate -> local storage -> feedback"],
             "impact": ["index.html", "src/app.js", "src/settings.js", "styles.css", "tests/settings-check.mjs"]},
            [context, requirements], "# 시스템 설계 — 합성 시험\n\n기존 웹과 홈 화면을 유지하고 한 UI 단위에 설정 form과 저장 helper를 추가한다. 새 라이브러리/API/DB는 없다. 순수 helper와 구조 계약을 Node로 검사하고 브라우저 상호작용은 별도 한계로 남긴다.")

        before = self.state_bytes()
        self.invoke("start_stage", {"run_id": RUN, "skill": "dev-unit-design", "owner": OWNER,
                    "unit_id": UNIT, "input_refs": [system]}, error="gate_a_required")
        self.invoke("begin_implementation", {"run_id": RUN, "unit_id": UNIT, "owner": OWNER,
                    "request_id": "blocked-before-a"}, error="gate_a_required")
        self.check("gate-a-rejections-do-not-write-state", before == self.state_bytes(), "No approval or implementation record was fabricated.")
        gate_a = self.invoke("create_review", {"run_id": RUN, "gate": "A", "input_refs": [context, requirements, system]})
        self.synthetic_approval(gate_a)

        unit_payload = {"requirement_ids": ["req-settings"], "case_ids": cases,
                        "profiles": ["ui"], "allowed_paths": ["index.html", "src/app.js", "src/settings.js", "styles.css", "tests/settings-check.mjs"],
                        "ui": {"layout": "Header navigation, main title, labelled form, persistent feedback", "tokens": {"text": "#17202a", "surface": "#ffffff", "accent": "#175cd3", "gap_px": 16},
                               "states": ["home", "settings-default", "settings-saved", "validation-error", "storage-error"],
                               "keyboard": "native labels/select/input/button; submit stays on form", "native_design": "not required by synthetic fixture"}}
        unit = self.publish("unit-spec", unit_payload, [system],
            "# 설정 UI 단위 — 합성 시험\n\n상단 홈/설정 navigation 아래 label을 연결한 theme select와 page-size number input, 저장 버튼, role=status 안내를 둔다. 글자 #17202a, 배경 #fff, 강조 #175cd3, 간격 16px. 좁은 폭에서는 세로 배치한다. 모듈은 읽기/검증/저장 결과를 분리한다. TestPlan 해시를 역참조하지 않는다.", UNIT)
        fixture_flag = self.root / "external-fixture-mode.txt"
        fixture_flag.write_text("normal", encoding="utf-8")
        check = {"check_id": "settings-contract", "argv": [self.node, "tests/settings-check.mjs", str(fixture_flag)],
                 "cwd": ".", "timeout_seconds": 30, "required": True, "expected_exit": 0,
                 "case_ids": cases, "expected": "All five independent setting contract cases pass",
                 "oracle": "Fixed synthetic settings requirements; explicit assertions do not call production to calculate expectations",
                 "evidence_mode": "case-results", "parser": "team-json"}
        plan = self.publish("test-plan", {"unit_ref": unit, "checks": [check]},
            [unit], "# 검사 계획 — 합성 시험\n\ncase-open은 navigation 선언과 기존 홈 계약을 확인한다. default/save/invalid/storage는 Node assert로 독립 고정 기대값을 확인한다. 실제 case 결과 marker를 출력한다. 이 검사는 브라우저 rendering/키보드 동작 검증이 아니며 배포 승인도 아니다.", UNIT)
        loaded_plan = self.invoke("get_artifact", {"ref": plan})
        self.check("exact-unit-test-pin", loaded_plan["payload"]["unit_ref"] == unit, "TestPlan pins the exact UnitSpec revision and hash.")
        gate_b = self.invoke("create_review", {"run_id": RUN, "gate": "B", "unit_id": UNIT, "input_refs": [unit, plan]})
        before = self.state_bytes()
        self.invoke("begin_implementation", {"run_id": RUN, "unit_id": UNIT, "owner": OWNER,
                    "request_id": "blocked-before-b"}, error="gate_b_required")
        self.check("gate-b-rejection-does-not-write-state", before == self.state_bytes(), "Gate A alone did not authorize implementation.")

        candidate = self.publish("unit-spec", {**unit_payload, "draft_note": "Exploratory wording only, not an accepted contract change"},
                                 [system], "# 탐색 초안 — 합성 시험\n\n비활성 탐색용 문구 수정 후보다.", UNIT, accept=False)
        state_before, tip_before = self.state_bytes(), self.journal_tip()
        product_before_view = tree(self.product)
        self.invoke("get_artifact", {"ref": unit})
        self.invoke("list_artifacts", {"run_id": RUN})
        self.invoke("diff_artifacts", {"before": unit, "after": candidate})
        rendered = self.invoke("render_artifact", {"ref": unit, "format": "markdown"})
        status = self.invoke("workflow_status", {"run_id": RUN})
        self.check("readonly-show-does-not-change-journal", state_before == self.state_bytes() and tip_before == self.journal_tip(),
                   "get/list/diff/status/render left authoritative state and history tip unchanged.")
        self.check("readonly-show-does-not-change-product", product_before_view == tree(self.product), "Showing a design did not regenerate product files.")
        self.check("rendered-report-exists", Path(rendered["path"]).is_file() and rendered["canonical_changed"] is False,
                   "Actual Markdown view was produced without changing canonical content.")
        self.check("candidate-does-not-replace-head", status["projection"]["heads"][RUN + "/unit-spec"]["revision_id"] == unit["revision_id"],
                   "An exploratory draft did not replace the accepted contract.")

        self.synthetic_approval(gate_b)
        session = self.invoke("begin_implementation", {"run_id": RUN, "unit_id": UNIT, "owner": OWNER, "request_id": "begin-approved"})
        self.check("no-implementation-before-gates", tree(self.product) == product_before,
                   "Only after the two synthetic approvals is this fixture implementation written.")
        (self.product / "index.html").write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>기존 웹</title><link rel="stylesheet" href="./styles.css"><nav><a href="#home">홈</a><a href="#settings">설정</a></nav><main id="view"></main><script type="module" src="./src/app.js"></script></html>', encoding="utf-8")
        (self.product / "src/settings.js").write_text(SETTINGS_JS, encoding="utf-8")
        (self.product / "src/app.js").write_text(APP_JS, encoding="utf-8")
        (self.product / "styles.css").write_text('body{font:16px/1.6 system-ui;color:#17202a;background:#fff;max-width:48rem;margin:auto;padding:1rem}nav,form{display:flex;gap:16px}form{flex-direction:column;max-width:28rem}button,a{color:#175cd3}input,select,button{font:inherit;padding:.5rem}\n', encoding="utf-8")
        (self.product / "tests").mkdir()
        (self.product / "tests/settings-check.mjs").write_text(CHECK_JS, encoding="utf-8")
        implementation = self.invoke("finish_implementation", {"session_id": session["session_id"], "owner": OWNER,
                      "summary": "SYNTHETIC fixture settings implementation and independent checks", "outcome": "completed"})
        self.check("implementation-receipt-completed", implementation["outcome"] == "completed", "Approved changed paths were captured.")
        first = self.invoke("run_checks", {"implementation_id": implementation["implementation_id"], "owner": OWNER, "request_id": "verify-first"})
        self.check("real-case-verification-passed", first["outcome"] == "passed", "Node executed five explicit case assertions and emitted the required marker.")
        replay = self.invoke("run_checks", {"implementation_id": implementation["implementation_id"], "owner": OWNER, "request_id": "verify-first"})
        self.check("transport-retry-is-idempotent", replay["campaign_id"] == first["campaign_id"], "Same request ID did not duplicate an actual run.")
        fixture_flag.write_text("force-failure", encoding="utf-8")
        second = self.invoke("run_checks", {"implementation_id": implementation["implementation_id"], "owner": OWNER, "request_id": "verify-second"})
        self.check("new-retest-preserves-failure", second["outcome"] == "failed" and second["campaign_id"] != first["campaign_id"],
                   "A new request executed again and recorded the intentionally injected failure.")
        verification = self.invoke("get_verification", {"implementation_id": implementation["implementation_id"]})
        self.check("old-pass-does-not-hide-new-failure", verification["eligible_complete"] is False,
                   "Earlier success did not keep the current verification complete.")
        self.invoke("get_artifact", {"ref": first["ref"]})
        self.invoke("get_artifact", {"ref": second["ref"]})

        exported = self.invoke("export_snapshot", {"snapshot_id": baseline["snapshot_id"], "destination": str(self.root / "baseline-export")})
        self.check("snapshot-export-verified", exported["status"] == "export_verified", "Original managed bytes were reconstructed outside the product.")
        restore = self.invoke("plan_restore", {"snapshot_id": baseline["snapshot_id"], "workspace_id": project["workspace_id"]})
        product_before_restore = tree(self.product)
        self.invoke("apply_restore", {"plan_id": restore["plan_id"], "request_id": "restore-without-approval"}, error="restore_approval_required")
        self.check("unapproved-restore-does-not-edit-product", product_before_restore == tree(self.product), "Restore preview did not authorize source overwrite.")
        self.check("product-git-metadata-preserved", git_before == tree(self.product / ".git"),
                   "Product Git management bytes, including staged index and refs, stayed unchanged.")
        self.check("user-files-preserved", all((self.product / name).read_bytes() == raw for name, raw in protected.items()),
                   "Staged, unstaged, and untracked user fixture content survived.")
        self.check("no-harness-marker-in-product", not (self.product / ".harness").exists(), "All records stayed outside the product.")

        self.refs = {"discovery": context, "requirements": requirements, "system": system,
                     "unit": unit, "test_plan": plan, "candidate": candidate,
                     "verification_pass": first["ref"], "verification_failed": second["ref"]}
        return {"skill_sha256": skill_hashes, "refs": self.refs,
                "runtime": {"python": sys.version.split()[0], "node": self.command([self.node, "--version"])},
                "cases": cases, "synthetic_decisions": 2, "customer_projects_changed": 0,
                "host_installations": 0, "external_accounts_used": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="JSON evidence path outside the common source; defaults to the retained fixture")
    parser.add_argument("--registration-only", action="store_true", help="Run only the new empty-project registration smoke.")
    args = parser.parse_args()
    scenario = Scenario()
    from harness.history import _no_links
    from harness.registry import atomic_json
    raw_output = Path(args.output).expanduser().absolute() if args.output else scenario.root / "forward-test-result.json"
    _no_links(raw_output)
    output = raw_output.resolve()
    if output == STANDARD or STANDARD in output.parents:
        parser.error("Keep generated execution evidence outside the common source.")
    result = {"schema_version": 1, "executed_at": datetime.now(timezone.utc).isoformat(),
              "scenario": "SYNTHETIC existing web project settings screen",
              "scope": "Real CLI and Node contract checks; no browser or external MCP integration",
              "checks": scenario.checks}
    try:
        result.update(scenario.new_registration_smoke() if args.registration_only else scenario.run())
        result["outcome"] = "passed"
    except Exception as error:
        result["outcome"] = "failed"
        result["failure"] = {"type": type(error).__name__, "message": str(error).replace(str(scenario.root), "<temporary-fixture>").replace(str(STANDARD), "<common-source>")}
    result["commands"] = scenario.commands
    result["passed_checks"] = sum(row["passed"] for row in scenario.checks)
    result["total_checks"] = len(scenario.checks)
    _no_links(raw_output)
    atomic_json(output, result)
    print(json.dumps({"outcome": result["outcome"], "checks": result["total_checks"],
                      "passed_checks": result["passed_checks"], "report": str(output),
                      "retained_fixture": str(scenario.root),
                      "failure": result.get("failure")}, ensure_ascii=False))
    return 0 if result["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
