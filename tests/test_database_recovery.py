"""Recovery tests use synthetic approvals/DB and never connect a real service."""
import copy
import unittest
from unittest.mock import patch

from harness.common import HarnessError, encoded
from harness.database import inspect_database
from harness.database_recovery import DatabaseRecovery
from harness.workflow import Workflow
from tests import test_database_execution as execution_fixtures


class DatabaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        fixture = execution_fixtures.DatabaseExecutionTests('test_unknown_commit_returned_by_real_adapter_blocks_new_writes')
        fixture.setUp()
        self.fixture = fixture
        self.addCleanup(fixture.tearDown)
        fixture.db.commit_error = True
        with patch('harness.database.execute_plan', side_effect=fixture.adapter):
            result = fixture.invoke()
        self.assertEqual('indeterminate', result['status'])
        fixture.db.commit_error = False
        fixture.journal.state['execution_sessions']['session']['status'] = 'closed'
        fixture.journal.state['runs'] = {'run': {'run_id': 'run'}}
        # Use the real change-intent transition, not a test-created pending flag.
        fixture.execution.workflow._operate = Workflow(fixture.journal)._operate
        fixture.execution.workflow._require_runtime = lambda state,run_id: None
        self.recovery = DatabaseRecovery(fixture.execution)
        self.observer = patch('harness.database.inspect_database', side_effect=self.observe)
        self.mock_observer = self.observer.start()
        self.addCleanup(self.observer.stop)

    def observe(self, resolved, tables, *, max_rows, max_catalog_objects):
        return inspect_database(resolved, tables, max_rows=max_rows, max_catalog_objects=max_catalog_objects,
                                connection_factory=self.fixture.db.connect)

    def plan(self):
        return self.recovery.execute('plan_database_recovery', {'request_id': 'fixture-request', 'owner': 'fixture-owner'})

    def decide(self, preview, decision='accept_observed', message='SYNTHETIC user decision fixture; not a real approval'):
        return self.recovery.execute('record_database_recovery', {'recovery_id': preview['recovery_id'],
            'decision': decision, 'user_message': message, 'source': 'isolated synthetic test'})

    def code(self, code, callback):
        with self.assertRaises(HarnessError) as caught:
            callback()
        self.assertEqual(code, caught.exception.code)

    def test_preview_is_bounded_readonly_and_contains_no_row_values(self):
        before_data = copy.deepcopy(self.fixture.db.data)
        calls_before = len(self.fixture.db.calls)
        preview = self.plan()
        self.assertEqual(before_data, self.fixture.db.data)
        self.assertTrue(all(call[0] in {'connect', 'close'} for call in self.fixture.db.calls[calls_before:]))
        observation = preview['preview']['observations'][0]['observation']
        self.assertEqual(2, observation['objects'][0]['row_count'])
        self.assertEqual(100, observation['limits']['max_rows'])
        self.assertEqual(100, observation['limits']['max_catalog_objects'])
        self.assertNotIn('Synthetic memo', encoded(preview).decode())
        self.assertNotIn('NEVER-REPORT', encoded(preview).decode())
        self.assertEqual('indeterminate', self.fixture.journal.read()['db_executions']['database/fixture-request']['status'])

    def test_accept_fresh_observation_preserves_history_and_creates_pending_change(self):
        preview = self.plan()
        original_receipts = copy.deepcopy(self.fixture.journal.read()['db_executions']['database/fixture-request']['receipts'])
        calls_before = len(self.fixture.db.calls)
        result = self.decide(preview)
        state = self.fixture.journal.read()
        attempt = state['db_executions']['database/fixture-request']
        self.assertEqual('reconciled', attempt['status'])
        self.assertEqual('indeterminate', attempt['original_status'])
        self.assertFalse(attempt['automatic_retry'])
        self.assertEqual(original_receipts, attempt['receipts'])
        self.assertEqual('requested', state['changes'][result['change_id']]['status'])
        self.assertEqual(['unit'], state['changes'][result['change_id']]['unit_ids'])
        self.assertEqual('revise_contract_and_obtain_new_gate_b', result['next_action'])
        self.assertEqual(preview, state['db_recovery_previews'][preview['recovery_id']])
        self.assertEqual(result, self.decide(preview))
        self.assertEqual(2, self.mock_observer.call_count)
        self.assertTrue(all(call[0] in {'connect', 'close'} for call in self.fixture.db.calls[calls_before:]))

    def test_stale_data_observation_needs_new_presented_preview(self):
        preview = self.plan()
        self.fixture.db.data['dbo.Notes'][1]['Body'] = 'External change after presentation'
        self.code('db_recovery_stale', lambda: self.decide(preview))
        state = self.fixture.journal.read()
        self.assertEqual('indeterminate', state['db_executions']['database/fixture-request']['status'])
        self.assertNotIn('changes', state)
        self.assertNotIn('db_recovery_decisions', state)

    def test_active_controller_is_blocked_even_when_lease_expired(self):
        self.fixture.journal.state['execution_sessions']['session']['status'] = 'open'
        self.fixture.journal.state['leases']['fixture-lease']['expires_at'] = '2000-01-01T00:00:00Z'
        self.code('db_controller_active', self.plan)
        self.mock_observer.assert_not_called()

    def test_recovery_requires_the_recorded_runtime_before_database_observation(self):
        def wrong_runtime(state,run_id):
            raise HarnessError('runtime_mismatch','Synthetic different pinned runtime')
        self.fixture.execution.workflow._require_runtime=wrong_runtime
        self.code('runtime_mismatch',self.plan)
        self.mock_observer.assert_not_called()

    def test_crash_left_running_adapter_requires_positive_controller_exit(self):
        state = self.fixture.journal.state
        attempt = state['db_executions']['database/fixture-request']
        attempt.update(status='running', phase='adapter_started')
        attempt.pop('finished_at', None)
        state['execution_requests'] = {'implementation/fixture': {'session_id': 'session', 'status': 'interrupted',
            'controller': {'pid': 99123, 'token': 'synthetic-birth-identity'}}}
        with patch('harness.execution.observed_process', return_value={'state': 'alive'}):
            self.code('db_adapter_active', self.plan)
        with patch('harness.execution.observed_process', return_value={'state': 'unknown'}):
            self.code('db_adapter_active', self.plan)
        self.mock_observer.assert_not_called()
        with patch('harness.execution.observed_process', return_value={'state': 'exited'}):
            preview = self.plan()
            accepted = self.decide(preview)
        self.assertFalse(accepted['sql_executed'])
        self.assertEqual('running', self.fixture.journal.read()['db_executions']['database/fixture-request']['original_status'])

    def test_real_decision_fields_required_and_reject_does_not_unblock(self):
        preview = self.plan()
        self.code('user_decision_required', lambda: self.decide(preview, message=' '))
        result = self.decide(preview, decision='reject')
        self.assertEqual('uncertain_attempt_remains_blocked', result['next_action'])
        self.assertEqual(1, self.mock_observer.call_count, 'Reject does not need another external connection.')
        self.assertEqual('indeterminate', self.fixture.journal.read()['db_executions']['database/fixture-request']['status'])
        self.assertNotIn('changes', self.fixture.journal.read())
        self.code('decision_exists', lambda: self.decide(preview))

    def test_target_or_permission_drift_prevents_recovery_acceptance(self):
        preview = self.plan()
        self.fixture.db.target['permissions_sha256'] = 'f' * 64
        self.code('db_recovery_target_drift', lambda: self.decide(preview))
        self.assertNotIn('changes', self.fixture.journal.read())

    def test_presentation_tampering_and_attempt_change_are_rejected(self):
        preview = self.plan()
        saved = self.fixture.journal.state['db_recovery_previews'][preview['recovery_id']]
        saved['report'] += 'unpresented modification'
        self.code('db_recovery_integrity', lambda: self.decide(preview))
        saved['report'] = preview['report']
        self.fixture.journal.state['db_executions']['database/fixture-request']['error'] = 'new-finding'
        self.code('db_recovery_stale', lambda: self.decide(preview))


if __name__ == '__main__':
    unittest.main()
