"""Private, typed environment profiles. Public operations never return resolved values.

Profiles are cooperative process configuration, not an OS sandbox. OAuth credentials
remain in their host's native store; this module only reads its selected private .env.
"""
from __future__ import annotations
import contextlib
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import threading
import time
from dataclasses import dataclass

from .common import HarnessError, encoded, fail, identifier, now, sha256, uid
from .registry import _reject_links, atomic_json
from .validation import BOOL, STR, obj, validate

KEY = {'type': 'string', 'pattern': r'^[A-Z][A-Z0-9_]{0,95}$', 'maxLength': 96}
ROLE_KINDS = ['inspect', 'application', 'migration', 'fixture', 'frontend']
KEY_SPEC = obj({'name': KEY, 'type': {'type': 'string', 'enum': ['string', 'integer', 'boolean']},
                'secret': BOOL, 'required': BOOL, 'description': STR,
                'minimum': {'type': 'integer'}, 'maximum': {'type': 'integer'}},
               ['name', 'type', 'secret', 'required'])
ROLE_SPEC = obj({'kind': {'type': 'string', 'enum': ROLE_KINDS},
                 'mappings': {'type': 'object', 'additionalProperties': KEY},
                 'inherit_keys': {'type': 'array', 'items': KEY, 'maxItems': 24}}, ['kind', 'mappings'])
PROFILE_SCHEMA = obj({'provider': {'type': 'string', 'enum': ['sqlserver', 'process']},
                      'description': STR,
                      'keys': {'type': 'array', 'items': KEY_SPEC, 'minItems': 1, 'maxItems': 64},
                      'roles': {'type': 'object', 'additionalProperties': ROLE_SPEC},
                      'target_keys': {'type': 'array', 'items': KEY, 'minItems': 1, 'maxItems': 16},
                      'precedence': {'type': 'string', 'const': 'profile-over-explicit-inheritance'}},
                     ['provider', 'keys', 'roles', 'target_keys', 'precedence'])

# This is an allowlist, intentionally not a name-based credential blacklist.
BASE_ENV_KEYS = frozenset({'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP',
                          'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)',
                          'PROGRAMDATA', 'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE', 'OS',
                          'HOME', 'LANG', 'LC_ALL', 'TZ'})
FORBIDDEN_INHERIT = ('TOKEN', 'PASSWORD', 'SECRET', 'API_KEY', 'CREDENTIAL', 'CONNECTION_STRING')
PUBLIC_PREFIXES = ('VITE_', 'NEXT_PUBLIC_', 'PUBLIC_', 'REACT_APP_')
_LOCKS = {}
_LOCK_GUARD = threading.Lock()
_OWNER_SID = None


def environment_operations():
    return {
        'environment_inspect': obj({'profile_id': STR}, ['profile_id']),
        'environment_plan': obj({'profile_id': STR, 'profile': PROFILE_SCHEMA}, ['profile_id', 'profile']),
        'environment_apply': obj({'plan_id': STR}, ['plan_id']),
        'environment_probe': obj({'profile_id': STR, 'role': STR, 'revision': STR}, ['profile_id', 'role']),
    }


def base_process_environment(overrides=None, inherit_keys=()):
    """Only named OS plumbing is inherited. Explicit overrides are trusted internal data."""
    names = BASE_ENV_KEYS | {name.upper() for name in inherit_keys}
    result = {name: value for name, value in os.environ.items() if name.upper() in names}
    for name, value in (overrides or {}).items():
        for previous in list(result):
            if previous.upper() == name.upper():
                del result[previous]
        result[name] = value
    return result


def redact_output(text, secret_values=()):
    """Mask known resolved credentials before text is persisted or returned."""
    result = str(text)
    for value in sorted(set(secret_values), key=len, reverse=True):
        if value:
            result = result.replace(value, '[REDACTED]')
    result = re.sub(r'(?i)((?:password|pwd|access_token|api[_-]?key)\s*[=:]\s*)([^;\s]+)',
                    r'\1[REDACTED]', result)
    return result


def redact_data(value, secret_values=()):
    """Redact strings before JSON encoding so quoted/backslash credentials stay masked."""
    if isinstance(value, str):
        return redact_output(value, secret_values)
    if isinstance(value, list):
        return [redact_data(item, secret_values) for item in value]
    if isinstance(value, dict):
        return {key: redact_data(item, secret_values) for key, item in value.items()}
    return value


def parse_dotenv(raw):
    """Bounded literal parser: no expansion, shell evaluation, export, or multiline values."""
    if len(raw) > 65536:
        fail('environment_file_large', 'Selected .env exceeds 64 KiB.')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError:
        fail('environment_file_encoding', 'Selected .env must use UTF-8.')
    if '\x00' in text:
        fail('environment_file_format', 'Selected .env contains an unsupported character.')
    values = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Z][A-Z0-9_]{0,95})\s*=\s*(.*)', line)
        if not match:
            fail('environment_file_format', f'Invalid .env assignment at line {number}; value omitted.')
        key, value = match.groups()
        if key in values:
            fail('environment_duplicate_key', f'Duplicate .env key at line {number}; value omitted.')
        if value.startswith(('"', "'")):
            quote = value[0]
            if len(value) < 2 or value[-1] != quote or quote in value[1:-1]:
                fail('environment_file_format', f'Unsupported quoted .env value at line {number}; value omitted.')
            value = value[1:-1]
        if '${' in value or '$(' in value or '`' in value:
            fail('environment_expansion', f'Expansion and shell syntax are unsupported at line {number}; value omitted.')
        if len(value) > 16384:
            fail('environment_value_large', f'Oversized .env value at line {number}; value omitted.')
        values[key] = value
    return values


def _profile_check(profile):
    validate(profile, PROFILE_SCHEMA)
    keys = {entry['name']: entry for entry in profile['keys']}
    if len(keys) != len(profile['keys']):
        fail('environment_duplicate_key', 'Profile key names must be unique.')
    for name, spec in keys.items():
        if any(part in name for part in FORBIDDEN_INHERIT) and not spec['secret']:
            fail('environment_secret_classification', 'Credential-named keys must be declared secret.')
    if not profile['roles'] or len(profile['roles']) > 16:
        fail('environment_role', 'Specify between one and sixteen environment roles.')
    for key in profile['target_keys']:
        if key not in keys or keys[key]['secret']:
            fail('environment_target_keys', 'Target keys must name declared non-secret fields.')
    for name, role in profile['roles'].items():
        identifier(name, 'role')
        if not role['mappings']:
            fail('environment_role', 'Each role must map at least one declared key.')
        for destination, source in role['mappings'].items():
            validate(destination, KEY)
            if source not in keys:
                fail('environment_mapping', 'Role mapping references an undeclared key.')
            if any(part in destination for part in FORBIDDEN_INHERIT) and not keys[source]['secret']:
                fail('environment_secret_classification', 'Credential destinations must map from declared secret fields.')
            if keys[source]['secret'] and (destination.startswith(PUBLIC_PREFIXES) or role['kind'] == 'frontend'):
                fail('environment_public_secret', 'Secret fields cannot be mapped into a frontend role or public variable.')
            if role['kind'] == 'frontend' and (destination.startswith(('MSSQL_', 'SQLSERVER_', 'DATABASE_')) or
                    (profile['provider'] == 'sqlserver' and source in profile['target_keys'])):
                fail('environment_frontend_database', 'Database target fields cannot be injected into a frontend role.')
        for inherited in role.get('inherit_keys', []):
            if inherited in keys or any(part in inherited for part in FORBIDDEN_INHERIT):
                fail('environment_inherit_secret', 'Configured credentials must use typed private mappings, not inherited variables.')
    return profile


def _secure_directory(path):
    global _OWNER_SID
    path = Path(path)
    _reject_links(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        if _OWNER_SID is None:
            result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True, timeout=10)
            match = re.search(r'S-1-5-\d+(?:-\d+)+', result.stdout)
            if result.returncode or not match:
                fail('environment_acl', 'Cannot identify the current Windows principal for private profile permissions.')
            _OWNER_SID = match.group()
        result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                                 '*' + _OWNER_SID + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                                capture_output=True, timeout=15)
        if result.returncode:
            fail('environment_acl', 'Cannot set private profile permissions; credentials were not written.')
    else:
        path.chmod(0o700)


def _read_json(path):
    _reject_links(path)
    try:
        if path.stat().st_size > 262144:
            fail('environment_record_large', 'Private environment metadata exceeds its size limit.')
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError, OSError):
        fail('environment_record_invalid', 'Private environment metadata is missing or invalid; values omitted.')


def _write_json(path, value):
    _reject_links(path)
    atomic_json(path, value)
    if os.name != 'nt':
        Path(path).chmod(0o600)


@dataclass(frozen=True, repr=False)
class ResolvedEnvironment:
    """Internal-only container. Never serialize this object into operation output or history."""
    env: dict
    secret_values: tuple
    binding: dict
    profile: dict


class Environment:
    def __init__(self, state_root):
        raw = Path(state_root).expanduser()
        if not raw.is_absolute():
            fail('invalid_root', 'Personal environment state root must be absolute.')
        _reject_links(raw)
        self.state_root = raw.resolve()
        self.root = self.state_root / 'environments'

    def _folder(self, profile_id):
        folder = self.root / identifier(profile_id, 'profile_id')
        _reject_links(folder)
        return folder

    @contextlib.contextmanager
    def _lock(self):
        _secure_directory(self.root)
        lock_path = self.root / '.lock'
        _reject_links(lock_path)
        key = str(lock_path)
        with _LOCK_GUARD:
            lock = _LOCKS.setdefault(key, threading.Lock())
        if not lock.acquire(timeout=10):
            fail('environment_busy', 'Environment state is being updated; retry the same request.')
        stream = None
        locked = False
        try:
            stream = open(lock_path, 'a+b')
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b'0'); stream.flush()
            deadline = time.monotonic() + 10
            while True:
                try:
                    stream.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        fail('environment_busy', 'Environment state is being updated; retry the same request.')
                    time.sleep(0.05)
            yield
        finally:
            if stream is not None:
                if locked:
                    stream.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                stream.close()
            lock.release()

    def execute(self, operation, params):
        schemas = environment_operations()
        if operation not in schemas:
            fail('unknown_operation', 'Unknown environment operation.')
        validate(params, schemas[operation])
        return getattr(self, operation.removeprefix('environment_'))(**params)

    def plan(self, profile_id, profile):
        _profile_check(profile)
        folder = self._folder(profile_id)
        with self._lock():
            existing = _read_json(folder / 'profile.json') if (folder / 'profile.json').exists() else None
            plan = {'plan_id': uid('env-plan'), 'profile_id': profile_id, 'created_at': now(),
                    'expected_profile_hash': sha256(encoded(existing)) if existing else None,
                    'profile': profile, 'state': 'prepared'}
            _write_json(self.root / 'plans' / (plan['plan_id'] + '.json'), plan)
        return {'plan_id': plan['plan_id'], 'profile_id': profile_id, 'profile': profile,
                'action': 'update' if existing else 'create', 'preserve_existing_env': True,
                'env_path': str(folder / 'secrets' / '.env'),
                'notice': 'Only blank declared assignments are created for a new .env. Enter actual values locally.'}

    def apply(self, plan_id):
        identifier(plan_id, 'plan_id')
        with self._lock():
            plan_path = self.root / 'plans' / (plan_id + '.json')
            plan = _read_json(plan_path)
            if plan.get('state') == 'applied':
                return plan['receipt']
            folder = self._folder(plan['profile_id'])
            profile = _profile_check(plan['profile'])
            existing = _read_json(folder / 'profile.json') if (folder / 'profile.json').exists() else None
            if (sha256(encoded(existing)) if existing else None) != plan['expected_profile_hash']:
                fail('environment_plan_stale', 'Profile changed after this plan; inspect and prepare a new plan.')
            _secure_directory(folder)
            _secure_directory(folder / 'secrets')
            env_path = folder / 'secrets' / '.env'
            _reject_links(env_path)
            created = not env_path.exists()
            if created:
                content = '# Private values: edit locally. Never paste credentials into chat or commit this file.\n'
                content += '\n'.join(key['name'] + '=' for key in profile['keys']) + '\n'
                with open(env_path, 'x', encoding='utf-8', newline='\n') as stream:
                    stream.write(content)
                if os.name != 'nt':
                    env_path.chmod(0o600)
            unchanged = existing is not None and existing['profile'] == profile
            record = {'profile_id': plan['profile_id'],
                      'profile_revision': existing['profile_revision'] if unchanged else uid('env-profile'),
                      'updated_at': now(), 'profile': profile}
            _write_json(folder / 'profile.json', record)
            receipt = {'receipt_id': uid('env-apply'), 'profile_id': plan['profile_id'],
                       'profile_revision': record['profile_revision'], 'applied_at': now(),
                       'env_created': created, 'existing_env_preserved': not created,
                       'env_path': str(env_path), 'keys': [key['name'] for key in profile['keys']],
                       'roles': sorted(profile['roles']), 'status': 'configuration_applied_values_unverified'}
            plan.update(state='applied', receipt=receipt)
            _write_json(plan_path, plan)
            _write_json(folder / 'receipts' / (receipt['receipt_id'] + '.json'), receipt)
            return receipt

    def _read_current(self, profile_id):
        folder = self._folder(profile_id)
        if not (folder / 'profile.json').exists():
            fail('environment_profile_missing', 'Create a private environment profile before resolving it.')
        record = _read_json(folder / 'profile.json')
        profile = _profile_check(record['profile'])
        env_path = folder / 'secrets' / '.env'
        _reject_links(env_path)
        try:
            if env_path.stat().st_size > 65536:
                fail('environment_file_large', 'Selected .env exceeds 64 KiB.')
            raw = env_path.read_bytes()
        except OSError:
            fail('environment_file_missing', 'The selected private .env is unavailable; values omitted.')
        values = parse_dotenv(raw)
        specs = {entry['name']: entry for entry in profile['keys']}
        if set(values) - set(specs):
            fail('environment_unknown_key', 'Selected .env has undeclared keys; update the profile explicitly before use.')
        problems = []
        for name, value in values.items():
            spec = specs[name]
            if not value:
                continue
            if spec['type'] == 'integer':
                if not re.fullmatch(r'-?[0-9]+', value):
                    problems.append({'key': name, 'issue': 'invalid_integer'})
                elif not spec.get('minimum', -(2**63)) <= int(value) <= spec.get('maximum', 2**63 - 1):
                    problems.append({'key': name, 'issue': 'out_of_range'})
            elif spec['type'] == 'boolean' and value.lower() not in {'true', 'false', '1', '0', 'yes', 'no'}:
                problems.append({'key': name, 'issue': 'invalid_boolean'})
        state_path = folder / 'secret-state.json'
        state = _read_json(state_path) if state_path.exists() else {'key': secrets.token_hex(32)}
        try:
            private_key = bytes.fromhex(state['key'])
        except (KeyError, ValueError, TypeError):
            fail('environment_state_invalid', 'Private change-detection state is invalid; no values returned.')
        if len(private_key) != 32:
            fail('environment_state_invalid', 'Private change-detection state has an invalid key.')
        def digest(label, data):
            return hmac.new(private_key, label.encode('ascii') + b'\x00' + encoded(data), hashlib.sha256).hexdigest()
        target_digest = digest('target', {name: values.get(name, '') for name in profile['target_keys']})
        secret_digest = digest('values', values)
        if state.get('target_digest') != target_digest:
            state['target_revision'] = uid('env-target')
        if state.get('secret_digest') != secret_digest:
            state['secret_revision'] = uid('env-secret')
        if (state.get('secret_digest'), state.get('profile_revision')) != (secret_digest, record['profile_revision']):
            state['revision'] = uid('env-revision')
        state.update(target_digest=target_digest, secret_digest=secret_digest, profile_revision=record['profile_revision'])
        _write_json(state_path, state)
        binding = {key: state[key] for key in ('revision', 'profile_revision', 'target_revision', 'secret_revision')}
        binding['profile_id'] = profile_id
        return record, values, binding, problems

    def inspect(self, profile_id):
        folder = self._folder(profile_id)
        if not (folder / 'profile.json').exists():
            return {'profile_id': profile_id, 'status': 'not_configured', 'env_path': str(folder / 'secrets' / '.env')}
        with self._lock():
            record, values, binding, problems = self._read_current(profile_id)
        profile = record['profile']
        missing = [item['name'] for item in profile['keys'] if item['required'] and not values.get(item['name'])]
        return {'profile_id': profile_id, 'binding': binding, 'profile': profile,
                'status': 'values_incomplete' if missing or problems else 'values_present_probe_required',
                'present_keys': sorted(key for key, value in values.items() if value), 'missing_keys': missing,
                'format_problems': problems, 'env_path': str(folder / 'secrets' / '.env'),
                'secrets_returned': False, 'precedence': profile['precedence']}

    def resolve(self, profile_id, revision=None, role='application'):
        identifier(role, 'role')
        with self._lock():
            record, values, binding, problems = self._read_current(profile_id)
        if revision is not None and revision != binding['revision']:
            fail('environment_revision_stale', 'Environment values or profile changed; inspect and probe the current revision.')
        profile = record['profile']
        if role not in profile['roles']:
            fail('environment_role_missing', 'Requested role is not configured in this profile.')
        selected = profile['roles'][role]
        specs = {entry['name']: entry for entry in profile['keys']}
        selected_sources = set(selected['mappings'].values())
        if any(item['key'] in selected_sources for item in problems):
            fail('environment_value_invalid', 'A mapped role value has an invalid type; inspect reports key names only.')
        missing = [name for name in selected_sources if specs[name]['required'] and not values.get(name)]
        if missing:
            fail('environment_values_missing', 'Required role values are missing: ' + ', '.join(sorted(missing)))
        mapped = {destination: values[source] for destination, source in selected['mappings'].items() if values.get(source)}
        # A profile may share optional SQL authentication credentials, but integrated auth
        # never requires a password and each role can map distinct least-privilege accounts.
        if profile['provider'] == 'sqlserver' and selected['kind'] != 'frontend':
            auth = mapped.get('MSSQL_AUTH', 'sql').lower()
            if auth not in {'sql', 'integrated'}:
                fail('environment_auth', 'MSSQL_AUTH must be sql or integrated.')
            if auth == 'sql' and (not mapped.get('MSSQL_USER') or not mapped.get('MSSQL_PASSWORD')):
                fail('environment_credentials_missing', 'SQL authentication requires mapped role user and password fields.')
            if auth == 'integrated':
                mapped.pop('MSSQL_USER', None)
                mapped.pop('MSSQL_PASSWORD', None)
        resolved = base_process_environment(mapped, selected.get('inherit_keys', []))
        secrets_to_mask = tuple(value for name, value in values.items() if value and specs[name]['secret'])
        binding.update(role=role, role_kind=selected['kind'])
        return ResolvedEnvironment(resolved, secrets_to_mask, binding, profile)

    def known_secret_values(self, profile_id):
        """Internal journal guard input, including a profile not yet ready to connect.

        Only the selected profile's declared secret fields are read. Callers must
        never serialize the returned tuple or expose it as a public operation.
        This does not validate that any role or external connection is ready.
        """
        with self._lock():
            record, values, _binding, _problems = self._read_current(profile_id)
        secret_names = {item['name'] for item in record['profile']['keys'] if item['secret']}
        return tuple(values[name] for name in sorted(secret_names) if values.get(name))

    def probe(self, profile_id, role, revision=None):
        try:
            resolved = self.resolve(profile_id, revision, role)
        except HarnessError as error:
            if error.code not in {'environment_values_missing', 'environment_credentials_missing', 'environment_value_invalid'}:
                raise
            return {'profile_id': profile_id, 'role': role, 'status': 'blocked', 'blocker': error.code,
                    'notice': 'Complete the selected private .env locally and repeat the probe; values omitted.'}
        if resolved.profile['provider'] == 'sqlserver' and resolved.binding['role_kind'] != 'frontend':
            try:
                from .database import probe_environment
            except ImportError:
                observation = {'status': 'blocked', 'blocker': 'sqlserver_adapter_unavailable'}
            else:
                observation = probe_environment(resolved)
        else:
            observation = {'status': 'passed', 'check': 'typed_process_environment',
                           'notice': 'This validates configuration only; it does not verify an external service.'}
        receipt = {'probe_receipt_id': uid('env-probe'), 'observed_at': now(),
                   'binding': resolved.binding, 'status': observation.get('status', 'blocked'), 'observation': observation}
        # Defense in depth: an adapter cannot accidentally persist a known injected secret.
        sanitized_observation = redact_data(observation, resolved.secret_values)
        # Random binding IDs and adapter-produced digests are not derived from
        # credential text. Do not corrupt them when a short secret is a substring.
        for key, value in observation.items():
            if (key in {'target_id', 'principal_digest', 'permissions_digest', 'permissions_sha256'} and
                    isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value)):
                sanitized_observation[key] = value
        if observation.get('status') in {'passed', 'failed', 'blocked'}:
            sanitized_observation['status'] = observation['status']
        sanitized = {**receipt, 'observation': sanitized_observation}
        with self._lock():
            folder = self._folder(profile_id)
            _write_json(folder / 'receipts' / (receipt['probe_receipt_id'] + '.json'), sanitized)
            _write_json(folder / ('latest-probe-' + role + '.json'), sanitized)
        return sanitized

    def validate_contract(self, contract, require_probe=True):
        """Pin target/config; secret rotations need a new probe, not a new user scope approval."""
        profile_id = identifier(contract['profile_id'], 'profile_id')
        roles = contract.get('roles', [])
        if not roles:
            fail('environment_contract_roles', 'Environment contract must specify at least one role.')
        pinned_roles = contract.get('role_probe_receipts', {})
        if require_probe and len(roles) > 1 and set(pinned_roles) != set(roles):
            fail('environment_probe_required', 'Each approved environment role must pin its own successful probe receipt.')
        bindings = []
        for role in roles:
            resolved = self.resolve(profile_id, None, role)
            for key in ('profile_revision', 'target_revision'):
                if contract.get(key) != resolved.binding[key]:
                    fail('environment_contract_stale', 'Environment target or role configuration changed; revise the approved contract.')
            if require_probe:
                pinned_id = identifier(pinned_roles.get(role, contract.get('probe_receipt_id', '')), 'probe_receipt_id')
                pinned_path = self._folder(profile_id) / 'receipts' / (pinned_id + '.json')
                if not pinned_path.exists():
                    fail('environment_probe_required', 'Pinned environment probe receipt does not exist.')
                pinned = _read_json(pinned_path)
                if (pinned.get('binding', {}).get('profile_id') != profile_id or
                        pinned.get('binding', {}).get('role') != role or pinned.get('status') != 'passed'):
                    fail('environment_probe_required', 'Pinned environment probe receipt is not a successful observation of this role.')
                probe_path = self._folder(profile_id) / ('latest-probe-' + identifier(role, 'role') + '.json')
                if not probe_path.exists():
                    fail('environment_probe_required', 'The approved environment role requires a successful current probe.')
                probe = _read_json(probe_path)
                if probe.get('status') != 'passed' or probe.get('binding') != resolved.binding:
                    fail('environment_probe_stale', 'Environment credentials changed or the probe failed; run a new role probe.')
                for key in ('target_id', 'principal_digest', 'permissions_digest', 'permissions_sha256'):
                    if pinned.get('observation', {}).get(key) != probe.get('observation', {}).get(key):
                        fail('environment_permission_drift', 'Observed database target, account or permissions changed; revise the approved environment contract.')
            bindings.append(resolved.binding)
        return {'status': 'passed', 'profile_id': profile_id, 'bindings': bindings}
