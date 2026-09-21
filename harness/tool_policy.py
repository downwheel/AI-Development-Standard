"""Versioned external-tool evidence contracts without provider credentials or I/O.

Evidence is caller/runner supplied provenance, not provider attestation. Gate checks
pin substantive observations; completion additionally pins actual runner blobs.
"""
from __future__ import annotations

from datetime import datetime
import html
import json
import re
from urllib.parse import parse_qsl, urlsplit

from .common import fail, sha256
from .validation import validate

POLICY_VERSION = '1'
CAPABILITIES = ('ui_design', 'library_docs', 'browser', 'database')


def _s(maximum=4000):
    return {'type': 'string', 'minLength': 1, 'maxLength': maximum}


def _o(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required,
            'additionalProperties': False}


def _a(items, minimum=0, maximum=100):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}


ID = {'type': 'string', 'pattern': '^[a-z0-9][a-z0-9_-]{0,95}$', 'maxLength': 96}
CAPABILITY = {'type': 'string', 'enum': list(CAPABILITIES)}
TRUE = {'type': 'boolean', 'enum': [True]}
TOOL_PLAN_SCHEMA = _a(_o({
    'capability': CAPABILITY,
    'mode': {'type': 'string', 'enum': ['required', 'preferred', 'local_only', 'not_applicable']},
    'reason': _s(), 'unit_ids': _a(ID),
}), 4, 4)
FAILURE_SCHEMA = _o({
    'code': {'type': 'string', 'enum': [
        'account_required', 'permission_denied', 'quota_exceeded', 'rate_limited', 'timeout',
        'service_unavailable', 'unsupported_version', 'unsupported_library', 'tool_unavailable',
    ]},
    'tool': _s(200), 'detail': _s(),
})
OBSERVATION_SCHEMA = _o({
    'capability': CAPABILITY, 'provider': _s(100), 'tool': _s(200),
    'status': {'type': 'string', 'enum': ['success', 'fallback', 'blocked']},
    'observed_at': _s(80), 'target': _s(1000), 'summary': _s(10000),
    'source_refs': _a(_s(4000), 1),
    'result': {'type': 'object'}, 'failure': FAILURE_SCHEMA,
}, ['capability', 'provider', 'tool', 'status', 'observed_at', 'target', 'summary', 'source_refs', 'result'])
TOOL_OBSERVATIONS_SCHEMA = _a(OBSERVATION_SCHEMA)
TOOL_CHECKS_SCHEMA = _a(_o({
    'capability': {'type': 'string', 'enum': ['browser', 'database']},
    'check_id': ID, 'evidence_id': ID,
}))
SOURCE = _o({'url': _s(), 'title': _s(1000)})
LOCAL_TYPE_CHECK = _o({'checked': TRUE, 'detail': _s()})
DOC_RESULT = _o({
    'library': _s(200), 'version': _s(200), 'sources': _a(SOURCE, 1),
    'version_checked': TRUE, 'library_id': _s(500),
    'local_type_check': LOCAL_TYPE_CHECK, 'scope': {'type': 'string', 'enum': ['openai']},
    'scope_reason': _s(),
}, ['library', 'version', 'sources', 'version_checked'])
FIGMA_RESULT = _o({
    'file_key': _s(200), 'node_ids': _a(_s(100), 1),
    'structure_checked': TRUE, 'screenshot_checked': TRUE,
})
LOCAL_DESIGN_RESULT = _o({
    'report_markdown': _s(30000), 'layout_content': _s(50000), 'user_choice': _s(10000),
}, ['report_markdown', 'layout_content'])
ASSERTION = _o({'name': _s(200), 'expected': _s(), 'observed': _s(), 'passed': TRUE})
DB_RESULT = _o({
    'engine': _s(100), 'target_ref': _s(1000),
    'connection_mode': {'type': 'string', 'enum': ['live']},
    'observation_kind': {'type': 'string', 'enum': ['catalog', 'readback']},
    'read_only': TRUE, 'rows_observed': {'type': 'integer', 'minimum': 0, 'maximum': 1000000000},
    'objects': _a(_s(500)), 'checks': _a(ASSERTION, 1),
})
BROWSER_RESULT = _o({
    'url': _s(), 'engine': _s(100), 'browser_session': _s(200),
    'connection_mode': {'type': 'string', 'enum': ['live']},
    'interaction_count': {'type': 'integer', 'minimum': 1, 'maximum': 1000000},
    'checks': _a(ASSERTION, 1),
})
COMPLETION_EVIDENCE_SCHEMA = _o({
    'tool_policy_version': {'type': 'string', 'enum': [POLICY_VERSION]},
    'capability': {'type': 'string', 'enum': ['browser', 'database']},
    'build_id': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
    'run_id': ID, 'observation': OBSERVATION_SCHEMA,
})


def validate_plan(plan, units):
    """Validate exact capability coverage against the pinned system unit graph."""
    validate(plan, TOOL_PLAN_SCHEMA, 'tool_plan')
    known = {row['unit_id'] for row in units}
    by_capability = {row['capability']: row for row in plan}
    if set(by_capability) != set(CAPABILITIES):
        fail('invalid_tool_plan', 'tool_plan must contain each of the four capabilities exactly once.')
    for row in plan:
        assigned = row['unit_ids']
        if len(assigned) != len(set(assigned)) or not set(assigned) <= known:
            fail('invalid_tool_plan', 'Tool unit assignments must be unique known system units.')
        if not row['reason'].strip():
            fail('invalid_tool_plan', 'Every capability requires a substantive applicability reason.')
        if row['mode'] == 'not_applicable':
            if assigned:
                fail('invalid_tool_plan', 'A non-applicable capability cannot assign units.')
        elif not assigned:
            fail('invalid_tool_plan', 'Applicable capabilities require at least one unit.')
        if row['capability'] != 'ui_design' and row['mode'] not in ('required', 'not_applicable'):
            fail('invalid_tool_plan', 'Only UI design permits preferred or user-selected local-only modes.')
    ui = by_capability['ui_design']
    browser = by_capability['browser']
    if ui['mode'] != 'not_applicable' and (browser['mode'] != 'required' or not set(ui['unit_ids']) <= set(browser['unit_ids'])):
        fail('invalid_tool_plan', 'Every UI unit requires browser verification coverage.')


def _url(value):
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        fail('invalid_tool_source', 'Evidence URL is malformed.')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        fail('invalid_tool_source', 'Evidence URLs require HTTP(S) and cannot contain credentials.')
    credential_key = r'(?:token|password|secret|api.?key|authorization|credential|signature|session|(?:^|[-_])sig(?:$|[-_])|(?:^|[-_])auth(?:$|[-_]))'
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    # Ordinary documentation anchors remain valid; OAuth-style fragment values do not.
    fragment_pairs = parse_qsl(parsed.fragment, keep_blank_values=True) if '=' in parsed.fragment else []
    if any(re.search(credential_key, key, re.I) for key, _ in query_pairs + fragment_pairs):
        fail('invalid_tool_source', 'Evidence URLs cannot contain credential parameters.')


def _source(value):
    if re.fullmatch(r'artifact:[a-z0-9][a-z0-9_-]{0,95}/[a-z0-9][a-z0-9_-]{0,95}/[0-9a-f]{64}', value):
        return
    _url(value)


def _failure(row, preferred=None):
    failure = row.get('failure')
    if not failure or not failure['detail'].strip():
        fail('tool_failure_required', 'A blocked or fallback observation requires the actual tool failure or availability finding.')
    if preferred and preferred not in failure['tool'].casefold():
        fail('invalid_tool_fallback', 'Fallback must record the preferred provider failure or unavailable capability.')


def _real_provider(row):
    if re.search(r'(?:mock|fake|stub|simulat)', row['provider'] + ' ' + row['tool'], re.I):
        fail('invalid_tool_observation', 'Mock or simulated tool observations cannot satisfy live evidence.')


def validate_observations(observations):
    """Validate substantive, typed results while allowing recorded blocked drafts."""
    validate(observations, TOOL_OBSERVATIONS_SCHEMA, 'tool_observations')
    for row in observations:
        for key in ('provider', 'tool', 'target', 'summary'):
            if not row[key].strip():
                fail('invalid_tool_observation', 'Tool provenance fields cannot be blank.')
        try:
            when = datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
            if when.utcoffset() is None:
                raise ValueError('timezone required')
        except ValueError:
            fail('invalid_tool_observation', 'observed_at must be an ISO timestamp with timezone.')
        for ref in row['source_refs']:
            _source(ref)
        status, capability, provider = row['status'], row['capability'], row['provider']
        if status == 'blocked':
            _failure(row)
            if row['result']:
                fail('invalid_tool_observation', 'Blocked observations cannot claim a completed result.')
            continue
        if status == 'success' and 'failure' in row:
            fail('invalid_tool_observation', 'A success cannot also claim fallback failure.')
        if capability == 'library_docs':
            validate(row['result'], DOC_RESULT, 'tool_observation.result')
            for source in row['result']['sources']:
                _url(source['url'])
            if status == 'fallback':
                if provider != 'official-docs' or 'local_type_check' not in row['result']:
                    fail('invalid_tool_fallback', 'Documentation fallback requires official-docs and a recorded local API/type check.')
                if row['result'].get('scope') == 'openai':
                    if not row['result'].get('scope_reason', '').strip() or any(not _openai_source(source['url']) for source in row['result']['sources']):
                        fail('invalid_tool_fallback', 'OpenAI documentation fallback requires explicit scope and official OpenAI sources.')
                    _failure(row, 'openai-docs')
                else:
                    _failure(row, 'context7')
            elif provider == 'context7':
                if not row['result'].get('library_id'):
                    fail('invalid_tool_observation', 'Context7 evidence requires its resolved library_id.')
            elif provider == 'openai-docs':
                if row['result'].get('scope') != 'openai' or not row['result'].get('scope_reason', '').strip():
                    fail('invalid_tool_observation', 'OpenAI Docs evidence requires explicit OpenAI scope and its reason.')
                if any(not _openai_source(source['url']) for source in row['result']['sources']):
                    fail('invalid_tool_observation', 'OpenAI Docs evidence requires official OpenAI sources.')
            else:
                fail('invalid_tool_observation', 'Documentation requires Context7, scoped OpenAI Docs, or recorded official-document fallback.')
        elif capability == 'ui_design':
            if provider == 'figma' and status == 'success':
                validate(row['result'], FIGMA_RESULT, 'tool_observation.result')
            elif provider == 'local-design':
                validate(row['result'], LOCAL_DESIGN_RESULT, 'tool_observation.result')
                if status == 'fallback':
                    _failure(row, 'figma')
                elif not row['result'].get('user_choice', '').strip():
                    fail('invalid_tool_observation', 'Local-only design requires the actual user choice.')
            else:
                fail('invalid_tool_observation', 'UI evidence requires inspected Figma nodes or a concrete local design.')
        elif capability in ('database', 'browser'):
            if status != 'success':
                fail('invalid_tool_fallback', 'Live DB and browser evidence cannot be replaced by fallback claims.')
            _real_provider(row)
            validate(row['result'], DB_RESULT if capability == 'database' else BROWSER_RESULT, 'tool_observation.result')
            if capability == 'browser':
                _url(row['result']['url'])
            elif row['target'] != row['result']['target_ref']:
                fail('invalid_tool_observation', 'DB result must identify the same observed target.')


def _openai_source(url):
    host = urlsplit(url).hostname or ''
    return any(host == domain or host.endswith('.' + domain) for domain in ('openai.com', 'chatgpt.com'))


def _selected(plan, unit_id=None):
    return {row['capability']: row for row in plan
            if row['mode'] != 'not_applicable' and (unit_id is None or unit_id in row['unit_ids'])}


def _satisfies(policy, observation):
    if observation['status'] == 'blocked':
        return False
    if policy['capability'] != 'ui_design':
        return True
    if policy['mode'] == 'required':
        return observation['provider'] == 'figma' and observation['status'] == 'success'
    if policy['mode'] == 'local_only':
        return (observation['provider'] == 'local-design' and observation['status'] == 'success'
                and bool(observation['result'].get('user_choice', '').strip()))
    return (observation['provider'] == 'figma' and observation['status'] == 'success'
            or observation['provider'] == 'local-design' and observation['status'] == 'fallback')


def check_gate(plan, observations, gate, unit_id=None):
    """Check system observations for A, or this exact unit's observations for B."""
    validate_observations(observations)
    if gate not in ('A', 'B') or gate == 'B' and not unit_id:
        fail('invalid_tool_gate', 'Tool evidence gates are A or B; B requires unit_id.')
    applicable = _selected(plan, unit_id if gate == 'B' else None)
    needed = ('library_docs',) if gate == 'A' else ('ui_design', 'library_docs', 'database')
    for capability in needed:
        if capability not in applicable:
            continue
        matches = [row for row in observations if row['capability'] == capability]
        if capability == 'database':
            # The workflow additionally checks every pinned environment/DB target.
            # Different targets may be observed in the same second legitimately.
            if not any(row['status'] == 'success' for row in matches):
                fail('tool_evidence_required', f'Gate {gate} requires database evidence for its pinned targets.')
            continue
        # Reject ambiguous latest findings; equal timestamps cannot hide a block.
        latest = []
        if matches:
            timestamp = lambda row: datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
            newest = max(timestamp(row) for row in matches)
            latest = [row for row in matches if timestamp(row) == newest]
        if len(latest) > 1:
            fail('ambiguous_tool_observation', 'The latest capability observations share a timestamp; record a single unambiguous current result.')
        if not latest or not _satisfies(applicable[capability], latest[0]):
            fail('tool_evidence_required', f'Gate {gate} requires current {capability} evidence for the selected scope.')


def check_database_targets(observations, expected_targets, *, kind='catalog'):
    """Require the latest successful observation of every exact approved DB target."""
    validate_observations(observations)
    if kind not in ('catalog', 'readback'):
        fail('invalid_tool_observation', 'Database evidence kind must be catalog or readback.')
    expected = set(expected_targets)
    if not expected or any(not isinstance(target, str) or not target.strip() for target in expected):
        fail('tool_database_target_required', 'Database evidence requires nonempty exact approved environment/DB targets.')
    rows = [row for row in observations if row['capability'] == 'database']
    if any(row['status'] == 'success' and row['target'] not in expected for row in rows):
        fail('tool_database_target_mismatch', 'A successful DB observation identifies an unapproved target.')
    for target in sorted(expected):
        matches = [row for row in rows if row['target'] == target]
        if not matches:
            fail('tool_database_evidence_required', 'Every approved database target requires its own observed evidence.')
        timestamp = lambda row: datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))
        newest = max(timestamp(row) for row in matches)
        latest = [row for row in matches if timestamp(row) == newest]
        if len(latest) != 1:
            fail('ambiguous_tool_observation', 'Latest DB observations for one target share a timestamp.')
        if latest[0]['status'] != 'success' or latest[0]['result']['observation_kind'] != kind:
            fail('tool_database_evidence_required', 'The latest observation of each approved target must successfully verify the required DB evidence kind.')


def validate_check_bindings(plan, unit_id, test_payload):
    """Pin required live checks to required JSON attachments on a project runner."""
    bindings = test_payload.get('tool_checks', [])
    validate(bindings, TOOL_CHECKS_SCHEMA, 'tool_checks')
    applicable = {cap for cap in _selected(plan, unit_id) if cap in ('browser', 'database')}
    checks = {row['check_id']: row for row in test_payload.get('checks', [])}
    seen, covered = set(), set()
    for binding in bindings:
        cap = binding['capability']
        key = (binding['check_id'], binding['evidence_id'])
        if key in seen or cap not in applicable:
            fail('invalid_tool_check', 'Tool bindings must be unique and applicable to this unit.')
        seen.add(key)
        check = checks.get(binding['check_id'])
        if not check or check.get('required') is not True or check.get('runner', {}).get('kind') != 'project-runner':
            fail('invalid_tool_check', 'Tool evidence requires an existing required project-runner check.')
        evidence = [item for item in check['runner'].get('evidence', []) if item['evidence_id'] == binding['evidence_id']]
        if len(evidence) != 1 or evidence[0].get('required') is not True or evidence[0].get('format') != 'json':
            fail('invalid_tool_check', 'Tool evidence must bind one required JSON attachment.')
        covered.add(cap)
    if covered != applicable:
        fail('tool_check_required', 'Every applicable browser/DB capability requires its own evidence binding.')


def validate_completion_evidence(plan, unit_id, test_payload, campaign, load_blob, *, build_id,
                                 expected_database_targets=None, validate_source_ref=None):
    """Read hash-checked blobs emitted by actual passing runner attempts.

    load_blob(oid) returns bytes from the personal journal. No caller-supplied
    inline report or earlier attempt can substitute for this campaign's blobs.
    """
    validate_check_bindings(plan, unit_id, test_payload)
    requires_database = any(row['capability'] == 'database' for row in test_payload.get('tool_checks', []))
    if requires_database and not expected_database_targets:
        fail('tool_database_target_required', 'DB completion must identify its exact approved environment/DB targets.')
    summaries, database_observations = [], []
    for binding in test_payload.get('tool_checks', []):
        attempt = campaign.get('check_results', {}).get(binding['check_id'])
        if not attempt or attempt.get('result') != 'passed':
            fail('tool_completion_required', 'A required tool evidence check has no passing attempt.')
        try:
            raw = load_blob(attempt['evidence_oid'])
            if sha256(raw) != attempt['evidence_sha256']:
                fail('tool_evidence_hash_mismatch', 'Runner observation blob changed.')
            execution = json.loads(raw)
            if not isinstance(execution, dict) or not isinstance(execution.get('preparation'), dict):
                fail('invalid_tool_evidence', 'Actual runner evidence must contain a preparation receipt.')
            preparation = execution['preparation']
            if preparation.get('passed') is not True:
                fail('tool_completion_required', 'Runner preparation and required cleanup must have passed.')
            evidence_rows = preparation.get('evidence', [])
            if not isinstance(evidence_rows, list) or any(not isinstance(row, dict) for row in evidence_rows):
                fail('invalid_tool_evidence', 'Runner attachment receipt must be an array of objects.')
            attachments = [row for row in evidence_rows
                           if row.get('evidence_id') == binding['evidence_id']]
            if len(attachments) != 1:
                fail('tool_completion_required', 'The passing attempt did not attach the required tool evidence.')
            attachment = attachments[0]
            if attachment.get('status') != 'attached' or attachment.get('format') != 'json' or attachment.get('required') is not True:
                fail('tool_completion_required', 'Tool completion requires a real attached required JSON evidence blob.')
            raw = load_blob(attachment['blob_oid'])
            if sha256(raw) != attachment['sha256']:
                fail('tool_evidence_hash_mismatch', 'Attached tool evidence changed.')
            evidence = json.loads(raw)
            validate(evidence, COMPLETION_EVIDENCE_SCHEMA, 'completion_tool_evidence')
            if (evidence['capability'] != binding['capability'] or evidence['build_id'] != build_id
                    or evidence['run_id'] != attempt['attempt_id']):
                fail('tool_evidence_stale', 'Evidence must belong to this capability, source build, and exact runner attempt.')
            observation = evidence['observation']
            validate_observations([observation])
            if observation['capability'] != binding['capability'] or observation['status'] != 'success':
                fail('tool_completion_required', 'Completion requires a successful observation of the bound capability.')
            if binding['capability'] == 'database' and observation['result']['observation_kind'] != 'readback':
                fail('tool_completion_required', 'DB completion requires actual readback rather than only catalog discovery.')
            for source in observation['source_refs']:
                if validate_source_ref:
                    validate_source_ref(source)
                elif source.startswith('artifact:'):
                    fail('tool_source_validation_required', 'Personal artifact evidence requires a current approved-reference resolver.')
            if binding['capability'] == 'database':
                database_observations.append(observation)
        except (KeyError, TypeError, ValueError, UnicodeError):
            fail('invalid_tool_evidence', 'Actual runner evidence is missing or malformed.')
        summaries.append({'capability': binding['capability'], 'check_id': binding['check_id'],
                          'evidence_id': binding['evidence_id'], 'sha256': attachment['sha256'],
                          'provider': observation['provider'], 'target': observation['target']})
    if requires_database:
        check_database_targets(database_observations, expected_database_targets, kind='readback')
    return summaries


def render_tools(plan, observations):
    """Render a deterministic review section without hiding failure provenance."""
    capability_labels = {'ui_design': '화면 설계', 'library_docs': '라이브러리 문서',
                         'browser': '브라우저 검증', 'database': 'DB 관찰'}
    mode_labels = {'required': '필수', 'preferred': '우선 사용',
                   'local_only': '사용자 로컬 선택', 'not_applicable': '해당 없음'}
    lines = ['## 외부 도구 활용 계획과 근거', '',
             '관찰 기록은 호출자·검사 실행기가 제출한 근거이며 공급자 인증이나 승인자 신원 인증이 아닙니다.', '',
             '| 기능 | 정책 | 대상 단위 | 적용 이유 |', '|---|---|---|---|']
    def cell(value):
        return html.escape(str(value), quote=False).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')
    for row in plan:
        capability = capability_labels[row['capability']] + ' (' + row['capability'] + ')'
        mode = mode_labels[row['mode']] + ' (' + row['mode'] + ')'
        lines.append('| ' + ' | '.join(cell(value) for value in (capability, mode, ', '.join(row['unit_ids']) or '해당 없음', row['reason'])) + ' |')
    lines.extend(['', '### 도구 관찰 기록', ''])
    if not observations:
        lines.append('아직 기록된 관찰이 없습니다. 필수 근거 충족 여부는 해당 승인 단계에서 검사합니다.')
    for row in observations:
        lines.extend([f"- {cell(row['capability'])}: {cell(row['provider'])} / {cell(row['tool'])} / {cell(row['status'])}",
                      f"  - 관찰: {cell(row['observed_at'])}; 대상: {cell(row['target'])}",
                      f"  - 결과: {cell(row['summary'])}",
                      '  - 근거: ' + ', '.join(cell(ref) for ref in row['source_refs'])])
        if row.get('failure'):
            failure = row['failure']
            lines.append(f"  - 대체·차단 사유: {cell(failure['tool'])} / {cell(failure['code'])} / {cell(failure['detail'])}")
        if row['result'].get('user_choice'):
            lines.append('  - 사용자 선택: ' + cell(row['result']['user_choice']))
        # Dynamic fences keep supplied Markdown/HTML as reviewable text, never markup.
        material = json.dumps(row['result'], ensure_ascii=False, indent=2)
        fence = '`' * max(3, 1 + max((len(run) for run in re.findall(r'`+', material)), default=0))
        lines.extend(['', '검토 대상 결과 원문:', '', fence + 'json', material, fence, ''])
    return '\n'.join(lines) + '\n'
