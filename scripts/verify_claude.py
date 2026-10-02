"""Check Claude Code files and optionally discover skills without a model request."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


def native_skills(binary, home, names):
    from package_lib import ROOT
    env=dict(os.environ,CLAUDE_CONFIG_DIR=str(home),CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
    command=[binary,'-p','--input-format','stream-json','--output-format','stream-json','--verbose',
             '--no-session-persistence','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--setting-sources','user']
    process=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             text=True,encoding='utf-8',errors='replace',creationflags=0x08000000 if os.name=='nt' else 0)
    messages=queue.Queue()
    def reader():
        for line in process.stdout:
            try:messages.put(json.loads(line))
            except ValueError:continue
        messages.put(None)
    def drain():
        for _ in process.stderr:pass
    threading.Thread(target=reader,daemon=True).start()
    threading.Thread(target=drain,daemon=True).start()
    try:
        process.stdin.write(json.dumps({'type':'control_request','request_id':'team-skills-init','request':{'subtype':'initialize','hooks':{}}})+'\n')
        process.stdin.flush()
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:item=messages.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty:break
            if item is None:raise RuntimeError('Claude Code exited during discovery')
            if item.get('type')=='control_response' and item.get('response',{}).get('request_id')=='team-skills-init':
                response=item['response']
                if response.get('subtype')!='success':raise RuntimeError('Claude Code discovery unsupported')
                commands=response.get('response',{}).get('commands',[])
                found={c.get('name') for c in commands}&set(names)
                if found!=set(names):raise RuntimeError('Missing Claude Code commands: '+', '.join(sorted(set(names)-found)))
                return {'status':'passed','discovered':len(found),'model_turn_started':False,'external_mcp_checked':False}
        raise TimeoutError('Claude Code skill discovery timed out')
    finally:
        process.stdin.close()
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)


if __name__=='__main__':
    from verify_codex import main
    main('claude')
