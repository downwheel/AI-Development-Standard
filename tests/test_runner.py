"""Real isolated processes validate preparation ownership and evidence boundaries."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from harness.common import HarnessError,sha256
from harness.execution import run_process
from harness.runner import PreparedRunner


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='team runner fixture ')
        self.root=Path(self.temp.name); self.blobs={}
        def store(raw):
            key=sha256(raw); self.blobs[key]=raw; return key
        self.journal=SimpleNamespace(put_blob=store)

    def tearDown(self): self.temp.cleanup()

    def runner(self,contract=None):
        return PreparedRunner(contract or {'kind':'project-runner'},self.root,self.root/'private-evidence','build-fixture','run-fixture',
                              lambda role:({'FIXTURE_SECRET':'synthetic-role-value'},('synthetic-role-value',),{'role':role}) if role else ({},(),None),
                              lambda:False,time.monotonic()+12)

    def test_unknown_parent_credentials_are_not_inherited_and_known_output_is_redacted(self):
        from unittest.mock import patch
        with patch.dict(os.environ,{'MSSQL_PWD':'synthetic-parent-password','DATABASE_URL':'synthetic-parent-url'}):
            result=run_process([sys.executable,'-c','import os; print(os.getenv("MSSQL_PWD")); print(os.getenv("DATABASE_URL"))'],self.root,5,lambda:False,lambda *a:None)
        self.assertEqual('None\nNone\n',result['streams']['stdout'].replace('\r\n','\n'))
        result=run_process([sys.executable,'-c','import os; print(os.environ["FIXTURE_SECRET"])'],self.root,5,lambda:False,lambda *a:None,
                           env={'SYSTEMROOT':os.environ.get('SYSTEMROOT',''),'FIXTURE_SECRET':'synthetic-role-value'},secret_values=('synthetic-role-value',))
        self.assertNotIn('synthetic-role-value',json.dumps(result)); self.assertTrue(result['redacted'])

    def test_known_secret_in_arguments_is_rejected_before_start(self):
        with self.assertRaises(HarnessError) as caught:
            run_process([sys.executable,'-c','print("synthetic-role-value")'],self.root,5,lambda:False,lambda *a:None,secret_values=('synthetic-role-value',))
        self.assertEqual('secret_in_argv',caught.exception.code)

    def test_text_attachment_is_redacted_and_missing_required_evidence_is_visible(self):
        runner=self.runner({'kind':'project-runner','evidence':[
            {'evidence_id':'log','path':'log.txt','format':'text','max_bytes':1024,'required':True},
            {'evidence_id':'missing','path':'missing.json','format':'json','max_bytes':1024,'required':True}]})
        runner.start(); runner._env('application')
        (runner.scratch/'log.txt').write_text('synthetic-role-value',encoding='utf-8')
        runner.attach(self.journal); receipt=runner.close()
        self.assertFalse(receipt['passed']); self.assertEqual('missing',receipt['evidence'][1]['status'])
        self.assertNotIn(b'synthetic-role-value',b''.join(self.blobs.values()))
        self.assertEqual('[REDACTED]',(runner.scratch/'log.txt').read_text())

    def test_cleanup_failure_does_not_become_successful_preparation(self):
        ok='print(\'HARNESS_CASE_RESULTS={"cases":[{"case_id":"fixture","status":"passed"}]}\')'
        command={'argv':[sys.executable,'-c',ok],'cwd':'.','timeout_seconds':5,'case_ids':['fixture']}
        cleanup={**command,'argv':[sys.executable,'-c','raise SystemExit(2)']}
        runner=self.runner({'kind':'project-runner','fixture':{'setup':command,'cleanup':cleanup,'namespace':'synthetic'}})
        runner.start(); receipt=runner.close()
        self.assertTrue(receipt['fixture']['passed']); self.assertFalse(receipt['passed'])
        self.assertIn('fixture_cleanup_failed',receipt['cleanup_errors'])

    def test_occupied_port_is_not_reused_or_stopped(self):
        listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
        try:
            runner=self.runner({'kind':'project-runner','services':[{'service_id':'web','argv':[sys.executable,'-c','pass'],'cwd':'.',
                'health_url':'http://127.0.0.1:'+str(listener.getsockname()[1])+'/health','readiness_seconds':2}]})
            with self.assertRaises(HarnessError) as caught: runner.start()
            self.assertEqual('service_port_in_use',caught.exception.code)
            self.assertEqual([],runner.close()['services'])
            self.assertGreaterEqual(listener.fileno(),0)
        finally: listener.close()

    def test_owned_service_reports_fresh_build_and_is_stopped(self):
        listener=socket.socket(); listener.bind(('127.0.0.1',0)); port=listener.getsockname()[1]; listener.close()
        script=self.root/'service.py'
        script.write_text('import http.server,json,os,sys\n'
            'class Handler(http.server.BaseHTTPRequestHandler):\n'
            ' def do_GET(self):\n'
            '  raw=json.dumps({"build_id":os.environ["HARNESS_BUILD_ID"],"run_id":os.environ["HARNESS_RUN_ID"]}).encode()\n'
            '  self.send_response(200);self.end_headers();self.wfile.write(raw)\n'
            ' def log_message(self,*args): pass\n'
            'http.server.HTTPServer(("127.0.0.1",int(sys.argv[1])),Handler).serve_forever()\n',encoding='utf-8')
        runner=self.runner({'kind':'project-runner','services':[{'service_id':'web','argv':[sys.executable,str(script),str(port)],'cwd':'.',
            'health_url':'http://127.0.0.1:'+str(port)+'/health','readiness_seconds':5}]})
        try:
            self.assertTrue(runner.start()['services'][0]['health_verified'])
        finally: receipt=runner.close()
        self.assertTrue(receipt['passed']); self.assertTrue(receipt['services'][0]['stopped'])


if __name__=='__main__': unittest.main()
