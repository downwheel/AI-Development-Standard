"""Exact cooperative scope contracts and deterministic review presentation.

Checks protect mediated actions and detect later drift; they are not OS isolation.
"""
from __future__ import annotations
import fnmatch
import os
import re
from pathlib import Path
from .common import encoded, fail, safe_relative, sha256


def _s(maximum=1000):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


def _o(properties, required=None, additional=False):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": additional}


def _a(items, minimum=0, maximum=10000):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


ID = {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,95}$", "minLength": 1, "maxLength": 96}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
REF = _o({"artifact_id": ID, "revision_id": ID, "sha256": HASH})
BASELINE = _o({"before_sha256": HASH, "expected_absent": {"type": "boolean"}}, [])
FILE = _o({"path": _s(512), "layer": _s(80), "action": {"type": "string", "enum": ["create", "modify", "delete"]},
           "reason": _s(10000), "requirement_ids": _a(ID, 1, 100), "case_ids": _a(ID, 1, 100),
           "required": {"type": "boolean"}, "before_sha256": HASH, "expected_absent": {"type": "boolean"}, "rename_id": ID},
          ["path", "layer", "action", "reason", "requirement_ids", "case_ids", "required"])
DB_OBJECT = _o({"target_ref": _s(512), "schema": _s(128), "object_type": _s(80), "name": _s(128), "action": _s(80),
                "table": _s(128), "db_work_id": ID, "baseline": _o({}, [], True)},
               ["target_ref", "schema", "object_type", "name", "action", "db_work_id", "baseline"])
GENERATED = _o({"generator": _s(1000), "version": _s(100), "input_sha256": HASH, "output_root": _s(512),
                "patterns": _a(_s(512), 1, 20), "actions": _a({"type": "string", "enum": ["create", "modify", "delete"]}, 1, 3),
                "max_files": {"type": "integer", "minimum": 1, "maximum": 10000},
                "max_bytes": {"type": "integer", "minimum": 1, "maximum": 67108864}})
SCOPE_SCHEMA = _o({"run_id": ID, "workspace_id": ID, "unit_id": ID, "unit_ref": REF, "requirement_ids": _a(ID, 1, 100),
                    "mode": {"type": "string", "enum": ["change", "observe"]}, "reason": _s(10000),
                    "source_baseline": _o({"snapshot_id": ID, "sha256": HASH}, ["sha256"]),
                    "files": _a(FILE), "db_objects": _a(DB_OBJECT, maximum=1000), "generated_files": _a(GENERATED, maximum=100),
                    "environment_refs": _a(REF, maximum=20), "db_plan_refs": _a(REF, maximum=100),
                    "scratch": _a(_o({"purpose": _s(1000), "root_id": ID, "lifetime": _s(1000), "max_files": {"type": "integer", "minimum": 1, "maximum": 10000}, "max_bytes": {"type": "integer", "minimum": 1, "maximum": 67108864}}), maximum=100)},
                   ["run_id", "workspace_id", "unit_id", "unit_ref", "requirement_ids", "mode", "source_baseline", "files", "db_objects"])
ENVIRONMENT_CONTRACT_SCHEMA = _o({"unit_ref": REF, "profile_id": ID, "profile_revision": _s(200), "target_revision": _s(200),
                                  "roles": _a(ID, 1, 20), "probe_receipt_id": ID, "role_probe_receipts": _o({}, [], True), "target_ref": _s(512)},
                                 ["unit_ref", "profile_id", "profile_revision", "target_revision", "roles"])
APPLICABILITY = _o({"required": {"type": "boolean"}, "reason": _s(10000)}, ["required"])
UNIT_GRAPH = _a(_o({"unit_id": ID, "title": _s(1000), "required": {"type": "boolean"}, "depends_on": _a(ID, maximum=100),
                     "requirement_ids": _a(ID, 1, 100), "case_ids": _a(ID, 1, 100),
                     "integration": {"type": "boolean"}},
                    ["unit_id", "title", "required", "depends_on", "requirement_ids", "case_ids"]), 1, 100)


def _path(path):
    parts = safe_relative(path).parts
    if path == '.' or any(part.casefold() in {'.git', '.hg', '.svn', 'node_modules', '.venv', 'venv'} for part in parts):
        fail('scope_path_forbidden', 'Source scope cannot include metadata, dependencies, or the whole root.')
    if any(part.casefold() == '.env' or part.casefold().startswith('.env.') and part.casefold() not in {'.env.example', '.env.template', '.env.sample'} for part in parts):
        fail('scope_path_forbidden', 'Personal secret files must not enter source scope.')
    return parts


def validate_scope(payload):
    from .workflow import validate
    validate(payload, SCOPE_SCHEMA, 'scope-manifest')
    names = [f['path'].casefold() for f in payload['files']]
    if len(names) != len(set(names)):
        fail('duplicate_scope_path', 'Scope contains duplicate or case-colliding paths.')
    if payload['mode'] == 'change' and not any((payload['files'], payload['db_objects'], payload.get('generated_files'))):
        fail('empty_scope', 'A changing unit requires exact file, DB, or bounded generated scope.')
    if payload['mode'] == 'observe':
        if not payload.get('reason') or any((payload['files'], payload['db_objects'], payload.get('generated_files'))):
            fail('invalid_observation_scope', 'Observation requires a reason and no declared writes.')
    renames = {}
    for item in payload['files']:
        _path(item['path'])
        if not set(item['requirement_ids']) <= set(payload['requirement_ids']):
            fail('missing_coverage', 'Scope file references requirements outside the unit.')
        if item['action'] == 'create':
            if item.get('expected_absent') is not True or 'before_sha256' in item:
                fail('invalid_scope_baseline', 'Create requires expected_absent true and no before hash.')
        elif 'before_sha256' not in item or 'expected_absent' in item:
            fail('invalid_scope_baseline', 'Modify/delete requires the original before hash.')
        if item.get('rename_id'):
            renames.setdefault(item['rename_id'], []).append(item)
    for rows in renames.values():
        if len(rows) != 2 or {row['action'] for row in rows} != {'create', 'delete'}:
            fail('invalid_rename', 'Rename must explicitly pair one create and one delete.')
    roots = []
    for group in payload.get('generated_files', []):
        _path(group['output_root'])
        root = group['output_root'].casefold()
        if any(root == previous or root.startswith(previous + '/') or previous.startswith(root + '/') for previous in roots):
            fail('overlapping_generated_scope', 'Generated output roots must be distinct and bounded.')
        roots.append(root)
        for pattern in group['patterns']:
            if pattern.startswith('/') or '\\' in pattern or ':' in pattern or '..' in pattern.split('/') or pattern in {'*', '**', '**/*'}:
                fail('unbounded_generated_scope', 'Generated patterns must name bounded output types or paths.')
    objects = [(row['target_ref'].casefold(), row['schema'].casefold(), row['object_type'].casefold(), row.get('table', '').casefold(), row['name'].casefold(), row['action']) for row in payload['db_objects']]
    if len(objects) != len(set(objects)):
        fail('duplicate_db_scope', 'DB scope contains duplicate object actions.')
    return payload


def validate_units(units, requirements):
    from .workflow import validate
    validate(units, UNIT_GRAPH, 'system-design.units')
    ids = [unit['unit_id'] for unit in units]
    if len(ids) != len(set(ids)):
        fail('duplicate_unit', 'System design contains duplicate units.')
    known = {row['id']: set(row['case_ids']) for row in requirements}
    graph = {unit['unit_id']: unit['depends_on'] for unit in units}
    coverage, cases = set(), set()
    for unit in units:
        if any(len(unit[key]) != len(set(unit[key])) for key in ('requirement_ids', 'case_ids')):
            fail('duplicate_unit_coverage', 'Unit requirements and case identifiers must be unique.')
        if len(unit['depends_on']) != len(set(unit['depends_on'])) or not set(unit['depends_on']) <= set(ids):
            fail('unknown_unit_dependency', 'Unit dependency is unknown or duplicated.')
        if not set(unit['requirement_ids']) <= set(known):
            fail('missing_coverage', 'System unit refers to an unknown requirement.')
        allowed = set().union(*(known[req] for req in unit['requirement_ids']))
        if not set(unit['case_ids']) <= allowed:
            fail('missing_coverage', 'System unit cases lack requirement provenance.')
        if unit['required']:
            coverage.update(unit['requirement_ids']); cases.update(unit['case_ids'])
            if any(not next(row for row in units if row['unit_id'] == dep)['required'] for dep in unit['depends_on']):
                fail('optional_dependency', 'A required unit cannot depend on an optional unit.')
    if coverage != set(known) or cases != set().union(*known.values()):
        fail('missing_coverage', 'Required work units must cover every requirement and acceptance case.')
    visiting, visited = set(), set()
    def visit(name):
        if name in visiting:
            fail('cyclic_units', 'System unit dependencies contain a cycle.')
        if name in visited:
            return
        visiting.add(name)
        for dependency in graph[name]:
            visit(dependency)
        visiting.remove(name); visited.add(name)
    for name in ids:
        visit(name)


def _observe(root, relative):
    target = root.joinpath(*_path(relative))
    if not target.resolve().is_relative_to(root):
        fail('scope_path_escape', 'Scope path resolves outside the workspace.')
    for part in [target, *target.parents]:
        if part == root.parent:
            break
        if part.exists() and (part.is_symlink() or getattr(part.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400):
            fail('scope_reparse', 'Scope paths cannot traverse symlinks or reparse points.')
    if not target.exists():
        return None
    if not target.is_file() or target.stat().st_size > 8 * 1024 * 1024:
        fail('scope_file_unsupported', 'Scope file is not a bounded regular source file.')
    return sha256(target.read_bytes())


def preflight_scope(payload, workspace_root, *, run_id=None, workspace_id=None, unit_id=None, source_digest=None):
    validate_scope(payload)
    for key, expected in [('run_id', run_id), ('workspace_id', workspace_id), ('unit_id', unit_id)]:
        if expected is not None and payload[key] != expected:
            fail('scope_mismatch', 'Scope does not identify the selected run, workspace, and unit.')
    if source_digest is not None and payload['source_baseline']['sha256'] != source_digest:
        fail('scope_baseline_changed', 'Workspace snapshot no longer matches the presented source baseline.')
    root = Path(workspace_root).resolve()
    observed = {}
    for item in payload['files']:
        actual = _observe(root, item['path'])
        expected = None if item['action'] == 'create' else item['before_sha256']
        if actual != expected:
            fail('scope_baseline_changed', 'A scoped file differs from the presented baseline; preserve it and revise the contract.')
        observed[item['path']] = actual
    return {'passed': True, 'observed_files': observed, 'source_digest': source_digest, 'mode': payload['mode']}


def _index(files):
    if isinstance(files, dict):
        return {path: {'path': path, 'sha256': value} if isinstance(value, str) else value for path, value in files.items()}
    return {row['path']: row for row in files}


def compare_scope(payload, before_files, after_files):
    validate_scope(payload)
    before, after = _index(before_files), _index(after_files)
    declared = {item['path']: item for item in payload['files']}
    changed = [path for path in sorted(set(before) | set(after)) if before.get(path, {}).get('sha256') != after.get(path, {}).get('sha256')]
    violations, changes, used = [], [], {}
    for path in changed:
        action = 'create' if path not in before else 'delete' if path not in after else 'modify'
        row = {'path': path, 'action': action}
        changes.append(row)
        if path in declared:
            if declared[path]['action'] != action:
                violations.append({**row, 'reason': 'action_mismatch', 'expected': declared[path]['action']})
            continue
        matches = []
        for i, group in enumerate(payload.get('generated_files', [])):
            prefix = group['output_root'] + '/'
            if path.startswith(prefix) and any(fnmatch.fnmatchcase(path[len(prefix):], pattern) for pattern in group['patterns']):
                matches.append((i, group))
        if len(matches) != 1 or action not in matches[0][1]['actions']:
            violations.append({**row, 'reason': 'outside_scope'})
        else:
            i, group = matches[0]
            totals = used.setdefault(i, {'files': 0, 'bytes': 0})
            totals['files'] += 1
            actual_file = after.get(path, before.get(path, {}))
            size = actual_file.get('size', actual_file.get('bytes'))
            if type(size) is not int:
                violations.append({**row, 'reason': 'generated_size_unobserved'})
            else:
                totals['bytes'] += size
    for i, totals in used.items():
        group = payload['generated_files'][i]
        if totals['files'] > group['max_files'] or totals['bytes'] > group['max_bytes']:
            violations.append({'reason': 'generated_budget_exceeded', 'output_root': group['output_root'], **totals})
    missing = [item['path'] for item in payload['files'] if item['required'] and item['path'] not in changed]
    return {'passed': not violations and not missing, 'changes': changes, 'violations': violations, 'missing_required': missing,
            'counts': {action: sum(row['action'] == action for row in changes) for action in ['create', 'modify', 'delete']},
            'generated_totals': {str(i): value for i, value in used.items()}}


def render_scope(payload):
    validate_scope(payload)
    def cell(value):
        return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ')
    lines = ['## 승인 대상 변경 범위', '', '| 계층 | 경로 | 작업 | 필수 | 이유 |', '|---|---|---|---|---|']
    for item in payload['files']:
        lines.append('| ' + ' | '.join(cell(item[key]) for key in ['layer', 'path', 'action', 'required', 'reason']) + ' |')
    lines += ['', '| DB 대상 | 스키마 | 종류 | 테이블 | 객체 | 작업 | 계획 |', '|---|---|---|---|---|---|---|']
    for item in payload['db_objects']:
        lines.append('| ' + ' | '.join(cell(item.get(key, '')) for key in ['target_ref', 'schema', 'object_type', 'table', 'name', 'action', 'db_work_id']) + ' |')
    lines += ['', '파일: ' + str(len(payload['files'])) + ', DB 객체 작업: ' + str(len(payload['db_objects'])) + ', 생성 그룹: ' + str(len(payload.get('generated_files', []))),
              '범위 모드: ' + payload['mode'], '원본 기준 SHA-256: ' + payload['source_baseline']['sha256']]
    lines += ['', '| 계층별 파일 합계 | create | modify | delete |', '|---|---|---|---|']
    for layer in sorted({item['layer'] for item in payload['files']}):
        lines.append('| ' + cell(layer) + ' | ' + ' | '.join(str(sum(item['layer'] == layer and item['action'] == action for item in payload['files'])) for action in ['create', 'modify', 'delete']) + ' |')
    if payload.get('generated_files'):
        lines += ['', '| 생성기 | 버전 | 출력 루트 | 패턴 | 파일 상한 | 바이트 상한 |', '|---|---|---|---|---|---|']
        for item in payload['generated_files']:
            lines.append('| ' + ' | '.join(cell(item[key]) for key in ['generator', 'version', 'output_root', 'patterns', 'max_files', 'max_bytes']) + ' |')
    return '\n'.join(lines) + '\n'


check_before = preflight_scope
check_after = compare_scope
