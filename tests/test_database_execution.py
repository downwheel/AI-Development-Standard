"""Synthetic journal/session integration with real SQL files and typed DB adapter.

The journal and approval provenance below are fixtures, not real user decisions.
No user credentials, account, SQL Server instance, or product repository is used.
"""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from harness.common import HarnessError, encoded, sha256
from harness.database import compile_migration, execute_plan, check_plan_current
from harness.execution_database import execute_database, database_completion
from harness.execution import Execution
from tests import test_database as database_fixtures


def ref(name):
    return {'artifact_id': name, 'revision_id': name + '-rev', 'sha256': sha256(name.encode())}


class SyntheticJournal:
    def __init__(self, state):
        self.state = copy.deepcopy(state)

    def read(self):
        return copy.deepcopy(self.state)

    def transaction(self, callback):
        proposed = copy.deepcopy(self.state)
        result = callback(proposed)
        self.state = proposed
        return copy.deepcopy(result)


class DatabaseExecutionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='synthetic DB execution ')
        self.root = Path(self.folder.name)
        fixture = database_fixtures.DatabaseTest('test_schema_and_preview_do_not_execute')
        fixture.setUp()
        self.db, self.resolved = fixture.db, fixture.resolved
        self.plan = fixture.plan()
        self.plan_ref, self.env_ref, self.scope_ref = ref('database'), ref('environment'), ref('scope')
        self.plan['environment_ref'] = self.env_ref
        self.contract = {'profile_id': 'fixture', 'roles': ['migration']}
        self.scope = {'files': [{'path': self.plan['migrations'][0]['source_path'], 'action': 'create'}]}
        self.sql = self.root / self.plan['migrations'][0]['source_path']
        self.sql.parent.mkdir(parents=True)
        self.sql.write_bytes(compile_migration(self.plan['migrations'][0]['operation'])['sql'].encode('utf-8'))
        self.basis = {'review_id': 'synthetic-gate-b-not-human', 'unit_ref': ref('unit'), 'test_ref': ref('tests'),
                      'scope_ref': self.scope_ref, 'environment_refs': [self.env_ref], 'db_plan_refs': [self.plan_ref]}
        self.live_basis = copy.deepcopy(self.basis)
        self.basis_error = None
        self.artifacts = {self.plan_ref['revision_id']: self.plan, self.env_ref['revision_id']: self.contract,
                          self.scope_ref['revision_id']: self.scope}
        state = {'execution_sessions': {'session': {'owner': 'fixture-owner', 'status': 'open', 'lease_id': 'fixture-lease',
                    'run_id': 'run', 'unit_id': 'unit', 'workspace_id': 'workspace', 'mode': 'change', 'basis': self.basis}},
                 'leases': {'fixture-lease': {'owner': 'fixture-owner', 'live': True}}}
        self.journal = SyntheticJournal(state)
        workflow = SimpleNamespace(_basis=lambda state, run, unit: self.current_basis(),
                                   implementation_basis=lambda run, unit: self.current_basis(),
                                   load_artifact=lambda item: {'payload': copy.deepcopy(self.artifacts[item['revision_id']])})
        manager = SimpleNamespace(validate_contract=lambda contract: {'status': 'passed'},
                                  resolve=lambda profile_id, role: self.resolved)
        self.execution = SimpleNamespace(journal=self.journal, workflow=workflow, _lease_state=self.lease,
                                         _environment_manager=lambda: manager, _root=lambda workspace: self.root,
                                         _artifact=self.artifact)

    def tearDown(self):
        self.folder.cleanup()

    def current_basis(self):
        if self.basis_error:
            raise HarnessError(self.basis_error, 'Synthetic missing or stale approval')
        return copy.deepcopy(self.live_basis)

    def lease(self, state, lease_id, owner):
        lease = state['leases'].get(lease_id)
        if not lease or not lease['live'] or lease['owner'] != owner:
            raise HarnessError('lease_lost', 'Synthetic lease lost')

    def artifact(self, state, kind, payload, report, session, refs, name):
        state.setdefault('evidence', []).append({'kind': kind, 'payload': payload, 'report': report})
        return ref(name)

    def invoke(self, request_id='fixture-request', owner='fixture-owner', session_id='session'):
        return execute_database(self.execution, session_id, owner, request_id)

    def adapter(self, plan, resolved, *, approval_binding):
        return execute_plan(plan, resolved, approval_binding=approval_binding, connection_factory=self.db.connect)

    def code(self, code, callback):
        with self.assertRaises(HarnessError) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)

    def test_migration_missing_or_modified_is_blocked_before_connection(self):
        for content in (None, b'-- unapproved SQL mutation'):
            with self.subTest(content=content):
                if content is None:
                    self.sql.unlink()
                else:
                    self.sql.write_bytes(content)
                with patch('harness.database.execute_plan', side_effect=self.adapter) as adapter:
                    self.code('db_migration_changed', lambda: self.invoke(request_id='missing' if content is None else 'changed'))
                    adapter.assert_not_called()
                self.assertEqual([], self.db.calls)
        rows = self.journal.read()['db_executions'].values()
        self.assertTrue(all(row['status'] == 'blocked' and row['phase'] == 'preflight' for row in rows))

    def test_unapproved_file_and_delete_scope_never_reach_adapter(self):
        for files in ([], [{'path': self.scope['files'][0]['path'], 'action': 'delete'}]):
            with self.subTest(files=files):
                self.artifacts[self.scope_ref['revision_id']]['files'] = files
                with patch('harness.database.execute_plan', side_effect=self.adapter) as adapter:
                    self.code('db_migration_scope', lambda: self.invoke(request_id='scope-' + str(len(files))))
                    adapter.assert_not_called()
        self.assertEqual([], self.db.calls)

    def test_session_ownership_lease_approval_and_observe_boundaries(self):
        with patch('harness.database.execute_plan', side_effect=self.adapter) as adapter:
            self.code('owner_mismatch', lambda: self.invoke(owner='other-owner'))
            self.code('owner_mismatch', lambda: self.invoke(session_id='missing-session'))
            self.journal.state['leases']['fixture-lease']['live'] = False
            self.code('lease_lost', lambda: self.invoke())
            self.journal.state['leases']['fixture-lease']['live'] = True
            self.basis_error = 'gate_b_required'
            self.code('gate_b_required', lambda: self.invoke())
            self.basis_error = None
            self.live_basis['review_id'] = 'different-current-review'
            self.code('basis_changed', lambda: self.invoke())
            self.live_basis = copy.deepcopy(self.basis)
            self.journal.state['execution_sessions']['session']['mode'] = 'observe'
            self.code('observation_readonly', lambda: self.invoke())
            adapter.assert_not_called()
        self.assertNotIn('db_executions', self.journal.read())

    def test_environment_must_be_in_same_approval_and_role_unambiguous(self):
        self.live_basis['environment_refs'] = []
        self.journal.state['execution_sessions']['session']['basis'] = copy.deepcopy(self.live_basis)
        with patch('harness.database.execute_plan', side_effect=self.adapter) as adapter:
            self.code('db_environment_unapproved', lambda: self.invoke())
            adapter.assert_not_called()
        self.live_basis = copy.deepcopy(self.basis)
        self.journal.state['execution_sessions']['session']['basis'] = copy.deepcopy(self.basis)
        self.contract['roles'] = ['migration', 'fixture']
        with patch('harness.database.execute_plan', side_effect=self.adapter) as adapter:
            self.code('db_role_ambiguous', lambda: self.invoke(request_id='two-roles'))
            adapter.assert_not_called()

    def test_exact_source_and_typed_adapter_commit_once_then_replay_is_readonly(self):
        with patch('harness.database.execute_plan', side_effect=self.adapter) as adapter:
            result = self.invoke()
            self.assertEqual('passed', result['status'])
            self.assertEqual('passed', result['receipts'][0]['result']['independent_observation'])
            self.assertEqual(1, sum(row[0] == 'commit' for row in self.db.calls))
            self.assertEqual(2, len(self.db.data['dbo.Notes']))
            replay = self.invoke()
            self.assertEqual(result, replay)
            self.assertEqual(1, adapter.call_count)
            self.code('request_conflict', lambda: self.invoke(owner='another-owner'))
            self.assertEqual(1, adapter.call_count)
        evidence = self.journal.read()['evidence']
        self.assertEqual('db-execution-receipt', evidence[0]['kind'])
        self.assertNotIn('NEVER-REPORT', encoded(evidence).decode())

    def test_interruption_after_adapter_started_preserves_uncertainty_and_blocks_new_write(self):
        with patch('harness.database.execute_plan', side_effect=RuntimeError('SYNTHETIC undisclosed driver failure')) as adapter:
            with self.assertRaises(RuntimeError):
                self.invoke()
            interrupted = self.journal.read()['db_executions']['database/fixture-request']
            self.assertEqual('indeterminate', interrupted['status'])
            self.assertFalse(interrupted['automatic_retry'])
            self.assertEqual(interrupted, self.invoke())
            self.code('db_reconciliation_required', lambda: self.invoke(request_id='new-attempt'))
            self.assertEqual(1, adapter.call_count)
            self.assertNotIn('undisclosed driver failure', encoded(self.journal.read()).decode())

    def test_unknown_commit_returned_by_real_adapter_blocks_new_writes(self):
        self.db.commit_error = True
        with patch('harness.database.execute_plan', side_effect=self.adapter) as adapter:
            result = self.invoke()
            self.assertEqual('unknown', result['receipts'][0]['result']['commit_outcome'])
            self.assertEqual(2, len(self.db.data['dbo.Notes']), 'Synthetic server committed before transport failure.')
            self.assertEqual('indeterminate', result['status'])
            self.code('db_reconciliation_required', lambda: self.invoke(request_id='must-not-retry'))
            self.assertEqual(1, adapter.call_count)

    def test_live_completion_observes_database_drift_independently(self):
        self.assertEqual('not_run', database_completion(self.execution, self.basis)['status'])
        with patch('harness.database.execute_plan', side_effect=self.adapter):
            self.invoke()
        observe = lambda plan, resolved, receipt: check_plan_current(plan, resolved, receipt, connection_factory=self.db.connect)
        with patch('harness.database.check_plan_current', side_effect=observe):
            self.assertTrue(database_completion(self.execution, self.basis)['passed'])
            self.db.data['dbo.Notes'][1]['Body'] = 'Independent external change'
            self.assertFalse(database_completion(self.execution, self.basis)['passed'])

    def test_finish_cannot_close_session_while_database_adapter_runs(self):
        core=Execution(self.journal)
        core.workflow._require_runtime=lambda state,run_id: None
        self.journal.state['db_executions']={'database/active':{'session_id':'session','status':'running'}}
        with patch('harness.execution.capture_snapshot') as capture:
            self.code('db_adapter_active',lambda: core.finish('session','fixture-owner','Synthetic finish','completed'))
            capture.assert_not_called()
        self.assertEqual('open',self.journal.state['execution_sessions']['session']['status'])

    def test_finish_rechecks_database_reservation_after_source_capture(self):
        core=Execution(self.journal)
        core.workflow._require_runtime=lambda state,run_id: None
        core._lease_state=lambda state,lease_id,owner: None
        def concurrent_start(*args,**kwargs):
            self.journal.state['db_executions']={'database/active':{'session_id':'session','status':'running'}}
            return {'snapshot_id':'synthetic-after'}
        with patch('harness.execution.capture_snapshot',side_effect=concurrent_start):
            self.code('db_adapter_active',lambda: core.finish('session','fixture-owner','Synthetic finish','completed'))
        self.assertEqual('open',self.journal.state['execution_sessions']['session']['status'])


if __name__ == '__main__':
    unittest.main()
