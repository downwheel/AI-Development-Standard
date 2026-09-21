"""Isolated fixtures: no real product, installation, or team Git is changed."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.common import HarnessError, sha256
from harness.history import (Journal, apply_restore, capture_snapshot, export_snapshot,
                             observe_workspace, plan_restore, reconcile_recovery,
                             record_restore_decision, snapshot_matches)
from harness import history


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.product = self.base / 'product'
        self.product.mkdir()
        self.journal = Journal(self.base / 'private' / 'history.git')
        self.initial = {'schema_version': 2,
                        'project': {'project_id': 'project-test', 'standard_root': str(self.base / 'standard'), 'standard_release': '2.0.0'},
                        'workspaces': {'workspace-test': {'root': str(self.product)}},
                        'snapshots': {}, 'events': [], 'requests': {}}
        self.journal.initialize(self.initial)

    def tearDown(self):
        self.temporary.cleanup()

    def assert_code(self, expected, function, *args, **kwargs):
        with self.assertRaises(HarnessError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected)

    def capture(self, **kwargs):
        return capture_snapshot(self.journal, 'workspace-test', **kwargs)

    def approve(self, plan, decision='approve'):
        return record_restore_decision(self.journal, plan['plan_id'], decision,
                                       'Fixture user explicitly approves these files.' if decision == 'approve' else 'Fixture user rejects this plan.',
                                       {'fixture': True, 'message_id': 'user-test'})

    def make_restore(self):
        (self.product / 'a.txt').write_bytes(b'before\r\n')
        (self.product / 'b.bin').write_bytes(b'\x00\x01\xff')
        snapshot = self.capture()
        (self.product / 'a.txt').write_bytes(b'after\n')
        (self.product / 'b.bin').unlink()
        (self.product / 'added.txt').write_bytes(b'added by later managed work')
        self.capture()
        plan = plan_restore(self.journal, snapshot['snapshot_id'], 'workspace-test')
        self.approve(plan)
        return snapshot, plan

    def test_read_constructor_and_missing_read_have_no_side_effects(self):
        path = self.base / 'missing' / 'history.git'
        journal = Journal(path)
        self.assertFalse(path.parent.exists())
        self.assert_code('journal_not_initialized', journal.read)
        self.assertFalse(path.parent.exists())

    def test_transaction_rollback_and_idempotent_empty_state(self):
        tip = self.journal._tip()
        def broken(state):
            state['bad'] = True
            self.journal.put_blob(b'abandoned')
            raise ValueError('fixture failure')
        with self.assertRaises(ValueError):
            self.journal.transaction(broken)
        self.assertEqual(self.journal._tip(), tip)
        self.assertNotIn('bad', self.journal.read())
        self.journal.transaction(lambda state: state['schema_version'])
        self.assertEqual(self.journal._tip(), tip)

    def test_nested_transaction_rejected(self):
        self.assert_code('nested_transaction', self.journal.transaction,
                         lambda state: self.journal.transaction(lambda inner: None))

    def test_raw_blobs_are_reachable_and_survive_gc(self):
        raw = b'\xef\xbb\xbfUnicode\r\n\x00\xff\x01'
        (self.product / 'binary.dat').write_bytes(raw)
        snapshot = self.capture()
        oid = snapshot['manifest']['files'][0]['oid']
        self.journal._git('gc', '--prune=now')  # isolated fixture, no concurrent writer
        self.assertEqual(self.journal.get_blob(oid), raw)
        self.assertTrue(self.journal.fsck()['ok'])
        self.assertTrue(snapshot_matches(self.journal, snapshot['snapshot_id']))

    def test_snapshot_excludes_metadata_secrets_and_caches(self):
        (self.product / '.env').write_text('PASSWORD=fixture-only', encoding='utf-8')
        (self.product / '.env.production').write_text('private', encoding='utf-8')
        (self.product / '.env.example').write_text('PASSWORD=', encoding='utf-8')
        (self.product / '.git').mkdir()
        (self.product / '.git' / 'config').write_text('private Git config', encoding='utf-8')
        (self.product / 'node_modules').mkdir()
        (self.product / 'node_modules' / 'cache.js').write_text('generated', encoding='utf-8')
        (self.product / 'new-untracked.py').write_text('print(1)', encoding='utf-8')
        snapshot = self.capture()
        self.assertEqual({item['path'] for item in snapshot['manifest']['files']}, {'.env.example', 'new-untracked.py'})
        self.assertEqual(len(snapshot['manifest']['exclusions']), 4)

    def test_secret_content_fails_without_snapshot(self):
        (self.product / 'source.txt').write_text('-----BEGIN ' + 'PRIVATE KEY-----', encoding='utf-8')
        tip = self.journal._tip()
        self.assert_code('secret_content', self.capture)
        self.assertEqual(self.journal._tip(), tip)

    def test_limits_do_not_publish_partial_snapshot(self):
        (self.product / 'large.bin').write_bytes(b'12345')
        tip = self.journal._tip()
        self.assert_code('capture_limit', self.capture, policy={'max_file_bytes': 4})
        self.assertEqual(self.journal._tip(), tip)
        self.assertEqual(self.journal.read()['snapshots'], {})

    def test_detected_change_between_passes_is_not_published(self):
        (self.product / 'a.txt').write_bytes(b'first')
        original = history._scan
        calls = []
        def mutate(root, policy):
            result = original(root, policy)
            calls.append(True)
            if len(calls) == 1:
                (root / 'a.txt').write_bytes(b'second')
            return result
        tip = self.journal._tip()
        with mock.patch.object(history, '_scan', side_effect=mutate):
            self.assert_code('source_changed', self.capture)
        self.assertEqual(self.journal._tip(), tip)

    def test_link_is_rejected_without_following_it(self):
        target = self.base / 'outside.txt'
        target.write_bytes(b'outside')
        try:
            (self.product / 'link.txt').symlink_to(target)
        except OSError:
            self.skipTest('Host does not permit symlink creation for this fixture.')
        self.assert_code('unsupported_link', self.capture)

    @unittest.skipUnless(os.name == 'nt', 'Windows junction fixture only')
    def test_windows_junction_is_rejected(self):
        target = self.base / 'outside-directory'
        target.mkdir()
        (target / 'private.txt').write_bytes(b'outside')
        link = self.product / 'linked-directory'
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        self.assert_code('unsupported_link', self.capture)
        self.assertEqual((target / 'private.txt').read_bytes(), b'outside')

    def test_export_preserves_bytes_and_empty_directories(self):
        (self.product / '한글 폴더').mkdir()
        (self.product / 'empty').mkdir()
        raw = b'\xef\xbb\xbftext\r\n\x00\xff'
        (self.product / '한글 폴더' / 'file.bin').write_bytes(raw)
        (self.product / '.env').write_bytes(b'EXCLUDED=value')
        snapshot = self.capture()
        destination = self.base / 'export'
        receipt = export_snapshot(self.journal, snapshot['snapshot_id'], destination)
        self.assertEqual(receipt['status'], 'export_verified')
        self.assertEqual((destination / '한글 폴더' / 'file.bin').read_bytes(), raw)
        self.assertTrue((destination / 'empty').is_dir())
        self.assertFalse((destination / '.env').exists())
        self.assertFalse((self.product / '.git').exists())
        self.assertFalse((self.product / '.harness').exists())

    def test_export_refuses_overlap_and_nonempty_destination(self):
        snapshot = self.capture()
        self.assert_code('path_overlap', export_snapshot, self.journal, snapshot['snapshot_id'], self.product / 'export')
        destination = self.base / 'export'
        destination.mkdir()
        (destination / 'user.txt').write_bytes(b'keep')
        self.assert_code('destination_not_empty', export_snapshot, self.journal, snapshot['snapshot_id'], destination)
        self.assertEqual((destination / 'user.txt').read_bytes(), b'keep')

    def test_even_a_registered_malformed_snapshot_cannot_export_git_metadata(self):
        (self.product / 'source.txt').write_bytes(b'source')
        snapshot = self.capture()
        def forge(state):
            item = state['snapshots'][snapshot['snapshot_id']]
            item['manifest']['files'][0]['path'] = '.git/config'
            item['manifest_sha256'] = history._digest(item['manifest'])
        self.journal.transaction(forge)
        self.assert_code('excluded_path', export_snapshot, self.journal, snapshot['snapshot_id'], self.base / 'export')
        self.assertFalse((self.base / 'export').exists())

    def test_capture_request_id_is_idempotent_and_bound(self):
        (self.product / 'a').write_bytes(b'a')
        first = self.capture(request_id='capture-once')
        tip = self.journal._tip()
        second = self.capture(request_id='capture-once')
        self.assertEqual(first, second)
        self.assertEqual(self.journal._tip(), tip)
        self.assert_code('request_conflict', self.capture, label='different', request_id='capture-once')

    def test_observe_and_matches_do_not_write_journal_or_lock(self):
        (self.product / 'a').write_bytes(b'a')
        snapshot = self.capture()
        lock = self.journal.directory / '.history.lock'
        lock.unlink()
        tip = self.journal._tip()
        self.assertEqual(observe_workspace(self.journal, 'workspace-test')['manifest_sha256'], snapshot['manifest_sha256'])
        self.assertTrue(snapshot_matches(self.journal, snapshot['snapshot_id']))
        self.assertFalse(lock.exists())
        self.assertEqual(self.journal._tip(), tip)

    def test_plan_needs_approval_and_reject_supersedes_approval(self):
        (self.product / 'a').write_bytes(b'a')
        snapshot = self.capture()
        (self.product / 'a').write_bytes(b'b')
        plan = plan_restore(self.journal, snapshot['snapshot_id'], 'workspace-test')
        self.assert_code('restore_approval_required', apply_restore, self.journal, plan['plan_id'], 'apply-one')
        self.approve(plan)
        self.approve(plan, 'reject')
        self.assert_code('restore_approval_required', apply_restore, self.journal, plan['plan_id'], 'apply-one')
        self.assertEqual((self.product / 'a').read_bytes(), b'b')

    def test_restore_recreates_deletes_and_idempotently_returns_receipt(self):
        snapshot, plan = self.make_restore()
        receipt = apply_restore(self.journal, plan['plan_id'], 'apply-once')
        self.assertEqual(receipt['status'], 'restore_verified')
        self.assertTrue(receipt['verification_required'])
        self.assertTrue(snapshot_matches(self.journal, snapshot['snapshot_id']))
        tip = self.journal._tip()
        self.assertEqual(apply_restore(self.journal, plan['plan_id'], 'apply-once'), receipt)
        self.assertEqual(self.journal._tip(), tip)

    def test_unrecorded_user_added_file_is_preserved(self):
        (self.product / 'a').write_bytes(b'old')
        snapshot = self.capture()
        (self.product / 'a').write_bytes(b'new')
        (self.product / 'user-new').write_bytes(b'keep')
        (self.product / 'user-empty').mkdir()
        plan = plan_restore(self.journal, snapshot['snapshot_id'], 'workspace-test')
        self.assertEqual(plan['preserved_paths'], ['user-new'])
        self.approve(plan)
        apply_restore(self.journal, plan['plan_id'], 'preserve-user')
        self.assertEqual((self.product / 'user-new').read_bytes(), b'keep')
        self.assertEqual((self.product / 'a').read_bytes(), b'old')
        self.assertTrue((self.product / 'user-empty').is_dir())

    def test_change_after_plan_approval_blocks_all_writes(self):
        unused, plan = self.make_restore()
        (self.product / 'a.txt').write_bytes(b'new user edit')
        self.assert_code('restore_conflict', apply_restore, self.journal, plan['plan_id'], 'conflict')
        self.assertEqual((self.product / 'a.txt').read_bytes(), b'new user edit')

    def test_crash_after_file_replace_can_resume(self):
        unused, plan = self.make_restore()
        original = history._replace_file
        def crash(path, raw):
            original(path, raw)
            raise RuntimeError('injected after file replace')
        with mock.patch.object(history, '_replace_file', side_effect=crash):
            with self.assertRaises(RuntimeError):
                apply_restore(self.journal, plan['plan_id'], 'crash-resume')
        self.assertEqual(reconcile_recovery(self.journal, plan['plan_id'], 'status')['status'], 'recovery_required')
        self.assert_code('recovery_required', self.capture)
        result = reconcile_recovery(self.journal, plan['plan_id'], 'resume')
        self.assertEqual(result['status'], 'restore_verified')
        self.assertEqual((self.product / 'a.txt').read_bytes(), b'before\r\n')

    def test_process_exit_after_replace_leaves_resumable_writeahead(self):
        unused, plan = self.make_restore()
        script = '''import os,sys
from pathlib import Path
from harness import history
journal=history.Journal(Path(sys.argv[1]))
original=history._replace_file
def crash(path,raw):
    original(path,raw)
    os._exit(77)
history._replace_file=crash
history.apply_restore(journal,sys.argv[2],'process-exit')
'''
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.journal.path), plan['plan_id']],
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 77, result.stderr.decode('utf-8', errors='replace'))
        self.assert_code('recovery_required', self.capture)
        self.assertEqual(reconcile_recovery(self.journal, plan['plan_id'], 'resume')['status'], 'restore_verified')

    def test_process_exit_after_final_commit_does_not_reapply(self):
        unused, plan = self.make_restore()
        script = '''import os,sys
from pathlib import Path
from harness import history
journal=history.Journal(Path(sys.argv[1]))
original=journal._commit
calls=0
def crash(state,previous=None):
    global calls
    result=original(state,previous)
    calls+=1
    if calls==2:
        os._exit(78)
    return result
journal._commit=crash
history.apply_restore(journal,sys.argv[2],'commit-exit')
'''
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.journal.path), plan['plan_id']],
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 78, result.stderr.decode('utf-8', errors='replace'))
        tip = self.journal._tip()
        receipt = apply_restore(self.journal, plan['plan_id'], 'commit-exit')
        self.assertEqual(receipt['status'], 'restore_verified')
        self.assertEqual(self.journal._tip(), tip)
        self.assertEqual(reconcile_recovery(self.journal, plan['plan_id'], 'status')['status'], 'completed')

    def test_crash_can_rollback_to_precapture(self):
        unused, plan = self.make_restore()
        before = observe_workspace(self.journal, 'workspace-test')['manifest_sha256']
        original = history._replace_file
        def crash(path, raw):
            original(path, raw)
            raise RuntimeError('injected crash')
        with mock.patch.object(history, '_replace_file', side_effect=crash):
            with self.assertRaises(RuntimeError):
                apply_restore(self.journal, plan['plan_id'], 'crash-rollback')
        result = reconcile_recovery(self.journal, plan['plan_id'], 'rollback')
        self.assertEqual(result['status'], 'rolled_back')
        self.assertEqual(observe_workspace(self.journal, 'workspace-test')['manifest_sha256'], before)

    def test_recovery_does_not_overwrite_new_user_edit(self):
        unused, plan = self.make_restore()
        original = history._replace_file
        def crash(path, raw):
            original(path, raw)
            raise RuntimeError('injected crash')
        with mock.patch.object(history, '_replace_file', side_effect=crash):
            with self.assertRaises(RuntimeError):
                apply_restore(self.journal, plan['plan_id'], 'crash-conflict')
        (self.product / 'a.txt').write_bytes(b'unrelated user edit')
        self.assert_code('recovery_conflict', reconcile_recovery, self.journal, plan['plan_id'], 'resume')
        self.assertEqual((self.product / 'a.txt').read_bytes(), b'unrelated user edit')

    def test_precapture_failure_leaves_source_unchanged(self):
        unused, plan = self.make_restore()
        original = (self.product / 'a.txt').read_bytes()
        with mock.patch.object(history, '_capture', side_effect=HarnessError('capture_io', 'fixture')):
            self.assert_code('capture_io', apply_restore, self.journal, plan['plan_id'], 'pre-failure')
        self.assertEqual((self.product / 'a.txt').read_bytes(), original)

    def test_git_cas_rejection_preserves_published_state(self):
        tip = self.journal._tip()
        original = self.journal._git
        def reject(*args, **kwargs):
            if args[0] == 'update-ref':
                return subprocess.CompletedProcess(args, 1, b'', b'CAS fixture conflict')
            return original(*args, **kwargs)
        with mock.patch.object(self.journal, '_git', side_effect=reject):
            self.assert_code('journal_conflict', self.journal.transaction, lambda state: state.update({'new': True}))
        self.assertEqual(self.journal._tip(), tip)
        self.assertNotIn('new', self.journal.read())

    def test_cross_process_transactions_do_not_lose_updates(self):
        script = ('import sys,time; from pathlib import Path; from harness.history import Journal; '
                  'j=Journal(Path(sys.argv[1])); '
                  'j.transaction(lambda s:(time.sleep(0.15),s.update(counter=s.get("counter",0)+1)))')
        children = [subprocess.Popen([sys.executable, '-B', '-c', script, str(self.journal.path)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE) for unused in range(4)]
        for child in children:
            stdout, stderr = child.communicate(timeout=60)
            self.assertEqual(child.returncode, 0, stderr.decode('utf-8', errors='replace'))
        self.assertEqual(self.journal.read()['counter'], 4)

    def test_existing_product_staged_and_unstaged_metadata_unchanged(self):
        def product_git(*args):
            result = subprocess.run(['git', '-C', str(self.product), *args], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
        product_git('init', '--quiet')
        (self.product / 'code.txt').write_bytes(b'staged')
        product_git('add', 'code.txt')
        (self.product / 'code.txt').write_bytes(b'working before')
        git_dir = self.product / '.git'
        digest = lambda: {str(p.relative_to(git_dir)): sha256(p.read_bytes()) for p in git_dir.rglob('*') if p.is_file()}
        before = digest()
        snapshot = self.capture()
        (self.product / 'code.txt').write_bytes(b'working after')
        plan = plan_restore(self.journal, snapshot['snapshot_id'], 'workspace-test')
        self.approve(plan)
        apply_restore(self.journal, plan['plan_id'], 'git-preservation')
        self.assertEqual((self.product / 'code.txt').read_bytes(), b'working before')
        self.assertEqual(digest(), before)

    def test_private_history_cannot_be_inside_product(self):
        journal = Journal(self.product / 'private' / 'history.git')
        self.assert_code('path_overlap', journal.initialize, self.initial)
        self.assertFalse(journal.directory.exists())


if __name__ == '__main__':
    unittest.main()
