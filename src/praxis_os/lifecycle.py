"""Transactional local release registry, scoped approvals and outcome-led rollback.

HMAC authenticates possession of a shared local key, NOT a human's real identity.
All state transitions concern this registry only; no external deployment occurs.
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path
from .common import ValidationError, canonical, digest, loads, nonempty, number

ROLES={'SHADOW':'reviewer','CANARY':'operator','ACTIVE':'operator','ROLLED_BACK':'operator'}
NEXT={'EVALUATED':{'SHADOW'},'SHADOW':{'CANARY','ROLLED_BACK'},
      'CANARY':{'ACTIVE','ROLLED_BACK'},'ACTIVE':{'ROLLED_BACK'},'BLOCKED':set(),'ROLLED_BACK':set()}


def sign(key,payload):
    if not isinstance(key,bytes) or len(key)<32:raise ValidationError('Use a random key of at least 32 bytes')
    return {'payload':payload,'hmac_sha256':hmac.new(key,canonical(payload),hashlib.sha256).hexdigest()}


def approval(key,release_id,artifact_hash,from_state,to_state,principal,evidence,expires,nonce=None):
    return sign(key,{'release_id':release_id,'artifact_hash':artifact_hash,'from':from_state,
                     'to':to_state,'principal':principal,'evidence_hash':digest(evidence),
                     'expires':expires,'nonce':nonce or secrets.token_hex(16)})


class Registry:
    def __init__(self,path,key,principals=None):
        if len(key)<32:raise ValidationError('Key too short')
        self.key=key
        self.db=sqlite3.connect(str(path),timeout=10,isolation_level=None)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS releases(id TEXT PRIMARY KEY, artifact TEXT NOT NULL,
            author TEXT NOT NULL, state TEXT NOT NULL, certificate TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY, previous TEXT NOT NULL,
            event TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY);
        CREATE TRIGGER IF NOT EXISTS journal_no_update BEFORE UPDATE ON journal
            BEGIN SELECT RAISE(ABORT,'Journal is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS journal_no_delete BEFORE DELETE ON journal
            BEGIN SELECT RAISE(ABORT,'Journal is append-only'); END;
        ''')
        stored=self.db.execute("SELECT v FROM settings WHERE k='principals'").fetchone()
        if stored:
            self.principals=loads(stored[0])
            if principals is not None and principals!=self.principals:
                raise ValidationError('Principal policy already frozen for this registry')
        else:
            if not principals or any(role not in ('author','reviewer','operator','observer') for role in principals.values()):
                raise ValidationError('Explicit local principal-role map required')
            self.principals=principals
            self.db.execute("INSERT INTO settings VALUES('principals',?)",(canonical(principals).decode(),))
        self.policy_hash=digest(self.principals)

    def close(self):self.db.close()

    def _append(self,event):
        last=self.db.execute('SELECT seq,hash FROM journal ORDER BY seq DESC LIMIT 1').fetchone()
        seq,prev=(last[0]+1,last[1]) if last else (1,'0'*64)
        obj={'seq':seq,'previous':prev,'event':event}
        hh=digest(obj)
        self.db.execute('INSERT INTO journal VALUES(?,?,?,?)',(seq,prev,canonical(event).decode(),hh))
        return hh

    def create(self,rid,artifact,author,certificate):
        for v,n in ((rid,'id'),(artifact,'artifact'),(author,'author')):nonempty(v,n)
        if len(artifact)!=64 or any(x not in '0123456789abcdef' for x in artifact):raise ValidationError('SHA-256 artifact identity required')
        if self.principals.get(author)!='author':raise ValidationError('Author role required')
        if certificate.get('release_authority') is not False:
            raise ValidationError('Evaluation cannot confer release authority')
        if certificate.get('candidate_hash')!=artifact:
            raise ValidationError('Candidate artifact and evaluation scope do not match')
        for field in ('assessment_hash','project_hash','observations_hash'):
            nonempty(certificate.get(field),field)
        state='EVALUATED' if certificate.get('state')=='ELIGIBLE_FOR_SHADOW_REVIEW' else 'BLOCKED'
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('INSERT INTO releases VALUES(?,?,?,?,?)',(rid,artifact,author,state,canonical(certificate).decode()))
            self._append({'kind':'REGISTERED','release':rid,'artifact_hash':artifact,'author':author,
                          'state':state,'certificate_hash':digest(certificate),'principal_policy_hash':self.policy_hash})
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK');raise
        return state

    def get(self,rid):
        r=self.db.execute('SELECT artifact,author,state,certificate FROM releases WHERE id=?',(rid,)).fetchone()
        if not r:raise ValidationError('Unknown release')
        return {'release_id':rid,'artifact_hash':r[0],'author':r[1],'state':r[2],'certificate':loads(r[3])}

    def transition(self,rid,to,evidence,token,now=None):
        now=time.time() if now is None else number(now,'now',0)
        p=token.get('payload',{})
        sig=token.get('hmac_sha256','')
        expected=hmac.new(self.key,canonical(p),hashlib.sha256).hexdigest()
        if not isinstance(sig,str) or not hmac.compare_digest(sig,expected):raise ValidationError('Invalid approval signature')
        if set(p)!={'release_id','artifact_hash','from','to','principal','evidence_hash','expires','nonce'}:
            raise ValidationError('Approval schema mismatch')
        number(p['expires'],'expires',0)
        if now>=p['expires']:raise ValidationError('Expired approval')
        nonempty(p['nonce'],'nonce')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            r=self.get(rid)
            if (p['release_id']!=rid or p['artifact_hash']!=r['artifact_hash'] or p['from']!=r['state'] or
                p['to']!=to or p['evidence_hash']!=digest(evidence)):
                raise ValidationError('Approval scope or evidence mismatch')
            if to not in NEXT.get(r['state'],set()):raise ValidationError('Illegal lifecycle transition')
            who=p['principal']
            if self.principals.get(who)!=ROLES.get(to) or who==r['author']:
                raise ValidationError('Separated human-role approval required')
            if to in ('CANARY','ACTIVE'):
                required_phase='SHADOW' if to=='CANARY' else 'CANARY'
                if evidence.get('phase')!=required_phase or evidence.get('artifact_hash')!=r['artifact_hash']:
                    raise ValidationError('Outcome evidence phase/artifact mismatch')
                if self.principals.get(evidence.get('observer'))!='observer':raise ValidationError('Named observation role required')
                if evidence.get('source_kind') not in ('synthetic','observed'):
                    raise ValidationError('Explicit evidence origin required')
                number(evidence.get('n'),'outcome.n',5,10**8,integer=True)
                if evidence.get('harm_events')!=0 or type(evidence.get('harm_events')) is not int:
                    raise ValidationError('Unresolved harm prevents progression')
                if evidence.get('accepted') is not True:raise ValidationError('Observed acceptance missing')
                number(evidence.get('expires'),'outcome.expires',0)
                if now>=evidence['expires']:raise ValidationError('Stale outcome evidence')
            elif to=='SHADOW':
                if evidence.get('independent_review') is not True or not evidence.get('rollback_plan'):
                    raise ValidationError('Independent review and rollback plan required')
            elif not evidence.get('reason'):
                raise ValidationError('Rollback reason required')
            try:self.db.execute('INSERT INTO nonces VALUES(?)',(p['nonce'],))
            except sqlite3.IntegrityError as exc:raise ValidationError('Approval replay denied') from exc
            self.db.execute('UPDATE releases SET state=? WHERE id=?',(to,rid))
            self._append({'kind':'TRANSITION','release':rid,'artifact_hash':r['artifact_hash'],
                          'from':r['state'],'to':to,'principal':who,'evidence':evidence,
                          'approval':token,'external_deployment_performed':False})
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK');raise
        return self.get(rid)

    def observe(self,rid,outcome,token,now=None):
        """A signed new outcome can revoke local eligibility without rewriting history."""
        now=time.time() if now is None else number(now,'now',0)
        p=token.get('payload',{}); sig=token.get('hmac_sha256','')
        expected=hmac.new(self.key,canonical(p),hashlib.sha256).hexdigest()
        if not isinstance(sig,str) or not hmac.compare_digest(sig,expected):raise ValidationError('Invalid observation signature')
        if set(p)!={'release_id','artifact_hash','principal','expires','nonce','outcome_hash'}:
            raise ValidationError('Observation schema mismatch')
        number(p['expires'],'expires',0);nonempty(p['nonce'],'nonce')
        if p['expires']<=now or p['release_id']!=rid or p['outcome_hash']!=digest(outcome):raise ValidationError('Observation scope/expiry mismatch')
        if self.principals.get(p['principal'])!='observer':raise ValidationError('Observer role required')
        if outcome.get('status') not in ('BENEFIT','NO_CHANGE','UNKNOWN','HARM'):raise ValidationError('Invalid outcome status')
        if outcome.get('source_kind') not in ('synthetic','observed'):raise ValidationError('Outcome provenance missing')
        nonempty(outcome.get('evidence_ref'),'evidence_ref')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            r=self.get(rid)
            if p['artifact_hash']!=r['artifact_hash']:raise ValidationError('Wrong artifact')
            try:self.db.execute('INSERT INTO nonces VALUES(?)',(p['nonce'],))
            except sqlite3.IntegrityError as exc:raise ValidationError('Observation replay denied') from exc
            target=r['state']
            if outcome['status']=='HARM' and r['state'] in ('SHADOW','CANARY','ACTIVE'):
                target='ROLLED_BACK'
            self.db.execute('UPDATE releases SET state=? WHERE id=?',(target,rid))
            self._append({'kind':'OUTCOME','release':rid,'artifact_hash':r['artifact_hash'],
                          'from':r['state'],'to':target,'observation':outcome,'approval':token,
                          'follow_up':'Local state only. Owner must execute and verify any real-world rollback separately.'})
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK');raise
        return self.get(rid)

    def export(self):
        rows=[{'seq':a,'previous':b,'event':loads(c),'hash':d} for a,b,c,d in self.db.execute('SELECT * FROM journal ORDER BY seq')]
        return {'events':rows,'tail':rows[-1]['hash'] if rows else '0'*64,'count':len(rows),
                'releases':[self.get(x[0]) for x in self.db.execute('SELECT id FROM releases ORDER BY id')],
                'boundary':'Local shared-key registry; not verified identity, institutional approval or an external deployer.'}

    def verify(self):
        from .common import verify_chain
        export=self.export()
        if not verify_chain(export['events'],export['tail'],export['count']):return False
        states={}; artifacts={}; certificates={};authors={};nonces=set()
        for row in export['events']:
            ev=row['event'];rid=ev['release']
            if ev['kind']=='REGISTERED':
                if rid in states:return False
                if ev.get('principal_policy_hash')!=self.policy_hash:return False
                states[rid]=ev['state'];artifacts[rid]=ev['artifact_hash']
                certificates[rid]=ev['certificate_hash'];authors[rid]=ev['author']
            else:
                if states.get(rid)!=ev['from'] or artifacts.get(rid)!=ev['artifact_hash']:return False
                tok=ev['approval']
                nonce=tok['payload'].get('nonce')
                if not nonce or nonce in nonces:return False
                nonces.add(nonce)
                sig=hmac.new(self.key,canonical(tok['payload']),hashlib.sha256).hexdigest()
                if not hmac.compare_digest(sig,tok['hmac_sha256']):return False
                states[rid]=ev['to']
        return (all(states.get(r['release_id'])==r['state'] and artifacts.get(r['release_id'])==r['artifact_hash']
                    and certificates.get(r['release_id'])==digest(r['certificate']) and authors.get(r['release_id'])==r['author']
                    for r in export['releases']) and len(states)==len(export['releases'])
                and nonces=={r[0] for r in self.db.execute('SELECT nonce FROM nonces')})
