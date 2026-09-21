"""Bounded JSON-RPC STDIO MCP. No network listener and no stdout diagnostics."""
from __future__ import annotations
import concurrent.futures
import json
import sys
import threading
from . import VERSION
from .common import HarnessError, encoded

PROTOCOLS=('2024-11-05','2025-03-26','2025-06-18','2025-11-25')
READ_ONLY={'info','project_list','workflow_status','get_artifact','list_artifacts','diff_artifacts','snapshot_list','get_verification','list_implementations','next_actions','evaluate_completion','preview_database','inspect_database','check_edit_scope','get_database_execution'}

def serve(api):
    lock=threading.Lock()
    def send(value):
        raw=encoded(value)
        if len(raw)>4*1024*1024:
            raw=encoded({'jsonrpc':'2.0','id':value.get('id'),'error':{'code':-32000,'message':'Response exceeds 4 MiB; narrow the query.'}})
        with lock:
            sys.stdout.buffer.write(raw+b'\n'); sys.stdout.buffer.flush()
    def process(request):
        rid=request.get('id')
        method=request.get('method')
        if rid is None:
            return
        try:
            if method=='initialize':
                offered=request.get('params',{}).get('protocolVersion')
                result={'protocolVersion':offered if offered in PROTOCOLS else PROTOCOLS[-1], 'capabilities':{'tools':{'listChanged':False}}, 'serverInfo':{'name':'team-harness','version':VERSION},
                        'instructions':'Use exact artifact refs and actual user decisions. Products and personal history are separate. This service is a cooperative workflow, not an OS permission boundary.'}
            elif method=='ping':
                result={}
            elif method=='tools/list':
                result={'tools':[{'name':'team_'+name,'description':f'Team Harness {name}. Read schema before calling; all records are local.', 'inputSchema':schema,
                                  'annotations':{'readOnlyHint':name in READ_ONLY,'destructiveHint':name in {'apply_restore','reconcile_recovery','run_checks','execute_database'},'openWorldHint':name in {'run_checks','execute_database','inspect_database','environment_probe','plan_database_recovery','record_database_recovery'}}}
                                 for name,schema in api.operations().items()]}
            elif method=='tools/call':
                params=request.get('params',{})
                name=params.get('name','')
                if not name.startswith('team_'):
                    raise HarnessError('unknown_tool','Unknown Team Harness tool.')
                try:
                    output=api.call(name[5:],params.get('arguments',{}))
                    result={'content':[{'type':'text','text':json.dumps(output,ensure_ascii=False,allow_nan=False)}],'isError':False}
                except HarnessError as exc:
                    result={'content':[{'type':'text','text':json.dumps({'error':exc.code,'message':str(exc)},ensure_ascii=False)}],'isError':True}
            else:
                send({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}})
                return
            send({'jsonrpc':'2.0','id':rid,'result':result})
        except (ValueError, TypeError, KeyError) as exc:
            send({'jsonrpc':'2.0','id':rid,'error':{'code':-32602,'message':'Invalid request or stored data: '+type(exc).__name__}})
        except Exception as exc:
            # Never leak arbitrary process/config values through an unexpected exception.
            send({'jsonrpc':'2.0','id':rid,'error':{'code':-32603,'message':'Internal error: '+type(exc).__name__}})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        pending=set()
        while True:
            line=sys.stdin.buffer.readline(2*1024*1024+1)
            if not line:
                break
            if len(line)>2*1024*1024:
                send({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Oversized message'}})
                break
            try:
                request=json.loads(line)
                if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':
                    raise ValueError()
            except (ValueError,UnicodeDecodeError):
                send({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON-RPC'}})
                continue
            pending={f for f in pending if not f.done()}
            if len(pending)>=32:
                send({'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32000,'message':'Too many active requests'}})
                continue
            pending.add(pool.submit(process,request))
