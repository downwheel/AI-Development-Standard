"""Read-only host probes. Never starts a model turn or queries a business DB."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class JsonProcess:
    def __init__(self,command,cwd=None,env=None):
        self.process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      text=True,encoding='utf-8',errors='replace',creationflags=0x08000000 if os.name=='nt' else 0)
        self.messages=queue.Queue(); self.serial=0
        def output():
            for line in self.process.stdout:
                try: self.messages.put(json.loads(line))
                except ValueError: self.messages.put({'invalid_stream':True})
            self.messages.put({'closed':True})
        def errors():
            for _ in self.process.stderr: pass
        threading.Thread(target=output,daemon=True).start(); threading.Thread(target=errors,daemon=True).start()

    def request(self,method,params=None,notify=False,jsonrpc=False,timeout=45):
        self.serial+=1
        request={'method':method}
        if jsonrpc: request['jsonrpc']='2.0'
        if params is not None: request['params']=params
        if not notify: request['id']=self.serial
        self.process.stdin.write(json.dumps(request)+'\n'); self.process.stdin.flush()
        if notify: return None
        deadline=time.monotonic()+timeout
        while True:
            message=self.messages.get(timeout=max(0.01,deadline-time.monotonic()))
            if message.get('closed') or message.get('invalid_stream'): raise RuntimeError('Protocol closed or invalid')
            if message.get('id')==self.serial:
                if 'error' in message: raise RuntimeError('Protocol returned an error')
                return message['result']
            if time.monotonic()>deadline: raise TimeoutError(method)

    def close(self):
        self.process.stdin.close()
        try: self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name=='nt': subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True)
            else: self.process.terminate()
            self.process.wait(timeout=5)
        self.process.stdout.close(); self.process.stderr.close()


def probe(profile,state_root,codex=False):
    names=sorted(p.name for p in (ROOT/'skills').iterdir() if (p/'SKILL.md').is_file())
    installed=json.loads((state_root/'settings.json').read_text(encoding='utf-8'))
    release=Path(installed['active_release'])
    from harness.release import verify_release
    result={'release':verify_release(release),'hosts':{},'accounts':'not_connected_by_doctor','team_git':'not_modified_by_doctor'}
    for host in ['codex','claude']:
        paths=[profile/('.'+host)/'skills'/name for name in names]
        result['hosts'][host]={'skill_files_present':all((p/'SKILL.md').is_file() and (p/'runtime.json').is_file() and (p/'scripts/harness.py').is_file() for p in paths),
                               'skill_count':len(paths),'client_available':bool(shutil.which(host)),'native_discovery':'not_probed'}
    claude=json.loads((profile/'.claude.json').read_text(encoding='utf-8'))
    registration=claude.get('mcpServers',{}).get('team_harness',{})
    result['hosts']['claude']['mcp_registered']=registration.get('type')=='stdio'
    command=[installed['python'],'-B','-X','utf8',str(release/'team_harness.py'),'--state-root',str(state_root),'--standard-root',installed['standard_source_root']]
    cli=subprocess.run(command+['call','info'],capture_output=True,timeout=30)
    if cli.returncode: raise RuntimeError('Installed CLI probe failed')
    result['cli']=json.loads(cli.stdout)
    mcp_command=command+['serve']
    mcp_cwd=None; mcp_env=None
    if codex:
        executable=shutil.which('codex')
        if not executable: raise RuntimeError('Codex CLI is unavailable')
        host_env={**os.environ,'CODEX_HOME':str(profile/'.codex')}
        output=subprocess.run([executable,'mcp','get','team_harness','--json'],env=host_env,capture_output=True,timeout=30)
        if output.returncode: raise RuntimeError('Codex MCP registration is unreadable')
        entry=json.loads(output.stdout); transport=entry.get('transport',entry)
        result['hosts']['codex']['mcp_registered']=bool(entry.get('enabled',True))
        mcp_command=[transport['command'],*transport.get('args',[])]
        mcp_cwd=transport.get('cwd')
        mcp_env={**os.environ,**(transport.get('env') or {})}
        client=JsonProcess([executable,'app-server'],cwd=ROOT,env=host_env)
        try:
            client.request('initialize',{'clientInfo':{'name':'team-standard-doctor','version':'2.0.0'}})
            client.request('initialized',notify=True)
            data=client.request('skills/list',{'cwds':[str(ROOT)],'forceReload':True})
            matches=[]; errors=[]
            for group in data.get('data',[]):
                errors.extend(group.get('errors',[]))
                matches.extend({k:skill.get(k) for k in ['name','path','scope','enabled']} for skill in group.get('skills',[]) if skill.get('name') in names)
            result['hosts']['codex'].update({'native_discovery':matches,'total_discovery_error_count':len(errors),
                                           'expected_skills_discovered':len(matches)==len(names) and len({m['name'] for m in matches})==len(names)})
        finally: client.close()
    client=JsonProcess(mcp_command,cwd=mcp_cwd,env=mcp_env)
    try:
        protocol=client.request('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'team-standard-doctor','version':'2.0.0'}},jsonrpc=True)
        client.request('notifications/initialized',notify=True,jsonrpc=True)
        inventory=client.request('tools/list',{},jsonrpc=True)
        info=client.request('tools/call',{'name':'team_info','arguments':{}},jsonrpc=True)
        if info.get('isError'): raise RuntimeError('Installed MCP info failed')
        result['mcp']={'initialized':True,'protocol_version':protocol['protocolVersion'],'tool_count':len(inventory['tools']),
                       'tools':sorted(t['name'] for t in inventory['tools']),'info_matches_cli':json.loads(info['content'][0]['text'])==result['cli']}
    finally: client.close()
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',type=Path,default=Path.home())
    parser.add_argument('--state-root',type=Path,default=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'TeamDevelopment')
    parser.add_argument('--codex',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=probe(args.profile,args.state_root,args.codex)
    if args.output:
        from harness.registry import atomic_json
        from harness.history import _no_links
        path=args.output.absolute(); _no_links(path); path=path.resolve()
        if ROOT==path or ROOT in path.parents: parser.error('Keep local probe reports outside the common source.')
        atomic_json(path,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
