"""External project bindings: never writes a marker into the product tree."""
from __future__ import annotations
import json
import os
import contextlib
from pathlib import Path
import stat
import tempfile
import threading
import time
from .common import HarnessError, encoded, fail, identifier, now, overlap, sha256

_THREAD_LOCKS = {}
_THREAD_LOCKS_GUARD = threading.Lock()

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(encoded(value)); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def _reject_links(raw):
    for part in [raw, *raw.parents]:
        if part.exists():
            info = part.lstat()
            if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
                fail('linked_root', 'Root paths through links or reparse points are unsupported.')

def normal_root(value, create=False):
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        fail('invalid_root', 'An absolute directory path is required.')
    _reject_links(raw)
    if create:
        raw.mkdir(parents=True, exist_ok=True)
    if not raw.is_dir():
        fail('missing_root', 'Project directory does not exist; explicitly request create_root for a new folder.')
    return raw.resolve()

class Registry:
    def __init__(self, state_root, standard_root):
        state_path, standard_path = Path(state_root).expanduser(), Path(standard_root).expanduser()
        if not state_path.is_absolute() or not standard_path.is_absolute():
            fail('invalid_root', 'Registry and standard roots must be absolute.')
        _reject_links(state_path); _reject_links(standard_path)
        self.state_root = state_path.resolve()
        self.standard_root = standard_path.resolve()
        if overlap(self.state_root, self.standard_root):
            fail('overlapping_roots', 'Personal state and shared standard must be separate roots.')

    @contextlib.contextmanager
    def _lock(self):
        """Serialize root registration across threads/processes; reads take no lock."""
        directory = normal_root(self.state_root / 'registry', create=True)
        lock_path = directory / '.lock'
        _reject_links(lock_path)
        key = os.path.normcase(str(lock_path))
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.Lock())
        if not thread_lock.acquire(timeout=10):
            fail('registry_busy', 'Registry is being updated; retry the same registration.')
        handle = None
        locked = False
        try:
            handle = open(lock_path, 'a+b')
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            deadline = time.monotonic() + 10
            while True:
                try:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        fail('registry_busy', 'Registry is being updated; retry the same registration.')
                    time.sleep(0.05)
            yield
        finally:
            if handle is not None:
                if locked:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
            thread_lock.release()

    @staticmethod
    def _read_record(path):
        _reject_links(path)
        try:
            if path.stat().st_size > 256 * 1024:
                fail('registry_corrupt', 'Oversized registry record.')
            row = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(row, dict):
                fail('registry_corrupt', 'Registry record must be an object.')
            return row
        except (OSError, ValueError):
            fail('registry_corrupt', 'Registry record is unreadable or invalid JSON.')

    def _bindings(self):
        folder = self.state_root / 'registry'
        if not folder.exists():
            return []
        rows = []
        for path in sorted(folder.glob('project-*.json')):
            row = self._read_record(path)
            if not all(isinstance(row.get(k), str) and row[k] for k in ('project_id','workspace_id','project_root','name')):
                fail('registry_corrupt', 'Project binding is missing required fields.')
            identifier(row['project_id']); identifier(row['workspace_id'])
            if path.name != row['project_id'] + '.json' or not Path(row['project_root']).is_absolute():
                fail('registry_corrupt', 'Project binding identity is inconsistent.')
            rows.append(row)
        return rows

    def list_projects(self):
        return self._bindings()

    def register(self, project_root, name, create_root=False):
        # Check containment before any mkdir so a rejected registration has no product writes.
        candidate = Path(project_root).expanduser()
        if not candidate.is_absolute():
            fail('invalid_root', 'An absolute project root is required.')
        if overlap(candidate, self.state_root) or overlap(candidate, self.standard_root):
            fail('overlapping_roots', 'Product, shared standard, and private history must not overlap.')
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            fail('invalid_name', 'Project name must contain 1-200 characters.')
        if type(create_root) is not bool:
            fail('invalid_input', 'create_root must be a boolean.')
        # Check paths before creating a user-requested new directory.
        _reject_links(candidate)
        if not candidate.is_dir() and not create_root:
            fail('missing_root', 'Project directory does not exist; explicitly request create_root for a new folder.')
        with self._lock():
            return self._register_locked(candidate, name.strip(), create_root)

    def _register_locked(self, candidate, name, create_root):
        root = candidate.resolve()
        project_id = 'project-' + sha256(str(root).casefold().encode('utf-8'))[:20]
        existing = self._bindings()
        for row in existing:
            if row['project_id'] == project_id:
                if Path(row['project_root']).resolve() != root:
                    fail('registry_collision', 'Project binding collision.')
                self.journal(project_id).read()
                pending_path = self.state_root / 'registry' / 'registrations' / (project_id + '.json')
                if pending_path.exists():
                    pending = self._read_record(pending_path)
                    if pending.get('binding') != row:
                        fail('registration_conflict', 'Binding conflicts with its pending registration receipt.')
                    if pending.get('phase') != 'bound':
                        pending.update({'phase': 'bound', 'bound_at': now()})
                        atomic_json(pending_path, pending)
                return row
            if overlap(root, row['project_root']):
                fail('overlapping_projects', 'Nested registered products are not supported; register a single solution root.')
        pending_folder = self.state_root / 'registry' / 'registrations'
        _reject_links(pending_folder)
        pending_path = pending_folder / (project_id + '.json')
        pending = None
        if pending_folder.exists():
            for path in sorted(pending_folder.glob('project-*.json')):
                record = self._read_record(path)
                if record.get('schema_version') != 1 or record.get('phase') not in {'prepared','journal_ready','bound'} or not isinstance(record.get('binding'), dict):
                    fail('registry_corrupt', 'Invalid pending registration record.')
                other = record['binding']
                if not isinstance(other.get('project_root'), str) or not Path(other['project_root']).is_absolute() or not isinstance(other.get('project_id'), str):
                    fail('registry_corrupt', 'Invalid pending registration identity.')
                if other['project_id'] == project_id:
                    if path != pending_path or Path(other['project_root']).resolve() != root:
                        fail('registry_collision', 'Pending registration identity conflicts.')
                    pending = record
                elif overlap(root, other['project_root']):
                    fail('overlapping_projects', 'Another pending or registered product overlaps this root.')
        root = normal_root(root, create=create_root)
        from .history import Journal
        release = self._release()
        row = {'project_id': project_id, 'workspace_id': 'workspace-main', 'project_root': str(root), 'name': name, 'registered_at': now(),
               'standard_root': str(self.standard_root), 'standard_release': release}
        if pending is not None:
            saved = pending['binding']
            if saved.get('workspace_id') != 'workspace-main' or saved.get('standard_root') != str(self.standard_root) or saved.get('standard_release') != release:
                fail('registration_conflict', 'Pending registration belongs to a different workspace, standard root, or release.')
            row = saved
        state = {'schema_version': 2, 'project': {'project_id': project_id, 'name': row['name'], 'standard_root': str(self.standard_root), 'standard_release': release},
                 'workspaces': {'workspace-main': {'root': str(root)}}, 'events': []}
        for key in ['runs','stages','artifacts','heads','reviews','decisions','changes','implementations','verification','snapshots','leases','requests']:
            state[key] = {}
        journal = Journal(self.state_root / 'projects' / project_id / 'history.git')
        if pending is None:
            pending = {'schema_version': 1, 'phase': 'prepared', 'binding': row, 'created_at': now()}
            atomic_json(pending_path, pending)
        if journal.path.exists() and any(journal.path.iterdir()):
            try:
                saved_state = journal.read()
            except (HarnessError, OSError, ValueError):
                fail('registration_recovery_required', 'Existing journal is incomplete or unreadable; it was preserved for recovery.')
            self._validate_initial_journal(saved_state, row)
            # A legacy crash may predate the pending file. Preserve the journal name.
            row['name'] = saved_state['project']['name']
            pending['binding'] = row
        else:
            journal.initialize(state)
        pending.update({'phase': 'journal_ready', 'journal_ready_at': now()})
        atomic_json(pending_path, pending)
        atomic_json(self.state_root / 'registry' / (project_id + '.json'), row)
        pending.update({'phase': 'bound', 'bound_at': now()})
        atomic_json(pending_path, pending)
        return row

    def _validate_initial_journal(self, state, row):
        project, workspaces = state.get('project', {}), state.get('workspaces', {})
        if (state.get('schema_version') != 2 or project.get('project_id') != row['project_id']
                or project.get('standard_root') != row['standard_root'] or project.get('standard_release') != row['standard_release']
                or not isinstance(project.get('name'), str) or not project['name'].strip()
                or set(workspaces) != {row['workspace_id']} or workspaces[row['workspace_id']].get('root') != row['project_root']):
            fail('registration_conflict', 'Existing journal does not match this initial registration.')
        if any(value not in ({}, []) for key, value in state.items() if key not in {'schema_version','project','workspaces'}):
            fail('registration_conflict', 'Unbound journal has workflow activity; explicit recovery is required.')

    def _release(self):
        return runtime_release()

    def journal(self, project_id):
        identifier(project_id, 'project_id')
        matches = [r for r in self._bindings() if r['project_id'] == project_id]
        if not matches:
            fail('unknown_project', 'Project is not registered in this personal registry.')
        row = matches[0]
        root = normal_root(row['project_root'])
        if overlap(root, self.state_root) or overlap(root, self.standard_root):
            fail('overlapping_roots', 'Registered path now overlaps the standard or personal state.')
        from .history import Journal
        journal = Journal(self.state_root / 'projects' / project_id / 'history.git')
        state = journal.read()
        if (state['project']['project_id'] != project_id or Path(state['workspaces'][row['workspace_id']]['root']).resolve() != root
                or Path(state['project'].get('standard_root', self.standard_root)).resolve() != self.standard_root
                or ('standard_release' in row and state['project'].get('standard_release') != row['standard_release'])):
            fail('registry_corrupt', 'Binding and journal workspace do not match.')
        return journal

    def import_legacy(self, project_id, legacy_path):
        """Preserve old evidence without upgrading it to v2 approvals or source snapshots."""
        journal = self.journal(project_id)
        candidate = Path(legacy_path)
        _reject_links(candidate)
        source = candidate.resolve()
        product = Path(journal.read()['workspaces']['workspace-main']['root'])
        if source != product / '.harness':
            fail('invalid_legacy_path', 'Legacy import must target the registered product .harness directory.')
        if not source.is_dir() or source.is_symlink():
            fail('missing_legacy', 'Legacy .harness directory is unavailable.')
        from .common import emit, scan_secrets
        files = []
        for path in sorted(source.rglob('*')):
            _reject_links(path)
            if source not in path.resolve().parents:
                fail('invalid_legacy_path', 'Legacy file resolves outside the registered source.')
            if not path.is_file() or path.suffix.lower() not in {'.json','.md','.txt'}:
                continue
            if path.stat().st_size > 2 * 1024 * 1024:
                fail('legacy_limit', 'Legacy file exceeds import limit.')
            if len(files) >= 2000:
                fail('legacy_limit', 'Legacy import exceeds file limit.')
            raw = scan_secrets(path.read_bytes())
            files.append({'path': path.relative_to(source).as_posix(), 'sha256':sha256(raw), 'oid':journal.put_blob(raw), 'size':len(raw)})
        if len(files) > 2000:
            fail('legacy_limit', 'Legacy import exceeds file limit.')
        digest = sha256(encoded(files))
        def change(state):
            if digest in state.setdefault('legacy_imports', {}):
                return state['legacy_imports'][digest]
            receipt = {'import_id':digest, 'at':now(), 'files':files, 'provenance':'legacy-v1-unverified', 'v2_approvals_created':False, 'source_snapshots_created':False}
            state['legacy_imports'][digest] = receipt
            emit(state, 'legacy_imported', {'import_id':digest, 'file_count':len(files)})
            return receipt
        return journal.transaction(change)


def runtime_release():
    """Identity of executing code, independent of the shared source boundary."""
    path = Path(__file__).resolve().parents[1] / 'release-manifest.json'
    if path.exists():
        manifest = Registry._read_record(path)
        release_id = manifest.get('release_id')
        if not isinstance(release_id, str) or not release_id or len(release_id) > 200:
            fail('invalid_release', 'Executing runtime manifest has no valid release ID.')
        return release_id
    from . import VERSION
    return 'development-'+VERSION
