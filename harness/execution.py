"""Managed implementation boundaries and real, bounded verification processes."""
from __future__ import annotations
import copy
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from .common import HarnessError, emit, encoded, fail, now, safe_relative, sha256, uid
from .history import capture_snapshot, snapshot_matches
from .validation import obj, STR, validate
from .workflow import Workflow

CAMPAIGN_BUDGET_SECONDS = 900
CASE_MARKER = 'HARNESS_CASE_RESULTS='

def execution_operations():
    from .database_recovery import database_recovery_operations
    return {
        **database_recovery_operations(),
        'begin_implementation':obj({'run_id':STR,'unit_id':STR,'owner':STR,'request_id':STR,'mode':{'type':'string','enum':['change','observe']}},['run_id','unit_id','owner','request_id']),
        'check_edit_scope':obj({'session_id':STR,'owner':STR,'changes':{'type':'array','minItems':1,'maxItems':1000,'items':obj({'path':STR,'action':{'type':'string','enum':['create','modify','delete']}},['path','action'])}},['session_id','owner','changes']),
        'execute_database':obj({'session_id':STR,'owner':STR,'request_id':STR},['session_id','owner','request_id']),
        'get_database_execution':obj({'request_id':STR},['request_id']),
        'finish_implementation':obj({'session_id':STR,'owner':STR,'summary':STR,'outcome':{'type':'string','enum':['completed','partial','failed']}},['session_id','owner','summary','outcome']),
        'list_implementations':obj({'run_id':STR},['run_id']),
        'run_checks':obj({'implementation_id':STR,'owner':STR,'request_id':STR,'check_ids':{'type':'array','items':STR,'minItems':1,'maxItems':100}},['implementation_id','owner','request_id']),
        'cancel_verification':obj({'campaign_id':STR,'owner':STR},['campaign_id','owner']),
        'get_verification':obj({'implementation_id':STR},['implementation_id']),
        'reconcile_execution':obj({'kind':{'type':'string','enum':['implementation','verification']},'request_id':STR,'owner':STR,'action':{'type':'string','enum':['status','reconcile']},'external_writers_stopped':{'type':'boolean'}},['kind','request_id','owner','action']),
    }

def git_metadata(root):
    """Observe small Git management files without running Git in the product."""
    from .registry import normal_root
    root=normal_root(root)
    root=next((p for p in [root,*root.parents] if (p/'.git').exists()),root)
    dot=root/'.git'
    if not dot.exists():
        return {'present':False,'files':{}}
    if dot.is_symlink() or getattr(dot.lstat(),'st_file_attributes',0)&0x400:
        fail('linked_git','Product Git metadata link is unsupported.')
    roots=[dot]
    records={}
    if dot.is_file():
        raw=dot.read_bytes()
        records['pointer']=sha256(raw)
        line=raw.decode('utf-8').strip()
        if not line.startswith('gitdir: '):
            fail('git_metadata_invalid','Unsupported Git pointer file.')
        roots=[normal_root(root/line[8:])]
    commondir=roots[0]/'commondir'
    if commondir.exists():
        roots.append(normal_root(roots[0]/commondir.read_text(encoding='utf-8').strip()))
    count=0
    for index,base in enumerate(roots):
        normal_root(base)
        selected=[]
        for folder,dirs,files in os.walk(base,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(folder)==base and d=='objects')]
            for name in dirs: normal_root(Path(folder)/name)
            selected.extend(Path(folder)/name for name in files)
        for path in selected:
            count+=1
            info=path.lstat()
            if not stat.S_ISREG(info.st_mode): fail('git_metadata_invalid','Only regular Git metadata files are supported.')
            if count>5000 or info.st_size>16*1024*1024:
                fail('git_metadata_limit','Git metadata observation exceeds the supported bound.')
            if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400: fail('linked_git','Linked Git metadata is unsupported.')
            records[f'{index}/{path.relative_to(base).as_posix()}']=sha256(path.read_bytes())
    return {'present':True,'git_root':str(root),'files':records}


def process_identity(pid):
    """Creation identity prevents treating a reused PID as the old controller."""
    result={'pid':pid,'state':'unknown','token':None}
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000|0x100000,False,pid)
        if not handle:
            if ctypes.get_last_error()==87: result['state']='exited'
            return result
        try:
            times=[wintypes.FILETIME() for _ in range(4)]; code=wintypes.DWORD()
            if kernel.GetProcessTimes(handle,*[ctypes.byref(v) for v in times]) and kernel.GetExitCodeProcess(handle,ctypes.byref(code)):
                result.update(state='alive' if code.value==259 else 'exited',token=str((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime))
        finally: kernel.CloseHandle(handle)
        return result
    try:
        parts=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'pid':pid,'state':'exited' if parts[0]=='Z' else 'alive','token':parts[19]}
    except (OSError,IndexError):
        try: os.kill(pid,0)
        except ProcessLookupError: result['state']='exited'
        except PermissionError: pass
        return result


def observed_process(record):
    if not record or not record.get('pid'): return {'state':'unknown'}
    current=process_identity(record['pid'])
    if current['state']=='exited': return current
    if not record.get('token') or not current.get('token'): return {**current,'state':'unknown'}
    if record['token']!=current['token']: return {**current,'state':'exited','pid_reused':True}
    return current


def _windows_job(process):
    """A non-inherited handle makes Windows kill managed descendants on controller exit."""
    if os.name!='nt': return lambda:None
    import ctypes
    from ctypes import wintypes
    class BASIC(ctypes.Structure):
        _fields_=[('PerProcessUserTimeLimit',ctypes.c_longlong),('PerJobUserTimeLimit',ctypes.c_longlong),('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',wintypes.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(n,ctypes.c_ulonglong) for n in ['ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount']]
    class EXTENDED(ctypes.Structure):
        _fields_=[('BasicLimitInformation',BASIC),('IoInfo',IO),('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]; kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateJobObjectW(None,None); limits=EXTENDED(); limits.BasicLimitInformation.LimitFlags=0x2000
    if not handle or not kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle,int(process._handle)):
        if handle: kernel.CloseHandle(handle)
        _terminate(process)
        fail('supervision_unavailable','Could not establish managed Windows process-tree supervision.')
    return lambda:kernel.CloseHandle(handle)


def _executable(argv,cwd):
    candidate=Path(argv[0])
    if candidate.is_absolute(): return str(candidate)
    if '/' in argv[0] or '\\' in argv[0]: return str(Path(cwd)/candidate)
    return shutil.which(argv[0])


def _process_environment():
    from .environment import base_process_environment
    return base_process_environment({'PYTHONDONTWRITEBYTECODE':'1'})


def case_result(check,result):
    mode=check.get('evidence_mode','case-results'); parser=check.get('parser','team-json')
    if mode=='command-exit' and parser=='exit-code':
        return {'result':'passed','mode':mode,'cases':[]}
    if mode!='case-results' or parser!='team-json': return {'result':'blocked','error':'unsupported_parser'}
    lines=[line[len(CASE_MARKER):] for line in result.get('streams',{}).get('stdout','').splitlines() if line.startswith(CASE_MARKER)]
    def unique_object(pairs):
        value={}
        for key,item in pairs:
            if key in value: raise ValueError('Duplicate JSON key')
            value[key]=item
        return value
    try:
        if len(lines)!=1: raise ValueError()
        value=json.loads(lines[0],object_pairs_hook=unique_object)
        if not isinstance(value,dict) or set(value)!={'cases'} or not isinstance(value['cases'],list) or not 1<=len(value['cases'])<=1000: raise ValueError()
        cases=value['cases']; ids=[]
        for case in cases:
            if not isinstance(case,dict) or set(case)!={'case_id','status'} or not isinstance(case['case_id'],str) or case['status'] not in ['passed','failed','skipped']: raise ValueError()
            ids.append(case['case_id'])
        if len(ids)!=len(set(ids)) or set(ids)!=set(check['case_ids']): raise ValueError()
    except (ValueError,TypeError,KeyError): return {'result':'blocked','error':'invalid_case_evidence'}
    statuses={case['status'] for case in cases}
    return {'result':'failed' if 'failed' in statuses else 'blocked' if 'skipped' in statuses else 'passed','mode':mode,'cases':cases}


def environment_fingerprint(checks,root):
    """Bounded executable/argument files and common local dependency trees, not remote services."""
    from .registry import normal_root
    files={}; size=0
    def add(path):
        nonlocal size
        path=Path(path).absolute()
        key=str(path)
        if key in files: return
        normal_root(path.parent)
        before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or path.is_symlink() or getattr(before,'st_file_attributes',0)&0x400: fail('environment_unverified','Only regular unlinked runtime files are supported.')
        size+=before.st_size
        if len(files)>=50000 or size>512*1024*1024: fail('environment_limit','Runtime observation exceeds the supported bound.')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
        after=path.stat()
        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino): fail('environment_changed','Runtime input changed while being observed.')
        files[key]=digest.hexdigest()
    expanded=list(checks)
    for check in checks:
        runner=check.get('runner',{})
        expanded.extend(runner.get('services',[]))
        if runner.get('fixture'): expanded.extend([runner['fixture']['setup'],runner['fixture']['cleanup']])
    for check in expanded:
        cwd=root if check['cwd']=='.' else root.joinpath(*safe_relative(check['cwd']).parts)
        executable=_executable(check['argv'],cwd)
        if not executable: fail('missing_executable','Approved executable was not found.')
        add(Path(executable))
        for argument in check['argv'][1:]:
            try:
                path=Path(argument)
                if not path.is_absolute(): path=cwd/path
                exists=path.is_file()
            except (OSError,ValueError): exists=False
            if exists: add(path)
    for name in ['node_modules','.venv','venv']:
        base=root/name
        if not base.exists(): continue
        normal_root(base)
        for folder,dirs,names in os.walk(base,followlinks=False):
            for directory in dirs: normal_root(Path(folder)/directory)
            for name in names: add(Path(folder)/name)
    return {'platform':platform.platform(),'python':sys.version,'path_digest':sha256(os.environ.get('PATH','').encode()),'process_environment_digest':sha256(encoded(_process_environment())),'files':files,
        'scope':'executable bytes, existing argv file bytes, root node_modules/.venv/venv and allowlisted process environment; external services and system libraries are not snapshotted'}

def redact(raw):
    text=raw.decode('utf-8',errors='replace')
    patterns=[r'\b(?:sk-(?:proj-)?|gh[pousr]_)[A-Za-z0-9_-]{20,}',r'\bAKIA[0-9A-Z]{16}\b',
              r'(?im)((?:password|pwd|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[=:]\s*)[^\s;,]+',
              r'(?i)(authorization:\s*(?:bearer|basic)\s+)[^\s]+',r'(?i)(https?://)[^/\s:@]+:[^@\s]+@']
    original=text
    for pattern in patterns:
        text=re.sub(pattern,lambda m:(m.group(1) if m.lastindex else '')+'[REDACTED]',text)
    text=re.sub(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----','[PRIVATE KEY REDACTED]',text,flags=re.S)
    return text, text!=original

def _terminate(process):
    if process.poll() is not None: return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
    else:
        os.killpg(process.pid,signal.SIGTERM)
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=5)

def run_process(argv,cwd,timeout,cancel,on_started,env=None,secret_values=()):
    if not argv or not all(isinstance(v,str) and '\x00' not in v for v in argv):
        fail('invalid_command','Command must be a nonempty argv array.')
    executable=_executable(argv,cwd)
    if not executable or not Path(executable).is_file():
        fail('missing_executable','Approved executable was not found.')
    if Path(executable).suffix.lower() in {'.cmd','.bat'}:
        fail('shell_shim','Use the underlying executable (for npm: node plus npm-cli.js) or an explicitly approved shell script entrypoint.')
    if Path(executable).stem.lower()=='git':
        fail('product_git_command','Verification does not run Git commands in the product.')
    actual=[str(executable),*argv[1:]]
    if any(value and any(value in argument for argument in actual) for value in secret_values):
        fail('secret_in_argv','Secrets cannot be supplied in process arguments.')
    env=_process_environment() if env is None else env
    options={'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
    process=subprocess.Popen(actual,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**options)
    close_job=_windows_job(process)
    buffers={'stdout':bytearray(),'stderr':bytearray()}; truncated={'stdout':False,'stderr':False}
    def drain(name,stream):
        while True:
            chunk=stream.read(4096)
            if not chunk: break
            room=max(0,1024*1024-len(buffers[name]))
            buffers[name].extend(chunk[:room])
            if len(chunk)>room: truncated[name]=True
        stream.close()
    workers=[threading.Thread(target=drain,args=(name,getattr(process,name)),daemon=True) for name in buffers]
    for worker in workers: worker.start()
    started=time.monotonic(); reason=None
    try:
        on_started(process.pid,actual)
        while process.poll() is None:
            if time.monotonic()-started>=timeout: reason='timeout'; _terminate(process); break
            if cancel(): reason='cancelled'; _terminate(process); break
            time.sleep(.1)
    except BaseException:
        _terminate(process)
        raise
    finally:
        close_job()
        if os.name!='nt':
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
        for worker in workers: worker.join(timeout=5)
    streams={}; changed=False
    for name,raw in buffers.items():
        streams[name],redacted=redact(bytes(raw)); changed=changed or redacted
        from .environment import redact_output
        cleaned=redact_output(streams[name],secret_values)
        if isinstance(cleaned,tuple): cleaned=cleaned[0]
        changed=changed or cleaned!=streams[name]; streams[name]=cleaned
    return {'argv':actual,'pid':process.pid,'exit_code':process.returncode,'duration_seconds':round(time.monotonic()-started,3),
            'termination':reason,'streams':streams,'truncated':any(truncated.values()) or any(w.is_alive() for w in workers),'redacted':changed}

class Execution:
    def __init__(self,journal):
        self.journal=journal
        self.workflow=Workflow(journal)

    def execute(self,operation,p):
        validate(p,execution_operations()[operation])
        if operation=='begin_implementation': return self.begin(**p)
        if operation=='finish_implementation': return self.finish(**p)
        if operation=='run_checks': return self.run_checks(**p)
        if operation=='check_edit_scope': return self.check_edit_scope(**p)
        if operation=='execute_database':
            from .execution_database import execute_database
            return execute_database(self,**p)
        if operation in {'plan_database_recovery','record_database_recovery'}:
            from .database_recovery import DatabaseRecovery
            return DatabaseRecovery(self).execute(operation,p)
        if operation=='get_database_execution':
            result=self.journal.read().get('db_executions',{}).get('database/'+p['request_id'])
            if result is None: fail('unknown_database_execution','Database request is not recorded.')
            return result
        if operation=='reconcile_execution': return self.reconcile(**p)
        if operation=='cancel_verification':
            def change(state):
                campaign=state.get('verification',{}).get(p['campaign_id'])
                if not campaign or campaign['owner']!=p['owner']: fail('owner_mismatch','Verification owner does not match.')
                if campaign['outcome']=='running':
                    campaign['cancel_requested']=True
                    emit(state,'verification_cancel_requested',{'campaign_id':p['campaign_id']})
                return {'campaign_id':p['campaign_id'],'cancel_requested':campaign.get('cancel_requested',False),'outcome':campaign['outcome']}
            return self.journal.transaction(change)
        if operation=='list_implementations':
            return [i for i in self.journal.read().get('implementations',{}).values() if i['run_id']==p['run_id']]
        if operation=='get_verification': return self.get_verification(**p)
        fail('unknown_operation','Unknown execution operation.')

    def _root(self,workspace_id):
        return Path(self.journal.read()['workspaces'][workspace_id]['root'])

    def _environment_manager(self):
        from .environment import Environment
        return Environment(self.journal.path.parents[2])

    def _environment_bindings(self,basis):
        if not basis.get('environment_refs'): return []
        manager=self._environment_manager()
        return [manager.validate_contract(self.workflow.load_artifact(ref)['payload'])
                for ref in basis.get('environment_refs',[])]

    def _role_environment(self,basis,environment_ref=None,role=None):
        refs=basis.get('environment_refs',[])
        if role is None:
            if environment_ref is not None and environment_ref not in refs: fail('unapproved_environment','Runner environment must be pinned by the current Gate B.')
            return {},(),None
        if environment_ref is None and len(refs)==1: environment_ref=refs[0]
        if environment_ref not in refs: fail('unapproved_environment','Runner environment must be pinned by the current Gate B.')
        contract=self.workflow.load_artifact(environment_ref)['payload']
        if role not in contract['roles']: fail('unapproved_environment_role','The process role was not approved for this unit.')
        manager=self._environment_manager(); manager.validate_contract(contract)
        resolved=manager.resolve(contract['profile_id'],role=role)
        return resolved.env,resolved.secret_values,resolved.binding

    @staticmethod
    def _in_scope(payload,path):
        if any(item['path']==path for item in payload['files']): return True
        return any(path.startswith(group['output_root']+'/') and any(fnmatch.fnmatchcase(path[len(group['output_root'])+1:],pattern) for pattern in group['patterns'])
                   for group in payload.get('generated_files',[]))

    def check_edit_scope(self,session_id,owner,changes):
        state=self.journal.read(); session=state.get('execution_sessions',{}).get(session_id)
        if not session or session['owner']!=owner or session['status']!='open': fail('owner_mismatch','An open owned implementation session is required.')
        self._lease_state(state,session['lease_id'],owner)
        if self.workflow._basis(state,session['run_id'],session['unit_id'])!=session['basis']: fail('basis_changed','Approval changed before edit.')
        if session.get('mode')=='observe': fail('observation_readonly','Observation sessions do not authorize edits.')
        payload=self.workflow.load_artifact(session['basis']['scope_ref'])['payload']
        root=self._root(session['workspace_id']); declared={item['path']:item for item in payload['files']}
        from .scope import _observe
        # Compare every proposed action with the current filesystem, then with the
        # approved net action. A prior approved create may receive a same-scope fix.
        for change in changes:
            path=change['path']; actual=_observe(root,path)
            if not self._in_scope(payload,path): fail('outside_scope','Proposed path is outside the approved scope.')
            if (change['action']=='create') != (actual is None): fail('edit_action_mismatch','Proposed action does not match the current file state.')
            item=declared.get(path)
            if item:
                allowed={item['action']}
                if session.get('continued_from') and item['action']=='create': allowed.add('modify')
                if change['action'] not in allowed: fail('edit_action_mismatch','Proposed action differs from the approved net action.')
            elif not any(change['action'] in group['actions'] and path.startswith(group['output_root']+'/') and any(fnmatch.fnmatchcase(path[len(group['output_root'])+1:],pattern) for pattern in group['patterns']) for group in payload.get('generated_files',[])):
                fail('edit_action_mismatch','Generated action is not approved.')
        return {'allowed':True,'scope_ref':session['basis']['scope_ref'],'changes':changes,'notice':'Preflight only; native editors are not intercepted.'}

    @staticmethod
    def _lease_state(state,lease_id,owner):
        lease=state.get('leases',{}).get(lease_id)
        if not lease or lease['owner']!=owner or lease.get('released_at'):
            fail('lease_lost','Cooperative writer ownership is no longer valid.')
        return lease

    def _reserve(self,key,fingerprint,run_id,unit_id,owner,skill,extra=None):
        # The first durable record atomically owns the request, stage and lease.
        def reserve(state):
            prior=state.setdefault('execution_requests',{}).get(key)
            if prior:
                if prior['fingerprint']!=fingerprint: fail('request_conflict','Request id was reused with different inputs.')
                return prior,False
            basis=self.workflow._basis(state,run_id,unit_id)
            pins=[basis['unit_ref'],basis['test_ref']]
            if basis.get('scope_ref'): pins.append(basis['scope_ref'])
            pins.extend(basis.get('environment_refs',[])); pins.extend(basis.get('db_plan_refs',[]))
            stage=self.workflow._operate(state,'start_stage',{'run_id':run_id,'unit_id':unit_id,'owner':owner,'skill':skill,'input_refs':pins})
            lease=self.workflow._operate(state,'acquire_lease',{'run_id':run_id,'unit_id':unit_id,'owner':owner,'stage_run_id':stage['stage_run_id'],'ttl_seconds':3600})
            row={'request_key':key,'fingerprint':fingerprint,'run_id':run_id,'unit_id':unit_id,'owner':owner,'workspace_id':basis['workspace_id'],
                 'basis':basis,'stage_run_id':stage['stage_run_id'],'lease_id':lease['lease_id'],'controller':process_identity(os.getpid()),
                 'status':'starting','created_at':now(),**(extra or {})}
            state['execution_requests'][key]=row
            state.setdefault('execution_order',[]).append(key)
            emit(state,'execution_reserved',row)
            return row,True
        return self.journal.transaction(reserve)

    def _close(self,state,row,outcome,refs=None):
        """Evidence, stage outcome, and ownership release share one commit."""
        self.workflow._require_runtime(state,row['run_id'])
        stage=state['stages'][row['stage_run_id']]
        if stage['status']=='running':
            self.workflow._operate(state,'finish_stage',{'stage_run_id':row['stage_run_id'],'owner':row['owner'],'status':outcome,'output_refs':refs if refs is not None else stage['output_refs']})
        lease=state['leases'][row['lease_id']]
        if not lease.get('released_at'):
            self.workflow._operate(state,'release_lease',{'lease_id':row['lease_id'],'owner':row['owner']})

    def _fail(self,key,error):
        def change(state):
            row=state['execution_requests'][key]
            if row['status'] in ['finished','failed','interrupted']: return
            row.update(status='failed',error=error,finished_at=now())
            self._close(state,row,'failed')
            emit(state,'execution_failed',{'request_key':key,'error':error})
        self.journal.transaction(change)

    @staticmethod
    def _prior(state,row):
        if row.get('session_id'): return state['execution_sessions'][row['session_id']]
        if row.get('campaign_id') in state.get('verification',{}): return state['verification'][row['campaign_id']]
        return {**row,'pending':row['status'] in ['starting','running','active']}

    def begin(self,run_id,unit_id,owner,request_id,mode='change'):
        key='implementation/'+request_id
        fingerprint=sha256(encoded({'run_id':run_id,'unit_id':unit_id,'owner':owner,'mode':mode}))
        row,new=self._reserve(key,fingerprint,run_id,unit_id,owner,'dev-implement')
        if not new: return self._prior(self.journal.read(),row)
        try:
            before=capture_snapshot(self.journal,row['workspace_id'],label='before implementation',request_id=uid('capture'))
            metadata=git_metadata(self._root(row['workspace_id']))
            if not snapshot_matches(self.journal,before['snapshot_id'],row['workspace_id']): fail('source_changed','Source changed before implementation handoff.')
            extra={'mode':mode}
            if row['basis'].get('contract_version')=='2.1':
                from .scope import preflight_scope
                payload=self.workflow.load_artifact(row['basis']['scope_ref'])['payload']
                state=self.journal.read()
                prior=state.get('implementations',{}).get(state.get('applied',{}).get(run_id+'/'+unit_id),{})
                if prior.get('basis')==row['basis'] and prior.get('outcome')=='completed':
                    prior_files={f['path']:f for f in state['snapshots'][prior['snapshot_after']]['manifest']['files']}
                    actual_files={f['path']:f for f in before['manifest']['files']}
                    for path in set(prior_files)|set(actual_files):
                        if self._in_scope(payload,path) and prior_files.get(path,{}).get('sha256')!=actual_files.get(path,{}).get('sha256'):
                            fail('scope_baseline_changed','Previously applied scoped files changed outside this implementation; preserve and reconcile them.')
                    extra.update(continued_from=prior['implementation_id'],scope_origin_snapshot=prior.get('scope_origin_snapshot',prior['snapshot_before']),
                                 scope_preflight={'passed':True,'kind':'prior_approved_scoped_baseline','snapshot_id':before['snapshot_id']})
                else:
                    if mode=='observe' and payload['mode']!='observe': fail('observation_requires_implementation','Fresh observation requires a prior completed implementation or an approved observation-only scope.')
                    extra.update(scope_preflight=preflight_scope(payload,self._root(row['workspace_id']),run_id=run_id,workspace_id=row['workspace_id'],unit_id=unit_id,source_digest=before['manifest_sha256']),scope_origin_snapshot=before['snapshot_id'])
                if payload['mode']=='observe' and mode!='observe': fail('observation_mode_required','The approved scope permits observation only.')
                extra['environment_bindings']=self._environment_bindings(row['basis'])
            session={**row,**extra,'session_id':uid('implementation-session'),'snapshot_before':before['snapshot_id'],'git_before':metadata,'status':'open'}
            def change(state):
                self._lease_state(state,row['lease_id'],owner)
                if self.workflow._basis(state,run_id,unit_id)!=row['basis']: fail('basis_changed','Approval basis changed before implementation.')
                state.setdefault('execution_sessions',{})[session['session_id']]=session
                state['execution_requests'][key].update(status='active',session_id=session['session_id'])
                emit(state,'implementation_started',{'session_id':session['session_id'],'snapshot_before':session['snapshot_before'],'basis':row['basis']})
                return session
            return self.journal.transaction(change)
        except BaseException as exc:
            self._fail(key,getattr(exc,'code',type(exc).__name__))
            raise

    def _artifact(self,state,kind,payload,report,row,inputs,artifact_id):
        return self.workflow.store_evidence_artifact(state,artifact_id=artifact_id,kind=kind,run_id=row['run_id'],unit_id=row['unit_id'],
            payload=payload,report=report,input_refs=inputs,stage_run_id=row['stage_run_id'])['ref']

    def finish(self,session_id,owner,summary,outcome):
        initial=self.journal.read()
        session=initial.get('execution_sessions',{}).get(session_id)
        if not session or session['owner']!=owner: fail('owner_mismatch','Implementation session does not belong to this owner.')
        self.workflow._require_runtime(initial,session['run_id'])
        if session['status']=='closed':
            def replay(state):
                self._close(state,session,'succeeded' if state['implementations'][session['implementation_id']]['outcome']=='completed' else 'failed')
                return state['implementations'][session['implementation_id']]
            return self.journal.transaction(replay)
        if session['status']!='open': fail('session_interrupted','Start a new implementation request after reconciliation.')
        self._require_database_idle(initial,session_id)
        self._lease_state(self.journal.read(),session['lease_id'],owner)
        try:
            after=capture_snapshot(self.journal,session['workspace_id'],label='after implementation',request_id=uid('capture'))
        except HarnessError as exc:
            def failure(state):
                state['execution_sessions'][session_id]['last_capture_error']=exc.code
                emit(state,'implementation_capture_failed',{'session_id':session_id,'error':exc.code,'may_have_source_changes':True})
            self.journal.transaction(failure)
            raise
        def record(state):
            self.workflow._require_runtime(state,session['run_id'])
            current=state['execution_sessions'][session_id]
            if current['status']=='closed': return state['implementations'][current['implementation_id']]
            self._require_database_idle(state,session_id)
            self._lease_state(state,session['lease_id'],owner)
            before=state['snapshots'][session['snapshot_before']]
            old={f['path']:f['sha256'] for f in before['manifest']['files']}
            new={f['path']:f['sha256'] for f in after['manifest']['files']}
            changed=sorted(p for p in set(old)|set(new) if old.get(p)!=new.get(p))
            try: basis_ok=self.workflow._basis(state,session['run_id'],session['unit_id'])==session['basis']
            except HarnessError: basis_ok=False
            git_ok=git_metadata(self._root(session['workspace_id']))==session['git_before']
            source_ok=snapshot_matches(self.journal,after['snapshot_id'],session['workspace_id'])
            scope_result=None; database_result=None; environment_ok=True
            if session['basis'].get('contract_version')=='2.1':
                from .scope import compare_scope
                payload=self.workflow.load_artifact(session['basis']['scope_ref'])['payload']
                origin=state['snapshots'][session['scope_origin_snapshot']]['manifest']['files']
                cumulative={f['path']:f for f in before['manifest']['files'] if not self._in_scope(payload,f['path'])}
                cumulative.update({f['path']:f for f in origin if self._in_scope(payload,f['path'])})
                scope_result=compare_scope(payload,list(cumulative.values()),after['manifest']['files'])
                if session.get('mode')=='observe' and changed:
                    scope_result['passed']=False; scope_result['violations'].append({'reason':'observation_changed_source','paths':changed})
                outside=[item['path'] for item in scope_result['violations'] if item.get('reason')=='outside_scope']
                from .execution_database import database_completion
                database_result=database_completion(self,session['basis'],session=session,state=state)
                try: environment_ok=self._environment_bindings(session['basis'])==session.get('environment_bindings',[])
                except HarnessError: environment_ok=False
            else:
                allowed=self.workflow.load_artifact(session['basis']['unit_ref'])['payload'].get('allowed_paths',[])
                outside=[p for p in changed if not allowed or not any(fnmatch.fnmatchcase(p,pattern) for pattern in allowed)]
            scope_ok=scope_result['passed'] if scope_result is not None else not outside
            database_ok=database_result['passed'] if database_result is not None else True
            actual=outcome if basis_ok and git_ok and source_ok and scope_ok and database_ok and environment_ok else 'needs_reconciliation'
            receipt={'implementation_id':uid('implementation'),'session_id':session_id,'run_id':session['run_id'],'unit_id':session['unit_id'],
                'workspace_id':session['workspace_id'],'stage_run_id':session['stage_run_id'],'basis':session['basis'],
                'snapshot_before':session['snapshot_before'],'snapshot_after':after['snapshot_id'],'source_digest':after['manifest_sha256'],
                'created_at':now(),'outcome':actual,'summary':summary,'changed_files':changed,'outside_declared_paths':outside,
                'source_git_unchanged':git_ok,'basis_current':basis_ok,'source_current':source_ok,
                'scope_origin_snapshot':session.get('scope_origin_snapshot',session['snapshot_before']),
                'scope_result':scope_result,'database_comparison':database_result,'environment_current':environment_ok,
                'environment_bindings':session.get('environment_bindings',[]),'mode':session.get('mode','change')}
            report='# 구현 결과\n\n'+summary+'\n\n결과: '+actual+'\n\n변경 파일:\n'+''.join('- '+p+'\n' for p in changed)
            receipt['ref']=self._artifact(state,'implementation-receipt',receipt,report,session,[session['basis']['unit_ref'],session['basis']['test_ref']],'implementation-'+session['unit_id'])
            state.setdefault('implementations',{})[receipt['implementation_id']]=receipt
            if actual=='completed': state.setdefault('applied',{})[session['run_id']+'/'+session['unit_id']]=receipt['implementation_id']
            current.update(status='closed',implementation_id=receipt['implementation_id'])
            state['execution_requests'][session['request_key']].update(status='finished',finished_at=now())
            self._close(state,session,'succeeded' if actual=='completed' else 'failed',[receipt['ref']])
            emit(state,'implementation_finished',{'implementation_id':receipt['implementation_id'],'outcome':actual,'ref':receipt['ref']})
            return receipt
        return self.journal.transaction(record)

    @staticmethod
    def _require_database_idle(state,session_id):
        if any(row.get('session_id')==session_id and row.get('status')=='running'
               for row in state.get('db_executions',{}).values()):
            fail('db_adapter_active','Wait for the database attempt or reconcile an exited controller before finishing implementation.')

    def _implementation(self,implementation_id):
        state=self.journal.read()
        implementation=state.get('implementations',{}).get(implementation_id)
        if not implementation or implementation['outcome']!='completed': fail('implementation_incomplete','A completed implementation receipt is required.')
        if state.get('applied',{}).get(implementation['run_id']+'/'+implementation['unit_id'])!=implementation_id: fail('implementation_superseded','This is not the currently applied implementation.')
        if self.workflow.implementation_basis(implementation['run_id'],implementation['unit_id'])!=implementation['basis']: fail('basis_changed','Implementation was made for a different approval basis.')
        if not snapshot_matches(self.journal,implementation['snapshot_after'],implementation['workspace_id']): fail('source_changed','Workspace differs from the recorded implementation snapshot.')
        self._environment_bindings(implementation['basis'])
        return implementation

    def _run_check_process(self,check,root,basis,implementation,attempt,deadline,cancel,launched):
        env,values,binding=self._role_environment(basis,check.get('environment_ref'),check.get('role'))
        cwd=root if check['cwd']=='.' else root.joinpath(*safe_relative(check['cwd']).parts)
        if not check.get('runner'):
            if binding:
                result=run_process(check['argv'],cwd,min(check['timeout_seconds'],deadline-time.monotonic()),cancel,launched,env=env,secret_values=values)
                result['environment_binding']=binding
                return result
            return run_process(check['argv'],cwd,min(check['timeout_seconds'],deadline-time.monotonic()),cancel,launched)
        from .runner import PreparedRunner
        runner=PreparedRunner(check['runner'],root,self.journal.path.parent/'evidence'/attempt['attempt_id'],implementation['source_digest'],attempt['attempt_id'],
                              lambda role:self._role_environment(basis,check.get('environment_ref'),role),cancel,deadline)
        result={}
        try:
            runner.start()
            env,values,binding=runner._env(check.get('role'))
            remaining=deadline-time.monotonic()
            if remaining<=0: fail('budget_exhausted','Preparation consumed the verification budget.')
            result=run_process(check['argv'],cwd,min(check['timeout_seconds'],remaining),cancel,launched,env=env,secret_values=values)
            result['environment_binding']=binding
        except (HarnessError,OSError) as exc:
            result={'error':getattr(exc,'code',type(exc).__name__),'exit_code':None,'termination':None,'streams':{},'truncated':False}
        finally:
            prepared=runner.close()
            try: runner.attach(self.journal)
            except (HarnessError,OSError) as exc:
                prepared['passed']=False; prepared['evidence_error']=getattr(exc,'code',type(exc).__name__)
            prepared['passed']=prepared['passed'] and all(item['status']=='attached' for item in prepared['evidence'] if item['required'])
            result['preparation']=prepared
        return result

    def run_checks(self,implementation_id,owner,request_id,check_ids=None):
        deadline=time.monotonic()+CAMPAIGN_BUDGET_SECONDS
        key='verification/'+request_id
        fingerprint=sha256(encoded({'implementation_id':implementation_id,'owner':owner,'check_ids':check_ids}))
        state=self.journal.read()
        prior=state.get('execution_requests',{}).get(key)
        if prior:
            if prior['fingerprint']!=fingerprint: fail('request_conflict','Verification request id was reused with different inputs.')
            return self._prior(state,prior)
        implementation=self._implementation(implementation_id); basis=implementation['basis']
        checks=self.workflow.load_artifact(basis['test_ref'])['payload']['checks']
        known={c['check_id'] for c in checks}; requested=set(check_ids or known)
        if not requested.issubset(known) or (check_ids and len(requested)!=len(check_ids)): fail('unknown_check','Requested checks are invalid or duplicated.')
        # No unproven partial-result carry: each campaign executes every required check.
        selected=requested|{c['check_id'] for c in checks if c['required']}
        row,new=self._reserve(key,fingerprint,implementation['run_id'],implementation['unit_id'],owner,'dev-verify',{'campaign_id':uid('campaign'),'implementation_id':implementation_id})
        if not new: return self._prior(self.journal.read(),row)
        root=self._root(row['workspace_id'])
        try:
            environment=environment_fingerprint(checks,root); initial_git=git_metadata(root)
            profile_bindings=self._environment_bindings(basis)
            campaign={**row,'test_ref':basis['test_ref'],'snapshot_id':implementation['snapshot_after'],'environment':environment,'environment_digest':sha256(encoded(environment)),'git_metadata':initial_git,'profile_bindings':profile_bindings,
                      'outcome':'running','check_results':{},'selected_checks':sorted(selected),'requested_checks':sorted(requested),'cancel_requested':False,'budget_seconds':CAMPAIGN_BUDGET_SECONDS}
            def begin(state):
                self._lease_state(state,row['lease_id'],owner)
                if self.workflow._basis(state,row['run_id'],row['unit_id'])!=basis: fail('basis_changed','Approval changed before verification.')
                state.setdefault('verification',{})[row['campaign_id']]=campaign
                state.setdefault('verification_order',[]).append(row['campaign_id'])
                state['execution_requests'][key]['status']='running'
                emit(state,'verification_started',{'campaign_id':row['campaign_id'],'implementation_id':implementation_id})
            self.journal.transaction(begin)
            for check in checks:
                if check['check_id'] not in selected: continue
                if time.monotonic()>=deadline: break
                attempt={'attempt_id':uid('attempt'),'campaign_id':row['campaign_id'],'check_id':check['check_id'],'started_at':now(),'result':'running','launch_state':'not_launched','check_contract':check,'implementation_id':implementation_id}
                def start(state):
                    self._lease_state(state,row['lease_id'],owner)
                    state.setdefault('verification_attempts',{})[attempt['attempt_id']]=attempt
                    emit(state,'check_started',{'attempt_id':attempt['attempt_id'],'check_id':check['check_id']})
                self.journal.transaction(start)
                def cancel():
                    state=self.journal.read()
                    self._lease_state(state,row['lease_id'],owner)
                    return state['verification'][row['campaign_id']].get('cancel_requested',False)
                def launched(pid,actual):
                    def update(state):
                        state['verification_attempts'][attempt['attempt_id']].update(pid=pid,process=process_identity(pid),actual_argv=actual,launch_state='identified')
                        emit(state,'check_process_started',{'attempt_id':attempt['attempt_id'],'pid':pid})
                    self.journal.transaction(update)
                result={}
                try:
                    self._implementation(implementation_id)
                    if self._environment_bindings(basis)!=profile_bindings: fail('environment_changed','Selected profile changed during verification.')
                    if environment_fingerprint(checks,root)!=environment or git_metadata(root)!=initial_git: fail('environment_changed','Source Git or runtime changed before check launch.')
                    if cancel(): fail('cancelled','Verification was cancelled before this check.')
                    cwd=root if check['cwd']=='.' else root.joinpath(*safe_relative(check['cwd']).parts)
                    from .registry import normal_root
                    normal_root(cwd)
                    if root!=cwd.resolve() and root not in cwd.resolve().parents: fail('path_escape','Check cwd escapes the product.')
                    def pending(state):
                        self._lease_state(state,row['lease_id'],owner)
                        if self.workflow._basis(state,row['run_id'],row['unit_id'])!=basis: fail('basis_changed','Approval changed before process launch.')
                        state['verification_attempts'][attempt['attempt_id']]['launch_state']='pid_pending'
                    remaining=deadline-time.monotonic()
                    if remaining<=0: fail('budget_exhausted','Total verification budget exhausted.')
                    self.journal.transaction(pending)
                    remaining=deadline-time.monotonic()
                    if remaining<=0: fail('budget_exhausted','Total verification budget exhausted.')
                    result=self._run_check_process(check,root,basis,implementation,attempt,deadline,cancel,launched)
                    applicable=snapshot_matches(self.journal,implementation['snapshot_after'],row['workspace_id']) and git_metadata(root)==initial_git
                    parsed=case_result(check,result); result['case_evidence']=parsed
                    if result.get('termination')=='cancelled': status='interrupted'
                    elif result.get('error') or not applicable or result.get('truncated') or not result.get('preparation',{}).get('passed',True): status='blocked'
                    elif result['termination']=='timeout' or result['exit_code']!=check['expected_exit']: status='failed'
                    else: status=parsed['result']
                    result['source_applicable']=applicable
                except HarnessError as exc:
                    status='interrupted' if exc.code=='cancelled' else 'blocked'
                    result={'error':exc.code,'message':str(exc),'exit_code':None}
                except OSError as exc:
                    status='blocked'; result={'error':'process_launch_failed','message':type(exc).__name__,'exit_code':None}
                evidence=encoded(result); oid=self.journal.put_blob(evidence)
                def finished(state):
                    final=state['verification_attempts'][attempt['attempt_id']]
                    final.update(result=status,finished_at=now(),exit_code=result.get('exit_code'),evidence_oid=oid,evidence_sha256=sha256(evidence))
                    state['verification'][row['campaign_id']]['check_results'][check['check_id']]=copy.deepcopy(final)
                    emit(state,'check_finished',{'attempt_id':attempt['attempt_id'],'result':status})
                self.journal.transaction(finished)
                if status in ['interrupted','blocked']: break
            def finalize(state):
                current=state['verification'][row['campaign_id']]
                self._lease_state(state,row['lease_id'],owner)
                statuses=[current['check_results'].get(c['check_id'],{}).get('result','not_run') for c in checks if c['required']]
                outcome='passed' if statuses and all(s=='passed' for s in statuses) else 'failed' if 'failed' in statuses else 'interrupted' if 'interrupted' in statuses else 'blocked'
                try:
                    basis_current=self.workflow._basis(state,row['run_id'],row['unit_id'])==basis and state['applied'].get(row['run_id']+'/'+row['unit_id'])==implementation_id
                    applicable=basis_current and snapshot_matches(self.journal,implementation['snapshot_after'],row['workspace_id']) and git_metadata(root)==initial_git and environment_fingerprint(checks,root)==environment and self._environment_bindings(basis)==profile_bindings
                except (HarnessError,OSError): applicable=False; basis_current=False
                if not applicable or time.monotonic()>=deadline: outcome='blocked'
                if outcome == 'passed':
                    try:
                        current['tool_evidence'] = self._tool_evidence(state, implementation, current)
                    except (HarnessError, OSError) as exc:
                        current['tool_evidence_error'] = getattr(exc, 'code', type(exc).__name__)
                        outcome = 'blocked'
                if current.get('cancel_requested'): outcome='interrupted'
                current.update(outcome=outcome,finished_at=now(),basis_current=basis_current,source_and_environment_current=applicable,budget_exhausted=time.monotonic()>=deadline)
                report='# 검증 결과\n\n결과: '+outcome+'\n\n구현: '+implementation_id+'\n\n'+''.join('- '+c['check_id']+': '+current['check_results'].get(c['check_id'],{}).get('result','not_run')+'\n' for c in checks)+'\n승인된 검사 계약과 실행 증거에 한정된 결과입니다.\n'
                current['ref']=self._artifact(state,'verification-report',copy.deepcopy(current),report,row,[implementation['ref'],basis['unit_ref'],basis['test_ref']],'verification-'+row['unit_id'])
                if outcome=='passed':
                    self._fulfill_changes(state,implementation,basis,current)
                state['execution_requests'][key].update(status='finished',finished_at=now())
                self._close(state,row,'succeeded' if outcome=='passed' else 'interrupted' if outcome=='interrupted' else 'failed',[current['ref']])
                emit(state,'verification_finished',{'campaign_id':row['campaign_id'],'outcome':outcome,'ref':current['ref']})
                return current
            return self.journal.transaction(finalize)
        except BaseException as exc:
            def interrupted(state):
                current=state.get('verification',{}).get(row['campaign_id'])
                if current and current['outcome']!='running': return
                if current: current.update(outcome='interrupted',finished_at=now(),error=getattr(exc,'code',type(exc).__name__))
                for attempt in state.get('verification_attempts',{}).values():
                    if attempt['campaign_id']==row['campaign_id'] and attempt['result']=='running': attempt.update(result='interrupted',finished_at=now())
                state['execution_requests'][key].update(status='failed',finished_at=now(),error=getattr(exc,'code',type(exc).__name__))
                self._close(state,row,'interrupted')
                emit(state,'verification_interrupted',{'campaign_id':row['campaign_id'],'error':getattr(exc,'code',type(exc).__name__)})
            self.journal.transaction(interrupted)
            raise

    def _tool_evidence(self, state, implementation, campaign):
        """Validate declared external observations from the actual runner's blobs."""
        run = state['runs'][implementation['run_id']]
        if run.get('tool_policy_version') != '1':
            return []
        from .tool_policy import validate_completion_evidence
        basis = implementation['basis']
        review = state['reviews'][basis['gate_a_review_id']]
        system = self.workflow._one([self.workflow._load(state, ref) for ref in review['input_refs']], 'system-design')
        test = self.workflow._load(state, basis['test_ref'])
        gate_b = state['reviews'][basis['review_id']]
        approved_refs = review['input_refs'] + gate_b['input_refs'] + test['manifest']['input_refs']
        loaded = [self.workflow._load(state, ref) for ref in gate_b['input_refs']]
        targets = self.workflow._tool_database_targets(system['payload']['tool_plan'], implementation['unit_id'], loaded)
        def validate_source(source):
            if not source.startswith('artifact:'):
                return
            artifact_id, revision_id, digest = source[len('artifact:'):].split('/')
            ref = {'artifact_id': artifact_id, 'revision_id': revision_id, 'sha256': digest}
            self.workflow._require_refs(state, [ref], implementation['run_id'])
            if ref not in approved_refs:
                fail('pin_mismatch', 'Runner artifact sources must belong to the exact approved input refs.')
        return validate_completion_evidence(system['payload']['tool_plan'], implementation['unit_id'], test['payload'],
                                            campaign, self.journal.get_blob, build_id=implementation['source_digest'],
                                            expected_database_targets=targets, validate_source_ref=validate_source)

    def _fulfill_changes(self,state,implementation,basis,campaign):
        for change in state.get('changes',{}).values():
            if change.get('run_id')!=implementation['run_id'] or change.get('status')!='contract_resolved' or basis['unit_ref'] not in change.get('target_refs',[]): continue
            completed=change.setdefault('verified_units',{})
            completed[implementation['unit_id']]=campaign['campaign_id']
            units=change.get('resolved_unit_ids',change.get('unit_ids',[]))
            valid=True
            for unit in units:
                prior=state['verification'].get(completed.get(unit),{})
                try:
                    projection=self._completion(state,prior['implementation_id'],allow_pending_campaign=campaign['campaign_id'])
                    valid=valid and projection['eligible_complete'] and projection['latest_campaign']['campaign_id']==prior['campaign_id']
                except (HarnessError,KeyError,IndexError): valid=False
            if units and valid:
                change.update(status='fulfilled',fulfilled_at=now())
                emit(state,'change_fulfilled',{'change_id':change['change_id'],'campaigns':completed})

    def reconcile(self,kind,request_id,owner,action,external_writers_stopped=False):
        key=kind+'/'+request_id
        def inspect(state):
            row=state.get('execution_requests',{}).get(key)
            if not row or row['owner']!=owner: fail('owner_mismatch','Execution request owner does not match.')
            controller=observed_process(row.get('controller'))
            attempts=[a for a in state.get('verification_attempts',{}).values() if a.get('campaign_id')==row.get('campaign_id') and a['result']=='running']
            children=[observed_process(a.get('process')) for a in attempts if a.get('launch_state')=='identified']
            unknown=any(a.get('launch_state')=='pid_pending' for a in attempts)
            finished=row['status'] in ['finished','failed','interrupted']
            managed_stopped=controller['state']=='exited' and all(c['state']=='exited' for c in children) and not unknown
            acknowledgement_required=kind=='implementation' and not external_writers_stopped
            safe=not finished and managed_stopped and not acknowledgement_required
            return row,{'request_key':key,'status':row['status'],'controller':controller,'children':children,'unidentified_launch':unknown,'can_reconcile':safe,'source_observation_required':kind=='implementation' and not finished,
                'external_writers_stopped_acknowledgement_required':acknowledgement_required,'notice':'Controller exit does not prove external editors or services have stopped. Ownership is cooperative, not OS access isolation.'}
        row,view=inspect(self.journal.read())
        if action=='reconcile': self.workflow._require_runtime(self.journal.read(),row['run_id'])
        if action=='status' or not view['can_reconcile']: return view
        def change(state):
            self.workflow._require_runtime(state,row['run_id'])
            current,fresh=inspect(state)
            if current!=row or not fresh['can_reconcile']: fail('reconcile_race','Execution changed; inspect again.')
            current.update(status='interrupted',finished_at=now())
            if current.get('session_id'):
                state['execution_sessions'][current['session_id']].update(status='interrupted',finished_at=now())
            if current.get('campaign_id') in state.get('verification',{}):
                state['verification'][current['campaign_id']].update(outcome='interrupted',finished_at=now(),reconciled=True)
            for attempt in state.get('verification_attempts',{}).values():
                if attempt.get('campaign_id')==current.get('campaign_id') and attempt['result']=='running': attempt.update(result='interrupted',finished_at=now())
            self._close(state,current,'interrupted')
            emit(state,'execution_reconciled',{'request_key':key,'controller':fresh['controller'],'children':fresh['children']})
            return {**fresh,'status':'interrupted','can_reconcile':False,'reconciled':True}
        return self.journal.transaction(change)

    def get_verification(self,implementation_id):
        return self._completion(self.journal.read(),implementation_id)

    def _completion(self,state,implementation_id,allow_pending_campaign=None):
        """Shared currentness predicate for user projection and ChangeIntent completion."""
        records=self._campaigns(state,implementation_id)
        requests=[state['execution_requests'][key] for key in state.get('execution_order',[]) if state['execution_requests'][key].get('implementation_id')==implementation_id]
        latest_request=requests[-1] if requests else None
        pending=any(r.get('implementation_id')==implementation_id and r.get('status') in ['starting','running'] and r.get('campaign_id')!=allow_pending_campaign for r in state.get('execution_requests',{}).values())
        request_failed=bool(latest_request and latest_request['status'] in ['failed','interrupted'])
        if not records: return {'implementation_id':implementation_id,'outcome':'pending' if pending else 'interrupted' if request_failed else 'not_run','latest_request':latest_request,'eligible_complete':False,'campaigns':[]}
        latest=records[-1]; current=True; reason=None
        try:
            implementation=state.get('implementations',{}).get(implementation_id)
            if not implementation or implementation['outcome']!='completed': fail('implementation_incomplete','A completed implementation receipt is required.')
            if state.get('applied',{}).get(implementation['run_id']+'/'+implementation['unit_id'])!=implementation_id: fail('implementation_superseded','Implementation is no longer applied.')
            if self.workflow._basis(state,implementation['run_id'],implementation['unit_id'])!=implementation['basis']: fail('basis_changed','Approval basis changed.')
            if not snapshot_matches(self.journal,implementation['snapshot_after'],implementation['workspace_id']): fail('source_changed','Source differs from the implementation snapshot.')
            checks=self.workflow.load_artifact(implementation['basis']['test_ref'])['payload']['checks']
            if environment_fingerprint(checks,self._root(implementation['workspace_id']))!=latest['environment']: fail('environment_changed','Observed runtime differs from this verification.')
            if git_metadata(self._root(implementation['workspace_id']))!=latest.get('git_metadata'): fail('git_metadata_changed','Observed source Git metadata differs from this verification.')
            if self._environment_bindings(implementation['basis'])!=latest.get('profile_bindings',[]): fail('environment_changed','Personal environment changed since verification.')
            if implementation['basis'].get('db_plan_refs'):
                from .execution_database import database_completion
                if not database_completion(self,implementation['basis'],state=state).get('passed'): fail('database_incomplete','Current DB plan verification is incomplete.')
            self._tool_evidence(state, implementation, latest)
        except (HarnessError,OSError) as exc: current=False; reason=getattr(exc,'code',type(exc).__name__)
        valid=bool(latest['check_results'])
        for result in latest['check_results'].values():
            try: valid=valid and sha256(self.journal.get_blob(result['evidence_oid']))==result['evidence_sha256']
            except (HarnessError,KeyError): valid=False
        return {'implementation_id':implementation_id,'latest_campaign':latest,'campaigns':[{'campaign_id':c['campaign_id'],'outcome':c['outcome'],'created_at':c['created_at']} for c in records],
            'outcome':'pending_reverification' if pending else 'interrupted' if request_failed else latest['outcome'],'latest_request':latest_request,'source_and_basis_current':current,'inapplicable_reason':reason,'evidence_valid':valid,
            'eligible_complete':not pending and not request_failed and latest['outcome']=='passed' and current and valid}

    @staticmethod
    def _campaigns(state,implementation_id):
        records=state.get('verification',{})
        return [records[cid] for cid in state.get('verification_order',[]) if cid in records and records[cid]['implementation_id']==implementation_id]
