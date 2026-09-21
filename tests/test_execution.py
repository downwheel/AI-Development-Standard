"""Real process and real private-Git tests, with synthetic approvals only."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace
from pathlib import Path
from harness.api import API
from harness.common import HarnessError, encoded, sha256
from harness.execution import run_process, case_result, process_identity, observed_process, git_metadata, Execution, environment_fingerprint

STANDARD=Path(__file__).resolve().parents[1]

def approved_fixture(api,product,marker,checks=None):
    project=api.call('project_register',{'project_root':str(product),'name':'SYNTHETIC isolated test'})
    pid=project['project_id']
    def call(op,**params): return api.call(op,{'project_id':pid,**params})
    call('create_run',run_id='fixture-run',workspace_id='workspace-main',goal='SYNTHETIC TEST ONLY: independent assertions')
    producers={'discovery-context':'dev-discover','requirements':'dev-requirements','system-design':'dev-system-design','unit-spec':'dev-unit-design','test-plan':'dev-test-design'}
    def publish(kind,payload,refs,unit=None):
        args={'run_id':'fixture-run','skill':producers[kind],'owner':'fixture-owner','input_refs':refs}
        if unit: args['unit_id']=unit
        stage=call('start_stage',**args)
        values={'run_id':'fixture-run','stage_run_id':stage['stage_run_id'],'owner':'fixture-owner','artifact_id':kind,'kind':kind,
                'payload':payload,'report':'# SYNTHETIC ISOLATED TEST\n\nNot an actual user decision.','input_refs':refs,'accept':True,'expected_head':{'revision_id':None,'generation':0}}
        if unit: values['unit_id']=unit
        ref=call('publish_artifact',**values)['ref']
        call('finish_stage',stage_run_id=stage['stage_run_id'],owner='fixture-owner',status='succeeded',output_refs=[ref])
        return ref
    def approve(gate,refs,unit=None):
        args={'run_id':'fixture-run','gate':gate,'input_refs':refs}
        if unit: args['unit_id']=unit
        review=call('create_review',**args)
        call('record_decision',review_id=review['review_id'],decision='approved',user_message='SYNTHETIC TEST FIXTURE approval',source='isolated automated test fixture')
        return review
    context=publish('discovery-context',{'facts':['Isolated fixture']},[])
    requirements=publish('requirements',{'requirements':[{'id':'req-1','description':'Fixture independently verifies two invariants','case_ids':['case-1','case-2']}]},[context])
    system=publish('system-design',{'requirement_ids':['req-1']},[context,requirements])
    approve('A',[context,requirements,system])
    unit=publish('unit-spec',{'requirement_ids':['req-1'],'case_ids':['case-1','case-2'],'allowed_paths':['check.py']},[system],'unit-1')
    plan=publish('test-plan',{'unit_ref':unit,'checks':checks or [{'check_id':'check-1','argv':[sys.executable,str(product/'check.py'),str(marker)],'cwd':'.','timeout_seconds':10,'required':True,'expected_exit':0,'case_ids':['case-1','case-2'],'expected':'Both explicit fixture assertions pass','oracle':'Fixed arithmetic and caller-controlled fixture flag independent of implementation'}]},[unit],'unit-1')
    approve('B',[unit,plan],'unit-1')
    return pid,call

class ProcessTests(unittest.TestCase):
    def test_process_identity_tracks_live_and_exited_process(self):
        identity=process_identity(os.getpid())
        self.assertEqual('alive',identity['state'])
        self.assertTrue(identity['token'])
        self.assertEqual('alive',observed_process(identity)['state'])
        process=subprocess.Popen([sys.executable,'-c','pass'],creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        child=process_identity(process.pid)
        process.wait(timeout=10)
        self.assertEqual('exited',observed_process(child)['state'])

    def test_case_evidence_requires_exact_nonempty_executed_ids(self):
        check={'case_ids':['one','two']}
        def result(cases): return case_result(check,{'streams':{'stdout':'HARNESS_CASE_RESULTS='+json.dumps({'cases':cases})}})
        passed=[{'case_id':c,'status':'passed'} for c in check['case_ids']]
        self.assertEqual('passed',result(passed)['result'])
        for cases in [[],passed[:1],passed+[passed[0]],passed+[{'case_id':'extra','status':'passed'}], [{'case_id':'one','status':'passed'},{'case_id':'two','status':'skipped'}]]:
            with self.subTest(cases=cases): self.assertEqual('blocked',result(cases)['result'])
        self.assertEqual('blocked',case_result(check,{'streams':{'stdout':'Ran 0 tests\nOK'}})['result'])
        self.assertEqual('blocked',case_result(check,{'streams':{'stdout':'HARNESS_CASE_RESULTS={}\nHARNESS_CASE_RESULTS={}'}})['result'])
        self.assertEqual('blocked',case_result(check,{'streams':{'stdout':'HARNESS_CASE_RESULTS={"cases":[],"cases":[{"case_id":"one","status":"passed"},{"case_id":"two","status":"passed"}]}'}})['result'])
        self.assertEqual('failed',result([{'case_id':'one','status':'failed'},{'case_id':'two','status':'passed'}])['result'])
        self.assertEqual('passed',case_result({**check,'evidence_mode':'command-exit','parser':'exit-code'},{})['result'])

    def test_ancestor_git_metadata_observes_staged_index_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); child=root/'solution'/'nested'; child.mkdir(parents=True)
            subprocess.run(['git','init',str(root)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            (root/'staged.txt').write_bytes(b'staged\r\n')
            subprocess.run(['git','-C',str(root),'add','staged.txt'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            before=git_metadata(child)
            self.assertTrue(before['present'])
            self.assertEqual(str(root.resolve()),before['git_root'])
            self.assertEqual(before,git_metadata(child))
            (root/'staged.txt').write_bytes(b'new unstaged bytes')
            self.assertEqual(before,git_metadata(child))
            subprocess.run(['git','-C',str(root),'add','staged.txt'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.assertNotEqual(before,git_metadata(child))

    def test_runtime_fingerprint_tracks_argument_file_and_dependency_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); script=root/'fixture.py'; script.write_text('pass')
            module=root/'node_modules'/'dependency'; module.mkdir(parents=True); (module/'data').write_bytes(b'a')
            checks=[{'cwd':'.','argv':[sys.executable,str(script)]}]
            original=environment_fingerprint(checks,root)
            (module/'data').write_bytes(b'b')
            self.assertNotEqual(original,environment_fingerprint(checks,root))

    def test_real_exit_and_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run_process([sys.executable,'-c','print("password=private-example-value")'],folder,5,lambda:False,lambda *a:None)
            self.assertEqual(0,result['exit_code'])
            self.assertTrue(result['redacted'])
            self.assertNotIn('private-example-value',result['streams']['stdout'])

    def test_timeout_terminates_owned_process(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run_process([sys.executable,'-c','import time; time.sleep(10)'],folder,1,lambda:False,lambda *a:None)
            self.assertEqual('timeout',result['termination'])
            self.assertIsNotNone(result['exit_code'])

    def test_cancellation_terminates_owned_process(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run_process([sys.executable,'-c','import time; time.sleep(10)'],folder,10,lambda:True,lambda *a:None)
            self.assertEqual('cancelled',result['termination'])

    def test_direct_product_git_command_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(HarnessError) as error:
                run_process(['git','status'],folder,5,lambda:False,lambda *a:None)
            self.assertEqual('product_git_command',error.exception.code)


class ContractBoundaryTests(unittest.TestCase):
    def test_release_mismatch_blocks_finish_and_reconcile_before_capture_or_write(self):
        row={'run_id':'run','owner':'owner','status':'starting','controller':process_identity(os.getpid())}
        state={'runs':{'run':{'standard_release':'old-release'}},'execution_sessions':{'session':{'run_id':'run','owner':'owner','status':'open'}},'execution_requests':{'implementation/request':row}}
        journal=SimpleNamespace(read=lambda:copy.deepcopy(state),transaction=Mock(side_effect=AssertionError('Must not mutate old release state')))
        execution=Execution(journal)
        with patch('harness.registry.runtime_release',return_value='new-release'), patch('harness.execution.capture_snapshot',side_effect=AssertionError('Must not capture under mismatched release')):
            with self.assertRaises(HarnessError) as error: execution.finish('session','owner','fixture','completed')
            self.assertEqual('release_mismatch',error.exception.code)
            self.assertEqual('starting',execution.reconcile('implementation','request','owner','status')['status'])
            with self.assertRaises(HarnessError) as error: execution.reconcile('implementation','request','owner','reconcile',True)
            self.assertEqual('release_mismatch',error.exception.code)
            with self.assertRaises(HarnessError) as error: execution._close(state,row,'interrupted')
            self.assertEqual('release_mismatch',error.exception.code)
        journal.transaction.assert_not_called()

    def test_change_fulfillment_uses_same_currentness_as_completion_projection(self):
        raw=b'independent stored execution evidence'
        refs={unit:{'artifact_id':unit,'revision_id':'revision-'+unit,'sha256':'fixed'} for unit in ['one','two']}
        initial={'verification':{},'verification_order':[],'implementations':{},'applied':{},'execution_requests':{},'execution_order':[],
            'changes':{'change':{'change_id':'change','run_id':'run','status':'contract_resolved','target_refs':[refs['two']], 'resolved_unit_ids':['one','two'],'verified_units':{'one':'campaign-one'}}}}
        for unit in ['one','two']:
            implementation={'implementation_id':'impl-'+unit,'outcome':'completed','run_id':'run','unit_id':unit,'workspace_id':'workspace','snapshot_after':'snapshot','basis':{'unit_ref':refs[unit],'test_ref':refs[unit]}}
            campaign={'campaign_id':'campaign-'+unit,'implementation_id':implementation['implementation_id'],'unit_id':unit,'workspace_id':'workspace','snapshot_id':'snapshot',
                'basis':implementation['basis'],'outcome':'passed','created_at':'fixture-time','environment':{'runtime':'same'},'git_metadata':{'present':False},
                'check_results':{'check':{'evidence_oid':'blob','evidence_sha256':sha256(raw),'result':'passed'}}}
            initial['implementations'][implementation['implementation_id']]=implementation
            initial['applied']['run/'+unit]=implementation['implementation_id']
            initial['verification'][campaign['campaign_id']]=campaign
            initial['verification_order'].append(campaign['campaign_id'])
            initial['execution_requests']['verification/'+unit]={'implementation_id':implementation['implementation_id'],'status':'finished' if unit=='one' else 'running','campaign_id':campaign['campaign_id']}
            initial['execution_order'].append('verification/'+unit)
        for mode in ['current','environment_drift','git_drift','corrupt_evidence','later_failed_request','later_pending_request']:
            with self.subTest(mode=mode):
                state=copy.deepcopy(initial)
                if mode=='environment_drift': state['verification']['campaign-one']['environment']={'runtime':'old'}
                if mode=='git_drift': state['verification']['campaign-one']['git_metadata']={'present':True}
                if mode=='corrupt_evidence': state['verification']['campaign-one']['check_results']['check']['evidence_sha256']='corrupt'
                if mode in ['later_failed_request','later_pending_request']:
                    state['execution_requests']['verification/later']={'implementation_id':'impl-one','status':'failed' if mode=='later_failed_request' else 'starting','campaign_id':'later-campaign'}
                    state['execution_order'].append('verification/later')
                journal=SimpleNamespace(read=lambda:copy.deepcopy(state),get_blob=lambda oid:raw)
                execution=Execution(journal)
                execution.workflow._basis=Mock(side_effect=lambda s,r,u:s['implementations']['impl-'+u]['basis'])
                execution.workflow.load_artifact=Mock(return_value={'payload':{'checks':[]}})
                execution._root=Mock(return_value=Path.cwd())
                with patch('harness.execution.snapshot_matches',return_value=True), patch('harness.execution.environment_fingerprint',return_value={'runtime':'same'}), patch('harness.execution.git_metadata',return_value={'present':False}):
                    self.assertEqual(mode=='current',execution.get_verification('impl-one')['eligible_complete'])
                    implementation=state['implementations']['impl-two']
                    execution._fulfill_changes(state,implementation,implementation['basis'],state['verification']['campaign-two'])
                self.assertEqual('fulfilled' if mode=='current' else 'contract_resolved',state['changes']['change']['status'])

class IntegrationTests(unittest.TestCase):
    def test_reservation_crash_reconciliation_partial_recheck_and_failed_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder); product=base/'product'; product.mkdir()
            marker=base/'fixture-flag'; marker.write_text('pass')
            (product/'check.py').write_text('import json,sys,time\nfrom pathlib import Path\nassert 2+3==5\nif Path(sys.argv[2]).read_text()=="sleep": time.sleep(30)\nprint("HARNESS_CASE_RESULTS="+json.dumps({"cases":[{"case_id":sys.argv[1],"status":"passed"}]}))\n',encoding='utf-8')
            checks=[{'check_id':'check-'+str(n),'argv':[sys.executable,str(product/'check.py'),'case-'+str(n),str(marker)],'cwd':'.','timeout_seconds':10,'required':True,'expected_exit':0,'case_ids':['case-'+str(n)],'expected':'Fixed invariant executes','oracle':'2 plus 3 equals 5'} for n in [1,2]]
            api=API(base/'private',STANDARD); pid,call=approved_fixture(api,product,marker,checks)
            journal=api.registry.journal(pid)
            with patch('harness.execution.capture_snapshot',side_effect=HarnessError('fixture_capture_failure','SYNTHETIC fault injection')):
                with self.assertRaises(HarnessError): call('begin_implementation',run_id='fixture-run',unit_id='unit-1',owner='fixture-owner',request_id='begin-failed')
            failed=journal.read()['execution_requests']['implementation/begin-failed']
            self.assertEqual('failed',failed['status'])
            self.assertIn('released_at',journal.read()['leases'][failed['lease_id']])
            self.assertEqual('failed',journal.read()['stages'][failed['stage_run_id']]['status'])

            # A genuine process exit occurs after durable reservation and before capture.
            worker='import os,sys\nfrom pathlib import Path\nfrom harness.api import API\nimport harness.execution as execution\nexecution.capture_snapshot=lambda *a,**k:os._exit(73)\napi=API(Path(sys.argv[1]),Path(sys.argv[2]))\napi.call("begin_implementation",{"project_id":sys.argv[3],"run_id":"fixture-run","unit_id":"unit-1","owner":"fixture-owner","request_id":"crashed-begin"})\n'
            process=subprocess.run([sys.executable,'-B','-c',worker,str(base/'private'),str(STANDARD),pid],cwd=STANDARD,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.assertEqual(73,process.returncode)
            pending=call('begin_implementation',run_id='fixture-run',unit_id='unit-1',owner='fixture-owner',request_id='crashed-begin')
            self.assertTrue(pending['pending'])
            before=encoded(journal.read())
            view=call('reconcile_execution',kind='implementation',request_id='crashed-begin',owner='fixture-owner',action='status')
            self.assertEqual('exited',view['controller']['state'])
            self.assertTrue(view['external_writers_stopped_acknowledgement_required'])
            self.assertFalse(view['can_reconcile'])
            self.assertEqual(before,encoded(journal.read()))
            recovered=call('reconcile_execution',kind='implementation',request_id='crashed-begin',owner='fixture-owner',action='reconcile',external_writers_stopped=True)
            self.assertTrue(recovered['reconciled'])
            self.assertFalse(call('reconcile_execution',kind='implementation',request_id='crashed-begin',owner='fixture-owner',action='reconcile',external_writers_stopped=True)['can_reconcile'])

            session=call('begin_implementation',run_id='fixture-run',unit_id='unit-1',owner='fixture-owner',request_id='begin-live')
            before=encoded(journal.read())
            view=call('reconcile_execution',kind='implementation',request_id='begin-live',owner='fixture-owner',action='reconcile',external_writers_stopped=True)
            self.assertEqual('alive',view['controller']['state']); self.assertFalse(view['can_reconcile'])
            self.assertEqual(before,encoded(journal.read()))
            transaction=journal.transaction
            def lost_ack(callback):
                result=transaction(callback)
                if callback.__name__=='record': raise RuntimeError('SYNTHETIC lost acknowledgement after commit')
                return result
            with patch.object(journal,'transaction',side_effect=lost_ack):
                with self.assertRaises(RuntimeError):
                    Execution(journal).finish(session['session_id'],'fixture-owner','SYNTHETIC fixture','completed')
            durable=journal.read()
            self.assertEqual('closed',durable['execution_sessions'][session['session_id']]['status'])
            self.assertEqual('succeeded',durable['stages'][session['stage_run_id']]['status'])
            self.assertIn('released_at',durable['leases'][session['lease_id']])
            receipt=call('finish_implementation',session_id=session['session_id'],owner='fixture-owner',summary='SYNTHETIC retry after lost acknowledgement',outcome='completed')
            campaign=call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='partial-request',check_ids=['check-1'])
            self.assertEqual('passed',campaign['outcome'])
            self.assertEqual(['check-1','check-2'],campaign['selected_checks'])
            self.assertEqual({'check-1','check-2'},set(campaign['check_results']))
            self.assertFalse(any('carried_from' in a for a in campaign['check_results'].values()))
            marker.write_text('sleep')
            worker='import os,sys\nfrom pathlib import Path\nfrom harness.api import API\nimport harness.execution as execution\noriginal=execution.run_process\ndef crash(argv,cwd,timeout,cancel,on_started):\n def started(pid,actual):\n  on_started(pid,actual)\n  os._exit(74)\n return original(argv,cwd,timeout,cancel,started)\nexecution.run_process=crash\nAPI(Path(sys.argv[1]),Path(sys.argv[2])).call("run_checks",{"project_id":sys.argv[3],"implementation_id":sys.argv[4],"owner":"fixture-owner","request_id":"crashed-check"})\n'
            process=subprocess.run([sys.executable,'-B','-c',worker,str(base/'private'),str(STANDARD),pid,receipt['implementation_id']],cwd=STANDARD,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.assertEqual(74,process.returncode)
            pending=call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='crashed-check')
            self.assertEqual('running',pending['outcome'])
            self.assertFalse(call('get_verification',implementation_id=receipt['implementation_id'])['eligible_complete'])
            view=call('reconcile_execution',kind='verification',request_id='crashed-check',owner='fixture-owner',action='status')
            self.assertEqual('exited',view['controller']['state'])
            if os.name=='nt':
                for _ in range(20):
                    if all(c['state']=='exited' for c in view['children']): break
                    time.sleep(.1)
                    view=call('reconcile_execution',kind='verification',request_id='crashed-check',owner='fixture-owner',action='status')
                self.assertTrue(view['can_reconcile'],view)
            else:
                # POSIX has no Windows job object: do not steal while an orphan still lives.
                for attempt in journal.read()['verification_attempts'].values():
                    if attempt['campaign_id']==pending['campaign_id'] and attempt.get('pid'):
                        try: os.killpg(attempt['pid'],9)
                        except ProcessLookupError: pass
            recovered=call('reconcile_execution',kind='verification',request_id='crashed-check',owner='fixture-owner',action='reconcile')
            self.assertTrue(recovered['reconciled'])
            self.assertEqual('interrupted',call('get_verification',implementation_id=receipt['implementation_id'])['outcome'])
            marker.write_text('pass')
            with patch('harness.execution.environment_fingerprint',side_effect=HarnessError('fixture_environment_failure','SYNTHETIC fault injection')):
                with self.assertRaises(HarnessError): call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='setup-failed')
            failed=journal.read()['execution_requests']['verification/setup-failed']
            self.assertEqual('failed',failed['status'])
            self.assertIn('released_at',journal.read()['leases'][failed['lease_id']])
            self.assertEqual('interrupted',journal.read()['stages'][failed['stage_run_id']]['status'])
            self.assertFalse(call('get_verification',implementation_id=receipt['implementation_id'])['eligible_complete'])
            with patch('harness.execution.CAMPAIGN_BUDGET_SECONDS',0):
                blocked=call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='budget-zero')
            self.assertEqual('blocked',blocked['outcome'])
            self.assertEqual({},blocked['check_results'])
            self.assertFalse(call('get_verification',implementation_id=receipt['implementation_id'])['eligible_complete'])
            original_fingerprint=environment_fingerprint
            changed=[False]
            def drift_before_launch(*args):
                result=original_fingerprint(*args)
                if not changed[0]:
                    (product/'unexpected.txt').write_bytes(b'SYNTHETIC concurrent edit')
                    changed[0]=True
                return result
            with patch('harness.execution.environment_fingerprint',side_effect=drift_before_launch), patch('harness.execution.run_process',side_effect=AssertionError('Process must not launch after source drift')):
                blocked=call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='source-drift-before-launch')
            self.assertEqual('blocked',blocked['outcome'])
            evidence=next(iter(blocked['check_results'].values()))
            self.assertEqual('not_launched',evidence['launch_state'])
            self.assertTrue(journal.fsck()['ok'])

    def test_full_stage_handoff_real_verification_rerun_and_readonly_view(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder); product=base/'product'; product.mkdir()
            marker=base/'fixture-flag'; marker.write_text('pass',encoding='utf-8')
            (product/'check.py').write_text('from pathlib import Path\nimport sys, json\nassert 2 + 3 == 5\nflag=Path(sys.argv[1]).read_text()\nif flag == "drift": Path("unexpected.py").write_text("drift")\nassert flag != "fail"\nprint("HARNESS_CASE_RESULTS="+json.dumps({"cases":[{"case_id":"case-1","status":"passed"},{"case_id":"case-2","status":"passed"}]}))\n',encoding='utf-8')
            api=API(base/'private',STANDARD)
            pid,call=approved_fixture(api,product,marker)
            self.assertFalse((product/'.git').exists())
            self.assertFalse((product/'.harness').exists())
            session=call('begin_implementation',run_id='fixture-run',unit_id='unit-1',owner='fixture-owner',request_id='begin-1')
            self.assertEqual(session['session_id'],call('begin_implementation',run_id='fixture-run',unit_id='unit-1',owner='fixture-owner',request_id='begin-1')['session_id'])
            receipt=call('finish_implementation',session_id=session['session_id'],owner='fixture-owner',summary='SYNTHETIC fixture implementation observed',outcome='completed')
            self.assertEqual('completed',receipt['outcome'])
            journal=api.registry.journal(pid)
            closed=journal.read()
            self.assertEqual('succeeded',closed['stages'][session['stage_run_id']]['status'])
            self.assertIn('released_at',closed['leases'][session['lease_id']])
            events=len(closed['events'])
            self.assertEqual(receipt,call('finish_implementation',session_id=session['session_id'],owner='fixture-owner',summary='same request retry',outcome='completed'))
            self.assertEqual(events,len(journal.read()['events']))
            first=call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='verify-1')
            self.assertEqual('passed',first['outcome'])
            self.assertTrue(call('get_verification',implementation_id=receipt['implementation_id'])['eligible_complete'])
            self.assertEqual(first['campaign_id'],call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='verify-1')['campaign_id'])
            journal=api.registry.journal(pid)
            before=encoded(journal.read())
            loaded=call('get_artifact',ref=first['ref'])
            self.assertIn('passed',loaded['report'])
            rendered=call('render_artifact',ref=first['ref'],format='html')
            self.assertTrue(Path(rendered['path']).is_file())
            self.assertEqual(before,encoded(journal.read()))
            marker.write_text('fail',encoding='utf-8')
            self.assertFalse(call('get_verification',implementation_id=receipt['implementation_id'])['eligible_complete'])
            second=call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='verify-2')
            self.assertEqual('failed',second['outcome'])
            status=call('get_verification',implementation_id=receipt['implementation_id'])
            self.assertFalse(status['eligible_complete'])
            self.assertEqual(second['campaign_id'],status['latest_campaign']['campaign_id'])
            self.assertEqual('passed',journal.read()['verification'][first['campaign_id']]['outcome'])
            marker.write_text('drift',encoding='utf-8')
            third=call('run_checks',implementation_id=receipt['implementation_id'],owner='fixture-owner',request_id='verify-3')
            self.assertEqual('blocked',third['outcome'])
            self.assertFalse(call('get_verification',implementation_id=receipt['implementation_id'])['eligible_complete'])
            self.assertFalse((product/'.git').exists())
            self.assertTrue(journal.fsck()['ok'])

if __name__=='__main__': unittest.main()
