"""Adversarial pure checks for the external-tool workflow contract."""
import copy
import json
import unittest

from harness.common import HarnessError, encoded, sha256
from harness.tool_policy import (
    CAPABILITIES, check_database_targets, check_gate, render_tools, validate_check_bindings,
    validate_completion_evidence, validate_observations, validate_plan,
)


def plan(**modes):
    return [{'capability': cap, 'mode': modes.get(cap, 'not_applicable'),
             'reason': 'Scoped to the requested unit' if cap in modes else 'Not used by this project',
             'unit_ids': ['screen'] if cap in modes else []} for cap in CAPABILITIES]


def observation(capability='library_docs', provider='context7', status='success', result=None):
    if result is None:
        result = {'library': 'react', 'version': '19.1.0', 'library_id': '/facebook/react/v19.1.0',
                  'version_checked': True, 'sources': [{'url': 'https://react.dev/reference/react', 'title': 'React reference'}]}
    return {'capability': capability, 'provider': provider, 'tool': provider + '.inspect', 'status': status,
            'observed_at': '2026-09-21T09:00:00+00:00', 'target': 'test-target', 'summary': 'Observed the stated target and recorded the outcome.',
            'source_refs': ['https://example.com/evidence'], 'result': result}


def figma():
    return observation('ui_design', 'figma', result={'file_key': 'test-file', 'node_ids': ['1:2'],
                        'structure_checked': True, 'screenshot_checked': True})


def local_design(status='fallback'):
    row = observation('ui_design', 'local-design', status,
                      {'report_markdown': '# Layout\nToolbar above canvas.', 'layout_content': '<main><nav>Tools</nav><canvas></canvas></main>'})
    if status == 'fallback':
        row['failure'] = {'code': 'quota_exceeded', 'tool': 'figma.use_figma', 'detail': 'The attempted tool returned a quota error.'}
    else:
        row['result']['user_choice'] = '문서와 로컬 화면 배치안으로 설계해 주세요.'
    return row


def browser():
    return observation('browser', 'playwright', result={
        'url': 'http://127.0.0.1:3000', 'engine': 'chromium', 'browser_session': 'isolated-test-session',
        'connection_mode': 'live', 'interaction_count': 3,
        'checks': [{'name': 'save-and-refresh', 'expected': 'Memo remains', 'observed': 'Memo remains', 'passed': True}],
    })


def database(kind='readback'):
    return observation('database', 'sqlserver-adapter', result={
        'engine': 'mssql', 'target_ref': 'test-target', 'connection_mode': 'live', 'observation_kind': kind,
        'read_only': True, 'rows_observed': 1, 'objects': ['dbo.Memo'],
        'checks': [{'name': 'memo-readback', 'expected': 'one matching row', 'observed': 'one matching row', 'passed': True}],
    })


def test_payload(capability='browser'):
    return {'checks': [{'check_id': 'e2e', 'required': True, 'runner': {
        'kind': 'project-runner', 'evidence': [{'evidence_id': 'live-observation', 'path': 'observation.json',
                    'format': 'json', 'required': True, 'max_bytes': 100000}]}}],
            'tool_checks': [{'capability': capability, 'check_id': 'e2e', 'evidence_id': 'live-observation'}]}


def completed_evidence(capability='browser'):
    payload = test_payload(capability)
    envelope = {'tool_policy_version': '1', 'capability': capability, 'build_id': 'a' * 64,
                'run_id': 'attempt-one', 'observation': browser() if capability == 'browser' else database()}
    attachment_raw = encoded(envelope)
    execution = {'preparation': {'passed': True, 'evidence': [{
        'evidence_id': 'live-observation', 'status': 'attached', 'required': True, 'format': 'json',
        'blob_oid': 'attachment', 'sha256': sha256(attachment_raw),
    }]}}
    execution_raw = encoded(execution)
    campaign = {'check_results': {'e2e': {'attempt_id': 'attempt-one', 'result': 'passed',
                                         'evidence_oid': 'execution', 'evidence_sha256': sha256(execution_raw)}}}
    blobs = {'attachment': attachment_raw, 'execution': execution_raw}
    return payload, envelope, execution, campaign, blobs


class ToolPolicyTests(unittest.TestCase):
    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(HarnessError) as caught:
            function(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def test_plan_requires_exact_four_rows(self):
        self.assert_code('invalid_input', validate_plan, [], [{'unit_id': 'screen'}])
        rows = plan(); rows[-1] = copy.deepcopy(rows[0])
        self.assert_code('invalid_tool_plan', validate_plan, rows, [{'unit_id': 'screen'}])

    def test_plan_rejects_unknown_and_duplicate_unit_assignments(self):
        for assignments in (['unknown'], ['screen', 'screen']):
            rows = plan(database='required'); rows[-1]['unit_ids'] = assignments
            self.assert_code('invalid_tool_plan', validate_plan, rows, [{'unit_id': 'screen'}])

    def test_applicability_and_modes_are_not_escape_hatches(self):
        cases = [plan(database='preferred'), plan(library_docs='local_only')]
        empty = plan(database='required'); empty[-1]['unit_ids'] = []; cases.append(empty)
        nonapplicable = plan(); nonapplicable[-1]['unit_ids'] = ['screen']; cases.append(nonapplicable)
        blank = plan(); blank[0]['reason'] = ' '; cases.append(blank)
        for rows in cases:
            self.assert_code('invalid_tool_plan', validate_plan, rows, [{'unit_id': 'screen'}])

    def test_ui_requires_browser_for_every_assigned_unit(self):
        self.assert_code('invalid_tool_plan', validate_plan, plan(ui_design='preferred'), [{'unit_id': 'screen'}])
        validate_plan(plan(ui_design='preferred', browser='required'), [{'unit_id': 'screen'}])

    def test_valid_not_applicable_plan_does_not_force_provider_use(self):
        validate_plan(plan(), [{'unit_id': 'screen'}])
        check_gate(plan(), [], 'A')
        check_gate(plan(), [], 'B', 'screen')
        validate_check_bindings(plan(), 'screen', {'checks': []})

    def test_gate_a_blocks_missing_and_blocked_documentation(self):
        rows = plan(library_docs='required')
        self.assert_code('tool_evidence_required', check_gate, rows, [], 'A')
        blocked = observation(status='blocked', result={})
        blocked['failure'] = {'code': 'tool_unavailable', 'tool': 'context7', 'detail': 'No matching installed tool exposed.'}
        self.assert_code('tool_evidence_required', check_gate, rows, [blocked], 'A')
        check_gate(rows, [observation()], 'A')

    def test_documentation_requires_context7_library_and_exact_version_evidence(self):
        for field in ('library_id', 'version', 'version_checked', 'sources'):
            row = observation(); del row['result'][field]
            with self.assertRaises(HarnessError):
                validate_observations([row])

    def test_official_docs_fallback_requires_failure_and_local_check(self):
        row = observation(provider='official-docs', status='fallback')
        row['result']['local_type_check'] = {'checked': True, 'detail': 'Confirmed installed package declarations and lockfile version.'}
        row['failure'] = {'code': 'unsupported_version', 'tool': 'context7.query-docs', 'detail': 'Requested version was absent from returned library versions.'}
        check_gate(plan(library_docs='required'), [row], 'A')
        del row['failure']
        self.assert_code('tool_failure_required', validate_observations, [row])

    def test_official_docs_cannot_claim_success_without_preferred_lookup(self):
        row = observation(provider='official-docs')
        self.assert_code('invalid_tool_observation', validate_observations, [row])

    def test_scoped_openai_docs_fallback_preserves_its_actual_failure(self):
        row = observation(provider='official-docs', status='fallback')
        row['result'].update(scope='openai', scope_reason='OpenAI SDK integration.',
                             local_type_check={'checked': True, 'detail': 'Checked the installed SDK API declarations.'},
                             sources=[{'url': 'https://developers.openai.com/api/reference', 'title': 'API reference'}])
        row['failure'] = {'code': 'timeout', 'tool': 'openai-docs.fetch', 'detail': 'The preferred documentation request timed out.'}
        validate_observations([row])
        row['failure']['tool'] = 'context7'
        self.assert_code('invalid_tool_fallback', validate_observations, [row])

    def test_openai_docs_scope_and_domains_are_explicit(self):
        row = observation(provider='openai-docs')
        row['result'].update(scope='openai', scope_reason='The unit implements OpenAI Responses API.',
                             sources=[{'url': 'https://developers.openai.com/api/reference', 'title': 'API reference'}])
        validate_observations([row])
        row['result']['sources'][0]['url'] = 'https://openai.com.attacker.example/api'
        self.assert_code('invalid_tool_observation', validate_observations, [row])

    def test_native_figma_requires_structure_and_screenshot_checks(self):
        row = figma(); row['result']['screenshot_checked'] = False
        self.assert_code('invalid_input', validate_observations, [row])
        check_gate(plan(ui_design='required', browser='required'), [figma()], 'B', 'screen')

    def test_figma_preferred_accepts_only_evidenced_fallback(self):
        rows = plan(ui_design='preferred', browser='required')
        check_gate(rows, [local_design()], 'B', 'screen')
        local = local_design(); del local['failure']
        self.assert_code('tool_failure_required', check_gate, rows, [local], 'B', 'screen')
        self.assert_code('tool_evidence_required', check_gate, rows, [local_design('success')], 'B', 'screen')

    def test_figma_required_never_accepts_local_fallback(self):
        self.assert_code('tool_evidence_required', check_gate,
                         plan(ui_design='required', browser='required'), [local_design()], 'B', 'screen')

    def test_local_only_requires_user_choice_and_local_material(self):
        rows = plan(ui_design='local_only', browser='required')
        check_gate(rows, [local_design('success')], 'B', 'screen')
        row = local_design('success'); del row['result']['user_choice']
        self.assert_code('invalid_tool_observation', validate_observations, [row])
        self.assert_code('tool_evidence_required', check_gate, rows, [figma()], 'B', 'screen')

    def test_later_block_cannot_be_hidden_by_earlier_success(self):
        blocked = observation(status='blocked', result={})
        blocked['observed_at'] = '2026-09-21T10:00:00+00:00'
        blocked['failure'] = {'code': 'permission_denied', 'tool': 'context7', 'detail': 'The next relevant lookup was denied.'}
        self.assert_code('tool_evidence_required', check_gate, plan(library_docs='required'), [observation(), blocked], 'A')

    def test_ambiguous_timestamp_cannot_hide_a_block(self):
        blocked = observation(status='blocked', result={})
        blocked['failure'] = {'code': 'permission_denied', 'tool': 'context7', 'detail': 'The relevant lookup was denied.'}
        self.assert_code('ambiguous_tool_observation', check_gate, plan(library_docs='required'), [observation(), blocked], 'A')

    def test_gate_b_checks_only_the_given_unit_and_requires_unit_id(self):
        rows = plan(library_docs='required')
        check_gate(rows, [], 'B', 'different-unit')
        self.assert_code('invalid_tool_gate', check_gate, rows, [], 'B')
        self.assert_code('tool_evidence_required', check_gate, rows, [], 'B', 'screen')

    def test_refs_reject_credentials_raw_paths_and_malformed_artifact_refs(self):
        for ref in ('https://user:password@example.com/result', 'https://example.com?api_key=secret',
                    'D:/private/.env', 'artifact:a/b/not-a-hash'):
            row = observation(); row['source_refs'] = [ref]
            self.assert_code('invalid_tool_source', validate_observations, [row])
        row['source_refs'] = ['artifact:report/revision-' + 'a' * 20 + '/' + 'b' * 64]
        validate_observations([row])

    def test_signed_urls_and_oauth_fragments_are_not_persistable_sources(self):
        for suffix in ('?sig=private', '?X-Amz-Signature=private', '?X-Amz-Credential=private',
                       '?session=private', '?auth=private', '?s%69g=private', '#access_token=private',
                       '#session=private', '?signature='):
            row = observation(); row['source_refs'] = ['https://example.test/path' + suffix]
            self.assert_code('invalid_tool_source', validate_observations, [row])
        row['source_refs'] = ['https://example.test/reference#authentication', 'https://example.test/reference#method-signature']
        validate_observations([row])

    def test_timestamp_timezone_and_nonempty_provenance_required(self):
        for key, value in (('observed_at', '2026-09-21T09:00:00'), ('summary', ' ')):
            row = observation(); row[key] = value
            self.assert_code('invalid_tool_observation', validate_observations, [row])

    def test_live_observations_reject_mock_failed_assertions_and_wrong_db_target(self):
        row = browser(); row['provider'] = 'mock-browser'
        self.assert_code('invalid_tool_observation', validate_observations, [row])
        row = database(); row['result']['checks'][0]['passed'] = False
        self.assert_code('invalid_input', validate_observations, [row])
        row = database(); row['result']['target_ref'] = 'other-database'
        self.assert_code('invalid_tool_observation', validate_observations, [row])

    def test_gate_b_database_catalog_is_a_valid_design_observation(self):
        check_gate(plan(database='required'), [database('catalog')], 'B', 'screen')

    def test_database_targets_require_every_exact_approved_target(self):
        row = database('catalog')
        check_database_targets([row], {'test-target'})
        self.assert_code('tool_database_target_mismatch', check_database_targets, [row], {'different-target'})
        self.assert_code('tool_database_evidence_required', check_database_targets, [row], {'test-target', 'second-target'})
        self.assert_code('tool_database_target_required', check_database_targets, [row], set())
        second = copy.deepcopy(row); second['target'] = second['result']['target_ref'] = 'second-target'
        check_database_targets([row, second], {'test-target', 'second-target'})
        check_gate(plan(database='required'), [row, second], 'B', 'screen')

    def test_database_targets_latest_block_or_wrong_kind_cannot_pass(self):
        row = database('catalog')
        blocked = observation('database', 'sqlserver-adapter', 'blocked', {})
        blocked['observed_at'] = '2026-09-21T10:00:00+00:00'
        blocked['failure'] = {'code': 'permission_denied', 'tool': 'sqlserver-adapter', 'detail': 'The selected target query was denied.'}
        self.assert_code('tool_database_evidence_required', check_database_targets, [row, blocked], {'test-target'})
        self.assert_code('tool_database_evidence_required', check_database_targets, [row], {'test-target'}, kind='readback')
        self.assert_code('ambiguous_tool_observation', check_database_targets, [row, row], {'test-target'})

    def test_live_check_bindings_require_complete_capability_coverage(self):
        self.assert_code('tool_check_required', validate_check_bindings, plan(browser='required'), 'screen', {'checks': []})
        validate_check_bindings(plan(browser='required'), 'screen', test_payload())
        self.assert_code('tool_check_required', validate_check_bindings, plan(browser='required', database='required'), 'screen', test_payload())

    def test_binding_cannot_point_at_optional_text_or_unmapped_evidence(self):
        for mutation in ('optional-check', 'optional-attachment', 'text', 'unmapped', 'no-runner', 'duplicate'):
            payload = test_payload()
            if mutation == 'optional-check': payload['checks'][0]['required'] = False
            if mutation == 'optional-attachment': payload['checks'][0]['runner']['evidence'][0]['required'] = False
            if mutation == 'text': payload['checks'][0]['runner']['evidence'][0]['format'] = 'text'
            if mutation == 'unmapped': payload['tool_checks'][0]['check_id'] = 'not-existing'
            if mutation == 'no-runner': del payload['checks'][0]['runner']
            if mutation == 'duplicate': payload['tool_checks'].append(copy.deepcopy(payload['tool_checks'][0]))
            self.assert_code('invalid_tool_check', validate_check_bindings, plan(browser='required'), 'screen', payload)

    def test_completion_loads_both_actual_blob_layers(self):
        payload, _, _, campaign, blobs = completed_evidence()
        loaded = []
        def load(oid): loaded.append(oid); return blobs[oid]
        summary = validate_completion_evidence(plan(browser='required'), 'screen', payload, campaign, load, build_id='a' * 64)
        self.assertEqual(['execution', 'attachment'], loaded)
        self.assertEqual('playwright', summary[0]['provider'])

    def test_completion_rejects_corrupted_outer_and_inner_blobs(self):
        for oid in ('execution', 'attachment'):
            payload, _, _, campaign, blobs = completed_evidence(); blobs[oid] += b' '
            self.assert_code('tool_evidence_hash_mismatch', validate_completion_evidence,
                             plan(browser='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64)

    def test_completion_rejects_old_attempt_build_and_wrong_capability(self):
        for field, value in (('run_id', 'old-attempt'), ('build_id', 'b' * 64), ('capability', 'database')):
            payload, envelope, execution, campaign, blobs = completed_evidence()
            envelope[field] = value
            blobs['attachment'] = encoded(envelope)
            execution['preparation']['evidence'][0]['sha256'] = sha256(blobs['attachment'])
            blobs['execution'] = encoded(execution)
            campaign['check_results']['e2e']['evidence_sha256'] = sha256(blobs['execution'])
            self.assert_code('tool_evidence_stale', validate_completion_evidence,
                             plan(browser='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64)

    def test_completion_rejects_missing_attachment_or_failed_check(self):
        for mutation in ('missing', 'failed'):
            payload, _, execution, campaign, blobs = completed_evidence()
            if mutation == 'failed': campaign['check_results']['e2e']['result'] = 'failed'
            else:
                execution['preparation']['evidence'] = []; blobs['execution'] = encoded(execution)
                campaign['check_results']['e2e']['evidence_sha256'] = sha256(blobs['execution'])
            self.assert_code('tool_completion_required', validate_completion_evidence,
                             plan(browser='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64)

    def test_completion_requires_database_readback_not_only_schema(self):
        payload, envelope, execution, campaign, blobs = completed_evidence('database')
        validate_completion_evidence(plan(database='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64,
                                     expected_database_targets={'test-target'})
        envelope['observation']['result']['observation_kind'] = 'catalog'
        blobs['attachment'] = encoded(envelope)
        execution['preparation']['evidence'][0]['sha256'] = sha256(blobs['attachment'])
        blobs['execution'] = encoded(execution)
        campaign['check_results']['e2e']['evidence_sha256'] = sha256(blobs['execution'])
        self.assert_code('tool_completion_required', validate_completion_evidence,
                         plan(database='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64,
                         expected_database_targets={'test-target'})

    def test_completion_cannot_use_a_different_database_or_omit_target_binding(self):
        payload, _, _, campaign, blobs = completed_evidence('database')
        self.assert_code('tool_database_target_required', validate_completion_evidence,
                         plan(database='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64)
        self.assert_code('tool_database_target_mismatch', validate_completion_evidence,
                         plan(database='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64,
                         expected_database_targets={'different-target'})

    def test_completion_artifact_refs_require_resolution_and_callback_cannot_be_bypassed(self):
        payload, envelope, execution, campaign, blobs = completed_evidence()
        ref = 'artifact:approved-ref/approved-revision/' + 'b' * 64
        envelope['observation']['source_refs'] = [ref, 'https://example.test/source']
        blobs['attachment'] = encoded(envelope)
        execution['preparation']['evidence'][0]['sha256'] = sha256(blobs['attachment'])
        blobs['execution'] = encoded(execution)
        campaign['check_results']['e2e']['evidence_sha256'] = sha256(blobs['execution'])
        self.assert_code('tool_source_validation_required', validate_completion_evidence,
                         plan(browser='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64)
        resolved = []
        validate_completion_evidence(plan(browser='required'), 'screen', payload, campaign, blobs.__getitem__,
                                     build_id='a' * 64, validate_source_ref=resolved.append)
        self.assertEqual(envelope['observation']['source_refs'], resolved)
        def reject(source):
            if source.startswith('artifact:'):
                raise HarnessError('artifact_mismatch', 'Unknown referenced artifact.')
        self.assert_code('artifact_mismatch', validate_completion_evidence,
                         plan(browser='required'), 'screen', payload, campaign, blobs.__getitem__,
                         build_id='a' * 64, validate_source_ref=reject)

    def test_completion_rejects_malformed_or_failed_preparation_receipts(self):
        for execution, code in (([], 'invalid_tool_evidence'), ({'preparation': {'passed': False}}, 'tool_completion_required'),
                                ({'preparation': {'passed': True, 'evidence': [None]}}, 'invalid_tool_evidence')):
            payload, _, _, campaign, blobs = completed_evidence()
            blobs['execution'] = encoded(execution)
            campaign['check_results']['e2e']['evidence_sha256'] = sha256(blobs['execution'])
            self.assert_code(code, validate_completion_evidence,
                             plan(browser='required'), 'screen', payload, campaign, blobs.__getitem__, build_id='a' * 64)

    def test_review_render_shows_actual_failure_and_user_choice(self):
        report = render_tools(plan(ui_design='preferred', browser='required'), [local_design()])
        self.assertIn('quota_exceeded', report)
        self.assertIn('figma.use_figma', report)
        self.assertIn('공급자 인증', report)
        self.assertIn('문서와 로컬', render_tools(plan(), [local_design('success')]))

    def test_review_renders_concrete_results_and_escapes_unsafe_markup(self):
        row = local_design(); row['summary'] = '<script>bad()</script>'
        row['result']['layout_content'] = '<main>```\n<script>literal content</script></main>'
        report = render_tools(plan(ui_design='preferred', browser='required'), [row])
        self.assertIn('&lt;script&gt;bad()&lt;/script&gt;', report)
        self.assertIn('````json', report)
        self.assertIn('layout_content', report)
        self.assertIn('Toolbar above canvas', report)
        self.assertIn('library_id', render_tools(plan(library_docs='required'), [observation()]))


if __name__ == '__main__':
    unittest.main()
