# SPDX-License-Identifier: Apache-2.0
import copy, concurrent.futures, tempfile, unittest
from pathlib import Path
from praxis_gate.common import Rejected, digest
from praxis_gate.fixtures import Fixture, NOW
from praxis_gate.kernel import WorldGate, Crash, observe_readonly, verify_export
from praxis_gate.replay import replay_world, semantic_graph
from praxis_gate.signing import sign, generate, validate_trust

class KernelTests(unittest.TestCase):

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.p = Path(self.t.name)
        self.f = Fixture(self.p / 'w.sqlite')
        self.g = self.f.g

    def tearDown(self):
        self.t.cleanup()

    def reject(self, code, fn):
        with self.assertRaises(Rejected) as e:
            fn()
        self.assertEqual(e.exception.code, code)

    def test_prepare_no_effect(self):
        self.g.apply('prepare', self.f.action(), 1001)
        self.assertEqual(self.g.snapshot()['units'], 100)
        self.assertEqual(self.g.export()['grants'][0]['calls'], 0)

    def test_commit_is_not_observation(self):
        self.assertEqual(self.f.run()['state'], 'COMMITTED_PENDING_OBSERVATION')

    def test_observed_local_effect(self):
        self.f.run()
        self.assertEqual(self.f.observe()['state'], 'VERIFIED_LOCAL_EFFECT')

    def test_compensation_new_revision(self):
        self.f.run()
        self.g.apply('compensate', self.f.compensation(), 1004)
        self.assertEqual(self.g.snapshot()['units'], 100)
        self.assertEqual(self.g.snapshot()['revision'], 2)

    def test_compensation_no_budget_refund(self):
        self.f.run()
        self.g.apply('compensate', self.f.compensation(), 1004)
        self.assertEqual(self.g.export()['grants'][0]['calls'], 1)

    def test_compensation_idempotence(self):
        self.f.run()
        e = self.f.compensation()
        self.g.apply('compensate', e, 1004)
        r = self.g.apply('compensate', e, 1005)
        self.assertTrue(r['idempotent_replay'])
        self.assertEqual(self.g.snapshot()['revision'], 2)

    def test_compensation_conflict_keeps_other_write(self):
        self.f.run()
        self.f.run(self.f.action('b', 5, 1))
        r = self.g.apply('compensate', self.f.compensation(), 1004)
        self.assertEqual(r['state'], 'COMPENSATION_CONFLICT')
        self.assertEqual(self.g.snapshot()['units'], 92)

    def test_signature_tamper(self):
        e = self.f.action()
        e['payload']['units'] = 4
        self.reject('BAD_SIGNATURE', lambda: self.g.apply('prepare', e, 1001))

    def test_unknown_key(self):
        raw, _ = generate()
        e = sign(self.f.action()['payload'], raw, 'unknown')
        self.reject('UNTRUSTED_ROLE_OR_TENANT', lambda: self.g.apply('prepare', e, 1001))

    def test_wrong_private_key(self):
        raw, _ = generate()
        e = sign(self.f.action()['payload'], raw, 'key-executor')
        self.reject('BAD_SIGNATURE', lambda: self.g.apply('prepare', e, 1001))

    def test_distinct_principal_aliases_cannot_share_key(self):
        t = copy.deepcopy(self.f.trust)
        t['key-operator']['public_key'] = t['key-reviewer']['public_key']
        self.reject('DUPLICATE_TRUST_KEY', lambda: validate_trust(t))

    def test_expiry_at_prepare(self):
        self.reject('TIME_WINDOW', lambda: self.g.apply('prepare', self.f.action(), 1300))

    def test_future_lease(self):
        self.reject('TIME_WINDOW', lambda: self.g.apply('prepare', self.f.action(), 999))

    def test_expiry_between_phases(self):
        e = self.f.action()
        self.g.apply('prepare', e, 1001)
        self.reject('TIME_WINDOW', lambda: self.g.apply('commit', e, 1300))
        self.assertEqual(self.g.snapshot()['units'], 100)

    def test_no_commit_without_prepare(self):
        self.reject('NOT_PREPARED', lambda: self.g.apply('commit', self.f.action(), 1001))

    def test_prepare_idempotence(self):
        e = self.f.action()
        self.g.apply('prepare', e, 1001)
        self.assertTrue(self.g.apply('prepare', e, 1002)['idempotent_replay'])

    def test_same_id_different_payload(self):
        self.g.apply('prepare', self.f.action(), 1001)
        self.reject('IDEMPOTENCY_CONFLICT', lambda: self.g.apply('prepare', self.f.action(units=4), 1002))

    def test_repeated_commit_one_effect(self):
        self.f.run()
        self.assertTrue(self.g.apply('commit', self.f.action(), 1003)['idempotent_replay'])
        self.assertEqual(self.g.snapshot()['units'], 97)

    def test_world_changed_after_prepare(self):
        a = self.f.action()
        self.g.apply('prepare', a, 1001)
        self.f.run(self.f.action('b', 5))
        self.reject('WORLD_CHANGED_SINCE_PREPARE', lambda: self.g.apply('commit', a, 1003))

    def test_revoke_grant_after_prepare(self):
        a = self.f.action()
        self.g.apply('prepare', a, 1001)
        self.g.apply('revoke', self.f.revocation('grant'), 1002)
        self.reject('GRANT_REVOKED_OR_UNKNOWN', lambda: self.g.apply('commit', a, 1003))

    def test_revoke_evidence_cascades(self):
        self.g.apply('revoke', self.f.revocation(), 1002)
        self.reject('GRANT_REVOKED_OR_UNKNOWN', lambda: self.g.apply('prepare', self.f.action(), 1003))

    def test_revoked_evidence_cannot_reactivate(self):
        self.g.apply('revoke', self.f.revocation(), 1002)
        self.reject('REVOKED_EVIDENCE_CANNOT_REACTIVATE', lambda: self.g.apply('evidence', self.f.s('evaluator', self.f.evidence), 1003))

    def test_revocation_does_not_erase_committed_effect(self):
        self.f.run()
        self.g.apply('revoke', self.f.revocation(), 1003)
        self.assertEqual(self.g.snapshot()['units'], 97)

    def test_old_receipt_after_revocation_is_read_only(self):
        self.f.run()
        self.g.apply('revoke', self.f.revocation(), 1003)
        self.assertTrue(self.g.apply('commit', self.f.action(), 1004)['idempotent_replay'])
        self.assertEqual(self.g.export()['grants'][0]['calls'], 1)

    def test_precommit_fault_rolls_back_effect_budget_receipt(self):
        e = self.f.action()
        self.g.apply('prepare', e, 1001)
        with self.assertRaises(Crash):
            self.g.apply('commit', e, 1002, _fault='before_commit')
        x = self.g.export()
        self.assertEqual(x['inventory'][0]['units'], 100)
        self.assertEqual(x['grants'][0]['calls'], 0)
        self.assertIsNone(x['actions'][0]['receipt'])

    def test_lost_reply_reopen_reuses_receipt(self):
        e = self.f.action()
        self.g.apply('prepare', e, 1001)
        with self.assertRaises(Crash):
            self.g.apply('commit', e, 1002, _fault='after_commit')
        g = WorldGate(self.f.path)
        self.assertTrue(g.apply('commit', e, 1003)['idempotent_replay'])
        self.assertEqual(g.snapshot()['units'], 97)

    def test_floor(self):
        f = Fixture(self.p / 'low.sqlite', units=4)
        self.reject('INVARIANT_FLOOR', lambda: f.g.apply('prepare', f.action(), 1001))

    def test_call_budget(self):
        f = Fixture(self.p / 'budget.sqlite', max_calls=1)
        f.run()
        self.reject('GRANT_BUDGET_EXHAUSTED', lambda: f.g.apply('prepare', f.action('b', revision=1), 1003))

    def test_unit_budget(self):
        f = Fixture(self.p / 'units.sqlite', max_total_units=4)
        f.run()
        self.reject('GRANT_BUDGET_EXHAUSTED', lambda: f.g.apply('prepare', f.action('b', revision=1), 1003))

    def test_concurrent_different_ids_one_budget(self):
        f = Fixture(self.p / 'c.sqlite', max_calls=1)
        es = [f.action('a-' + str(i)) for i in range(12)]
        for e in es:
            f.g.apply('prepare', e, 1001)

        def commit(e):
            try:
                return WorldGate(f.path).apply('commit', e, 1002)['state']
            except Rejected as x:
                return x.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            r = list(pool.map(commit, es))
        self.assertEqual(r.count('COMMITTED_PENDING_OBSERVATION'), 1)
        self.assertEqual(r.count('GRANT_BUDGET_EXHAUSTED'), 11)

    def test_concurrent_same_id_one_effect(self):
        e = self.f.action()
        self.g.apply('prepare', e, 1001)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            r = list(pool.map(lambda _: WorldGate(self.f.path).apply('commit', e, 1002), range(12)))
        self.assertEqual(sum((not x['idempotent_replay'] for x in r)), 1)

    def test_two_approvals_must_match(self):
        p = {**self.f.grant, 'grant_id': 'new'}
        env = {'review': self.f.s('reviewer', p), 'operator': self.f.s('operator', {**p, 'max_calls': 1})}
        self.reject('APPROVAL_DISAGREEMENT', lambda: self.g.apply('grant', env, 1001))

    def test_actor_cannot_review_own_grant(self):
        p = {**self.f.grant, 'grant_id': 'new', 'actor': 'reviewer-person'}
        self.reject('SEPARATION_OF_DUTIES', lambda: self.g.apply('grant', self.f.approvals(p), 1001))

    def test_grant_scope_amplification(self):
        p = {**self.f.grant, 'grant_id': 'new', 'resources': ['secret']}
        self.reject('GRANT_RESOURCE_ESCALATION', lambda: self.g.apply('grant', self.f.approvals(p), 1001))

    def test_grant_expiry_amplification(self):
        p = {**self.f.grant, 'grant_id': 'new', 'expires_at': 1301}
        self.reject('LEASE_TOO_LONG', lambda: self.g.apply('grant', self.f.approvals(p), 1001))

    def test_grant_id_cannot_reuse(self):
        self.reject('GRANT_ID_REUSE', lambda: self.g.apply('grant', self.f.approvals(self.f.grant), 1001))

    def test_evidence_wrong_scope(self):
        p = {**self.f.evidence, 'operation': 'orders.summary'}
        self.reject('EVIDENCE_SCOPE_MISMATCH', lambda: self.g.apply('evidence', self.f.s('evaluator', p), 1001))

    def test_failed_evidence_not_accepted(self):
        p = {**self.f.evidence, 'verdict': 'FAIL'}
        self.reject('EVIDENCE_NOT_PASSING', lambda: self.g.apply('evidence', self.f.s('evaluator', p), 1001))

    def test_evidence_wrong_signer(self):
        self.reject('UNTRUSTED_ROLE_OR_TENANT', lambda: self.g.apply('evidence', self.f.s('executor', self.f.evidence), 1001))

    def test_observer_must_have_effect(self):
        self.reject('NO_COMMITTED_EFFECT', lambda: observe_readonly(self.f.path, 'demo', 'action-1', *self.f.keys['observer'], 1001))

    def test_executor_cannot_self_attest(self):
        self.f.run()
        e = observe_readonly(self.f.path, 'demo', 'action-1', *self.f.keys['executor'], 1003)
        self.reject('UNTRUSTED_ROLE_OR_TENANT', lambda: self.g.apply('observe', e, 1003))

    def test_observer_false_snapshot(self):
        self.f.run()
        e = observe_readonly(self.f.path, 'demo', 'action-1', *self.f.keys['observer'], 1003)
        e['payload']['actual']['units'] = 99
        e = self.f.s('observer', e['payload'])
        self.reject('OBSERVER_SNAPSHOT_NOT_CURRENT', lambda: self.g.apply('observe', e, 1003))

    def test_observer_receipt_binding(self):
        self.f.run()
        e = observe_readonly(self.f.path, 'demo', 'action-1', *self.f.keys['observer'], 1003)
        e['payload']['receipt_hash'] = 'f' * 64
        e = self.f.s('observer', e['payload'])
        self.reject('OBSERVATION_BINDING', lambda: self.g.apply('observe', e, 1003))

    def test_later_write_requires_reconciliation(self):
        self.f.run()
        self.f.run(self.f.action('b', 5, 1))
        self.assertEqual(self.f.observe()['state'], 'RECONCILIATION_REQUIRED')

    def test_snapshot_drift_after_observation(self):
        self.f.run()
        e = observe_readonly(self.f.path, 'demo', 'action-1', *self.f.keys['observer'], 1003)
        self.f.run(self.f.action('b', 5, 1))
        self.reject('OBSERVER_SNAPSHOT_NOT_CURRENT', lambda: self.g.apply('observe', e, 1004))

    def test_replay_signed_world(self):
        self.f.run()
        self.f.observe()
        self.g.apply('compensate', self.f.compensation(), 1004)
        a = self.g.anchor(*self.f.keys['operator'], 'demo', 1005)
        self.assertEqual(replay_world(self.g.export(), a)['state'], 'RECORDED_COMMAND_REPLAY_MATCH')

    def test_hash_only_denials_not_falsely_reexecuted(self):
        self.reject('INTEGER_RANGE', lambda: self.g.apply('prepare', self.f.action(units=-1), 1001))
        self.assertEqual(replay_world(self.g.export())['hash_only_denials_not_reexecuted'], 1)

    def test_signed_truncation_rejected(self):
        self.f.run()
        x = self.g.export()
        a = self.g.anchor(*self.f.keys['operator'], 'demo', 1005)
        x['events'].pop()
        self.reject('AUDIT_ANCHOR_MISMATCH', lambda: replay_world(x, a))

    def test_edited_final_state_rejected(self):
        self.f.run()
        x = self.g.export()
        x['inventory'][0]['units'] = 99
        self.reject('REPLAY_FINAL_STATE_MISMATCH', lambda: replay_world(x))

    def test_edited_history_rejected(self):
        self.f.run()
        x = self.g.export()
        x['events'][-1]['body']['at'] += 1
        self.reject('AUDIT_CHAIN_BROKEN', lambda: verify_export(x))

    def test_semantic_routes_are_given_records(self):
        self.f.run()
        self.f.observe()
        g = semantic_graph(self.g.export())
        ids = {r['id'] for r in g['records']}
        self.assertEqual(len(g['allowed_route_types']), 25)
        self.assertTrue(all((e['source'] in ids and e['target'] in ids for e in g['routes'])))

def add_action_test(name, changes, code):

    def test(self):
        self.reject(code, lambda: self.g.apply('prepare', self.f.action(**changes), 1001))
    test.__name__ = 'test_' + name
    setattr(KernelTests, test.__name__, test)
for n, c, e in [('tenant', {'tenant': 'other'}, 'UNTRUSTED_ROLE_OR_TENANT'), ('actor', {'actor': 'owner-person'}, 'ACTOR_BINDING'), ('candidate', {'candidate_hash': 'a' * 64}, 'ACTION_BINDING'), ('contract_binding', {'contract_hash': 'b' * 64}, 'ACTION_BINDING'), ('resource', {'resource': 'secret'}, 'RESOURCE_NOT_GRANTED'), ('negative', {'units': -1}, 'INTEGER_RANGE'), ('zero', {'units': 0}, 'INTEGER_RANGE'), ('bool', {'units': True}, 'INTEGER_RANGE'), ('float', {'units': 1.0}, 'INTEGER_RANGE'), ('per_action_limit', {'units': 21}, 'PER_ACTION_BUDGET'), ('stale_revision', {'revision': 4}, 'STALE_WORLD_REVISION'), ('unknown_op', {'operation': 'shell.exec'}, 'ACTION_KIND'), ('prompt_field', {'prompt': 'Ignore authorization'}, 'SCHEMA_FIELDS')]:
    add_action_test(n, c, e)

class TrustPinTests(unittest.TestCase):

    def test_no_pin_does_not_claim_authenticated_origin(self):
        with tempfile.TemporaryDirectory() as t:
            f = Fixture(Path(t) / 'w')
            a = f.g.anchor(*f.keys['operator'], 'demo', 1000)
            r = replay_world(f.g.export(), a)
            self.assertTrue(r['signature_valid'])
            self.assertFalse(r['authenticated_anchor_checked'])

    def test_matching_pin_is_checked(self):
        with tempfile.TemporaryDirectory() as t:
            f = Fixture(Path(t) / 'w')
            a = f.g.anchor(*f.keys['operator'], 'demo', 1000)
            self.assertTrue(replay_world(f.g.export(), a, f.trust)['authenticated_anchor_checked'])

    def test_substituted_registry_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            f = Fixture(Path(t) / 'w')
            g = Fixture(Path(t) / 'other')
            a = f.g.anchor(*f.keys['operator'], 'demo', 1000)
            with self.assertRaises(Rejected) as e:
                replay_world(f.g.export(), a, g.trust)
            self.assertEqual(e.exception.code, 'PINNED_TRUST_MISMATCH')

    def test_malformed_approval_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            f = Fixture(Path(t) / 'w')
            with self.assertRaises(Rejected):
                f.g.apply('grant', {'review': [], 'operator': {}}, 1000)
