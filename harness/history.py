"""Private Git journal and bounded, byte-preserving local file recovery.

Only regular files and directories are supported. Links, reparse points, special
files, unsupported names, and unstable reads fail closed. Product Git is never
invoked. Two matching observations are not an atomic filesystem snapshot.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .common import HarnessError, encoded, emit, fail, identifier, now, overlap, safe_relative, scan_secrets, sha256, uid

REF = 'refs/heads/history'
_OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
_CACHES = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
           '.mypy_cache', '.ruff_cache', '.cache', '.next', 'coverage', 'dist',
           'build', 'bin', 'obj', 'logs'}
_SECRET_NAMES = {'credentials.json', 'secrets.json', 'id_rsa', 'id_ed25519', '.npmrc', '.pypirc'}
_DEFAULT_POLICY = {'exclude_patterns': [], 'max_file_bytes': 8 * 1024 * 1024,
                   'max_total_bytes': 64 * 1024 * 1024, 'max_files': 10000}


def _no_links(path):
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            fail('unsupported_link', 'Links and reparse points are outside the supported file scope.')
    return path


def _atomic_json(path, value):
    path = Path(path)
    _no_links(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.journal-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Journal:
    """State lives at one ref; raw blobs are reachable through each commit tree."""

    def __init__(self, path: Path):
        self.path = Path(os.path.abspath(path))
        self.directory = self.path.parent
        self._pending_blobs = set()
        self._in_transaction = False

    def _git(self, *arguments, raw=None, check=True):
        _no_links(self.path)
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
        env.update({'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                    'GIT_TERMINAL_PROMPT': '0', 'GIT_AUTHOR_NAME': 'Local Development Harness',
                    'GIT_AUTHOR_EMAIL': 'harness@localhost', 'GIT_COMMITTER_NAME': 'Local Development Harness',
                    'GIT_COMMITTER_EMAIL': 'harness@localhost'})
        argv = ['git', '--no-optional-locks', '-c', 'core.autocrlf=false',
                '-c', 'core.fsmonitor=false', '-c', 'commit.gpgSign=false',
                '-c', 'core.fsync=committed', '--git-dir=' + str(self.path), *arguments]
        try:
            result = subprocess.run(argv, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=str(self.directory) if self.directory.exists() else None,
                                    env=env, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            fail('git_unavailable', 'Private journal Git could not complete: ' + type(error).__name__)
        if check and result.returncode:
            fail('git_error', 'Private journal Git operation failed: ' + arguments[0])
        return result

    def _require(self):
        _no_links(self.path)
        if not self.path.is_dir() or not (self.path / 'HEAD').is_file():
            fail('journal_not_initialized', 'The private journal has not been initialized.')
        if self._git('rev-parse', '--is-bare-repository').stdout.strip() != b'true':
            fail('invalid_journal', 'The history path must be a private bare repository.')

    @contextmanager
    def _lock(self):
        _no_links(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        lock_path = self.directory / '.history.lock'
        _no_links(lock_path)
        stream = open(lock_path, 'a+b')
        try:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b'0')
                stream.flush()
            deadline = time.monotonic() + 15
            while True:
                try:
                    stream.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        fail('journal_busy', 'Another process owns the private journal lock.')
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()

    def _tip(self):
        result = self._git('rev-parse', '--verify', REF, check=False)
        if result.returncode:
            fail('journal_corrupt', 'The private journal authoritative ref is missing.')
        return result.stdout.decode('ascii').strip()

    def _read_tip(self, tip):
        try:
            state = json.loads(self._git('show', tip + ':state.json').stdout)
        except (ValueError, UnicodeError):
            fail('journal_corrupt', 'The private journal state is invalid JSON.')
        if not isinstance(state, dict):
            fail('journal_corrupt', 'The private journal state must be an object.')
        return state

    def _pending_recovery(self):
        location = self.directory / 'recovery'
        if not location.exists():
            return []
        _no_links(location)
        unfinished = []
        for path in location.glob('*.json'):
            _no_links(path)
            try:
                data = json.loads(path.read_bytes())
            except (ValueError, OSError):
                fail('recovery_corrupt', 'A recovery journal cannot be read; writes are blocked.')
            if data.get('status') not in ('completed', 'rolled_back'):
                unfinished.append(data)
        return unfinished

    def _check_recovery(self):
        if self._pending_recovery():
            fail('recovery_required', 'Reconcile the unfinished file recovery before another managed write.')

    def _commit(self, state, previous=None):
        state_raw = encoded(state)
        state_oid = self.put_blob(state_raw)
        blobs = set(self._pending_blobs)
        if previous:
            result = self._git('ls-tree', '-z', previous + ':objects', check=False)
            if result.returncode == 0:
                for item in result.stdout.split(b'\0'):
                    if item:
                        blobs.add(item.split(b'\t', 1)[0].split()[2].decode('ascii'))
        blobs.discard(state_oid)
        object_tree = self._git('mktree', '-z', raw=b''.join(
            ('100644 blob ' + oid + '\t' + oid + '\0').encode('ascii') for oid in sorted(blobs)
        )).stdout.decode('ascii').strip()
        tree = self._git('mktree', '-z', raw=(
            '100644 blob ' + state_oid + '\tstate.json\0' +
            '040000 tree ' + object_tree + '\tobjects\0').encode('ascii')).stdout.decode('ascii').strip()
        args = ['commit-tree', tree]
        if previous:
            args += ['-p', previous]
        commit = self._git(*args, raw=b'Private development record\n').stdout.decode('ascii').strip()
        result = self._git('update-ref', REF, commit, previous or '0' * len(commit), check=False)
        if result.returncode:
            fail('journal_conflict', 'The authoritative journal tip changed before publication.')
        self._pending_blobs.clear()
        return commit

    def initialize(self, initial_state: dict) -> dict:
        if not isinstance(initial_state, dict):
            fail('invalid_state', 'Initial state must be an object.')
        _validate_roots(self, initial_state)
        with self._lock():
            if self.path.exists() and any(self.path.iterdir()):
                fail('already_initialized', 'The journal directory is not empty.')
            self.path.mkdir(parents=True, exist_ok=True)
            self._git('init', '--bare', '--quiet', str(self.path))
            self._git('symbolic-ref', 'HEAD', REF)
            self._commit(copy.deepcopy(initial_state))
        return self.read()

    def read(self) -> dict:
        self._require()
        return self._read_tip(self._tip())

    def transaction(self, callback):
        if self._in_transaction:
            fail('nested_transaction', 'A journal callback cannot start another transaction.')
        self._require()
        with self._lock():
            self._check_recovery()
            self._in_transaction = True
            pending_before = set(self._pending_blobs)
            try:
                previous = self._tip()
                state = self._read_tip(previous)
                original = encoded(state)
                result = callback(state)
                _validate_roots(self, state)
                if encoded(state) != original:
                    self._commit(state, previous)
                return copy.deepcopy(result)
            except BaseException:
                self._pending_blobs = pending_before
                raise
            finally:
                self._in_transaction = False

    def put_blob(self, raw: bytes) -> str:
        if not isinstance(raw, bytes):
            fail('invalid_blob', 'Blob content must be bytes.')
        oid = self._git('hash-object', '--stdin', '--no-filters', '-w', raw=raw).stdout.decode('ascii').strip()
        if not _OID.fullmatch(oid):
            fail('git_error', 'Git returned an invalid object identifier.')
        self._pending_blobs.add(oid)
        return oid

    def get_blob(self, oid: str) -> bytes:
        if not isinstance(oid, str) or not _OID.fullmatch(oid):
            fail('invalid_oid', 'Invalid Git object identifier.')
        return self._git('cat-file', 'blob', oid).stdout

    def fsck(self):
        self._require()
        result = self._git('fsck', '--full', '--no-reflogs', check=False)
        return {'ok': result.returncode == 0, 'exit_code': result.returncode,
                'output': (result.stdout + result.stderr).decode('utf-8', errors='replace')[:16000]}


def _validate_roots(journal, state):
    standard = state.get('project', {}).get('standard_root')
    if standard and overlap(journal.directory, standard):
        fail('path_overlap', 'Private history must be outside the common standard root.')
    for workspace in state.get('workspaces', {}).values():
        if not isinstance(workspace, dict) or not workspace.get('root'):
            fail('invalid_workspace', 'Workspace registration requires its root.')
        if overlap(journal.directory, workspace['root']):
            fail('path_overlap', 'Private history must be outside every product root.')


def _workspace(journal, state, workspace_id):
    identifier(workspace_id, 'workspace_id')
    try:
        value = state['workspaces'][workspace_id]['root']
    except KeyError:
        fail('workspace_not_found', 'Register the workspace before using source history.')
    root = _no_links(value)
    if not root.is_dir():
        fail('workspace_missing', 'The registered product directory does not exist.')
    _validate_roots(journal, state)
    return root


def _policy(value):
    result = copy.deepcopy(_DEFAULT_POLICY)
    if value is not None:
        if not isinstance(value, dict) or set(value) - set(result):
            fail('invalid_policy', 'Unsupported snapshot policy fields.')
        result.update(value)
    if not isinstance(result['exclude_patterns'], list) or len(result['exclude_patterns']) > 100:
        fail('invalid_policy', 'exclude_patterns must be a bounded list.')
    for pattern in result['exclude_patterns']:
        if not isinstance(pattern, str) or not pattern or len(pattern) > 300 or '\x00' in pattern:
            fail('invalid_policy', 'Invalid exclusion pattern.')
    for key in ('max_file_bytes', 'max_total_bytes', 'max_files'):
        if type(result[key]) is not int or result[key] < 1 or result[key] > _DEFAULT_POLICY[key]:
            fail('invalid_policy', 'Snapshot limits must be positive and within the supported maxima.')
    return result


def _excluded(relative, policy):
    name = relative.rsplit('/', 1)[-1]
    lower = name.lower()
    if lower in _CACHES:
        return 'git_metadata' if lower == '.git' else 'generated_or_cache'
    if lower in _SECRET_NAMES or lower.endswith(('.pem', '.key', '.pfx', '.p12')):
        return 'secret_path'
    if lower == '.env' or (lower.startswith('.env.') and lower not in ('.env.example', '.env.sample', '.env.template')):
        return 'secret_path'
    if lower.endswith(('.pyc', '.pyo')) or lower in ('.ds_store', 'thumbs.db'):
        return 'generated_or_cache'
    if any(fnmatch.fnmatchcase(relative, pattern) for pattern in policy['exclude_patterns']):
        return 'project_policy'
    return None


def _managed_path(relative, policy):
    parts = safe_relative(relative).parts
    if any(_excluded('/'.join(parts[:index]), policy) for index in range(1, len(parts) + 1)):
        fail('excluded_path', 'The operation references excluded source or Git metadata.')
    return relative


def _file_bytes(path, limit):
    _no_links(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        fail('unsupported_file', 'Only regular source files are supported.')
    if before.st_size > limit:
        fail('capture_limit', 'A required source file exceeds the snapshot size limit.')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
        after_handle = os.fstat(stream.fileno())
    after = path.lstat()
    signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if len(raw) > limit or not (signature(before) == signature(opened) == signature(after_handle) == signature(after)):
        fail('source_changed', 'Source changed while being read; capture was not published.')
    scan_secrets(raw)
    return raw


def _scan(root, policy):
    files, directories, exclusions, contents = [], [], [], {}
    seen, total = set(), 0

    def visit(folder, prefix=''):
        nonlocal total
        _no_links(folder)
        with os.scandir(folder) as listing:
            entries = sorted(list(listing), key=lambda item: item.name)
        for entry in entries:
            relative = prefix + entry.name
            reason = _excluded(relative, policy)
            if reason:
                exclusions.append({'path': relative, 'reason': reason})
                continue
            safe_relative(relative)
            folded = relative.casefold()
            if folded in seen:
                fail('path_collision', 'Source paths collide on case-insensitive filesystems.')
            seen.add(folded)
            path = root / relative
            _no_links(path)
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                directories.append(relative)
                if len(directories) > policy['max_files']:
                    fail('capture_limit', 'Source directory count exceeds the snapshot limit.')
                visit(path, relative + '/')
            elif stat.S_ISREG(info.st_mode):
                raw = _file_bytes(path, policy['max_file_bytes'])
                total += len(raw)
                if total > policy['max_total_bytes'] or len(files) >= policy['max_files']:
                    fail('capture_limit', 'Source contents exceed the bounded snapshot limits.')
                files.append({'path': relative, 'sha256': sha256(raw), 'size': len(raw)})
                contents[relative] = raw
            else:
                fail('unsupported_file', 'Special source files are not supported.')

    try:
        visit(root)
    except HarnessError:
        raise
    except OSError as error:
        fail('capture_io', 'Required source content could not be read: ' + type(error).__name__)
    manifest = {'files': files, 'directories': sorted(directories), 'exclusions': exclusions, 'policy': policy}
    return manifest, contents


def _digest(manifest):
    normalized = {'files': [{key: item[key] for key in ('path', 'sha256', 'size')}
                            for item in sorted(manifest['files'], key=lambda item: item['path'])],
                  'directories': sorted(manifest['directories']),
                  'exclusions': sorted(manifest['exclusions'], key=lambda item: item['path']), 'policy': manifest['policy']}
    return sha256(encoded(normalized))


def _observe(root, policy):
    first, contents = _scan(root, policy)
    second, unused = _scan(root, policy)
    if _digest(first) != _digest(second):
        fail('source_changed', 'The two source observations differ; capture was not published.')
    first['manifest_sha256'] = _digest(first)
    return first, contents


def observe_workspace(journal, workspace_id, policy=None):
    state = journal.read()
    root = _workspace(journal, state, workspace_id)
    manifest, unused = _observe(root, _policy(policy))
    return manifest


def _request(state, request_id, signature):
    if request_id is None:
        return None
    identifier(request_id, 'request_id')
    saved = state.setdefault('requests', {}).get('history:' + request_id)
    if saved:
        if saved['signature'] != signature:
            fail('request_conflict', 'This request ID was already used with different inputs.')
        return saved['result']
    return None


def _remember(state, request_id, signature, result):
    if request_id is not None:
        state.setdefault('requests', {})['history:' + request_id] = {'signature': signature, 'result': copy.deepcopy(result)}


def _capture(journal, state, workspace_id, label, policy):
    root = _workspace(journal, state, workspace_id)
    manifest, contents = _observe(root, policy)
    for item in manifest['files']:
        item['oid'] = journal.put_blob(contents[item['path']])
        if journal.get_blob(item['oid']) != contents[item['path']]:
            fail('blob_mismatch', 'Stored source bytes do not match the captured file.')
    snapshot = {'snapshot_id': uid('snapshot'), 'workspace_id': workspace_id, 'label': label,
                'manifest': manifest, 'manifest_sha256': _digest(manifest), 'completeness': 'complete',
                'consistency': 'observed-stable', 'created_at': now()}
    state.setdefault('snapshots', {})[snapshot['snapshot_id']] = snapshot
    emit(state, 'snapshot_captured', {'snapshot_id': snapshot['snapshot_id'], 'workspace_id': workspace_id})
    return snapshot


def capture_snapshot(journal, workspace_id, label='', policy=None, request_id=None):
    if not isinstance(label, str) or len(label) > 500:
        fail('invalid_label', 'Snapshot label must be a short string.')
    policy = _policy(policy)
    signature = sha256(encoded(['capture', workspace_id, label, policy]))
    def perform(state):
        saved = _request(state, request_id, signature)
        if saved is not None:
            return saved
        result = _capture(journal, state, workspace_id, label, policy)
        _remember(state, request_id, signature, result)
        return result
    return journal.transaction(perform)


def _snapshot(journal, state, snapshot_id):
    identifier(snapshot_id, 'snapshot_id')
    snapshot = state.get('snapshots', {}).get(snapshot_id)
    if not snapshot or snapshot.get('completeness') != 'complete':
        fail('snapshot_not_found', 'A complete source snapshot is required.')
    manifest = snapshot['manifest']
    if _digest(manifest) != snapshot['manifest_sha256']:
        fail('snapshot_corrupt', 'Snapshot manifest hash mismatch.')
    _policy(manifest['policy'])
    seen = set()
    for name in [*manifest['directories'], *(item['path'] for item in manifest['files'])]:
        _managed_path(name, manifest['policy'])
        if name.casefold() in seen:
            fail('path_collision', 'Snapshot paths collide.')
        seen.add(name.casefold())
    directories = set(manifest['directories'])
    for name in [*directories, *(item['path'] for item in manifest['files'])]:
        parts = safe_relative(name).parts
        if any('/'.join(parts[:index]) not in directories for index in range(1, len(parts))):
            fail('snapshot_corrupt', 'Snapshot parent directory metadata is incomplete.')
    contents = {}
    for item in manifest['files']:
        raw = journal.get_blob(item['oid'])
        if len(raw) != item['size'] or sha256(raw) != item['sha256']:
            fail('snapshot_corrupt', 'Snapshot blob hash mismatch.')
        contents[item['path']] = raw
    return snapshot, contents


def snapshot_matches(journal, snapshot_id, workspace_id=None):
    state = journal.read()
    snapshot, unused = _snapshot(journal, state, snapshot_id)
    observed = observe_workspace(journal, workspace_id or snapshot['workspace_id'], snapshot['manifest']['policy'])
    return _digest(observed) == snapshot['manifest_sha256']


def _destination(journal, state, destination):
    destination = _no_links(destination)
    roots = [journal.directory, *[item['root'] for item in state.get('workspaces', {}).values()]]
    if state.get('project', {}).get('standard_root'):
        roots.append(state['project']['standard_root'])
    if any(overlap(destination, root) for root in roots):
        fail('path_overlap', 'Export must be outside product, private history, and common standard roots.')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        fail('destination_not_empty', 'Export requires a new or empty directory.')
    return destination


def _replace_file(path, raw):
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.restore-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _no_links(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_snapshot(journal, snapshot_id, destination):
    state = journal.read()
    snapshot, contents = _snapshot(journal, state, snapshot_id)
    destination = _destination(journal, state, destination)
    destination.mkdir(parents=True, exist_ok=True)
    for relative in sorted(snapshot['manifest']['directories'], key=lambda item: (item.count('/'), item)):
        _no_links(destination / relative).mkdir(exist_ok=True)
    for relative, raw in contents.items():
        _replace_file(destination / relative, raw)
    observed, unused = _observe(destination, snapshot['manifest']['policy'])
    # Excluded source paths are deliberately absent in an exported product copy.
    expected = copy.deepcopy(snapshot['manifest'])
    expected['exclusions'] = []
    if _digest(observed) != _digest(expected):
        fail('export_mismatch', 'The exported managed files differ from the snapshot.')
    return {'snapshot_id': snapshot_id, 'destination': str(destination), 'status': 'export_verified',
            'manifest_sha256': _digest(observed), 'source_manifest_sha256': snapshot['manifest_sha256'], 'created_at': now()}


def _plan_hash(plan):
    return sha256(encoded({key: value for key, value in plan.items() if key != 'sha256'}))


def plan_restore(journal, snapshot_id, workspace_id):
    def perform(state):
        snapshot, unused = _snapshot(journal, state, snapshot_id)
        root = _workspace(journal, state, workspace_id)
        if snapshot['workspace_id'] != workspace_id:
            fail('workspace_mismatch', 'Cross-workspace source restoration is not supported.')
        current, unused = _observe(root, snapshot['manifest']['policy'])
        targets = {item['path']: item for item in snapshot['manifest']['files']}
        before = {item['path']: item for item in current['files']}
        known = {item['path'] for old in state.get('snapshots', {}).values()
                 if old['workspace_id'] == workspace_id for item in old['manifest']['files']}
        operations, preserved = [], []
        for relative in sorted(set(before) | set(targets)):
            previous, target = before.get(relative), targets.get(relative)
            if previous and not target and relative not in known:
                preserved.append(relative)
                continue
            if (previous or {}).get('sha256') != (target or {}).get('sha256'):
                operations.append({'path': relative, 'before': previous, 'target': target})
        target_dirs, current_dirs = set(snapshot['manifest']['directories']), set(current['directories'])
        known_dirs = {directory for old in state.get('snapshots', {}).values()
                      if old['workspace_id'] == workspace_id for directory in old['manifest']['directories']}
        if set(before) & target_dirs or set(targets) & current_dirs:
            fail('unsupported_transition', 'File/directory type replacement requires a separate manual plan.')
        delete_dirs = [path for path in current_dirs - target_dirs
                       if path in known_dirs
                       and not any(name == path or name.startswith(path + '/') for name in preserved)
                       and not any(item['path'].startswith(path + '/') for item in current['exclusions'])]
        plan = {'plan_id': uid('restore'), 'snapshot_id': snapshot_id, 'workspace_id': workspace_id,
                'root': str(root), 'before_manifest': current, 'before_manifest_sha256': _digest(current),
                'policy': snapshot['manifest']['policy'], 'operations': operations,
                'create_directories': sorted(target_dirs - current_dirs, key=lambda name: (name.count('/'), name)),
                'delete_directories': sorted(delete_dirs, key=lambda name: (-name.count('/'), name)),
                'preserved_paths': preserved, 'created_at': now(), 'failure_recovery': 'restore_pre_capture'}
        plan['sha256'] = _plan_hash(plan)
        state.setdefault('restore_plans', {})[plan['plan_id']] = plan
        emit(state, 'restore_planned', {'plan_id': plan['plan_id'], 'sha256': plan['sha256']})
        return plan
    return journal.transaction(perform)


def _get_plan(state, plan_id):
    identifier(plan_id, 'plan_id')
    plan = state.get('restore_plans', {}).get(plan_id)
    if not plan or plan.get('sha256') != _plan_hash(plan):
        fail('invalid_restore_plan', 'The fixed restoration plan is missing or changed.')
    return plan


def record_restore_decision(journal, plan_id, decision, user_message, source):
    if decision not in ('approve', 'reject'):
        fail('invalid_decision', 'Restoration decision must be approve or reject.')
    if not isinstance(user_message, str) or not user_message.strip() or len(user_message) > 16000:
        fail('invalid_decision', 'The actual bounded user decision message is required.')
    if not isinstance(source, (str, dict)) or not source or len(encoded(source)) > 8000:
        fail('invalid_decision', 'The actual user decision source is required.')
    scan_secrets(encoded([user_message, source]))
    def perform(state):
        plan = _get_plan(state, plan_id)
        root = _workspace(journal, state, plan['workspace_id'])
        observed, unused = _observe(root, plan['policy'])
        if _digest(observed) != plan['before_manifest_sha256']:
            fail('restore_conflict', 'Product files changed after the restoration plan was prepared.')
        receipt = {'decision_id': uid('decision'), 'plan_id': plan_id, 'plan_sha256': plan['sha256'],
                   'decision': decision, 'user_message': user_message, 'source': source,
                   'sequence': len(state.get('restore_decisions', {})),
                   'provenance': 'caller_recorded_not_identity_authenticated', 'created_at': now()}
        state.setdefault('restore_decisions', {})[receipt['decision_id']] = receipt
        emit(state, 'restore_decision', {'decision_id': receipt['decision_id'], 'plan_id': plan_id, 'decision': decision})
        return receipt
    return journal.transaction(perform)


def _approval(state, plan):
    decisions = [item for item in state.get('restore_decisions', {}).values() if item['plan_id'] == plan['plan_id']]
    decisions.sort(key=lambda item: item['sequence'])
    if not decisions or decisions[-1]['decision'] != 'approve' or decisions[-1]['plan_sha256'] != plan['sha256']:
        fail('restore_approval_required', 'The exact current restoration plan needs an explicit user approval.')
    return decisions[-1]


def _wal_path(journal, plan_id):
    identifier(plan_id, 'plan_id')
    return journal.directory / 'recovery' / (plan_id + '.json')


def _current_hash(path, policy):
    _no_links(path)
    if not path.exists():
        return None
    return sha256(_file_bytes(path, policy['max_file_bytes']))


def _apply_operations(root, operations, policy, contents, wal, wal_path, rollback=False):
    for index, operation in enumerate(operations):
        path = root / _managed_path(operation['path'], policy)
        before_hash = (operation['before'] or {}).get('sha256')
        target_hash = (operation['target'] or {}).get('sha256')
        actual = _current_hash(path, policy)
        if actual not in (before_hash, target_hash):
            fail('recovery_conflict', 'A planned file has an unrelated edit; recovery will not overwrite it.')
        desired = operation['before'] if rollback else operation['target']
        desired_hash = (desired or {}).get('sha256')
        if actual != desired_hash:
            if desired is None:
                _no_links(path)
                path.unlink()
            else:
                raw = contents[operation['path']]
                if sha256(raw) != desired_hash:
                    fail('snapshot_corrupt', 'Recovery contents do not match the fixed plan.')
                _replace_file(path, raw)
        wal['last_operation'] = index
        wal['status'] = 'rolling_back' if rollback else 'applying'
        _atomic_json(wal_path, wal)


def _finish_restore(journal, state, tip, plan, wal, rollback=False):
    root = _workspace(journal, state, plan['workspace_id'])
    if str(root) != plan['root']:
        fail('workspace_mismatch', 'The product root changed after the restoration plan was prepared.')
    target_snapshot_id = wal['pre_snapshot_id'] if rollback else plan['snapshot_id']
    snapshot, contents = _snapshot(journal, state, target_snapshot_id)
    directories = snapshot['manifest']['directories']
    for relative in sorted(directories, key=lambda name: (name.count('/'), name)):
        _no_links(root / relative).mkdir(parents=True, exist_ok=True)
    _apply_operations(root, plan['operations'], plan['policy'], contents, wal, _wal_path(journal, plan['plan_id']), rollback)
    remove_dirs = plan['create_directories'] if rollback else plan['delete_directories']
    for relative in sorted(remove_dirs, key=lambda name: (-name.count('/'), name)):
        path = _no_links(root / relative)
        if path.exists():
            try:
                path.rmdir()
            except OSError:
                fail('recovery_conflict', 'A directory is no longer empty; it was not removed.')
    observed, unused = _observe(root, plan['policy'])
    expected = copy.deepcopy(snapshot['manifest'])
    expected['exclusions'] = plan['before_manifest']['exclusions']
    if not rollback:
        preserved = set(plan['preserved_paths'])
        expected['files'] += [item for item in plan['before_manifest']['files'] if item['path'] in preserved]
        expected['files'].sort(key=lambda item: item['path'])
        expected['directories'] = sorted(set(expected['directories']) | {
            directory for directory in plan['before_manifest']['directories'] if directory not in plan['delete_directories']})
    if _digest(observed) != _digest(expected):
        fail('recovery_conflict', 'The resulting managed file tree differs from the approved recovery scope.')
    post = _capture(journal, state, plan['workspace_id'], 'restoration result', plan['policy'])
    result = {'plan_id': plan['plan_id'], 'plan_sha256': plan['sha256'], 'status': 'rolled_back' if rollback else 'restore_verified',
              'pre_snapshot_id': wal['pre_snapshot_id'], 'post_snapshot_id': post['snapshot_id'],
              'request_id': wal['request_id'], 'preserved_paths': plan['preserved_paths'],
              'verification_required': True, 'created_at': now()}
    state.setdefault('restore_receipts', {})[plan['plan_id']] = result
    state.setdefault('restore_recoveries', {})[plan['plan_id']] = {'status': result['status']}
    _remember(state, wal['request_id'], wal['request_signature'], result)
    emit(state, 'source_restored', result)
    journal._commit(state, tip)
    wal['status'] = 'rolled_back' if rollback else 'completed'
    _atomic_json(_wal_path(journal, plan['plan_id']), wal)
    return result


def apply_restore(journal, plan_id, request_id):
    identifier(request_id, 'request_id')
    journal._require()
    with journal._lock():
        tip = journal._tip()
        state = journal._read_tip(tip)
        plan = _get_plan(state, plan_id)
        signature = sha256(encoded(['apply_restore', plan_id, plan['sha256']]))
        saved = _request(state, request_id, signature)
        if saved is not None:
            path = _wal_path(journal, plan_id)
            if path.exists():
                wal = json.loads(path.read_bytes())
                wal['status'] = 'rolled_back' if saved['status'] == 'rolled_back' else 'completed'
                _atomic_json(path, wal)
            return saved
        journal._check_recovery()
        _approval(state, plan)
        root = _workspace(journal, state, plan['workspace_id'])
        if str(root) != plan['root']:
            fail('workspace_mismatch', 'The registered product root changed after planning.')
        observed, unused = _observe(root, plan['policy'])
        if _digest(observed) != plan['before_manifest_sha256']:
            fail('restore_conflict', 'Product files changed after the restoration plan was approved.')
        pre = _capture(journal, state, plan['workspace_id'], 'before source restoration', plan['policy'])
        if pre['manifest_sha256'] != plan['before_manifest_sha256']:
            fail('restore_conflict', 'Product files changed while the pre-restore capture was prepared.')
        # Publish recovery bytes before any product write. Git tip publication and
        # file replacement cannot be a single transaction.
        tip = journal._commit(state, tip)
        wal = {'plan_id': plan_id, 'plan_sha256': plan['sha256'], 'status': 'prepared',
               'pre_snapshot_id': pre['snapshot_id'], 'request_id': request_id,
               'request_signature': signature, 'last_operation': -1, 'created_at': now()}
        _atomic_json(_wal_path(journal, plan_id), wal)
        try:
            return _finish_restore(journal, state, tip, plan, wal)
        except BaseException:
            wal['status'] = 'recovery_required'
            _atomic_json(_wal_path(journal, plan_id), wal)
            raise


def reconcile_recovery(journal, plan_id, action):
    if action not in ('status', 'resume', 'rollback'):
        fail('invalid_recovery_action', 'Use status, resume, or rollback.')
    journal._require()
    path = _wal_path(journal, plan_id)
    if not path.exists():
        fail('recovery_not_found', 'No file recovery journal exists for this plan.')
    if action == 'status':
        _no_links(path)
        return json.loads(path.read_bytes())
    with journal._lock():
        _no_links(path)
        wal = json.loads(path.read_bytes())
        state = journal._read_tip(journal._tip())
        if wal['status'] in ('completed', 'rolled_back'):
            return state.get('restore_receipts', {}).get(plan_id, wal)
        plan = _get_plan(state, plan_id)
        if wal['plan_sha256'] != plan['sha256']:
            fail('recovery_corrupt', 'The recovery journal does not match the approved plan.')
        _approval(state, plan)
        saved = _request(state, wal['request_id'], wal['request_signature'])
        if saved is not None:
            wal['status'] = 'rolled_back' if saved['status'] == 'rolled_back' else 'completed'
            _atomic_json(path, wal)
            return saved
        try:
            return _finish_restore(journal, state, journal._tip(), plan, wal, rollback=action == 'rollback')
        except BaseException:
            wal['status'] = 'recovery_required'
            _atomic_json(path, wal)
            raise
