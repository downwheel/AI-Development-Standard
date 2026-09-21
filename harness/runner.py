"""Bounded preparation around an approved project test runner.

Only processes started here are stopped. Product-specific assertions remain in
the versioned project runner; service ownership and attachments are observed here.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .common import fail, safe_relative, sha256
from .validation import obj

S={'type':'string','minLength':1,'maxLength':4000}
ID={'type':'string','pattern':'^[a-z0-9][a-z0-9_-]{0,95}$'}
COMMAND=obj({'argv':{'type':'array','items':S,'minItems':1,'maxItems':100},'cwd':S,
             'timeout_seconds':{'type':'integer','minimum':1,'maximum':120},
             'role':ID,'case_ids':{'type':'array','items':ID,'minItems':1,'maxItems':100}},
            ['argv','cwd','timeout_seconds','case_ids'])
SERVICE=obj({'service_id':ID,'argv':{'type':'array','items':S,'minItems':1,'maxItems':100},
             'cwd':S,'role':ID,'health_url':S,
             'readiness_seconds':{'type':'integer','minimum':1,'maximum':60}},
            ['service_id','argv','cwd','health_url','readiness_seconds'])
ATTACHMENT=obj({'evidence_id':ID,'path':S,'format':{'type':'string','enum':['text','json']},
                'required':{'type':'boolean'},'max_bytes':{'type':'integer','minimum':1,'maximum':1048576}},['evidence_id','path','format','required','max_bytes'])
RUNNER_SCHEMA=obj({'kind':{'type':'string','enum':['project-runner']},
                   'services':{'type':'array','items':SERVICE,'maxItems':5},
                   'fixture':obj({'setup':COMMAND,'cleanup':COMMAND,'namespace':ID},['setup','cleanup','namespace']),
                   'evidence':{'type':'array','items':ATTACHMENT,'maxItems':20}},['kind'])


def command_cwd(root,value):
    from .history import _no_links
    path=root if value=='.' else root.joinpath(*safe_relative(value).parts)
    _no_links(path)
    if not path.is_dir() or root.resolve() not in (path.resolve(),*path.resolve().parents):
        fail('runner_path_escape','Runner cwd must be an existing project directory.')
    return path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def health_address(url):
    parsed=urllib.parse.urlsplit(url)
    try: port=parsed.port
    except ValueError: fail('invalid_health_url','Invalid health port.')
    if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'} or not port or parsed.username or parsed.password or parsed.fragment or parsed.query:
        fail('invalid_health_url','Health checks require an explicit local HTTP host and port without credentials or query.')
    return parsed.hostname,port


class PreparedRunner:
    def __init__(self,contract,root,scratch,build_id,run_id,resolve_role,cancel,deadline):
        self.contract=contract or {'kind':'project-runner'}
        self.root=Path(root); self.scratch=Path(scratch); self.build_id=build_id; self.run_id=run_id
        self.resolve_role=resolve_role; self.cancel=cancel; self.deadline=deadline
        self.services=[]; self.fixture_started=False; self.secrets=set()
        self.receipt={'services':[],'fixture':{'status':'not_applicable'},'cleanup':{'status':'not_required'},'evidence':[]}

    def _env(self,role=None):
        from .environment import base_process_environment
        env,values,binding=self.resolve_role(role)
        self.secrets.update(values)
        result=base_process_environment()
        result.update(env)
        result.update({'HARNESS_EVIDENCE_DIR':str(self.scratch),'HARNESS_BUILD_ID':self.build_id,
                       'HARNESS_RUN_ID':self.run_id,'HARNESS_FIXTURE_NAMESPACE':self.contract.get('fixture',{}).get('namespace','')})
        return result,values,binding

    def _command(self,command,cleanup=False):
        from .execution import run_process,case_result
        env,values,binding=self._env(command.get('role'))
        remaining=30 if cleanup else self.deadline-time.monotonic()
        if remaining<=0: fail('budget_exhausted','Preparation budget exhausted.')
        result=run_process(command['argv'],command_cwd(self.root,command['cwd']),min(command['timeout_seconds'],remaining),
                           (lambda:False) if cleanup else self.cancel,lambda *args:None,env=env,secret_values=values)
        parsed=case_result(command,result)
        result.update(case_evidence=parsed,environment_binding=binding)
        result['passed']=result['exit_code']==0 and not result['termination'] and not result['truncated'] and parsed['result']=='passed'
        return result

    def start(self):
        from .history import _no_links
        from .execution import _executable,_windows_job,process_identity
        _no_links(self.scratch); self.scratch.mkdir(parents=True,exist_ok=False)
        fixture=self.contract.get('fixture')
        if fixture:
            self.fixture_started=True
            self.receipt['fixture']=self._command(fixture['setup'])
            if not self.receipt['fixture']['passed']: fail('fixture_setup_failed','Fixture setup did not provide passing case evidence.')
        for spec in self.contract.get('services',[]):
            address=health_address(spec['health_url'])
            try:
                with socket.create_connection(address,timeout=.3):
                    fail('service_port_in_use','Approved service port is occupied; no existing process was reused or stopped.')
            except OSError: pass
            if self.cancel(): fail('cancelled','Preparation was cancelled.')
            cwd=command_cwd(self.root,spec['cwd']); exe=_executable(spec['argv'],cwd)
            if not exe or Path(exe).suffix.lower() in {'.cmd','.bat'} or Path(exe).stem.lower()=='git':
                fail('invalid_service_command','Use an approved executable and project script, without Git or shell shims.')
            env,values,binding=self._env(spec.get('role'))
            if any(value and any(value in arg for arg in spec['argv']) for value in values):
                fail('secret_in_argv','Secrets cannot be supplied in process arguments.')
            options={'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
            process=subprocess.Popen([exe,*spec['argv'][1:]],cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**options)
            close_job=_windows_job(process)
            record={'service_id':spec['service_id'],'process':process_identity(process.pid),'environment_binding':binding,
                    'health_verified':False,'stopped':False,'build_id':self.build_id,'run_id':self.run_id}
            buffers={'stdout':bytearray(),'stderr':bytearray()}; overflow=[]
            def drain(name,stream,buffers=buffers,overflow=overflow):
                try:
                    for chunk in iter(lambda:stream.read(4096),b''):
                        room=max(0,1048576-len(buffers[name])); buffers[name].extend(chunk[:room])
                        if len(chunk)>room: overflow.append(True)
                finally: stream.close()
            workers=[threading.Thread(target=drain,args=(name,getattr(process,name)),daemon=True) for name in buffers]
            for worker in workers: worker.start()
            self.services.append((process,close_job,record,buffers,workers,overflow))
            self.receipt['services'].append(record)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            until=min(self.deadline,time.monotonic()+spec['readiness_seconds'])
            while time.monotonic()<until:
                if self.cancel(): fail('cancelled','Service readiness was cancelled.')
                if process.poll() is not None: fail('service_exited','Owned service exited before readiness.')
                try:
                    with opener.open(spec['health_url'],timeout=min(1,max(.1,until-time.monotonic()))) as response:
                        body=response.read(65537)
                        if response.status==200 and len(body)<=65536:
                            data=json.loads(body)
                            if data.get('build_id')==self.build_id and data.get('run_id')==self.run_id:
                                record['health_verified']=True; break
                except (OSError,ValueError,urllib.error.URLError): pass
                time.sleep(.15)
            if not record['health_verified']: fail('service_health_failed','Health must report the current HARNESS_BUILD_ID and HARNESS_RUN_ID.')
        return self.receipt

    def attach(self,journal):
        from .history import _no_links
        from .environment import redact_output,redact_data
        from .execution import redact
        for item in self.contract.get('evidence',[]):
            relative=safe_relative(item['path']); path=self.scratch.joinpath(*relative.parts)
            _no_links(path)
            row={'evidence_id':item['evidence_id'],'path':relative.as_posix(),'format':item['format'],'required':item['required']}
            if not path.is_file():
                row['status']='missing'; self.receipt['evidence'].append(row); continue
            if path.stat().st_size>item['max_bytes']:
                row['status']='too_large'; self.receipt['evidence'].append(row); continue
            raw=path.read_bytes()
            try:
                text=raw.decode('utf-8')
                if item['format']=='json': json.loads(text)
            except (UnicodeError,ValueError):
                row['status']='invalid_content'; self.receipt['evidence'].append(row); continue
            # Browser storage state, cookies and auth headers must not become portable evidence.
            if any(word in text.lower() for word in ['"cookies"','"origins"','"authorization"','"access_token"','"refresh_token"']):
                row['status']='sensitive_content'; self.receipt['evidence'].append(row); continue
            cleaned=json.dumps(redact_data(json.loads(text),tuple(self.secrets)),ensure_ascii=False,indent=2) if item['format']=='json' else redact_output(text,tuple(self.secrets))
            if isinstance(cleaned,tuple): cleaned=cleaned[0]
            cleaned,_=redact(cleaned.encode('utf-8'))
            content=cleaned.encode('utf-8')
            # Preserve only a redacted file as well as a redacted journal blob.
            if content!=raw: path.write_bytes(content)
            row.update(status='attached',sha256=sha256(content),bytes=len(content),blob_oid=journal.put_blob(content),redacted=content!=raw)
            self.receipt['evidence'].append(row)

    def close(self):
        from .execution import _terminate,redact
        from .environment import redact_output
        errors=[]
        if self.fixture_started:
            try:
                self.receipt['cleanup']=self._command(self.contract['fixture']['cleanup'],cleanup=True)
                if not self.receipt['cleanup']['passed']: errors.append('fixture_cleanup_failed')
            except Exception as exc:
                self.receipt['cleanup']={'status':'failed','error':getattr(exc,'code',type(exc).__name__)}
                errors.append('fixture_cleanup_failed')
        for process,close_job,record,buffers,workers,overflow in reversed(self.services):
            if process.poll() is not None and record['health_verified']: errors.append('service_exited_early')
            try:
                _terminate(process)
            except (OSError,subprocess.TimeoutExpired): errors.append('service_stop_failed')
            finally: close_job()
            record['stopped']=process.poll() is not None
            for worker in workers: worker.join(timeout=3)
            record['truncated']=bool(overflow) or any(w.is_alive() for w in workers)
            if record['truncated']: errors.append('service_output_truncated')
            record['streams']={}
            for name,raw in buffers.items():
                text,_=redact(bytes(raw)); text=redact_output(text,tuple(self.secrets))
                record['streams'][name]=text[0] if isinstance(text,tuple) else text
        self.receipt['cleanup_errors']=errors
        required=[row for row in self.receipt['evidence'] if row['required']]
        self.receipt['passed']=not errors and all(row['status']=='attached' for row in required)
        return self.receipt
