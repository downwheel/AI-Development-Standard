"""Scope/graph boundary regressions with explicit synthetic approval fixtures."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from harness.common import HarnessError, encoded, sha256
from harness.scope import compare_scope, preflight_scope, render_scope, validate_scope, validate_units
from harness.workflow import Workflow
from tests import test_workflow, test_database

REF = {'artifact_id': 'unit', 'revision_id': 'rev', 'sha256': '1' * 64}


def fixture_scope(files=None, **updates):
    return {'run_id': 'run', 'workspace_id': 'work', 'unit_id': 'unit', 'unit_ref': REF,
            'requirement_ids': ['req'], 'mode': 'change', 'source_baseline': {'sha256': '0' * 64},
            'files': files or [], 'db_objects': [], **updates}


def file_scope(path='src/app.py', action='create', **updates):
    baseline = {'expected_absent': True} if action == 'create' else {'before_sha256': sha256(b'before')}
    return {'path': path, 'action': action, 'layer': 'backend', 'reason': 'Fixed fixture requirement',
            'requirement_ids': ['req'], 'case_ids': ['case'], 'required': True, **baseline, **updates}


class ScopeBoundaryTests(unittest.TestCase):
    def rejected(self, code, fn, *args, **kwargs):
        with self.assertRaises(HarnessError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def test_empty_scope_requires_explicit_nonwriting_observation(self):
        self.rejected('empty_scope', validate_scope, fixture_scope())
        self.rejected('invalid_observation_scope', validate_scope, fixture_scope(mode='observe'))
        scope = fixture_scope(mode='observe', reason='Fresh source observation only')
        validate_scope(scope)
        self.assertTrue(compare_scope(scope, {}, {})['passed'])
        self.assertFalse(compare_scope(scope, {}, {'surprise.py': '2' * 64})['passed'])

    def test_baseline_checked_against_actual_files_and_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'before.txt').write_bytes(b'before')
            scope = fixture_scope([file_scope('before.txt', 'modify'), file_scope('new.txt')])
            self.assertTrue(preflight_scope(scope, root, source_digest='0' * 64)['passed'])
            self.rejected('scope_baseline_changed', preflight_scope, scope, root, source_digest='1' * 64)
            (root / 'new.txt').write_bytes(b'user work')
            self.rejected('scope_baseline_changed', preflight_scope, scope, root)
            self.assertEqual(b'user work', (root / 'new.txt').read_bytes())

    def test_scope_identity_must_match_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            self.rejected('scope_mismatch', preflight_scope, fixture_scope([file_scope()]), folder, run_id='other')

    def test_no_case_collision_secret_metadata_or_source_glob(self):
        self.rejected('duplicate_scope_path', validate_scope, fixture_scope([file_scope('A.py'), file_scope('a.py')]))
        for path in ['.git/config', '.env', 'src/.env.local', 'node_modules/x.js', '../escape.py', 'src/*.py']:
            with self.subTest(path=path):
                with self.assertRaises(HarnessError):
                    validate_scope(fixture_scope([file_scope(path)]))
        validate_scope(fixture_scope([file_scope('.env.example')]))

    def test_action_and_required_files_are_enforced(self):
        scope = fixture_scope([file_scope('old.txt', 'modify'), file_scope('new.txt')])
        before = {'old.txt': sha256(b'before')}
        result = compare_scope(scope, before, {'new.txt': sha256(b'new'), 'extra.txt': sha256(b'extra')})
        self.assertFalse(result['passed'])
        self.assertEqual({'action_mismatch', 'outside_scope'}, {row['reason'] for row in result['violations']})
        self.assertEqual(['new.txt'], compare_scope(scope, before, {'old.txt': sha256(b'changed')})['missing_required'])
        self.assertTrue(compare_scope(scope, before, {'old.txt': sha256(b'changed'), 'new.txt': sha256(b'new')})['passed'])

    def test_generated_outputs_are_bounded_by_root_pattern_actions_and_size(self):
        group = {'generator': 'schema-generator', 'version': '1', 'input_sha256': '2' * 64, 'output_root': 'generated',
                 'patterns': ['*.ts'], 'actions': ['create'], 'max_files': 1, 'max_bytes': 3}
        scope = fixture_scope(generated_files=[group])
        self.assertTrue(compare_scope(scope, [], [{'path': 'generated/api.ts', 'sha256': '3' * 64, 'size': 3}])['passed'])
        self.assertFalse(compare_scope(scope, [], [{'path': 'generated/api.ts', 'sha256': '3' * 64, 'size': 4}])['passed'])
        self.assertFalse(compare_scope(scope, [], [{'path': 'generated/api.py', 'sha256': '3' * 64, 'size': 1}])['passed'])
        self.assertFalse(compare_scope(scope, [], [{'path': 'src/api.ts', 'sha256': '3' * 64, 'size': 1}])['passed'])
        self.assertFalse(compare_scope(scope, [], [{'path': 'generated/api.ts', 'sha256': '3' * 64}])['passed'])
        scope['generated_files'][0]['patterns'] = ['**/*']
        self.rejected('unbounded_generated_scope', validate_scope, scope)

    def test_rename_requires_linked_delete_and_create(self):
        bad = fixture_scope([file_scope('old.txt', 'delete', rename_id='rename-1')])
        self.rejected('invalid_rename', validate_scope, bad)
        bad['files'].append(file_scope('new.txt', rename_id='rename-1'))
        validate_scope(bad)

    def test_scope_presentation_escapes_html_and_derives_totals(self):
        scope = fixture_scope([file_scope(reason='<script>|untrusted\nnext')])
        output = render_scope(scope)
        self.assertIn('src/app.py', output)
        self.assertIn('파일: 1', output)
        self.assertNotIn('<script>', output)
        self.assertEqual(output, render_scope(copy.deepcopy(scope)))

    def test_unit_graph_rejects_unknown_cycle_and_missing_required_coverage(self):
        requirements = [{'id': 'req', 'case_ids': ['case']}]
        unit = {'unit_id': 'unit', 'title': 'Fixture', 'required': True, 'depends_on': [], 'requirement_ids': ['req'], 'case_ids': ['case']}
        validate_units([unit], requirements)
        self.rejected('unknown_unit_dependency', validate_units, [{**unit, 'depends_on': ['absent']}], requirements)
        self.rejected('cyclic_units', validate_units, [{**unit, 'depends_on': ['unit']}], requirements)
        self.rejected('missing_coverage', validate_units, [{**unit, 'required': False}], requirements)


class WorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_workflow.WorkflowTest('test_same_create_run_is_idempotent_without_request_id')
        self.fixture.setUp()
        self.workflow = self.fixture.workflow

    def call(self, operation, **params):
        return self.workflow.execute(operation, params)

    def test_new_run_is_strict_and_missing_scope_cannot_reuse_gate_b(self):
        _, _, _, unit, plan, _, _ = self.fixture.unit()
        self.assertEqual('2.1', self.fixture.journal.state['runs']['run']['contract_version'])
        with self.assertRaises(HarnessError) as caught:
            self.call('create_review', run_id='run', gate='B', unit_id='ui-1', input_refs=[unit, plan])
        self.assertEqual('missing_input', caught.exception.code)

    def test_gate_presentation_is_canonical_and_immutable(self):
        _, _, _, _, _, _, review = self.fixture.unit()
        scope = self.workflow.load_artifact(self.fixture.scope)
        self.assertEqual(render_scope(scope['payload']), scope['report'])
        self.assertIn('fixture.txt', review['presentation'])
        self.assertEqual(self.fixture.scope, review['approval_binding']['scope_ref'])
        self.assertEqual(sha256(review['presentation'].encode()), review['presentation_sha256'])
        journal = self.fixture.journal
        journal.blobs[review['presentation_oid']] = b'changed'
        with self.assertRaises(HarnessError) as caught:
            self.workflow.implementation_basis('run', 'ui-1')
        self.assertEqual('gate_b_required', caught.exception.code)

    def test_missing_scope_in_implementation_stage_inputs_is_rejected(self):
        _, _, _, unit, plan, _, _ = self.fixture.unit()
        with self.assertRaises(HarnessError) as caught:
            self.call('start_stage', run_id='run', skill='dev-implement', owner='fixture', input_refs=[unit, plan], unit_id='ui-1')
        self.assertEqual('pin_mismatch', caught.exception.code)

    def test_next_actions_and_completion_are_readonly_and_do_not_invent_evidence(self):
        journal = self.fixture.journal
        self.assertEqual('dev-discover', self.call('next_actions', run_id='run')['actions'][0]['skill'])
        self.fixture.unit()
        before, writes = encoded(journal.state), journal.writes
        self.assertEqual('dev-implement', self.call('next_actions', run_id='run')['actions'][0]['skill'])
        result = self.call('evaluate_completion', run_id='run')
        self.assertFalse(result['eligible_complete'])
        self.assertEqual(1, result['required_unit_count'])
        self.assertEqual(['ui-1:implementation_required'], result['blockers'])
        self.assertEqual(before, encoded(journal.state))
        self.assertEqual(writes, journal.writes)

    def test_completion_requires_live_verification_and_scope_receipt(self):
        self.fixture.unit()
        journal = self.fixture.journal
        journal.state['applied'] = {'run/ui-1': 'impl'}
        journal.state['implementations']['impl'] = {'scope_result': {'passed': True}}
        with patch('harness.execution.Execution.get_verification', return_value={'eligible_complete': False, 'inapplicable_reason': 'source_changed'}) as observed:
            result = self.call('evaluate_completion', run_id='run')
            self.assertFalse(result['eligible_complete'])
            self.assertEqual(['ui-1:source_changed'], result['blockers'])
            observed.assert_called_once_with('impl')
        with patch('harness.execution.Execution.get_verification', return_value={'eligible_complete': True}):
            self.assertTrue(self.call('evaluate_completion', run_id='run')['eligible_complete'])
            journal.state['implementations']['impl'] = {}
            self.assertFalse(self.call('evaluate_completion', run_id='run')['eligible_complete'])

    def db_review_fixture(self, duplicate=False, migration_file=True):
        fixture = self.fixture
        _, _, system, _ = fixture.system()
        unit = fixture.publish('unit-spec', {'requirement_ids': ['req-1'], 'case_ids': ['case-1', 'case-2'],
                    'environment': {'required': True}, 'database': {'required': True}}, [system], 'ui-1')
        env = fixture.publish('environment-contract', {'unit_ref': unit, 'profile_id': 'fixture-profile', 'profile_revision': 'fixture-revision',
                    'target_revision': 'fixture-target', 'roles': ['migration'], 'probe_receipt_id': 'fixture-probe'}, [unit], 'ui-1')
        source = test_database.DatabaseTest('test_schema_and_preview_do_not_execute'); source.setUp()
        payload = source.plan()
        payload.update(unit_ref=unit, environment_ref=env, unit_id='ui-1', requirement_ids=['req-1'], case_ids=['case-1'])
        payload['migrations'][0]['case_ids'] = ['case-1']
        payload['verification']['case_ids'] = ['case-1']
        db = fixture.publish('db-work-plan', payload, [system, unit, env], 'ui-1', artifact_id='db-one')
        plans = [db]
        if duplicate:
            other = copy.deepcopy(payload); other['db_work_id'] = 'db-work-two'
            plans.append(fixture.publish('db-work-plan', other, [system, unit, env], 'ui-1', artifact_id='db-two'))
        scope_payload = {'run_id': 'run', 'workspace_id': 'work', 'unit_id': 'ui-1', 'unit_ref': unit, 'requirement_ids': ['req-1'],
                    'mode': 'change', 'source_baseline': {'sha256': '0' * 64}, 'environment_refs': [env], 'db_plan_refs': plans,
                    'files': [{'path': payload['migrations'][0]['source_path'] if migration_file else 'unrelated.py', 'layer': 'db', 'action': 'create',
                              'reason': 'Synthetic migration source', 'requirement_ids': ['req-1'], 'case_ids': ['case-1'], 'required': True, 'expected_absent': True}],
                    'db_objects': [{**row, 'target_ref': payload['target_ref'], 'db_work_id': payload['db_work_id']} for row in payload['objects'] if row['action'] != 'observe']}
        scope = fixture.publish('scope-manifest', scope_payload, [system, unit, env] + plans, 'ui-1')
        test = fixture.publish('test-plan', {'unit_ref': unit, 'checks': [{'check_id': 'check', 'argv': ['python', '--version'], 'cwd': '.',
                    'timeout_seconds': 5, 'required': True, 'expected_exit': 0, 'case_ids': ['case-1', 'case-2'], 'expected': 'Synthetic', 'oracle': 'Independent synthetic specification'}]}, [unit], 'ui-1')
        return [unit, test, scope, env] + plans

    def test_duplicate_target_plans_cannot_receive_gate_b(self):
        refs = self.db_review_fixture(duplicate=True)
        with self.assertRaises(HarnessError) as caught:
            self.call('create_review', run_id='run', gate='B', unit_id='ui-1', input_refs=refs)
        self.assertEqual('duplicate_db_target_plan', caught.exception.code)

    def test_migration_file_must_be_in_exact_scope_and_report_contains_budget(self):
        refs = self.db_review_fixture(migration_file=False)
        with self.assertRaises(HarnessError) as caught:
            self.call('create_review', run_id='run', gate='B', unit_id='ui-1', input_refs=refs)
        self.assertEqual('migration_source_scope', caught.exception.code)
        report = self.workflow.load_artifact(refs[-1])['report']
        self.assertIn('SQL SHA-256', report)
        self.assertIn('max_batch_rows', report)

    def test_exact_db_scope_bundle_is_presentable_before_any_database_execution(self):
        refs = self.db_review_fixture()
        review = self.call('create_review', run_id='run', gate='B', unit_id='ui-1', input_refs=refs)
        self.assertIn('db/migrations/001.sql', review['presentation'])
        self.assertIn('max_observed_rows', review['presentation'])
        self.assertNotIn('db-execution-receipt', {entry['manifest']['kind'] for entry in [self.workflow.load_artifact(ref) for ref in refs]})

    def test_approved_dependent_unit_cannot_start_before_predecessor_implementation(self):
        fixture = self.fixture
        context, requirements, old_system, _ = fixture.system()
        payload = self.workflow.load_artifact(old_system)['payload']
        payload['units'].append({**payload['units'][0], 'unit_id': 'ui-2', 'depends_on': ['ui-1']})
        system = fixture.publish('system-design', payload, [context, requirements])
        fixture.approve(self.call('create_review', run_id='run', gate='A', input_refs=[context, requirements, system]))
        unit = fixture.publish('unit-spec', {'requirement_ids': ['req-1'], 'case_ids': ['case-1', 'case-2']}, [system], 'ui-2')
        scope = fixture.publish('scope-manifest', {'run_id': 'run', 'workspace_id': 'work', 'unit_id': 'ui-2', 'unit_ref': unit,
                    'requirement_ids': ['req-1'], 'mode': 'observe', 'reason': 'Synthetic dependent observation',
                    'source_baseline': {'sha256': '0' * 64}, 'files': [], 'db_objects': []}, [system, unit], 'ui-2')
        plan = fixture.publish('test-plan', {'unit_ref': unit, 'checks': [{'check_id': 'check', 'argv': ['python'], 'cwd': '.', 'timeout_seconds': 1,
                    'required': True, 'expected_exit': 0, 'case_ids': ['case-1', 'case-2'], 'expected': 'Synthetic', 'oracle': 'Independent'}]}, [unit], 'ui-2')
        refs = [unit, plan, scope]
        fixture.approve(self.call('create_review', run_id='run', gate='B', unit_id='ui-2', input_refs=refs))
        with self.assertRaises(HarnessError) as caught:
            self.call('start_stage', run_id='run', skill='dev-implement', owner='fixture', unit_id='ui-2', input_refs=refs)
        self.assertEqual('unit_dependency_incomplete', caught.exception.code)

    def test_next_actions_resumes_exact_waiting_stage_with_questions_and_candidate(self):
        stage = self.call('start_stage', run_id='run', skill='dev-discover', owner='fixture', input_refs=[])
        candidate = self.call('publish_artifact', run_id='run', stage_run_id=stage['stage_run_id'], owner='fixture', artifact_id='discovery',
                    kind='discovery-context', payload={'questions': [{'id': 'q1', 'question': 'Synthetic missing project choice', 'required': True}]},
                    report='# Synthetic open question', input_refs=[])['ref']
        self.call('finish_stage', stage_run_id=stage['stage_run_id'], owner='fixture', status='waiting_input', output_refs=[candidate], notes='Need the synthetic project choice')
        before = encoded(self.fixture.journal.state)
        result = self.call('next_actions', run_id='run')
        self.assertEqual(1, len(result['actions']))
        self.assertEqual(('resume_stage', stage['stage_run_id']), (result['actions'][0]['operation'], result['actions'][0]['stage_run_id']))
        self.assertEqual([candidate], result['waiting_stages'][0]['candidate_refs'])
        self.assertEqual('Synthetic missing project choice', result['waiting_stages'][0]['required_questions'][0]['question'])
        self.assertEqual(before, encoded(self.fixture.journal.state))


if __name__ == '__main__':
    unittest.main()
