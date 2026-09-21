"""Environment tests use private temporary fixtures; never connect a real database."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.common import HarnessError
from harness.environment import Environment, base_process_environment, parse_dotenv, redact_data, redact_output


def process_profile():
    return {'provider': 'process', 'description': 'SYNTHETIC environment fixture',
            'keys': [{'name': 'APP_TARGET', 'type': 'string', 'secret': False, 'required': True},
                     {'name': 'APP_TOKEN', 'type': 'string', 'secret': True, 'required': True},
                     {'name': 'MIGRATION_TOKEN', 'type': 'string', 'secret': True, 'required': False},
                     {'name': 'APP_PORT', 'type': 'integer', 'secret': False, 'required': False, 'minimum': 1, 'maximum': 65535}],
            'roles': {'application': {'kind': 'application', 'mappings': {'SERVICE_TOKEN': 'APP_TOKEN', 'APP_TARGET': 'APP_TARGET', 'APP_PORT': 'APP_PORT'}},
                      'migration': {'kind': 'migration', 'mappings': {'SERVICE_TOKEN': 'MIGRATION_TOKEN', 'APP_TARGET': 'APP_TARGET'}}},
            'target_keys': ['APP_TARGET'], 'precedence': 'profile-over-explicit-inheritance'}


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='team environment fixture ')
        self.root = Path(self.temp.name)
        self.manager = Environment(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, profile=None):
        plan = self.manager.plan('fixture', profile or process_profile())
        applied = self.manager.apply(plan['plan_id'])
        self.env = Path(applied['env_path'])
        return applied

    def fill(self, token='synthetic-secret-A', target='isolated-target'):
        self.env.write_text('APP_TARGET=' + target + '\nAPP_TOKEN=' + token + '\nMIGRATION_TOKEN=synthetic-migration-only\nAPP_PORT=8080\n', encoding='utf-8')

    def code(self, expected, fn):
        with self.assertRaises(HarnessError) as raised:
            fn()
        self.assertEqual(expected, raised.exception.code)

    def test_inspect_absent_does_not_create_state(self):
        self.assertEqual('not_configured', self.manager.inspect('fixture')['status'])
        self.assertFalse((self.root / 'environments').exists())

    def test_create_blank_profile_reports_missing_without_values(self):
        self.create()
        observed = self.manager.inspect('fixture')
        self.assertEqual('values_incomplete', observed['status'])
        self.assertEqual(['APP_TARGET', 'APP_TOKEN'], observed['missing_keys'])
        probe = self.manager.probe('fixture', 'application')
        self.assertEqual('blocked', probe['status'])
        self.assertFalse(observed['secrets_returned'])

    def test_role_isolation_and_strict_inherited_environment(self):
        self.create(); self.fill()
        with patch.dict(os.environ, {'UNEXPECTED_CREDENTIAL': 'inherited-secret', 'DATABASE_URL': 'inherited-db', 'MSSQL_PWD': 'inherited-pwd'}, clear=False):
            resolved = self.manager.resolve('fixture', None, 'application')
        self.assertEqual('synthetic-secret-A', resolved.env['SERVICE_TOKEN'])
        self.assertNotIn('synthetic-migration-only', resolved.env.values())
        for key in ['UNEXPECTED_CREDENTIAL', 'DATABASE_URL', 'MSSQL_PWD', 'MIGRATION_TOKEN']:
            self.assertNotIn(key, resolved.env)
        self.assertNotIn('synthetic-secret-A', repr(resolved))

    def test_internal_secret_guard_can_protect_unconfigured_target_without_public_exposure(self):
        self.create()
        self.env.write_text('APP_TARGET=\nAPP_TOKEN=synthetic-partial-secret\nMIGRATION_TOKEN=\nAPP_PORT=not-ready\n', encoding='utf-8')
        self.assertEqual(('synthetic-partial-secret',), self.manager.known_secret_values('fixture'))
        inspected = self.manager.inspect('fixture')
        self.assertEqual('values_incomplete', inspected['status'])
        self.assertNotIn('synthetic-partial-secret', json.dumps(inspected))
        from harness.environment import environment_operations
        self.assertNotIn('known_secret_values', environment_operations())

    def test_public_returns_and_receipts_do_not_contain_credentials(self):
        self.create(); self.fill()
        public = [self.manager.inspect('fixture'), self.manager.probe('fixture', 'application')]
        exported = json.dumps(public)
        for path in (self.root / 'environments').rglob('*.json'):
            if path.name != 'secret-state.json':
                exported += path.read_text(encoding='utf-8')
        self.assertNotIn('synthetic-secret-A', exported)
        self.assertNotIn('synthetic-migration-only', exported)
        private = json.loads((self.env.parent.parent / 'secret-state.json').read_text(encoding='utf-8'))
        self.assertEqual(64, len(private['key']))
        self.assertNotIn(private['key'], exported)
        self.assertNotIn(private['secret_digest'], exported)

    def test_existing_env_is_preserved_and_apply_idempotent(self):
        first = self.create(); self.fill()
        before = self.env.read_bytes()
        profile = process_profile(); profile['description'] = 'Changed safe metadata'
        plan = self.manager.plan('fixture', profile)
        result = self.manager.apply(plan['plan_id'])
        self.assertTrue(result['existing_env_preserved'])
        self.assertEqual(before, self.env.read_bytes())
        self.assertEqual(result, self.manager.apply(plan['plan_id']))
        self.assertNotEqual(first['profile_revision'], result['profile_revision'])

    def test_stale_plan_cannot_overwrite_another_profile_change(self):
        self.create()
        first = self.manager.plan('fixture', process_profile())
        profile = process_profile(); profile['description'] = 'Newer metadata'
        second = self.manager.plan('fixture', profile)
        self.manager.apply(second['plan_id'])
        self.code('environment_plan_stale', lambda: self.manager.apply(first['plan_id']))

    def test_secret_rotation_requires_new_probe_but_same_approved_target(self):
        self.create(); self.fill()
        probe = self.manager.probe('fixture', 'application')
        original = probe['binding']
        contract = {key: original[key] for key in ['profile_id', 'profile_revision', 'target_revision']}
        contract.update(roles=['application'], probe_receipt_id=probe['probe_receipt_id'])
        self.assertEqual('passed', self.manager.validate_contract(contract)['status'])
        self.fill(token='synthetic-secret-B')
        changed = self.manager.inspect('fixture')['binding']
        self.assertNotEqual(original['revision'], changed['revision'])
        self.assertNotEqual(original['secret_revision'], changed['secret_revision'])
        self.assertEqual(original['target_revision'], changed['target_revision'])
        self.code('environment_probe_stale', lambda: self.manager.validate_contract(contract))
        self.manager.probe('fixture', 'application')
        self.assertEqual('passed', self.manager.validate_contract(contract)['status'])
        self.code('environment_revision_stale', lambda: self.manager.resolve('fixture', original['revision'], 'application'))

    def test_changed_target_requires_contract_revision(self):
        self.create(); self.fill()
        probe = self.manager.probe('fixture', 'application')
        contract = {key: probe['binding'][key] for key in ['profile_id', 'profile_revision', 'target_revision']}
        contract.update(roles=['application'], probe_receipt_id=probe['probe_receipt_id'])
        self.fill(target='other-isolated-target')
        self.manager.probe('fixture', 'application')
        self.code('environment_contract_stale', lambda: self.manager.validate_contract(contract))

    def test_multiple_roles_pin_distinct_probe_receipts(self):
        self.create(); self.fill()
        app = self.manager.probe('fixture', 'application')
        migration = self.manager.probe('fixture', 'migration')
        contract = {key: app['binding'][key] for key in ['profile_id', 'profile_revision', 'target_revision']}
        contract.update(roles=['application', 'migration'], probe_receipt_id=app['probe_receipt_id'])
        self.code('environment_probe_required', lambda: self.manager.validate_contract(contract))
        contract['role_probe_receipts'] = {'application': app['probe_receipt_id'], 'migration': migration['probe_receipt_id']}
        self.assertEqual('passed', self.manager.validate_contract(contract)['status'])

    def test_permission_drift_cannot_be_hidden_by_credential_rotation(self):
        self.create(); self.fill()
        probe = self.manager.probe('fixture', 'application')
        contract = {key: probe['binding'][key] for key in ['profile_id', 'profile_revision', 'target_revision']}
        contract.update(roles=['application'], probe_receipt_id=probe['probe_receipt_id'])
        latest = self.env.parent.parent / 'latest-probe-application.json'
        observed = json.loads(latest.read_text(encoding='utf-8'))
        observed['observation']['permissions_digest'] = 'a' * 64
        latest.write_text(json.dumps(observed), encoding='utf-8')
        self.code('environment_permission_drift', lambda: self.manager.validate_contract(contract))

    def test_malformed_unmapped_and_invalid_typed_values_are_rejected(self):
        self.create(); self.fill()
        self.env.write_text('APP_TARGET=synthetic\nAPP_TOKEN=secret\nUNDECLARED=private\n', encoding='utf-8')
        self.code('environment_unknown_key', lambda: self.manager.inspect('fixture'))
        self.fill()
        self.env.write_text(self.env.read_text(encoding='utf-8').replace('8080', '999999'), encoding='utf-8')
        self.assertEqual([{'key': 'APP_PORT', 'issue': 'out_of_range'}], self.manager.inspect('fixture')['format_problems'])
        self.code('environment_value_invalid', lambda: self.manager.resolve('fixture', None, 'application'))

    def test_dotenv_literal_parser_duplicate_and_expansion_contract(self):
        self.assertEqual({'VALUE': 'a # b', 'EMPTY': ''}, parse_dotenv(b"# comment\nVALUE='a # b'\nEMPTY=\n"))
        for raw, code in [(b'A=x\nA=y', 'environment_duplicate_key'), (b'A=${OTHER}', 'environment_expansion'),
                          (b'A=$(secret)', 'environment_expansion'), (b'export A=x', 'environment_file_format'),
                          (b'A="unterminated', 'environment_file_format')]:
            with self.subTest(code=code):
                self.code(code, lambda: parse_dotenv(raw))

    def test_frontend_secret_and_undeclared_mapping_blocked(self):
        profile = process_profile()
        profile['roles']['frontend'] = {'kind': 'frontend', 'mappings': {'VITE_TOKEN': 'APP_TOKEN'}}
        self.code('environment_public_secret', lambda: self.manager.plan('fixture', profile))
        profile = process_profile()
        profile['roles']['application']['mappings']['UNDECLARED'] = 'OTHER'
        self.code('environment_mapping', lambda: self.manager.plan('fixture', profile))
        profile = process_profile(); profile['keys'][1]['secret'] = False
        self.code('environment_secret_classification', lambda: self.manager.plan('fixture', profile))

    def test_profile_paths_cannot_escape_or_follow_symlink(self):
        self.code('invalid_identifier', lambda: self.manager.inspect('../other'))
        self.create()
        try:
            target = self.root / 'outside.env'; target.write_text('APP_TOKEN=secret', encoding='utf-8')
            self.env.unlink(); self.env.symlink_to(target)
        except OSError:
            self.skipTest('Symbolic link creation privilege unavailable; junction tests cover host reparse guard separately.')
        self.code('linked_root', lambda: self.manager.inspect('fixture'))

    def test_sqlserver_template_integrated_auth_does_not_require_password(self):
        template = Path(__file__).resolve().parents[1] / 'templates' / 'environment' / 'sqlserver.profile.json'
        profile = json.loads(template.read_text(encoding='utf-8'))
        self.create(profile)
        values = {'MSSQL_SERVER': 'synthetic-server', 'MSSQL_DATABASE': 'synthetic-db', 'MSSQL_SCHEMA': 'fixture',
                  'MSSQL_DRIVER': 'ODBC Driver 18 for SQL Server', 'MSSQL_AUTH': 'integrated',
                  'MSSQL_ENCRYPT': 'true', 'MSSQL_TRUST_SERVER_CERTIFICATE': 'false', 'MSSQL_CONNECTION_TIMEOUT': '5'}
        self.env.write_text('\n'.join(key['name'] + '=' + values.get(key['name'], '') for key in profile['keys']) + '\n', encoding='utf-8')
        resolved = self.manager.resolve('fixture', None, 'migration')
        self.assertEqual('integrated', resolved.env['MSSQL_AUTH'])
        self.assertNotIn('MSSQL_PASSWORD', resolved.env)
        self.assertEqual('migration', resolved.binding['role_kind'])

    def test_redaction_handles_quotes_backslashes_and_connection_fields(self):
        secret = 'quoted"with\\slash'
        data = redact_data({'output': 'prefix ' + secret, 'nested': [secret]}, [secret])
        self.assertNotIn(secret, json.dumps(data))
        self.assertEqual({'output': 'prefix [REDACTED]', 'nested': ['[REDACTED]']}, data)
        self.assertNotIn('raw-password', redact_output('Server=synthetic;Pwd=raw-password;'))

    def test_base_environment_drops_unlisted_variables(self):
        with patch.dict(os.environ, {'HARNESS_UNDECLARED_SECRET': 'do-not-inherit', 'CUSTOM_SAFE': 'yes'}, clear=False):
            self.assertNotIn('HARNESS_UNDECLARED_SECRET', base_process_environment())
            self.assertNotIn('CUSTOM_SAFE', base_process_environment())
            self.assertEqual('yes', base_process_environment(inherit_keys=['CUSTOM_SAFE'])['CUSTOM_SAFE'])


if __name__ == '__main__':
    unittest.main()
