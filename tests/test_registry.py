"""Registration crash/retry tests use isolated temporary products/private Git."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness.common import HarnessError, sha256
from harness.history import Journal
from harness.registry import Registry, atomic_json


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="registry-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.standard = self.root / "standard"
        self.standard.mkdir()
        self.product = self.root / "product"
        self.product.mkdir()
        (self.product / "source.txt").write_bytes(b"user-owned\r\n")
        self.personal = self.root / "personal"
        self.registry = Registry(self.personal, self.standard)

    def project_id(self, root=None):
        path = (root or self.product).resolve()
        return "project-" + sha256(str(path).casefold().encode("utf-8"))[:20]

    def history(self):
        return Journal(self.personal / "projects" / self.project_id() / "history.git")

    def pending_path(self):
        return self.personal / "registry" / "registrations" / (self.project_id() + ".json")

    def assert_code(self, code, callback):
        with self.assertRaises(HarnessError) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)

    def test_register_retry_and_readonly_lookup_preserve_tip_and_product(self):
        row = self.registry.register(self.product, "fixture")
        journal = self.history()
        tip = journal._tip()
        self.assertEqual(row, self.registry.register(self.product, "another display request"))
        self.assertEqual([row], self.registry.list_projects())
        self.assertEqual(tip, self.registry.journal(row["project_id"])._tip())
        self.assertEqual(["source.txt"], sorted(p.name for p in self.product.iterdir()))
        self.assertEqual(b"user-owned\r\n", (self.product / "source.txt").read_bytes())
        self.assertEqual("bound", json.loads(self.pending_path().read_bytes())["phase"])

    def test_crash_after_initial_commit_before_binding_resumes_without_new_commit(self):
        def crash_binding(path, value):
            if Path(path).parent == self.personal / "registry" and Path(path).name == self.project_id() + ".json":
                raise OSError("SYNTHETIC crash before binding")
            return atomic_json(path, value)
        with patch("harness.registry.atomic_json", side_effect=crash_binding):
            with self.assertRaises(OSError):
                self.registry.register(self.product, "fixture")
        journal, initial_tip = self.history(), self.history()._tip()
        self.assertEqual([], self.registry.list_projects())
        self.assertEqual("journal_ready", json.loads(self.pending_path().read_bytes())["phase"])
        row = self.registry.register(self.product, "fixture retry")
        self.assertEqual(initial_tip, journal._tip())
        self.assertEqual("fixture", row["name"])
        self.assertEqual("bound", json.loads(self.pending_path().read_bytes())["phase"])

    def test_crash_after_binding_before_bound_marker_finishes_receipt(self):
        def crash_marker(path, value):
            if Path(path) == self.pending_path() and value.get("phase") == "bound":
                raise OSError("SYNTHETIC crash before bound marker")
            return atomic_json(path, value)
        with patch("harness.registry.atomic_json", side_effect=crash_marker):
            with self.assertRaises(OSError):
                self.registry.register(self.product, "fixture")
        self.assertEqual(1, len(self.registry.list_projects()))
        tip = self.history()._tip()
        self.registry.register(self.product, "fixture")
        self.assertEqual(tip, self.history()._tip())
        self.assertEqual("bound", json.loads(self.pending_path().read_bytes())["phase"])

    def test_legacy_orphan_initial_journal_is_reused(self):
        initial = {"schema_version": 2, "project": {"project_id": self.project_id(), "name": "original-name", "standard_root": str(self.standard), "standard_release": self.registry._release()},
                   "workspaces": {"workspace-main": {"root": str(self.product)}}, "events": [], "runs": {}}
        journal = self.history()
        journal.initialize(initial)
        tip = journal._tip()
        row = self.registry.register(self.product, "retry-name")
        self.assertEqual(tip, journal._tip())
        self.assertEqual("original-name", row["name"])

    def test_unbound_journal_with_activity_is_not_adopted_or_deleted(self):
        initial = {"schema_version": 2, "project": {"project_id": self.project_id(), "name": "fixture", "standard_root": str(self.standard), "standard_release": self.registry._release()},
                   "workspaces": {"workspace-main": {"root": str(self.product)}}, "events": [], "runs": {"unknown": {"goal": "fixture"}}}
        self.history().initialize(initial)
        tip = self.history()._tip()
        self.assert_code("registration_conflict", lambda: self.registry.register(self.product, "fixture"))
        self.assertEqual(tip, self.history()._tip())
        self.assertEqual([], self.registry.list_projects())

    def test_orphan_wrong_release_is_preserved(self):
        initial = {"schema_version": 2, "project": {"project_id": self.project_id(), "name": "fixture", "standard_root": str(self.standard), "standard_release": "another-release"},
                   "workspaces": {"workspace-main": {"root": str(self.product)}}, "events": []}
        self.history().initialize(initial)
        tip = self.history()._tip()
        self.assert_code("registration_conflict", lambda: self.registry.register(self.product, "fixture"))
        self.assertEqual(tip, self.history()._tip())

    def test_partial_git_directory_is_preserved_for_explicit_recovery(self):
        directory = self.history().path
        directory.mkdir(parents=True)
        (directory / "partial.txt").write_bytes(b"SYNTHETIC partial init")
        self.assert_code("registration_recovery_required", lambda: self.registry.register(self.product, "fixture"))
        self.assertEqual(b"SYNTHETIC partial init", (directory / "partial.txt").read_bytes())
        self.assertEqual([], self.registry.list_projects())

    def test_invalid_name_does_not_create_requested_product_root(self):
        missing = self.root / "not-created"
        self.assert_code("invalid_name", lambda: self.registry.register(missing, "", create_root=True))
        self.assertFalse(missing.exists())
        self.assertFalse(self.personal.exists())

    def test_pending_parent_registration_blocks_nested_product(self):
        nested = self.product / "nested"
        nested.mkdir()
        with patch.object(Journal, "initialize", side_effect=OSError("SYNTHETIC interruption")):
            with self.assertRaises(OSError):
                self.registry.register(self.product, "fixture")
        self.assert_code("overlapping_projects", lambda: self.registry.register(nested, "nested"))

    def test_two_processes_register_same_root_once(self):
        code = "import json,sys;from harness.registry import Registry;print(json.dumps(Registry(sys.argv[1],sys.argv[2]).register(sys.argv[3],'fixture')))"
        args = [sys.executable, "-X", "utf8", "-B", "-c", code, str(self.personal), str(self.standard), str(self.product)]
        cwd = str(Path(__file__).resolve().parents[1])
        processes = [subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        rows = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=35)
            self.assertEqual(0, process.returncode, stderr.decode("utf-8", errors="replace"))
            rows.append(json.loads(stdout))
        self.assertEqual(rows[0], rows[1])
        self.assertEqual(1, len(self.registry.list_projects()))
        self.assertEqual("bound", json.loads(self.pending_path().read_bytes())["phase"])
        count = self.history()._git("rev-list", "--count", "HEAD").stdout.strip()
        self.assertEqual(b"1", count)

    def test_release_identity_uses_executing_package_not_shared_source(self):
        (self.standard / "release-manifest.json").write_text(json.dumps({"release_id": "new-shared-source"}), encoding="utf-8")
        runtime_root = self.root / "runtime-release"
        (runtime_root / "harness").mkdir(parents=True)
        (runtime_root / "release-manifest.json").write_text(json.dumps({"release_id": "pinned-executing-release"}), encoding="utf-8")
        with patch("harness.registry.__file__", str(runtime_root / "harness" / "registry.py")):
            row = self.registry.register(self.product, "fixture")
        self.assertEqual("pinned-executing-release", row["standard_release"])
        self.assertEqual(str(self.standard), row["standard_root"])
        self.assertEqual("pinned-executing-release", self.history().read()["project"]["standard_release"])

    def test_development_runtime_does_not_claim_shared_source_release(self):
        (self.standard / "release-manifest.json").write_text(json.dumps({"release_id": "shared-only"}), encoding="utf-8")
        runtime_root = self.root / "development-runtime"
        (runtime_root / "harness").mkdir(parents=True)
        with patch("harness.registry.__file__", str(runtime_root / "harness" / "registry.py")):
            from harness import VERSION
            self.assertEqual("development-"+VERSION, self.registry._release())

    def test_legacy_import_rejects_nested_junction_before_reading_external_files(self):
        row = self.registry.register(self.product, "fixture")
        legacy = self.product / ".harness"
        legacy.mkdir()
        outside = self.root / "outside-fixture"
        outside.mkdir()
        (outside / "not-imported.md").write_text("Fixture outside legacy boundary", encoding="utf-8")
        link = legacy / "nested-link"
        if os.name == "nt":
            environment = {**os.environ, "HARNESS_FIXTURE_LINK": str(link), "HARNESS_FIXTURE_TARGET": str(outside)}
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                     "New-Item -ItemType Junction -Path $env:HARNESS_FIXTURE_LINK -Target $env:HARNESS_FIXTURE_TARGET -ErrorAction Stop | Out-Null"],
                                    env=environment, capture_output=True, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
        else:
            link.symlink_to(outside, target_is_directory=True)
        tip = self.history()._tip()
        self.assert_code("linked_root", lambda: self.registry.import_legacy(row["project_id"], legacy))
        self.assertEqual(tip, self.history()._tip())
        self.assertEqual("Fixture outside legacy boundary", (outside / "not-imported.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
