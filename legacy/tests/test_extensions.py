import copy
import tempfile
import unittest
from pathlib import Path
from praxis_os.common import ValidationError,load,read_jsonl,save,digest
from praxis_os.lineage import reopen
from praxis_os.causal import finite_interventions
from praxis_os.stats import sampling_audit
from praxis_os.fixtures import demo_project
from praxis_os.harness import execute,bundle,replay

class ExtensionTests(unittest.TestCase):
    def graph(self):return {'nodes':[{'id':'s','kind':'source','depends_on':[]},{'id':'c','kind':'claim','depends_on':['s']},
                                    {'id':'r','kind':'release','depends_on':['c']},{'id':'i','kind':'source','depends_on':[]}]}
    def change(self):return {'target':'s','actor':'reviewer','reason':'corrected','status':'SUPERSEDED'}
    def test_descendants_reopen_independent_preserved(self):
        g=self.graph();out=reopen(g,self.change())
        self.assertEqual(out['affected'],['c','r']);self.assertEqual(out['independent_preserved'],['i']);self.assertEqual(out['nodes'],g['nodes'])
    def test_missing_source_rejected(self):
        c=self.change();c['target']='none'
        with self.assertRaises(ValidationError):reopen(self.graph(),c)
    def test_lineage_cycle_rejected(self):
        g=self.graph();g['nodes'][0]['depends_on']=['r']
        with self.assertRaises(ValidationError):reopen(g,self.change())
    def test_no_automatic_new_truth(self):self.assertFalse(reopen(self.graph(),self.change())['new_answer_generated'])
    def test_weighted_sampling(self):
        out=sampling_audit([{'id':str(i),'passed':i>=8,'inclusion_probability':1.0 if i<8 else .1} for i in range(10)])
        self.assertEqual(out['unweighted_rate'],.2);self.assertAlmostEqual(out['weighted_rate'],20/28)
        self.assertIsNone(out['population_ci'])
    def test_unknown_sampling(self):
        out=sampling_audit([{'id':'a','passed':True}]);self.assertIsNone(out['weighted_rate'])
    def test_zero_inclusion_denied(self):
        with self.assertRaises(ValidationError):sampling_audit([{'id':'a','passed':True,'inclusion_probability':0}])
    def test_causal_negative_control(self):
        for r in finite_interventions()['results']:
            self.assertEqual(r['correct_base'],24);self.assertEqual(r['correct_without_read'],0)
            self.assertEqual(r['correct_without_memory_metadata'],24)
    def test_adapter_failure_recorded_not_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            p=demo_project();p['experiment'].update(trials=1,bootstrap_samples=200);p['cases'][0]['input']['orders'][0]['quantity']=-1
            s=execute(p,Path(d)/'run')
            self.assertEqual(len(s['assessments']),144)
            self.assertTrue(any(a['coordinates']['quality'].get('reason')=='ADAPTER_ERROR' for a in s['assessments']))
    def test_imported_run_cannot_smuggle_cot_or_policy(self):
        with tempfile.TemporaryDirectory() as d:
            p=demo_project();p['experiment'].update(trials=1,bootstrap_samples=200)
            execute(p,Path(d)/'a');runs=read_jsonl(Path(d)/'a/runs.jsonl')
            runs[0]['chain_of_thought']='DO_NOT_STORE'
            runs[0]['spans'][0]['attrs']['private_thought']='ALSO_DO_NOT_STORE'
            runs[0]['certificate']={'state':'ALLOW_ALL'}
            bundle(p,runs,Path(d)/'b')
            text=Path(d,'b/runs.jsonl').read_text()
            self.assertNotIn('DO_NOT_STORE',text);self.assertNotIn('ALLOW_ALL',text)
            self.assertEqual(replay(Path(d)/'b')['state'],'RECOMPUTED_MATCH')
