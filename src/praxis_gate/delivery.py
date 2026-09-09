# SPDX-License-Identifier: Apache-2.0
"""Two real local databases demonstrate ambiguous delivery. No external connector."""
import sqlite3
from pathlib import Path
from .common import Rejected, canonical, loads, digest, ident, integer
from .kernel import Connection, Crash

class DeliveryLab:

    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            raise Rejected('OUTPUT_EXISTS')
        self.path.mkdir(parents=True)
        with self.connect('client') as c:
            c.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,body TEXT,hash TEXT,state TEXT)')
        with self.connect('provider') as c:
            c.executescript('CREATE TABLE effects(id TEXT PRIMARY KEY,hash TEXT,units INTEGER);CREATE TABLE stock(units INTEGER);INSERT INTO stock VALUES(100);')

    def connect(self, which):
        return sqlite3.connect(self.path / (which + '.sqlite'), isolation_level=None, timeout=10, factory=Connection)

    def enqueue(self, id, units):
        ident(id)
        integer(units, 1, 100)
        b = {'id': id, 'units': units}
        with self.connect('client') as c:
            row = c.execute('SELECT hash FROM jobs WHERE id=?', (id,)).fetchone()
            if row:
                if row[0] != digest(b):
                    raise Rejected('IDEMPOTENCY_CONFLICT')
            else:
                c.execute("INSERT INTO jobs VALUES(?,?,?,'READY')", (id, canonical(b).decode(), digest(b)))
        return self.status(id)

    def status(self, id):
        with self.connect('client') as c:
            r = c.execute('SELECT body,hash,state FROM jobs WHERE id=?', (id,)).fetchone()
        if not r:
            raise Rejected('JOB_UNKNOWN')
        return {'body': loads(r[0]), 'hash': r[1], 'state': r[2]}

    def provider_apply(self, id, h, u, lie=False):
        with self.connect('provider') as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT hash FROM effects WHERE id=?', (id,)).fetchone()
            if old:
                if old[0] != h:
                    raise Rejected('PROVIDER_IDEMPOTENCY_CONFLICT')
                return
            if lie:
                return
            if c.execute('SELECT units FROM stock').fetchone()[0] < u:
                raise Rejected('PROVIDER_STOCK')
            c.execute('UPDATE stock SET units=units-?', (u,))
            c.execute('INSERT INTO effects VALUES(?,?,?)', (id, h, u))

    def deliver(self, id, lose_reply=False, crash_before_send=False, lie=False):
        with self.connect('client') as c:
            c.execute('BEGIN IMMEDIATE')
            r = c.execute('SELECT body,hash,state FROM jobs WHERE id=?', (id,)).fetchone()
            if not r or r[2] != 'READY':
                raise Rejected('NO_BLIND_REDELIVERY')
            c.execute("UPDATE jobs SET state='SENDING' WHERE id=?", (id,))
        if crash_before_send:
            raise Crash('Stopped after durable SENDING')
        self.provider_apply(id, r[1], loads(r[0])['units'], lie)
        with self.connect('client') as c:
            c.execute('UPDATE jobs SET state=? WHERE id=?', ('OUTCOME_UNKNOWN' if lose_reply else 'ACK_UNVERIFIED', id))
        return self.status(id) if lose_reply else self.reconcile(id)

    def reconcile(self, id, status_available=True):
        j = self.status(id)
        if j['state'] == 'READY':
            raise Rejected('NOT_SENT')
        if not status_available:
            s = 'OUTCOME_UNKNOWN'
        else:
            with self.connect('provider') as c:
                r = c.execute('SELECT hash,units FROM effects WHERE id=?', (id,)).fetchone()
            s = 'VERIFIED_PROVIDER_EFFECT' if r and r[0] == j['hash'] and (r[1] == j['body']['units']) else 'RECONCILIATION_REQUIRED' if r else 'RETRY_AUTHORIZATION_REQUIRED'
        with self.connect('client') as c:
            c.execute('UPDATE jobs SET state=? WHERE id=?', (s, id))
        return {**self.status(id), 'automatic_retry': False}

    def export(self):
        with self.connect('provider') as c:
            u = c.execute('SELECT units FROM stock').fetchone()[0]
            n = c.execute('SELECT COUNT(*) FROM effects').fetchone()[0]
        with self.connect('client') as c:
            ids = [r[0] for r in c.execute('SELECT id FROM jobs ORDER BY id')]
        return {'jobs': [self.status(id) for id in ids], 'provider_remaining_units': u, 'provider_effects': n, 'boundary': 'Two local SQLite databases, not a network/payment adapter or distributed exactly-once guarantee.'}
