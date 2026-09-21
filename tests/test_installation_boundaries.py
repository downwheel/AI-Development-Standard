"""One bounded regression for installer input links; synthetic profiles only."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import install
from harness.common import HarnessError


class InstallationBoundaryTest(unittest.TestCase):
    def test_input_junctions_are_rejected_before_plan_or_rollback_changes_settings(self):
        with tempfile.TemporaryDirectory(prefix="install-boundary-fixture-") as directory:
            base = Path(directory)
            shared, profile, private = base / "shared", base / "profile", base / "private"
            shared.mkdir(); profile.mkdir(); private.mkdir()
            config = profile / ".codex" / "config.toml"
            config.parent.mkdir()
            config.write_bytes(b'theme = "synthetic-preserve-me"\r\n')
            settings = private / "settings.json"
            settings.write_bytes(b'{"custom_policy":"synthetic-preserve-me"}\r\n')
            before = {config: config.read_bytes(), settings: settings.read_bytes()}
            profile_link, private_link = base / "profile-link", base / "private-link"
            if os.name == "nt":
                environment = {**os.environ, "HARNESS_PROFILE_LINK": str(profile_link), "HARNESS_PROFILE_TARGET": str(profile),
                               "HARNESS_PRIVATE_LINK": str(private_link), "HARNESS_PRIVATE_TARGET": str(private)}
                result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "New-Item -ItemType Junction -Path $env:HARNESS_PROFILE_LINK -Target $env:HARNESS_PROFILE_TARGET -ErrorAction Stop | Out-Null\n"
                    "New-Item -ItemType Junction -Path $env:HARNESS_PRIVATE_LINK -Target $env:HARNESS_PRIVATE_TARGET -ErrorAction Stop | Out-Null"],
                    env=environment, capture_output=True, timeout=15)
                self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))
            else:
                profile_link.symlink_to(profile, target_is_directory=True)
                private_link.symlink_to(private, target_is_directory=True)
            with patch.object(install, "SOURCE", shared):
                for selected_profile, selected_private in ((profile_link, private), (profile, private_link)):
                    for operation in ("plan", "rollback"):
                        with self.subTest(root="profile" if selected_profile == profile_link else "private", operation=operation):
                            with self.assertRaises(HarnessError) as caught:
                                if operation == "plan":
                                    install.build_plan(selected_profile, selected_private, sys.executable)
                                else:
                                    # Rejection must precede even reading a receipt, let alone restoring files.
                                    install.rollback(private / "installation-backups" / "not-read.json", True,
                                                     selected_profile, selected_private)
                            self.assertEqual("unsupported_link", caught.exception.code)
                            for path, raw in before.items():
                                self.assertEqual(raw, path.read_bytes())
                            self.assertFalse((private / "installation-backups").exists())
                            self.assertFalse((private / "releases").exists())
                            self.assertEqual([], list(shared.iterdir()))


if __name__ == "__main__":
    unittest.main()
