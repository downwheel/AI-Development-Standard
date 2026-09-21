"""Real STDIO/CLI, release drift, and derived-view boundaries in isolated folders."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from harness.api import API
from harness.common import HarnessError, encoded, sha256
from harness.release import verify_release

SOURCE=Path(__file__).resolve().parents[1]


class InterfaceTests(unittest.TestCase):
    def test_stdio_negotiation_tools_validation_and_cli_parity_are_readonly(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)/'private'
            prefix=[sys.executable,'-B','-X','utf8',str(SOURCE/'team_harness.py'),'--state-root',str(state),'--standard-root',str(SOURCE)]
            requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'isolated-test','version':'1'}}},
                      {'jsonrpc':'2.0','method':'notifications/initialized'},
                      {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                      {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'team_info','arguments':{}}},
                      {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'team_project_register','arguments':{'unexpected':True}}}]
            result=subprocess.run(prefix+['serve'],input=b''.join(encoded(r)+b'\n' for r in requests),capture_output=True,timeout=30)
            self.assertEqual(0,result.returncode,result.stderr.decode(errors='replace'))
            responses={r['id']:r for r in map(json.loads,result.stdout.splitlines())}
            self.assertEqual('2025-11-25',responses[1]['result']['protocolVersion'])
            tools=responses[2]['result']['tools']
            self.assertTrue(any(t['name']=='team_begin_implementation' for t in tools))
            self.assertTrue(responses[4]['result']['isError'])
            cli=subprocess.run(prefix+['call','info'],capture_output=True,timeout=30)
            self.assertEqual(json.loads(cli.stdout),json.loads(responses[3]['result']['content'][0]['text']))
            self.assertFalse(state.exists(),'Read-only protocol calls must not create a registry or Git journal.')

    def test_render_preserves_authoritative_state_and_blocks_junction_export(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder); product=base/'product'; product.mkdir()
            api=API(base/'private',SOURCE)
            binding=api.call('project_register',{'project_root':str(product),'name':'SYNTHETIC VIEW FIXTURE'})
            common={'project_id':binding['project_id']}
            def call(op,**params): return api.call(op,{**common,**params})
            call('create_run',run_id='fixture',workspace_id=binding['workspace_id'],goal='SYNTHETIC VIEW FIXTURE')
            stage=call('start_stage',run_id='fixture',skill='dev-discover',owner='fixture',input_refs=[])
            result=call('publish_artifact',run_id='fixture',stage_run_id=stage['stage_run_id'],owner='fixture',artifact_id='context',kind='discovery-context',
                        payload={'facts':['Synthetic context']},report='# Synthetic report\n\n<script>unsafe()</script>',input_refs=[],accept=True,
                        expected_head={'revision_id':None,'generation':0})
            ref=result['ref']; journal=api.registry.journal(binding['project_id']); before=encoded(journal.read())
            render=call('render_artifact',ref=ref,format='html')
            output=Path(render['path'])
            self.assertIn('&lt;script&gt;',output.read_text(encoding='utf-8'))
            self.assertEqual(before,encoded(journal.read()))
            output.unlink(); output.parent.rmdir()
            outside=base/'outside'; outside.mkdir()
            if os.name=='nt':
                quoted=lambda p:"'"+str(p).replace("'","''")+"'"
                command='New-Item -ItemType Junction -Path '+quoted(output.parent)+' -Target '+quoted(outside)+' | Out-Null'
                result=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True)
                self.assertEqual(0,result.returncode,result.stderr.decode(errors='replace'))
            else:
                output.parent.symlink_to(outside,target_is_directory=True)
            try:
                with self.assertRaises(HarnessError): call('render_artifact',ref=ref,format='html')
                self.assertEqual([],list(outside.iterdir()))
                self.assertEqual(before,encoded(journal.read()))
            finally:
                if os.name=='nt': os.rmdir(output.parent)
                else: output.parent.unlink()

    def test_release_identity_detects_modified_missing_and_unlisted_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'releases/v2'; root.mkdir(parents=True)
            code=root/'team_harness.py'; raw=b'print("synthetic")\n'; code.write_bytes(raw)
            files=[{'path':code.name,'sha256':sha256(raw),'bytes':len(raw)}]; digest=sha256(encoded(files))
            manifest={'files':files,'content_sha256':digest,'version':'2.0.0','release_id':'2.0.0-'+digest[:16]}
            path=root/'release-manifest.json'; path.write_bytes(encoded(manifest))
            self.assertTrue(verify_release(root)['verified'])
            code.write_bytes(b'changed')
            with self.assertRaises(HarnessError): verify_release(root)
            code.write_bytes(raw); extra=root/'extra.py'; extra.write_bytes(b'injected')
            with self.assertRaises(HarnessError): verify_release(root)
            extra.unlink(); path.unlink()
            with self.assertRaises(HarnessError): verify_release(root)

    def test_malformed_manifest_has_structured_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); manifest=root/'release-manifest.json'
            for invalid in [[],None,{'files':[]},'text']:
                manifest.write_bytes(encoded(invalid))
                with self.assertRaises(HarnessError) as error: verify_release(root)
                self.assertEqual('invalid_release',error.exception.code)


if __name__=='__main__': unittest.main()
