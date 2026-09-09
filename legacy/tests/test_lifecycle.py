import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from praxis_os.common import ValidationError,digest
from praxis_os.lifecycle import Registry,approval,sign

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.key=b'a'*32
        self.roles={'a':'author','r':'reviewer','o':'operator','v':'observer'}
        self.reg=Registry(Path(self.tmp.name)/'s.db',self.key,self.roles)
        self.art=digest('artifact')
        self.cert={'state':'ELIGIBLE_FOR_SHADOW_REVIEW','release_authority':False,'candidate_hash':self.art,
                   'assessment_hash':digest('test'),'project_hash':digest('project'),'observations_hash':digest('observations')}
        self.reg.create('r1',self.art,'a',self.cert)
    def tearDown(self):self.reg.close();self.tmp.cleanup()
    def move(self,to,e,who,nonce='unique'):
        state=self.reg.get('r1')['state']
        tok=approval(self.key,'r1',self.art,state,to,who,e,2000,nonce)
        return self.reg.transition('r1',to,e,tok,now=1000)
    def shadow(self):return self.move('SHADOW',{'independent_review':True,'rollback_plan':'restore'},'r')
    def outcome(self,phase='SHADOW'):
        return {'phase':phase,'artifact_hash':self.art,'observer':'v','source_kind':'synthetic',
                'n':5,'harm_events':0,'accepted':True,'expires':2000}
    def test_initial_not_active(self):self.assertEqual(self.reg.get('r1')['state'],'EVALUATED')
    def test_bad_cert_blocked(self):
        self.reg.create('bad',self.art,'a',dict(self.cert,state='BLOCK'))
        self.assertEqual(self.reg.get('bad')['state'],'BLOCKED')
    def test_eval_cannot_grant_authority(self):
        with self.assertRaises(ValidationError):self.reg.create('bad',self.art,'a',{'state':'ELIGIBLE_FOR_SHADOW_REVIEW','release_authority':True})
    def test_unsigned_denied(self):
        with self.assertRaises(ValidationError):self.reg.transition('r1','SHADOW',{}, {},now=1000)
    def test_expired_token(self):
        e={'independent_review':True,'rollback_plan':'restore'}
        tok=approval(self.key,'r1',self.art,'EVALUATED','SHADOW','r',e,900,'n')
        with self.assertRaises(ValidationError):self.reg.transition('r1','SHADOW',e,tok,now=1000)
    def test_evidence_substitution(self):
        e={'independent_review':True,'rollback_plan':'restore'}
        tok=approval(self.key,'r1',self.art,'EVALUATED','SHADOW','r',e,2000,'n')
        e['rollback_plan']='different'
        with self.assertRaises(ValidationError):self.reg.transition('r1','SHADOW',e,tok,now=1000)
    def test_artifact_substitution(self):
        e={'independent_review':True,'rollback_plan':'restore'}
        tok=approval(self.key,'r1',digest('wrong'),'EVALUATED','SHADOW','r',e,2000,'n')
        with self.assertRaises(ValidationError):self.reg.transition('r1','SHADOW',e,tok,now=1000)
    def test_role_separation(self):
        with self.assertRaises(ValidationError):self.move('SHADOW',{'independent_review':True,'rollback_plan':'x'},'a')
    def test_cannot_skip_shadow(self):
        with self.assertRaises(ValidationError):self.move('ACTIVE',self.outcome(),'o')
    def test_no_rollback_plan(self):
        with self.assertRaises(ValidationError):self.move('SHADOW',{'independent_review':True},'r')
    def test_shadow_succeeds(self):self.assertEqual(self.shadow()['state'],'SHADOW')
    def test_missing_outcome_blocks_canary(self):
        self.shadow()
        with self.assertRaises(ValidationError):self.move('CANARY',{},'o','n2')
    def test_small_n_blocks_canary(self):
        self.shadow();e=self.outcome();e['n']=0
        with self.assertRaises(ValidationError):self.move('CANARY',e,'o','n2')
    def test_harm_blocks_canary(self):
        self.shadow();e=self.outcome();e['harm_events']=1
        with self.assertRaises(ValidationError):self.move('CANARY',e,'o','n2')
    def test_expired_observation_blocks(self):
        self.shadow();e=self.outcome();e['expires']=500
        with self.assertRaises(ValidationError):self.move('CANARY',e,'o','n2')
    def test_nonce_replay_blocks(self):
        self.shadow()
        with self.assertRaises(ValidationError):self.move('CANARY',self.outcome(),'o','unique')
    def test_full_path_and_harm_rollback(self):
        self.shadow();self.move('CANARY',self.outcome(),'o','n2')
        self.move('ACTIVE',self.outcome('CANARY'),'o','n3')
        out={'status':'HARM','source_kind':'synthetic','evidence_ref':'new-failure'}
        tok=sign(self.key,{'release_id':'r1','artifact_hash':self.art,'principal':'v','expires':2000,'nonce':'n4','outcome_hash':digest(out)})
        self.assertEqual(self.reg.observe('r1',out,tok,now=1000)['state'],'ROLLED_BACK')
        self.assertTrue(self.reg.verify());self.assertEqual(self.reg.export()['count'],5)
    def test_unknown_outcome_keeps_state(self):
        self.shadow();out={'status':'UNKNOWN','source_kind':'synthetic','evidence_ref':'unmeasured'}
        tok=sign(self.key,{'release_id':'r1','artifact_hash':self.art,'principal':'v','expires':2000,'nonce':'n4','outcome_hash':digest(out)})
        self.assertEqual(self.reg.observe('r1',out,tok,now=1000)['state'],'SHADOW')
    def test_journal_update_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):self.reg.db.execute("UPDATE journal SET event='{}'")
    def test_journal_delete_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):self.reg.db.execute('DELETE FROM journal')
    def test_materialized_state_tamper_detected(self):
        self.reg.db.execute("UPDATE releases SET state='ACTIVE' WHERE id='r1'")
        self.assertFalse(self.reg.verify())
    def test_role_map_cannot_change_silently(self):
        with self.assertRaises(ValidationError):Registry(Path(self.tmp.name)/'s.db',self.key,{'a':'operator'})
    def test_invalid_short_key(self):
        with self.assertRaises(ValidationError):sign(b'x',{})

    def test_candidate_artifact_binding(self):
        with self.assertRaises(ValidationError):self.reg.create('wrong',digest('different'),'a',self.cert)

    def test_stored_certificate_tamper_detected(self):
        self.reg.db.execute("UPDATE releases SET certificate='{}' WHERE id='r1'")
        self.assertFalse(self.reg.verify())
    def test_nonce_store_tamper_detected(self):
        self.shadow();self.reg.db.execute("DELETE FROM nonces")
        self.assertFalse(self.reg.verify())
