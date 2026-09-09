import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from praxis_os.common import *
from praxis_os.stats import *
from praxis_os.contracts import *
from praxis_os.evaluators import *
from praxis_os.fixtures import demo_project,judge_fixture,otlp_fixture,adversarial_diagnostics
from praxis_os.adapters import builtin_execute,ToolBroker
from praxis_os.harness import analysis,execute,replay
from praxis_os.telemetry import import_otlp
from praxis_os.feedback import proposals

class SerializationTests(unittest.TestCase):
    def test_duplicate_keys(self):
        with self.assertRaises(ValidationError):loads('{"a":1,"a":2}')
    def test_nonfinite_load(self):
        for x in ('NaN','Infinity','-Infinity'):
            with self.subTest(x=x),self.assertRaises(ValidationError):loads('{"x":'+x+'}')
    def test_nonfinite_dump(self):
        with self.assertRaises(ValidationError):canonical({'x':float('nan')})
    def test_canonical_order(self):
        self.assertEqual(digest({'b':2,'a':1}),digest({'a':1,'b':2}))
    def test_bool_not_number(self):
        with self.assertRaises(ValidationError):number(True,'x')
    def test_size_limit(self):
        with self.assertRaises(ValidationError):loads(' '*8_000_001)
    def test_new_output_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValidationError):new_output(d)
    def test_chain_valid(self):
        rows=chained([{'a':1},{'b':2}]);self.assertTrue(verify_chain(rows))
    def test_chain_tamper(self):
        rows=chained([{'a':1},{'b':2}]);rows[0]['event']['a']=8
        self.assertFalse(verify_chain(rows))
    def test_chain_truncation_needs_anchor(self):
        rows=chained([{'a':1},{'b':2}]);self.assertTrue(verify_chain(rows[:1]))
        self.assertFalse(verify_chain(rows[:1],rows[-1]['hash'],2))
    def test_manifest_extra_file(self):
        with tempfile.TemporaryDirectory() as d:
            save(Path(d)/'x.json',{'a':1});save(Path(d)/'manifest.json',file_manifest(d))
            self.assertTrue(verify_manifest(d))
            Path(d,'extra.txt').write_text('x')
            self.assertFalse(verify_manifest(d))

class StatsTests(unittest.TestCase):
    def test_wilson_extremes(self):
        a=wilson(0,10);b=wilson(10,10)
        self.assertEqual(a[0],0);self.assertGreater(a[1],.2);self.assertLess(b[0],.8)
    def test_wilson_empty(self):self.assertIsNone(wilson(0,0))
    def test_wilson_invalid(self):
        for s,n in [(3,2),(-1,2),(1,-1)]:
            with self.subTest(s=s,n=n),self.assertRaises(ValidationError):wilson(s,n)
    def test_wilson_symmetry(self):
        for n in range(1,60):
            for s in range(n+1):
                lo,hi=wilson(s,n);rlo,rhi=wilson(n-s,n)
                self.assertGreaterEqual(lo,0);self.assertLessEqual(hi,1)
                self.assertAlmostEqual(lo,1-rhi);self.assertAlmostEqual(hi,1-rlo)
    def rows(self,repeat=2):
        return [{'group_id':str(g),'case_id':str(g),'trial':t,'arm':arm,
                 'passed':True if arm=='ON' else bool(g%2)} for g in range(10) for t in range(repeat) for arm in ('OFF','ON')]
    def test_paired_effect(self):
        r=paired_cluster(self.rows(),300);self.assertEqual(r['delta'],.5);self.assertEqual(r['independent_groups'],10)
    def test_repeats_not_new_units(self):
        a=paired_cluster(self.rows(1),400);b=paired_cluster(self.rows(10),400)
        self.assertEqual(a['ci95'],b['ci95']);self.assertNotEqual(a['paired_trials'],b['paired_trials'])
    def test_missing_arm_rejected(self):
        with self.assertRaises(ValidationError):paired_cluster(self.rows()[:-1])
    def test_duplicate_pair_rejected(self):
        a=self.rows();a.append(a[0])
        with self.assertRaises(ValidationError):paired_cluster(a)
    def test_single_cluster_no_interval(self):
        self.assertIsNone(paired_cluster(self.rows()[:4])['ci95'])
    def test_judge_abstentions(self):
        a=judge_audit(judge_fixture());self.assertEqual(a['coverage'],.9);self.assertEqual(a['confusion']['abstain'],2)
    def test_judge_no_negative_gold(self):
        a=judge_audit({'judge_version':'j','rows':[{'item_id':'x','truth':True,'prediction':True}]})
        self.assertIsNone(a['false_accept_rate']);self.assertIsNone(a['false_accept_ci95'])
    def test_judge_duplicate(self):
        a=judge_fixture();a['rows'].append(a['rows'][0])
        with self.assertRaises(ValidationError):judge_audit(a)
    def test_judge_probability_invalid(self):
        a=judge_fixture();a['rows'][0]['probability']=1.2
        with self.assertRaises(ValidationError):judge_audit(a)
    def test_panel_disagreement(self):
        a=judge_panel([{'judge_id':'a','family':'one','verdict':'PASS'},{'judge_id':'b','family':'one','verdict':'FAIL'}])
        self.assertEqual(a['status'],'DISAGREEMENT_REQUIRES_REVIEW');self.assertEqual(a['families'],1)
        self.assertFalse(a['release_authority'])
    def test_panel_duplicate(self):
        a={'judge_id':'a','family':'one','verdict':'PASS'}
        with self.assertRaises(ValidationError):judge_panel([a,a])
    def test_panel_unanimity_not_independence(self):
        a=judge_panel([{'judge_id':str(i),'family':'one','verdict':'PASS'} for i in range(5)])
        self.assertEqual(a['status'],'ADVISORY_CONSENSUS');self.assertFalse(a['independence_established'])

class ContractsTests(unittest.TestCase):
    def test_demo_contract(self):self.assertIsNotNone(validate_project(demo_project()))
    def test_unknown_check(self):
        p=demo_project();p['contract']['checks'][0]['kind']='execute_python'
        with self.assertRaises(ValidationError):validate_project(p)
    def test_duplicate_case(self):
        p=demo_project();p['cases'].append(p['cases'][0])
        with self.assertRaises(ValidationError):validate_project(p)
    def test_bad_trials(self):
        p=demo_project();p['experiment']['trials']=0
        with self.assertRaises(ValidationError):validate_project(p)
    def test_no_holdout(self):
        p=demo_project()
        for c in p['cases']:c['split']='train'
        with self.assertRaises(ValidationError):validate_project(p)
    def test_exact_leakage(self):
        p=demo_project();c=copy.deepcopy(p['cases'][0]);c.update(case_id='extra',group_id='other',split='train')
        self.assertEqual(dataset_audit(p['cases']+[c])['state'],'BLOCK')
    def test_group_leakage(self):
        p=demo_project();c=copy.deepcopy(p['cases'][0]);c.update(case_id='extra',split='train');c['input']={'changed':True}
        self.assertEqual(dataset_audit(p['cases']+[c])['state'],'BLOCK')
    def test_trace_cycle(self):
        spans=[{'id':'r','parent':None,'kind':'root'},{'id':'a','parent':'b','kind':'tool'},{'id':'b','parent':'a','kind':'tool'}]
        with self.assertRaises(ValidationError):validate_spans(spans)
    def test_missing_parent(self):
        with self.assertRaises(ValidationError):validate_spans([{'id':'r','parent':None,'kind':'root'},{'id':'a','parent':'no','kind':'tool'}])
    def test_multiple_roots(self):
        with self.assertRaises(ValidationError):validate_spans([{'id':'a','parent':None,'kind':'root'},{'id':'b','parent':None,'kind':'root'}])
    def test_private_thought_removed(self):
        spans=[{'id':'r','parent':None,'kind':'root','attrs':{'chain_of_thought':'secret','prompt':'private','operation':'read','password':'bad'}}]
        a,d=sanitize_spans(spans);self.assertNotIn('secret',canonical(a).decode());self.assertEqual(set(d),{'chain_of_thought','prompt','password'})
    def test_redaction(self):
        self.assertNotIn('abc@xyz.com',redact_text('abc@xyz.com Bearer abc123'))
        self.assertNotIn('abc123',redact_text('abc@xyz.com Bearer abc123'))
    def test_otel_import_content_minimization(self):
        a=import_otlp(otlp_fixture());txt=canonical(a).decode()
        self.assertNotIn('private@example.com',txt);self.assertNotIn('DO NOT LOG',txt)
        self.assertEqual(len(a['traces'][0]['spans']),2)
    def test_otel_empty(self):
        with self.assertRaises(ValidationError):import_otlp({})

class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.p=demo_project();self.c=self.p['cases'][0];self.contract=self.p['contract']
        self.run=builtin_execute('direct',self.c,'ON',0,0,self.contract)
        self.run.update(run_id='r',carrier='direct',arm='ON',trial=0)
    def grade(self):return evaluate_run(self.run,self.c,self.contract)
    def test_good(self):self.assertEqual(self.grade()['verdict'],'PASS_WITHIN_SCOPE')
    def test_bool_cannot_equal_int(self):
        a=grade_output({'x':True},{'x':1},[{'id':'a','kind':'equals_expected','field':'x'}]);self.assertEqual(a['state'],'FAIL')
    def test_missing_expectation_unknown(self):
        a=grade_output({'x':1},{},[{'id':'a','kind':'equals_expected','field':'x'}]);self.assertEqual(a['state'],'UNKNOWN')
    def test_wrong_output(self):
        self.run['output']['total_cents']=1;self.assertEqual(self.grade()['verdict'],'REVISE')
    def test_resource_overrun(self):
        self.contract['limits']['cost_microunits']=0;self.run['metrics']['cost_microunits']=1
        self.assertEqual(self.grade()['verdict'],'REVISE')
    def test_energy_unknown_not_zero(self):
        self.contract['limits']['energy_j']=3
        self.assertEqual(self.grade()['coordinates']['resources']['state'],'UNKNOWN')
    def test_energy_scope_missing(self):
        self.run['metrics']['energy_j']=3
        self.assertEqual(self.grade()['coordinates']['resources']['state'],'UNKNOWN')
    def test_unauthorized_tool_blocks(self):
        self.run['spans'][2]['attrs']['operation']='delete'
        self.assertEqual(self.grade()['verdict'],'BLOCK')
    def test_tool_budget_blocks(self):
        self.contract['authority']['max_tool_calls']=0
        self.assertEqual(self.grade()['verdict'],'BLOCK')
    def test_expired_lease_blocks(self):
        self.contract['authority']['expires_step']=0
        self.assertEqual(self.grade()['verdict'],'BLOCK')
    def test_principal_mismatch(self):
        self.run['spans'][2]['attrs']['principal']='intruder'
        self.assertEqual(self.grade()['verdict'],'BLOCK')
    def test_denied_call_not_performed_violation(self):
        self.run['spans'][2]['attrs'].update(performed=False,operation='delete')
        self.assertEqual(self.grade()['coordinates']['authority']['state'],'PASS')
    def test_missing_authority_unknown(self):
        del self.run['spans'][2]['attrs']['principal']
        self.assertEqual(self.grade()['coordinates']['authority']['state'],'UNKNOWN')
    def test_memory_other_namespace(self):
        self.run['spans'][3]['attrs']['namespace']='other'
        self.assertEqual(self.grade()['verdict'],'BLOCK')
    def test_memory_untracked(self):
        self.run['spans'][3]['attrs']['source_refs']=['x']
        self.assertEqual(self.grade()['verdict'],'BLOCK')
    def test_self_report_not_outcome(self):
        self.run['outcome']['source_kind']='agent_self_report'
        self.assertEqual(self.grade()['coordinates']['outcome']['state'],'UNKNOWN')
    def test_failed_outcome(self):
        self.run['outcome']['state']['summary_saved']=False
        self.assertEqual(self.grade()['verdict'],'REVISE')
    def test_timeout_in_denominator(self):
        self.run['execution_status']='TIMEOUT'
        self.assertEqual(self.grade()['coordinates']['quality']['state'],'FAIL')
    def test_broker_enforcement(self):
        b=ToolBroker(self.contract['authority'],[])
        with self.assertRaises(PermissionError):b.invoke('orders.delete','orders','local-operator',1)
        self.assertEqual(b.calls,0)
    def test_broker_quota(self):
        a=copy.deepcopy(self.contract['authority']);a['max_tool_calls']=1;b=ToolBroker(a,[])
        b.invoke('orders.read','orders','local-operator',1)
        with self.assertRaises(PermissionError):b.invoke('orders.read','orders','local-operator',2)
    def test_sql_and_direct_agree(self):
        for c in self.p['cases']:
            for arm in ['ON','OFF']:
                a=builtin_execute('direct',c,arm,0,0,self.contract)
                b=builtin_execute('relational',c,arm,0,0,self.contract)
                self.assertEqual(a['output'],b['output'])
    def test_diagnostics_have_positive_control(self):
        a=adversarial_diagnostics()['scenarios'];self.assertEqual(a[0]['full_verdict'],'PASS_WITHIN_SCOPE')
        self.assertTrue(all(x['full_verdict']!='PASS_WITHIN_SCOPE' for x in a[1:]))

class HarnessTests(unittest.TestCase):
    def test_run_and_replay(self):
        with tempfile.TemporaryDirectory() as d:
            p=demo_project();p['experiment'].update(trials=1,bootstrap_samples=200)
            s=execute(p,Path(d)/'run')
            self.assertEqual(len(s['assessments']),144)
            self.assertEqual(s['carriers']['unsafe']['gate']['state'],'BLOCK')
            self.assertEqual(s['carriers']['direct']['gate']['state'],'ELIGIBLE_FOR_SHADOW_REVIEW')
            self.assertEqual(replay(Path(d)/'run')['state'],'RECOMPUTED_MATCH')
            self.assertTrue(proposals(s)['proposals'])
    def test_no_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=demo_project();p['experiment'].update(trials=1,bootstrap_samples=200)
            with self.assertRaises(ValidationError):execute(p,d)
    def test_incomplete_matrix_cannot_drop_failures(self):
        with self.assertRaises(ValidationError):analysis(demo_project(),[])
    def test_gate_dataset_leakage(self):
        s={'independent_groups':24,'ci95':[.3,.6]}
        a=skill_gate(s,[],{'state':'BLOCK'},{})
        self.assertEqual(a['state'],'BLOCK')
    def test_low_groups_review(self):
        s={'independent_groups':2,'ci95':[.3,.6]}
        self.assertEqual(skill_gate(s,[],{'state':'PASS'},{})['state'],'REVIEW')
    def test_missing_confidence_review(self):
        s={'independent_groups':24,'ci95':None}
        self.assertEqual(skill_gate(s,[],{'state':'PASS'},{})['state'],'REVIEW')

    def test_no_on_records_never_eligible(self):
        s={'independent_groups':24,'ci95':[.3,.6]}
        self.assertEqual(skill_gate(s,[],{'state':'PASS'},{})['state'],'REVIEW')
