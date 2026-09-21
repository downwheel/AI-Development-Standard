"""Exact Git failure classification without retries or sensitive stderr output."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from harness.common import HarnessError
from harness.history import Journal, REF, _git_failure_details


class GitDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='git-diagnostic-fixture-')
        self.root = Path(self.temporary.name)
        self.journal = Journal(self.root / 'private' / 'history.git')

    def tearDown(self):
        self.temporary.cleanup()

    def test_real_missing_ref_uses_quiet_missing_exit_without_creating_history(self):
        self.journal.path.mkdir(parents=True)
        subprocess.run(['git', 'init', '--bare', '--quiet', str(self.journal.path)], check=True, capture_output=True)
        with self.assertRaises(HarnessError) as caught:
            self.journal._tip()
        self.assertEqual('journal_corrupt', caught.exception.code)
        self.assertIn('exit_code=1', str(caught.exception))
        self.assertFalse((self.journal.path / 'refs' / 'heads' / 'history').exists())

    def test_process_failure_is_not_reported_as_deleted_ref_and_not_retried(self):
        outcome = subprocess.CompletedProcess(['git'], 0xc0000142, b'', b'')
        with patch.object(self.journal, '_git', return_value=outcome) as run:
            with self.assertRaises(HarnessError) as caught:
                self.journal._tip()
        self.assertEqual('git_error', caught.exception.code)
        self.assertIn('status_hex=0xc0000142', str(caught.exception))
        self.assertIn('diagnostic=process_initialization_failed', str(caught.exception))
        run.assert_called_once_with('rev-parse', '--verify', '--quiet', REF, check=False)

    def test_resource_failure_has_only_allowlisted_diagnostics(self):
        stderr = b'fatal: cannot fork: Resource temporarily unavailable; password=NEVER-EXPOSE; path=C:/private/user-data'
        result = subprocess.CompletedProcess(['git'], 128, b'', stderr)
        diagnostic = _git_failure_details('cat-file', result)
        self.assertIn('exit_code=128', diagnostic)
        self.assertIn('diagnostic=resource_exhausted', diagnostic)
        self.assertNotIn('NEVER-EXPOSE', diagnostic)
        self.assertNotIn('C:/private', diagnostic)
        self.assertNotIn('password', diagnostic)

    def test_general_git_failure_preserves_status_and_uses_one_attempt(self):
        result = subprocess.CompletedProcess(['git'], 129, b'', b'error: private text NEVER-EXPOSE')
        with patch('harness.history.subprocess.run', return_value=result) as run:
            with self.assertRaises(HarnessError) as caught:
                self.journal._git('cat-file', 'blob', 'a' * 40)
        self.assertEqual('git_error', caught.exception.code)
        self.assertIn('command=cat-file', str(caught.exception))
        self.assertIn('exit_code=129', str(caught.exception))
        self.assertNotIn('NEVER-EXPOSE', str(caught.exception))
        self.assertEqual(1, run.call_count)

    def test_success_requires_valid_object_identifier(self):
        for value in (b'', b'unexpected diagnostics', b'\xff'):
            with self.subTest(value=value), patch.object(self.journal, '_git', return_value=subprocess.CompletedProcess(['git'], 0, value, b'')):
                with self.assertRaises(HarnessError) as caught:
                    self.journal._tip()
                self.assertEqual('journal_corrupt', caught.exception.code)
        with patch.object(self.journal, '_git', return_value=subprocess.CompletedProcess(['git'], 0, b'a' * 40 + b'\n', b'')):
            self.assertEqual('a' * 40, self.journal._tip())


if __name__ == '__main__':
    unittest.main()
