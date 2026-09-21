"""Observe uncertain DB outcomes and record an explicit human recovery decision.

This never retries SQL, compensates changes, or restores database contents.
Accepting an observation creates a pending contract change before further writes.
"""
from __future__ import annotations
import copy
import json

from .common import emit, encoded, fail, identifier, now, sha256, uid
from .validation import STR, obj, validate


def database_recovery_operations():
    return {
        'plan_database_recovery': obj({'request_id': STR, 'owner': STR}, ['request_id', 'owner']),
        'record_database_recovery': obj({'recovery_id': STR,
            'decision': {'type': 'string', 'enum': ['accept_observed', 'reject']},
            'user_message': STR, 'source': STR}, ['recovery_id', 'decision', 'user_message', 'source']),
    }


def _semantic(value):
    if isinstance(value, dict):
        return {key: _semantic(item) for key, item in value.items() if key != 'observed_at'}
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return value


def _preview_hash(preview, report):
    return sha256(encoded({'preview': preview, 'report': report}))


class DatabaseRecovery:
    def __init__(self, execution):
        self.execution = execution
        self.journal = execution.journal

    def execute(self, operation, params):
        schemas = database_recovery_operations()
        if operation not in schemas:
            fail('unknown_operation', 'Unknown database recovery operation.')
        validate(params, schemas[operation])
        if operation == 'plan_database_recovery':
            return self.plan(**params)
        return self.record(**params)

    def _request(self, state, key, owner):
        from .execution import observed_process
        request = state.get('db_executions', {}).get(key)
        if not request or request.get('owner') != owner:
            fail('owner_mismatch', 'Recovery must identify the owner of an existing database attempt.')
        self.execution.workflow._require_runtime(state,request['run_id'])
        if request.get('status') not in {'indeterminate', 'running'}:
            fail('db_recovery_not_needed', 'Only an unresolved uncertain database attempt can be recovered.')
        session = state.get('execution_sessions', {}).get(request['session_id'])
        if not session or session.get('status') not in {'closed', 'finished', 'failed', 'interrupted'}:
            fail('db_controller_active', 'Finish or reconcile the implementation controller before observing recovery; lease expiry is insufficient.')
        controllers = [item for item in state.get('execution_requests', {}).values()
                       if item.get('session_id') == request['session_id']]
        if any(item.get('status') not in {'finished', 'failed', 'interrupted'} for item in controllers):
            fail('db_controller_active', 'The implementation controller is still active or unconfirmed; reconcile it first.')
        if request['status'] == 'running' or not request.get('finished_at'):
            identities = [item.get('controller') for item in controllers if item.get('controller')]
            if not identities or any(observed_process(identity).get('state') != 'exited' for identity in identities):
                fail('db_adapter_active', 'An unfinished adapter requires positive controller-exit evidence before recovery.')
        if any(other['request_key'] != key and other.get('workspace_id') == request['workspace_id'] and
               other.get('status') == 'running' for other in state.get('db_executions', {}).values()):
            fail('db_adapter_active', 'Another database adapter may still be running in this workspace.')
        return request

    def _observe(self, request):
        from .database import inspect_database
        from .execution_database import resolve_plan_environment
        observations = []
        for plan_ref in request['basis']['db_plan_refs']:
            plan = self.execution.workflow.load_artifact(plan_ref)['payload']
            resolved = resolve_plan_environment(self.execution, request['basis'], plan)
            tables = sorted({migration['operation']['table'] for migration in plan['migrations']})
            observation = inspect_database(resolved, tables, max_rows=plan['limits']['max_observed_rows'],
                                           max_catalog_objects=plan['limits']['max_catalog_objects'])
            target = observation.get('target', {})
            if observation.get('status') != 'passed' or any(target.get(key) != value for key, value in plan['target'].items()):
                fail('db_recovery_target_drift', 'Recovery observation must identify the same approved database, schema, account and permissions.')
            if target.get('engine_version') != plan['engine_version']:
                fail('db_recovery_target_drift', 'Observed engine version differs from the approved recovery target.')
            observations.append({'plan_ref': plan_ref, 'db_work_id': plan['db_work_id'],
                                 'environment_binding': resolved.binding, 'observation': observation})
        return observations

    def plan(self, request_id, owner):
        identifier(request_id, 'request_id'); identifier(owner, 'owner')
        key = 'database/' + request_id
        request = self._request(self.journal.read(), key, owner)
        fingerprint = sha256(encoded(request))
        observations = self._observe(request)
        preview = {'recovery_id': uid('db-recovery'), 'request_key': key, 'owner': owner,
                   'run_id': request['run_id'], 'unit_id': request['unit_id'], 'workspace_id': request['workspace_id'],
                   'request_sha256': fingerprint, 'basis': copy.deepcopy(request['basis']), 'created_at': now(),
                   'observations': observations, 'observation_sha256': sha256(encoded(_semantic(observations))),
                   'notice': 'Read-only observation of an uncertain outcome. Acceptance requires a new contract review before further writes; no SQL is retried or undone.'}
        report = '# DB 불확실한 실행 결과 확인\n\n'
        report += '대상 요청: ' + key + '\n\n'
        report += '아래 내용은 새로운 읽기 관찰입니다. DB 데이터 복원이나 SQL 재실행을 수행하지 않았습니다. '
        report += '관찰 결과 수락 시 해당 단위에 변경 요청을 기록하며 새 설계·승인 전에는 추가 쓰기를 진행할 수 없습니다.\n\n'
        report += '```json\n' + json.dumps(observations, ensure_ascii=False, indent=2) + '\n```\n'
        record = {'recovery_id': preview['recovery_id'], 'preview': preview, 'report': report,
                  'preview_sha256': _preview_hash(preview, report)}
        def save(state):
            current = self._request(state, key, owner)
            if sha256(encoded(current)) != fingerprint:
                fail('db_recovery_race', 'Database attempt changed during the observation; prepare a new preview.')
            state.setdefault('db_recovery_previews', {})[preview['recovery_id']] = copy.deepcopy(record)
            emit(state, 'database_recovery_presented', {'recovery_id': preview['recovery_id'],
                    'request_key': key, 'preview_sha256': record['preview_sha256']})
            return record
        return self.journal.transaction(save)

    def record(self, recovery_id, decision, user_message, source):
        identifier(recovery_id, 'recovery_id')
        if decision not in {'accept_observed', 'reject'}:
            fail('invalid_input', 'Unsupported recovery decision.')
        if not isinstance(user_message, str) or not user_message.strip() or not isinstance(source, str) or not source.strip():
            fail('user_decision_required', 'A real user message and its source are required; an AI finding or silence is not approval.')
        state = self.journal.read()
        saved = state.get('db_recovery_previews', {}).get(recovery_id)
        if not saved:
            fail('db_recovery_unknown', 'Recovery preview does not exist.')
        previous = state.get('db_recovery_decisions', {}).get(recovery_id)
        if previous:
            if all(previous[key] == value for key, value in {'decision': decision, 'user_message': user_message, 'source': source}.items()):
                return previous
            fail('decision_exists', 'Recovery decision is immutable; prepare a new preview if needed.')
        preview = saved['preview']
        if saved['preview_sha256'] != _preview_hash(preview, saved['report']):
            fail('db_recovery_integrity', 'Presented recovery observation or report changed.')
        request = self._request(state, preview['request_key'], preview['owner'])
        if sha256(encoded(request)) != preview['request_sha256']:
            fail('db_recovery_stale', 'The original database attempt changed after presentation.')
        if decision == 'accept_observed':
            observations = self._observe(request)
            if sha256(encoded(_semantic(observations))) != preview['observation_sha256']:
                fail('db_recovery_stale', 'Database state changed since presentation; show a new observation before accepting it.')
        def save(current_state):
            if recovery_id in current_state.get('db_recovery_decisions', {}):
                fail('decision_exists', 'Another recovery decision was recorded concurrently.')
            stored = current_state.get('db_recovery_previews', {}).get(recovery_id)
            if stored != saved:
                fail('db_recovery_integrity', 'Recovery presentation changed before its decision.')
            current = self._request(current_state, preview['request_key'], preview['owner'])
            if sha256(encoded(current)) != preview['request_sha256']:
                fail('db_recovery_stale', 'Database attempt changed before its decision.')
            result = {'recovery_id': recovery_id, 'decision_id': uid('db-recovery-decision'), 'decision': decision,
                      'user_message': user_message, 'source': source, 'recorded_at': now(),
                      'preview_sha256': saved['preview_sha256'], 'request_key': preview['request_key'],
                      'provenance': 'caller-supplied; not authenticated', 'sql_executed': False}
            if decision == 'accept_observed':
                change = self.execution.workflow._operate(current_state, 'record_change', {
                    'run_id': preview['run_id'], 'unit_ids': [preview['unit_id']],
                    'user_message': user_message, 'source': source})
                current.update(status='reconciled', recovered_at=now(), recovery_id=recovery_id,
                               original_status=current['status'], pending_change_id=change['change_id'], automatic_retry=False)
                result.update(change_id=change['change_id'], next_action='revise_contract_and_obtain_new_gate_b')
            else:
                result['next_action'] = 'uncertain_attempt_remains_blocked'
            current_state.setdefault('db_recovery_decisions', {})[recovery_id] = result
            emit(current_state, 'database_recovery_decided', result)
            return result
        return self.journal.transaction(save)
