# SPDX-License-Identifier: Apache-2.0
"""Synthetic workloads with ephemeral keys, not real organizational approvals."""
from pathlib import Path
from .common import digest
from .signing import generate, sign, ROLES
from .kernel import WorldGate, observe_readonly
from .probes import cases, oracle, planner
NOW = 1000

class Fixture:

    def __init__(self, path, units=100, max_calls=10, max_total_units=100, clock=NOW):
        self.path = Path(path)
        self.now = clock
        self.keys = {}
        self.trust = {}
        for role in ROLES:
            raw, pub = generate()
            self.keys[role] = (raw, 'key-' + role)
            self.trust['key-' + role] = {'principal': role + '-person', 'tenant': 'demo', 'roles': [role], 'public_key': pub}
        self.g = WorldGate.create(path, self.trust, [{'tenant': 'demo', 'resource': 'stock-a', 'units': units}, {'tenant': 'demo', 'resource': 'stock-b', 'units': units}])
        policy = {'strict_integer': True, 'respect_floor': True, 'ignore_untrusted_text': True}
        self.candidate_hash = digest({'policy': policy, 'adapter': 'inventory.reserve-v2'})
        self.contract = {'kind': 'contract', 'tenant': 'demo', 'owner': 'owner-person', 'contract_id': 'contract-1', 'candidate_hash': self.candidate_hash, 'operation': 'inventory.reserve', 'resources': ['stock-a', 'stock-b'], 'min_remaining': 2, 'max_units_per_action': 20, 'issued_at': clock, 'expires_at': clock + 3600, 'max_lease_seconds': 300}
        self.ch = self.g.apply('contract', self.s('owner', self.contract), clock)['hash']
        data = cases(81)
        grades = [planner(c, policy) == oracle(c) for c in data]
        self.preflight = {'input_hash': digest(data), 'grades': grades, 'groups': len(grades)}
        self.evidence = {'kind': 'evidence', 'tenant': 'demo', 'contract_hash': self.ch, 'candidate_hash': self.candidate_hash, 'operation': 'inventory.reserve', 'verdict': 'PASS_WITHIN_SCOPE', 'origin': 'synthetic_local_execution', 'case_groups': len(grades), 'artifact_hash': digest(self.preflight), 'issued_at': clock, 'expires_at': clock + 1200}
        self.eh = self.g.apply('evidence', self.s('evaluator', self.evidence), clock)['hash']
        self.grant = {'kind': 'grant', 'tenant': 'demo', 'grant_id': 'grant-1', 'actor': 'executor-person', 'contract_hash': self.ch, 'candidate_hash': self.candidate_hash, 'evidence_hash': self.eh, 'resources': ['stock-a', 'stock-b'], 'operation': 'inventory.reserve', 'max_calls': max_calls, 'max_total_units': max_total_units, 'issued_at': clock, 'expires_at': clock + 300}
        self.g.apply('grant', self.approvals(self.grant), clock)

    def s(self, role, p):
        return sign(p, *self.keys[role])

    def approvals(self, p):
        return {'review': self.s('reviewer', p), 'operator': self.s('operator', p)}

    def action(self, id='action-1', units=3, revision=0, **changes):
        p = {'kind': 'action', 'tenant': 'demo', 'action_id': id, 'actor': 'executor-person', 'grant_id': 'grant-1', 'contract_hash': self.ch, 'candidate_hash': self.candidate_hash, 'operation': 'inventory.reserve', 'resource': 'stock-a', 'units': units, 'expected_revision': revision}
        p.update(changes)
        return self.s('executor', p)

    def run(self, e=None):
        e = e or self.action()
        self.g.apply('prepare', e, self.now + 1)
        return self.g.apply('commit', e, self.now + 2)

    def observe(self, id='action-1', now=None):
        now = self.now + 3 if now is None else now
        e = observe_readonly(self.path, 'demo', id, *self.keys['observer'], now)
        return self.g.apply('observe', e, now)

    def compensation(self, id='action-1', request=None, now=None):
        n = self.now + 4 if now is None else now
        r = request or self.action(id)
        return self.s('operator', {'kind': 'compensate', 'tenant': 'demo', 'action_id': id, 'request_hash': digest(r['payload']), 'reason': 'Synthetic authorized compensation', 'nonce': 'undo-' + id, 'issued_at': n, 'expires_at': n + 120})

    def revocation(self, kind='evidence', now=None):
        n = self.now + 2 if now is None else now
        return self.s('operator', {'kind': 'revoke', 'tenant': 'demo', 'target_kind': kind, 'target': self.eh if kind == 'evidence' else 'grant-1', 'reason': 'Corrected evidence invalidates future authority', 'nonce': 'revoke-1', 'issued_at': n, 'expires_at': n + 120})
