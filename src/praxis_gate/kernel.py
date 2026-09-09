# SPDX-License-Identifier: Apache-2.0
"""Real local SQLite inventory effects, with evidence and approval checks.
The trusted base is the host clock, OS, database, configured keys and adapter code.
An untrusted agent must NOT have direct access to that trusted base.
"""
from __future__ import annotations
import sqlite3, time
from contextlib import contextmanager
from pathlib import Path
from .common import Rejected, canonical, loads, digest, fields, ident, integer, hexhash, interval
from .signing import validate_trust, verify, sign

class Crash(RuntimeError):
    pass

class Connection(sqlite3.Connection):

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()
SCHEMA = '\nCREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);\nCREATE TABLE inventory(tenant TEXT,resource TEXT,units INTEGER CHECK(units>=0),revision INTEGER,PRIMARY KEY(tenant,resource));\nCREATE TABLE objects(kind TEXT,id TEXT,tenant TEXT,body TEXT,active INTEGER DEFAULT 1,PRIMARY KEY(kind,id,tenant));\nCREATE TABLE grants(tenant TEXT,id TEXT,body TEXT,calls INTEGER,units INTEGER,active INTEGER,PRIMARY KEY(tenant,id));\nCREATE TABLE actions(tenant TEXT,id TEXT,body TEXT,request_hash TEXT,state TEXT,before_state TEXT,after_state TEXT,receipt TEXT,observation TEXT,PRIMARY KEY(tenant,id));\nCREATE TABLE events(seq INTEGER PRIMARY KEY,prev TEXT,body TEXT,hash TEXT);\n'

class WorldGate:

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            raise Rejected('DB_NOT_FOUND')
        with self.connect() as c:
            self.trust = validate_trust(loads(c.execute("SELECT v FROM meta WHERE k='trust'").fetchone()[0]))

    @classmethod
    def create(cls, path, trust, resources):
        validate_trust(trust)
        p = Path(path)
        if p.exists():
            raise Rejected('DB_EXISTS')
        seen = set()
        for r in resources:
            fields(r, ('tenant', 'resource', 'units'))
            ident(r['tenant'])
            ident(r['resource'])
            integer(r['units'])
            key = (r['tenant'], r['resource'])
            if key in seen:
                raise Rejected('DUPLICATE_RESOURCE')
            seen.add(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(p, isolation_level=None, factory=Connection) as c:
            c.executescript(SCHEMA)
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO meta VALUES(?,?)', ('trust', canonical(trust).decode()))
            for r in resources:
                c.execute('INSERT INTO inventory VALUES(?,?,?,0)', (r['tenant'], r['resource'], r['units']))
            cls.event(c, {'stage': 'bootstrap', 'resources': resources, 'trust_hash': digest(trust)})
        return cls(p)

    def connect(self):
        c = sqlite3.connect(self.path, timeout=15, isolation_level=None, factory=Connection)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA synchronous=FULL')
        return c

    @contextmanager
    def tx(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            yield c

    @staticmethod
    def event(c, body):
        r = c.execute('SELECT seq,hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        seq, prev = (r[0] + 1, r[1]) if r else (1, '0' * 64)
        e = {'seq': seq, 'prev': prev, 'body': body}
        h = digest(e)
        c.execute('INSERT INTO events VALUES(?,?,?,?)', (seq, prev, canonical(body).decode(), h))
        return {**e, 'hash': h}

    @staticmethod
    def snap(c, t, r):
        x = c.execute('SELECT units,revision FROM inventory WHERE tenant=? AND resource=?', (t, r)).fetchone()
        if not x:
            raise Rejected('RESOURCE_NOT_FOUND')
        return {'tenant': t, 'resource': r, 'units': x['units'], 'revision': x['revision']}

    def snapshot(self, t='demo', r='stock-a'):
        with self.connect() as c:
            return self.snap(c, t, r)

    @staticmethod
    def get(c, kind, id, tenant, now):
        r = c.execute('SELECT body,active FROM objects WHERE kind=? AND id=? AND tenant=?', (kind, id, tenant)).fetchone()
        if not r or not r['active']:
            raise Rejected(kind.upper() + '_UNAVAILABLE')
        b = loads(r['body'])
        interval(now, b['issued_at'], b['expires_at'])
        return b

    @staticmethod
    def result(r, reused=False):
        return {'action_id': r['id'], 'state': r['state'], 'request_hash': r['request_hash'], 'before': loads(r['before_state']), 'after': loads(r['after_state']), 'receipt': loads(r['receipt']) if r['receipt'] else None, 'idempotent_replay': reused}

    @staticmethod
    def action_row(c, t, id):
        return c.execute('SELECT * FROM actions WHERE tenant=? AND id=?', (t, id)).fetchone()

    def active(self, c, p, now):
        row = c.execute('SELECT * FROM grants WHERE tenant=? AND id=?', (p['tenant'], p['grant_id'])).fetchone()
        if not row or not row['active']:
            raise Rejected('GRANT_REVOKED_OR_UNKNOWN')
        g = loads(row['body'])
        interval(now, g['issued_at'], g['expires_at'])
        for key in ('actor', 'candidate_hash', 'contract_hash', 'operation'):
            if g[key] != p[key]:
                raise Rejected('ACTION_BINDING', key)
        if p['resource'] not in g['resources']:
            raise Rejected('RESOURCE_NOT_GRANTED')
        ct = self.get(c, 'contract', g['contract_hash'], p['tenant'], now)
        self.get(c, 'evidence', g['evidence_hash'], p['tenant'], now)
        if p['units'] > ct['max_units_per_action']:
            raise Rejected('PER_ACTION_BUDGET')
        if row['calls'] + 1 > g['max_calls'] or row['units'] + p['units'] > g['max_total_units']:
            raise Rejected('GRANT_BUDGET_EXHAUSTED')
        return (ct, g)

    def apply(self, stage, env, now=None, _fault=None):
        """now and _fault are trusted test-driver inputs, never signed agent fields.
        Production adapters must supply a trusted host clock, not user-controlled time.
        """
        now = int(time.time()) if now is None else integer(now)
        try:
            with self.tx() as c:
                result = self.step(c, stage, env, now)
                if not result.get('idempotent_replay'):
                    self.event(c, {'stage': stage, 'input': env, 'at': now, 'result_hash': digest(result)})
                if stage == 'commit' and _fault == 'before_commit':
                    raise Crash('Injected fault before commit; transaction rolls back')
            if stage == 'commit' and _fault == 'after_commit':
                raise Crash('Injected lost reply after durable commit')
            return result
        except Rejected as e:
            try:
                h = digest(env)
            except Rejected:
                h = 'UNSERIALIZABLE'
            with self.tx() as c:
                self.event(c, {'stage': 'denied', 'operation': stage, 'input_hash': h, 'reason': e.code, 'at': now})
            raise

    def step(self, c, stage, env, now):
        if stage == 'grant':
            fields(env, ('review', 'operator'))
            fields(env['review'], ('key_id', 'payload', 'signature'))
            fields(env['operator'], ('key_id', 'payload', 'signature'))
            p = env['review']['payload']
            fields(p, ('kind', 'tenant', 'grant_id', 'actor', 'contract_hash', 'candidate_hash', 'evidence_hash', 'resources', 'operation', 'max_calls', 'max_total_units', 'issued_at', 'expires_at'))
            if p['kind'] != 'grant' or p != env['operator'].get('payload'):
                raise Rejected('APPROVAL_DISAGREEMENT')
            rev = verify(env['review'], self.trust, 'reviewer', p['tenant'])
            op = verify(env['operator'], self.trust, 'operator', p['tenant'])
            ct = self.get(c, 'contract', p['contract_hash'], p['tenant'], now)
            ev = self.get(c, 'evidence', p['evidence_hash'], p['tenant'], now)
            if len({rev, op, ct['owner'], p['actor']}) != 4:
                raise Rejected('SEPARATION_OF_DUTIES')
            interval(now, p['issued_at'], p['expires_at'], ct['max_lease_seconds'])
            ident(p['grant_id'])
            ident(p['actor'])
            integer(p['max_calls'], 1, 100000)
            integer(p['max_total_units'], 1)
            if not isinstance(p['resources'], list) or not p['resources'] or len(set(p['resources'])) != len(p['resources']):
                raise Rejected('RESOURCE_SCOPE')
            if not set(p['resources']) <= set(ct['resources']):
                raise Rejected('GRANT_RESOURCE_ESCALATION')
            if p['contract_hash'] != ev['contract_hash'] or p['candidate_hash'] != ct['candidate_hash'] or p['candidate_hash'] != ev['candidate_hash'] or (p['operation'] != ct['operation']):
                raise Rejected('GRANT_SCOPE_MISMATCH')
            if p['expires_at'] > min(ct['expires_at'], ev['expires_at']):
                raise Rejected('GRANT_OUTLIVES_EVIDENCE')
            if not any((e['principal'] == p['actor'] and e['tenant'] == p['tenant'] and ('executor' in e['roles']) for e in self.trust.values())):
                raise Rejected('UNKNOWN_ACTOR')
            if c.execute('SELECT 1 FROM grants WHERE tenant=? AND id=?', (p['tenant'], p['grant_id'])).fetchone():
                raise Rejected('GRANT_ID_REUSE')
            c.execute('INSERT INTO grants VALUES(?,?,?,0,0,1)', (p['tenant'], p['grant_id'], canonical(p).decode()))
            return {'grant_id': p['grant_id'], 'grant_hash': digest(p)}
        fields(env, ('key_id', 'payload', 'signature'))
        p = env['payload']
        if not isinstance(p, dict):
            raise Rejected('OBJECT_REQUIRED')
        if stage == 'contract':
            fields(p, ('kind', 'tenant', 'owner', 'contract_id', 'candidate_hash', 'operation', 'resources', 'min_remaining', 'max_units_per_action', 'issued_at', 'expires_at', 'max_lease_seconds'))
            if p['kind'] != 'contract' or p['operation'] != 'inventory.reserve':
                raise Rejected('CONTRACT_KIND')
            for k in ('tenant', 'owner', 'contract_id'):
                ident(p[k])
            hexhash(p['candidate_hash'])
            integer(p['min_remaining'])
            integer(p['max_units_per_action'], 1)
            integer(p['max_lease_seconds'], 1, 86400)
            interval(now, p['issued_at'], p['expires_at'])
            if not isinstance(p['resources'], list) or not p['resources'] or len(p['resources']) != len(set(p['resources'])):
                raise Rejected('RESOURCE_SCOPE')
            for r in p['resources']:
                ident(r)
            if verify(env, self.trust, 'owner', p['tenant']) != p['owner']:
                raise Rejected('OWNER_BINDING')
        elif stage == 'evidence':
            fields(p, ('kind', 'tenant', 'contract_hash', 'candidate_hash', 'operation', 'verdict', 'origin', 'case_groups', 'artifact_hash', 'issued_at', 'expires_at'))
            if p['kind'] != 'evidence' or p['verdict'] != 'PASS_WITHIN_SCOPE':
                raise Rejected('EVIDENCE_NOT_PASSING')
            if p['origin'] not in ('synthetic_local_execution', 'externally_supplied_observation'):
                raise Rejected('EVIDENCE_ORIGIN')
            who = verify(env, self.trust, 'evaluator', p['tenant'])
            ct = self.get(c, 'contract', p['contract_hash'], p['tenant'], now)
            if who == ct['owner']:
                raise Rejected('EVALUATOR_AUTHOR_CONFLICT')
            for k in ('contract_hash', 'candidate_hash', 'artifact_hash'):
                hexhash(p[k])
            integer(p['case_groups'], 1)
            interval(now, p['issued_at'], p['expires_at'])
            if p['operation'] != ct['operation'] or p['candidate_hash'] != ct['candidate_hash']:
                raise Rejected('EVIDENCE_SCOPE_MISMATCH')
            if p['expires_at'] > ct['expires_at']:
                raise Rejected('EVIDENCE_OUTLIVES_CONTRACT')
        if stage in ('contract', 'evidence'):
            h = digest(p)
            r = c.execute('SELECT active FROM objects WHERE kind=? AND id=? AND tenant=?', (stage, h, p['tenant'])).fetchone()
            if r and (not r['active']):
                raise Rejected('REVOKED_EVIDENCE_CANNOT_REACTIVATE')
            if r:
                return {'hash': h, 'idempotent_replay': True}
            c.execute('INSERT INTO objects VALUES(?,?,?,?,1)', (stage, h, p['tenant'], canonical(p).decode()))
            return {'hash': h}
        if stage in ('prepare', 'commit'):
            fields(p, ('kind', 'tenant', 'action_id', 'actor', 'grant_id', 'contract_hash', 'candidate_hash', 'operation', 'resource', 'units', 'expected_revision'))
            if p['kind'] != 'action' or p['operation'] != 'inventory.reserve':
                raise Rejected('ACTION_KIND')
            for k in ('tenant', 'action_id', 'actor', 'grant_id', 'resource'):
                ident(p[k])
            hexhash(p['contract_hash'])
            hexhash(p['candidate_hash'])
            integer(p['units'], 1)
            integer(p['expected_revision'])
            if verify(env, self.trust, 'executor', p['tenant']) != p['actor']:
                raise Rejected('ACTOR_BINDING')
            row = self.action_row(c, p['tenant'], p['action_id'])
            h = digest(p)
            if row and row['request_hash'] != h:
                raise Rejected('IDEMPOTENCY_CONFLICT')
            if row and (stage == 'prepare' or row['state'] != 'PREPARED'):
                return self.result(row, True)
            if stage == 'commit' and (not row):
                raise Rejected('NOT_PREPARED')
            ct, g = self.active(c, p, now)
            current = self.snap(c, p['tenant'], p['resource'])
            if stage == 'prepare':
                if current['revision'] != p['expected_revision']:
                    raise Rejected('STALE_WORLD_REVISION')
                if current['units'] - p['units'] < ct['min_remaining']:
                    raise Rejected('INVARIANT_FLOOR')
                after = {**current, 'units': current['units'] - p['units'], 'revision': current['revision'] + 1}
                c.execute('INSERT INTO actions VALUES(?,?,?,?,?,?,?,NULL,NULL)', (p['tenant'], p['action_id'], canonical(p).decode(), h, 'PREPARED', canonical(current).decode(), canonical(after).decode()))
            else:
                before, after = (loads(row['before_state']), loads(row['after_state']))
                if current != before:
                    raise Rejected('WORLD_CHANGED_SINCE_PREPARE')
                if after['units'] < ct['min_remaining']:
                    raise Rejected('INVARIANT_FLOOR')
                c.execute('UPDATE inventory SET units=?,revision=? WHERE tenant=? AND resource=?', (after['units'], after['revision'], p['tenant'], p['resource']))
                c.execute('UPDATE grants SET calls=calls+1,units=units+? WHERE tenant=? AND id=?', (p['units'], p['tenant'], p['grant_id']))
                receipt = {'action_id': p['action_id'], 'tenant': p['tenant'], 'request_hash': h, 'evidence_hash': g['evidence_hash'], 'before': before, 'after': after, 'committed_at': now, 'candidate_hash': p['candidate_hash']}
                receipt['receipt_hash'] = digest(receipt)
                c.execute("UPDATE actions SET state='COMMITTED_PENDING_OBSERVATION',receipt=? WHERE tenant=? AND id=?", (canonical(receipt).decode(), p['tenant'], p['action_id']))
            return self.result(self.action_row(c, p['tenant'], p['action_id']))
        if stage == 'observe':
            fields(p, ('kind', 'tenant', 'action_id', 'request_hash', 'receipt_hash', 'actual', 'observed_at', 'expires_at'))
            if p['kind'] != 'observation':
                raise Rejected('OBSERVATION_KIND')
            interval(now, p['observed_at'], p['expires_at'], 300)
            who = verify(env, self.trust, 'observer', p['tenant'])
            row = self.action_row(c, p['tenant'], p['action_id'])
            if not row or not row['receipt']:
                raise Rejected('NO_COMMITTED_EFFECT')
            req = loads(row['body'])
            rc = loads(row['receipt'])
            if who == req['actor']:
                raise Rejected('SELF_OBSERVATION')
            if p['request_hash'] != row['request_hash'] or p['receipt_hash'] != rc['receipt_hash']:
                raise Rejected('OBSERVATION_BINDING')
            if p['observed_at'] < rc['committed_at']:
                raise Rejected('PREMATURE_OBSERVATION')
            if row['observation']:
                if loads(row['observation']) != env:
                    raise Rejected('OBSERVATION_ALREADY_RECORDED')
                return self.result(row, True)
            if row['state'] != 'COMMITTED_PENDING_OBSERVATION':
                raise Rejected('ACTION_NOT_OBSERVABLE')
            actual = self.snap(c, p['tenant'], req['resource'])
            if actual != p['actual']:
                raise Rejected('OBSERVER_SNAPSHOT_NOT_CURRENT')
            state = 'VERIFIED_LOCAL_EFFECT' if actual == loads(row['after_state']) else 'RECONCILIATION_REQUIRED'
            c.execute('UPDATE actions SET state=?,observation=? WHERE tenant=? AND id=?', (state, canonical(env).decode(), p['tenant'], p['action_id']))
            if state == 'RECONCILIATION_REQUIRED':
                c.execute('UPDATE grants SET active=0 WHERE tenant=? AND id=?', (p['tenant'], req['grant_id']))
            return self.result(self.action_row(c, p['tenant'], p['action_id']))
        if stage in ('compensate', 'revoke'):
            required = ('kind', 'tenant', 'reason', 'nonce', 'issued_at', 'expires_at') + (('action_id', 'request_hash') if stage == 'compensate' else ('target_kind', 'target'))
            fields(p, required)
            if p['kind'] != stage:
                raise Rejected('COMMAND_KIND')
            interval(now, p['issued_at'], p['expires_at'], 300)
            ident(p['nonce'])
            who = verify(env, self.trust, 'operator', p['tenant'])
            if not isinstance(p['reason'], str) or not 1 <= len(p['reason']) <= 500:
                raise Rejected('REASON_REQUIRED')
            if stage == 'revoke':
                if p['target_kind'] == 'evidence':
                    row = c.execute("SELECT 1 FROM objects WHERE kind='evidence' AND id=? AND tenant=?", (p['target'], p['tenant'])).fetchone()
                    if not row:
                        raise Rejected('TARGET_NOT_FOUND')
                    c.execute("UPDATE objects SET active=0 WHERE kind='evidence' AND id=? AND tenant=?", (p['target'], p['tenant']))
                    ids = [r['id'] for r in c.execute('SELECT * FROM grants WHERE tenant=? AND active=1 ORDER BY id', (p['tenant'],)) if loads(r['body'])['evidence_hash'] == p['target']]
                elif p['target_kind'] == 'grant':
                    if not c.execute('SELECT 1 FROM grants WHERE tenant=? AND id=?', (p['tenant'], p['target'])).fetchone():
                        raise Rejected('TARGET_NOT_FOUND')
                    ids = [p['target']]
                else:
                    raise Rejected('COMMAND_KIND')
                for gid in ids:
                    c.execute('UPDATE grants SET active=0 WHERE tenant=? AND id=?', (p['tenant'], gid))
                return {'state': 'REVOKED', 'affected_grants': ids, 'historical_effects_erased': False}
            row = self.action_row(c, p['tenant'], p['action_id'])
            if not row or not row['receipt']:
                raise Rejected('NO_COMMITTED_EFFECT')
            req = loads(row['body'])
            before, after = (loads(row['before_state']), loads(row['after_state']))
            if who == req['actor'] or p['request_hash'] != row['request_hash']:
                raise Rejected('COMPENSATION_AUTHORITY')
            if row['state'] in ('COMPENSATED', 'COMPENSATION_CONFLICT'):
                return self.result(row, True)
            current = self.snap(c, p['tenant'], req['resource'])
            state = 'COMPENSATION_CONFLICT'
            if current == after:
                c.execute('UPDATE inventory SET units=?,revision=revision+1 WHERE tenant=? AND resource=?', (before['units'], p['tenant'], req['resource']))
                state = 'COMPENSATED'
            c.execute('UPDATE actions SET state=? WHERE tenant=? AND id=?', (state, p['tenant'], p['action_id']))
            return self.result(self.action_row(c, p['tenant'], p['action_id']))
        raise Rejected('UNKNOWN_STAGE')

    def export(self):
        with self.connect() as c:
            inv = [dict(r) for r in c.execute('SELECT * FROM inventory ORDER BY tenant,resource')]
            acts = [self.result(r) for r in c.execute('SELECT * FROM actions ORDER BY tenant,id')]
            grants = [dict(r) for r in c.execute('SELECT tenant,id,calls,units,active FROM grants ORDER BY tenant,id')]
            objects = [dict(r) for r in c.execute('SELECT kind,id,tenant,active FROM objects ORDER BY tenant,kind,id')]
            events = [{'seq': r['seq'], 'prev': r['prev'], 'body': loads(r['body']), 'hash': r['hash']} for r in c.execute('SELECT * FROM events ORDER BY seq')]
        return {'system': 'PRAXIS-WORLDGATE', 'version': '2.0.0', 'trust': self.trust, 'inventory': inv, 'actions': acts, 'grants': grants, 'objects': objects, 'events': events}

    def anchor(self, private, key_id, tenant, now=None):
        e = self.export()['events']
        p = {'kind': 'anchor', 'tenant': tenant, 'event_count': len(e), 'tail': e[-1]['hash'], 'trust_hash': digest(self.trust), 'issued_at': int(time.time()) if now is None else now}
        out = sign(p, private, key_id)
        verify(out, self.trust, 'operator', tenant)
        return out

def verify_export(x, anchor=None, trusted_registry=None):
    trust = validate_trust(x['trust'])
    prev = '0' * 64
    if trusted_registry is not None:
        validate_trust(trusted_registry)
        if digest(trusted_registry) != digest(trust):
            raise Rejected('PINNED_TRUST_MISMATCH')
    for i, e in enumerate(x['events'], 1):
        fields(e, ('seq', 'prev', 'body', 'hash'))
        if e['seq'] != i or e['prev'] != prev or digest({k: v for k, v in e.items() if k != 'hash'}) != e['hash']:
            raise Rejected('AUDIT_CHAIN_BROKEN')
        prev = e['hash']
    if anchor:
        p = anchor['payload']
        verify(anchor, trust, 'operator', p['tenant'])
        if p['kind'] != 'anchor' or p['event_count'] != len(x['events']) or p['tail'] != prev or (p['trust_hash'] != digest(trust)):
            raise Rejected('AUDIT_ANCHOR_MISMATCH')
    return {'chain_valid': True, 'events': len(x['events']), 'tail': prev, 'signature_valid': anchor is not None, 'external_trust_pinned': trusted_registry is not None, 'authenticated_anchor_checked': anchor is not None and trusted_registry is not None}

def observe_readonly(db, tenant, action_id, private, key_id, now=None):
    now = int(time.time()) if now is None else now
    with sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True, factory=Connection) as c:
        c.row_factory = sqlite3.Row
        r = WorldGate.action_row(c, tenant, action_id)
        if not r or not r['receipt']:
            raise Rejected('NO_COMMITTED_EFFECT')
        req, rc = (loads(r['body']), loads(r['receipt']))
        actual = WorldGate.snap(c, tenant, req['resource'])
    return sign({'kind': 'observation', 'tenant': tenant, 'action_id': action_id, 'request_hash': r['request_hash'], 'receipt_hash': rc['receipt_hash'], 'actual': actual, 'observed_at': now, 'expires_at': now + 120}, private, key_id)
