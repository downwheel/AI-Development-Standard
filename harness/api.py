"""One public operation surface shared by the CLI and STDIO MCP."""
from __future__ import annotations
import html
import json
import os
import tempfile
from pathlib import Path
from .common import fail, now, encoded, sha256
from .registry import Registry, atomic_json
from .validation import obj, STR, BOOL, validate

def base_operations():
    return {
        'info': obj({}),
        'project_list': obj({}),
        'project_register': obj({'project_root':STR,'name':STR,'create_root':BOOL}, ['project_root','name']),
        'import_legacy':obj({'project_id':STR,'legacy_path':STR},['project_id','legacy_path']),
        'capture_snapshot':obj({'project_id':STR,'workspace_id':STR,'label':STR,'request_id':STR},['project_id','workspace_id']),
        'snapshot_list':obj({'project_id':STR},['project_id']),
        'export_snapshot':obj({'project_id':STR,'snapshot_id':STR,'destination':STR},['project_id','snapshot_id','destination']),
        'plan_restore':obj({'project_id':STR,'snapshot_id':STR,'workspace_id':STR},['project_id','snapshot_id','workspace_id']),
        'record_restore_decision':obj({'project_id':STR,'plan_id':STR,'decision':{'type':'string','enum':['approve','reject']},'user_message':STR,'source':STR},['project_id','plan_id','decision','user_message','source']),
        'apply_restore':obj({'project_id':STR,'plan_id':STR,'request_id':STR},['project_id','plan_id','request_id']),
        'reconcile_recovery':obj({'project_id':STR,'plan_id':STR,'action':STR},['project_id','plan_id','action']),
        'journal_check':obj({'project_id':STR},['project_id']),
        'render_artifact':obj({'project_id':STR,'ref':{'type':'object'},'format':{'type':'string','enum':['markdown','html']}},['project_id','ref']),
        'preview_database':obj({'operation':{'type':'object'}},['operation']),
        'inspect_database':obj({'profile_id':STR,'role':STR,'tables':{'type':'array','minItems':1,'maxItems':20,'items':obj({'schema':STR,'table':STR},['schema','table'])},
                                'max_rows':{'type':'integer','minimum':1,'maximum':1000}},['profile_id','role','tables']),
    }

class API:
    def __init__(self, state_root, standard_root):
        self.registry = Registry(state_root, standard_root)

    def operations(self):
        from .workflow import Workflow
        from .execution import execution_operations
        from .environment import environment_operations
        schemas = base_operations()
        schemas.update(environment_operations())
        workflow = Workflow.operations()
        for name, schema in {**workflow, **execution_operations()}.items():
            # The workflow core deliberately receives no external project_id.
            schemas[name] = {**schema, 'properties':{'project_id':STR, **schema.get('properties',{})}, 'required':['project_id',*schema.get('required',[])]}
        return schemas

    def call(self, operation, params):
        schemas = self.operations()
        if operation not in schemas:
            fail('unknown_operation','Use describe to list supported operations.')
        validate(params, schemas[operation])
        if len(encoded(params)) > 2*1024*1024:
            fail('request_too_large','Request exceeds 2 MiB.')
        if operation == 'info':
            from . import VERSION
            from .capabilities import capabilities
            return {'version':VERSION,'standard_root':str(self.registry.standard_root),'state_root':str(self.registry.state_root),
                    'capabilities':capabilities(),
                    'runtime_release':self.registry._release(),
                    'notice':'Local cooperative records; not an OS sandbox or identity-authenticated approval service.',
                    'history_remote_default':False,'source_git_mutations':False,'account_connection':'deferred','team_git_connection':'deferred'}
        if operation == 'project_list':
            return self.registry.list_projects()
        if operation == 'project_register':
            return self.registry.register(**params)
        from .environment import Environment, environment_operations
        if operation in environment_operations():
            return Environment(self.registry.state_root).execute(operation, params)
        if operation == 'preview_database':
            from .database import compile_migration
            return compile_migration(params['operation'])
        if operation == 'inspect_database':
            from .database import inspect_database
            manager=Environment(self.registry.state_root)
            resolved=manager.resolve(params['profile_id'],role=params['role'])
            return inspect_database(resolved,params['tables'],max_rows=params.get('max_rows',1000))
        if operation == 'import_legacy':
            return self.registry.import_legacy(**params)
        values = dict(params)
        project_id = values.pop('project_id')
        journal = self.registry.journal(project_id)
        from .sensitive import guard_journal
        from .environment import Environment
        additional=[]
        if operation=='publish_artifact' and values.get('kind')=='environment-contract':
            profile_id=values.get('payload',{}).get('profile_id')
            if profile_id: additional.append(profile_id)
        # A new environment contract selects its profile before its own body is
        # journaled. Later source/evidence writes reuse only this project's pins.
        if operation not in {'snapshot_list','journal_check','render_artifact','get_artifact','list_artifacts','diff_artifacts','workflow_status','next_actions','evaluate_completion','get_verification','get_database_execution','list_implementations','check_edit_scope'}:
            guard_journal(journal,Environment(self.registry.state_root),additional)
        from . import history
        if operation in {'capture_snapshot','export_snapshot','plan_restore','record_restore_decision','apply_restore','reconcile_recovery'}:
            return getattr(history, operation)(journal, **values)
        if operation == 'snapshot_list':
            return list(journal.read().get('snapshots',{}).values())
        if operation == 'journal_check':
            return journal.fsck()
        from .workflow import Workflow
        if operation == 'render_artifact':
            result = Workflow(journal).load_artifact(values['ref'])
            ref = result['ref']
            report = result['report']
            extension = 'html' if values.get('format') == 'html' else 'md'
            folder = journal.path.parent / 'exports' / 'views'
            from .history import _no_links
            _no_links(folder)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (ref['revision_id']+'.'+extension)
            _no_links(path)
            if folder.resolve() not in path.resolve().parents:
                fail('view_path_escape','Derived view must remain inside the private view folder.')
            heading = '# 저장된 산출물 조회\n\n' + f"Revision: {ref['revision_id']}\n\nManifest SHA-256: {ref['sha256']}\n\n" + '이 표지는 파생 조회 자료이며 승인 원본을 변경하지 않습니다.\n\n---\n\n'
            body = heading + report
            if extension == 'html':
                body = '<!doctype html><meta charset="utf-8"><title>저장된 개발 산출물</title><style>body{max-width:960px;margin:48px auto;padding:0 24px;font:16px/1.7 system-ui;color:#1d2939}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><pre>'+html.escape(body)+'</pre>'
            raw = body.encode('utf-8')
            # The deterministic derived file is never an approval input or authoritative event.
            fd,temporary=tempfile.mkstemp(prefix='.view-',dir=folder)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary,path)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)
            return {'path':str(path),'ref':ref,'derived':True,'sha256':sha256(raw),'canonical_changed':False}
        from .execution import Execution, execution_operations
        if operation in execution_operations():
            return Execution(journal).execute(operation, values)
        return Workflow(journal).execute(operation, values)
