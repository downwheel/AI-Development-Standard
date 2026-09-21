"""Bind DB adapter side effects to a current, owned implementation session."""
from __future__ import annotations
import copy
from .common import HarnessError,emit,encoded,fail,now,sha256,uid


def resolve_plan_environment(execution,basis,plan):
    if plan['environment_ref'] not in basis.get('environment_refs',[]):
        fail('db_environment_unapproved','Database plan must use its approved environment contract.')
    contract=execution.workflow.load_artifact(plan['environment_ref'])['payload']
    manager=execution._environment_manager(); manager.validate_contract(contract)
    candidates=[]
    for role in contract['roles']:
        resolved=manager.resolve(contract['profile_id'],role=role)
        if resolved.binding['role_kind'] in {'migration','fixture'}: candidates.append(resolved)
    if len(candidates)!=1:
        fail('db_role_ambiguous','Pin exactly one migration or fixture role in each database environment contract.')
    return candidates[0]


def _report(record):
    lines=['# DB 계획 대비 실행 결과','','상태: '+record['status'],'','| DB 작업 | 상태 | commit | 독립 관찰 | 정리 |','|---|---|---|---|---|']
    for item in record.get('receipts',[]):
        result=item['result']
        lines.append('| '+' | '.join(str(value).replace('|','&#124;') for value in [item['db_work_id'],result.get('status'),result.get('committed'),result.get('independent_observation'),result.get('cleanup')])+' |')
        lines += ['','```json',__import__('json').dumps({key:result.get(key) for key in ['migrations','objects','duration_ms','rollback','cleanup','case_results','limits']},ensure_ascii=False,indent=2),'```']
    lines += ['','소스 snapshot은 DB 백업이 아닙니다. 연결·실행·반영·복구 결과는 위 실측 기록으로 판단합니다.']
    return '\n'.join(lines)+'\n'


def execute_database(execution,session_id,owner,request_id):
    from .database import execute_plan
    key='database/'+request_id
    fingerprint=sha256(encoded({'session_id':session_id,'owner':owner}))
    def reserve(state):
        previous=state.get('db_executions',{}).get(key)
        if previous:
            if previous['fingerprint']!=fingerprint: fail('request_conflict','Database request ID was used with different inputs.')
            return previous,False
        session=state.get('execution_sessions',{}).get(session_id)
        if not session or session['owner']!=owner or session['status']!='open': fail('owner_mismatch','Database execution requires an open owned implementation session.')
        execution._lease_state(state,session['lease_id'],owner)
        basis=execution.workflow._basis(state,session['run_id'],session['unit_id'])
        if basis!=session['basis']: fail('basis_changed','The database approval basis changed.')
        if session.get('mode')=='observe': fail('observation_readonly','An observation session cannot write to a database.')
        if not basis.get('db_plan_refs'): fail('db_plan_required','No database work was approved for this unit.')
        if any(row['status'] in {'running','indeterminate'} and row['workspace_id']==session['workspace_id'] for row in state.get('db_executions',{}).values()):
            fail('db_reconciliation_required','An earlier database attempt has an uncertain result; inspect its actual target before a new plan.')
        record={'request_key':key,'fingerprint':fingerprint,'session_id':session_id,'run_id':session['run_id'],'unit_id':session['unit_id'],
                'workspace_id':session['workspace_id'],'owner':owner,'basis':basis,'status':'running','phase':'preflight','receipts':[],'started_at':now()}
        state.setdefault('db_executions',{})[key]=record
        state.setdefault('db_execution_order',[]).append(key)
        emit(state,'database_execution_started',{'request_key':key,'session_id':session_id,'basis':basis})
        return record,True
    record,new=execution.journal.transaction(reserve)
    if not new: return record
    try:
        for plan_ref in record['basis']['db_plan_refs']:
            execution._lease_state(execution.journal.read(),execution.journal.read()['execution_sessions'][session_id]['lease_id'],owner)
            if execution.workflow.implementation_basis(record['run_id'],record['unit_id'])!=record['basis']:
                fail('basis_changed','Approval changed before the next database operation.')
            plan=execution.workflow.load_artifact(plan_ref)['payload']
            from .history import _no_links
            from .common import safe_relative
            scope=execution.workflow.load_artifact(record['basis']['scope_ref'])['payload']
            files={item['path']:item for item in scope['files']}
            for migration in plan['migrations']:
                relative=migration['source_path']; file=files.get(relative)
                if not file or file['action'] not in {'create','modify'}:
                    fail('db_migration_scope','Each migration SQL file must be an approved exact create/modify source path.')
                path=execution._root(record['workspace_id']).joinpath(*safe_relative(relative).parts)
                _no_links(path)
                if not path.is_file() or path.stat().st_size>8*1024*1024 or sha256(path.read_bytes())!=migration['sql_sha256']:
                    fail('db_migration_changed','Product SQL bytes do not match the SQL preview approved at Gate B.')
            resolved=resolve_plan_environment(execution,record['basis'],plan)
            binding={'review_id':record['basis']['review_id'],'plan_sha256':sha256(encoded(plan)),
                     'environment_revision':resolved.binding['revision'],'target_revision':resolved.binding['target_revision']}
            execution.journal.transaction(lambda state: state['db_executions'][key].update(phase='adapter_started'))
            result=execute_plan(plan,resolved,approval_binding=binding)
            row={'plan_ref':plan_ref,'db_work_id':plan['db_work_id'],'result':result}
            def save(state):
                state['db_executions'][key]['receipts'].append(row)
                state['db_executions'][key]['phase']='preflight'
                emit(state,'database_plan_finished',{'request_key':key,'plan_ref':plan_ref,'status':result['status'],'committed':result.get('committed',False)})
            execution.journal.transaction(save)
            if result['status']!='passed': break
        def finish(state):
            current=state['db_executions'][key]
            def uncertain(result):
                cleanup=result.get('cleanup',{})
                return result.get('commit_outcome')=='unknown' or result.get('rollback') in {'failed-or-unknown','attempted-after-unknown-commit'} or (
                    isinstance(cleanup,dict) and (cleanup.get('commit_outcome')=='unknown' or cleanup.get('rollback') in {'failed-or-unknown','failed'}))
            current['status']='indeterminate' if any(uncertain(item['result']) for item in current['receipts']) else (
                'passed' if len(current['receipts'])==len(current['basis']['db_plan_refs']) and all(item['result']['status']=='passed' for item in current['receipts']) else 'blocked')
            current['finished_at']=now()
            session=state['execution_sessions'][session_id]
            current['ref']=execution._artifact(state,'db-execution-receipt',copy.deepcopy(current),_report(current),session,current['basis']['db_plan_refs'],'database-'+current['unit_id'])
            emit(state,'database_execution_finished',{'request_key':key,'status':current['status'],'ref':current['ref']})
            return current
        return execution.journal.transaction(finish)
    except BaseException as exc:
        def interrupted(state):
            current=state['db_executions'][key]
            current.update(status='indeterminate' if current.get('phase')=='adapter_started' else 'blocked',error=getattr(exc,'code',type(exc).__name__),finished_at=now(),automatic_retry=False)
            emit(state,'database_execution_interrupted',{'request_key':key,'error':current['error'],'automatic_retry':False})
            return current
        execution.journal.transaction(interrupted)
        raise


def database_completion(execution,basis,session=None,state=None):
    if not basis.get('db_plan_refs'): return {'passed':True,'status':'not_applicable','plans':[]}
    from .database import check_plan_current
    state=execution.journal.read() if state is None else state
    records=[state['db_executions'][key] for key in state.get('db_execution_order',[]) if state['db_executions'][key]['basis']==basis]
    if not records: return {'passed':False,'status':'not_run','plans':[]}
    latest=records[-1]
    if latest['status']!='passed': return {'passed':False,'status':latest['status'],'request_key':latest['request_key'],'plans':[]}
    observations=[]
    for item in latest['receipts']:
        try:
            plan=execution.workflow.load_artifact(item['plan_ref'])['payload']
            resolved=resolve_plan_environment(execution,basis,plan)
            observation=check_plan_current(plan,resolved,item['result'])
        except (HarnessError,OSError) as exc:
            observation={'current':False,'error':getattr(exc,'code',type(exc).__name__)}
        observations.append({'plan_ref':item['plan_ref'],'observation':observation})
    return {'passed':len(observations)==len(basis['db_plan_refs']) and all(row['observation'].get('current') is True for row in observations),
            'status':'observed','request_key':latest['request_key'],'plans':observations,'receipt_ref':latest.get('ref')}
