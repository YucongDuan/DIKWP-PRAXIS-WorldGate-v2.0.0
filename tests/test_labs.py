# SPDX-License-Identifier: Apache-2.0
import copy, json, math, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from praxis_gate.common import Rejected, digest, loads, canonical, integer, save, load
from praxis_gate.signing import generate, sign, keyfile, validate_trust
from praxis_gate.kernel import Crash
from praxis_gate.fixtures import Fixture
from praxis_gate.delivery import DeliveryLab
from praxis_gate.probes import HoldoutBudget, repair_lab, reduce_counterexample, oracle, planner, cases
from praxis_gate.monitor import monitor

class LabTests(unittest.TestCase):

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.p = Path(self.t.name)

    def tearDown(self):
        self.t.cleanup()

    def reject(self, code, fn):
        with self.assertRaises(Rejected) as e:
            fn()
        self.assertEqual(e.exception.code, code)

    def cfg(self):
        return {'monitor_id': 'm', 'p0': 0.05, 'alternatives': [0.1, 0.2, 0.4, 0.7], 'family_alpha': 0.05, 'family_size': 2, 'protocol_hash': digest('fixed')}

    def rows(self, n=25, start=10):
        return [{'sequence': i + 1, 'group_id': 'g-' + str(i), 'failed': i >= start} for i in range(n)]

    def test_duplicate_json(self):
        self.reject('DUPLICATE_JSON_KEY', lambda: loads('{"a":1,"a":2}'))

    def test_nonfinite_json(self):
        self.reject('NONFINITE_JSON', lambda: loads('{"a":NaN}'))

    def test_nonfinite_serialization(self):
        self.reject('FINITE_JSON', lambda: canonical({'x': float('inf')}))

    def test_integer_bool_not_valid(self):
        self.reject('INTEGER_RANGE', lambda: integer(True))

    def test_delivery_loss_no_blind_retry(self):
        d = DeliveryLab(self.p / 'd')
        d.enqueue('a', 7)
        self.assertEqual(d.deliver('a', lose_reply=True)['state'], 'OUTCOME_UNKNOWN')
        self.reject('NO_BLIND_REDELIVERY', lambda: d.deliver('a'))
        self.assertEqual(d.export()['provider_effects'], 1)

    def test_delivery_reconciliation(self):
        d = DeliveryLab(self.p / 'd')
        d.enqueue('a', 7)
        d.deliver('a', lose_reply=True)
        self.assertEqual(d.reconcile('a')['state'], 'VERIFIED_PROVIDER_EFFECT')
        self.assertEqual(d.export()['provider_remaining_units'], 93)

    def test_delivery_unavailable_status(self):
        d = DeliveryLab(self.p / 'd')
        d.enqueue('a', 7)
        d.deliver('a', lose_reply=True)
        r = d.reconcile('a', False)
        self.assertEqual(r['state'], 'OUTCOME_UNKNOWN')
        self.assertFalse(r['automatic_retry'])

    def test_delivery_false_success(self):
        d = DeliveryLab(self.p / 'd')
        d.enqueue('a', 7)
        r = d.deliver('a', lie=True)
        self.assertEqual(r['state'], 'RETRY_AUTHORIZATION_REQUIRED')
        self.assertEqual(d.export()['provider_effects'], 0)

    def test_delivery_pre_send_crash(self):
        d = DeliveryLab(self.p / 'd')
        d.enqueue('a', 7)
        with self.assertRaises(Crash):
            d.deliver('a', crash_before_send=True)
        self.assertEqual(d.reconcile('a')['state'], 'RETRY_AUTHORIZATION_REQUIRED')
        self.assertEqual(d.export()['provider_remaining_units'], 100)

    def test_delivery_id_conflict(self):
        d = DeliveryLab(self.p / 'd')
        d.enqueue('a', 7)
        self.reject('IDEMPOTENCY_CONFLICT', lambda: d.enqueue('a', 8))

    def test_provider_duplicate_once(self):
        d = DeliveryLab(self.p / 'd')
        b = {'id': 'a', 'units': 7}
        d.provider_apply('a', digest(b), 7)
        d.provider_apply('a', digest(b), 7)
        self.assertEqual(d.export()['provider_remaining_units'], 93)

    def test_provider_id_conflict(self):
        d = DeliveryLab(self.p / 'd')
        d.provider_apply('a', digest('a'), 7)
        self.reject('PROVIDER_IDEMPOTENCY_CONFLICT', lambda: d.provider_apply('a', digest('b'), 7))

    def test_monitor_alarm_reference(self):
        self.assertEqual(monitor(self.cfg(), self.rows())['first_alarm_at'], 15)

    def test_monitor_clean_not_certificate(self):
        self.assertEqual(monitor(self.cfg(), self.rows(25, 100))['state'], 'NO_REJECTION_NOT_A_SAFETY_CERTIFICATE')

    def test_monitor_missing_stops_ordered_prefix(self):
        r = self.rows()
        r[5]['failed'] = None
        a = monitor(self.cfg(), r)
        self.assertEqual(a['processed_ordered_groups'], 5)
        self.assertEqual(a['state'], 'AWAITING_ORDERED_OUTCOME')

    def test_monitor_duplicate_group_rejected(self):
        r = self.rows()
        r[1]['group_id'] = r[0]['group_id']
        self.reject('ORDER_OR_GROUP_DUPLICATE', lambda: monitor(self.cfg(), r))

    def test_monitor_order_rejected(self):
        r = self.rows()
        r[0]['sequence'] = 2
        self.reject('ORDER_OR_GROUP_DUPLICATE', lambda: monitor(self.cfg(), r))

    def test_monitor_false_numeric_outcome(self):
        r = self.rows()
        r[0]['failed'] = 1
        self.reject('BINARY_OR_MISSING_REQUIRED', lambda: monitor(self.cfg(), r))

    def test_monitor_formula_first_failure(self):
        cfg = self.cfg()
        cfg['family_size'] = 1
        a = monitor(cfg, self.rows(1, 0))
        self.assertAlmostEqual(a['series'][0]['e_value_capped'], sum(cfg['alternatives']) / len(cfg['alternatives']) / cfg['p0'])

    def test_monitor_formula_two_failures(self):
        cfg = self.cfg()
        a = monitor(cfg, self.rows(2, 0))
        self.assertAlmostEqual(a['series'][1]['e_value_capped'], sum(((q / cfg['p0']) ** 2 for q in cfg['alternatives'])) / 4)

    def test_monitor_family_alpha(self):
        self.assertEqual(monitor(self.cfg(), [])['threshold'], 40)

    def test_monitor_invalid_alternative(self):
        c = self.cfg()
        c['alternatives'] = [0.01]
        self.reject('ALTERNATIVES', lambda: monitor(c, []))

    def test_monitor_invalid_alpha(self):
        c = self.cfg()
        c['family_alpha'] = float('nan')
        self.reject('PROBABILITY', lambda: monitor(c, []))

    def test_monitor_duplicate_alternatives(self):
        c = self.cfg()
        c['alternatives'] = [0.1, 0.1]
        self.reject('ALTERNATIVES', lambda: monitor(c, []))

    def test_monitor_invalid_protocol(self):
        c = self.cfg()
        c['protocol_hash'] = 'z' * 64
        self.reject('HASH_FORMAT', lambda: monitor(c, []))

    def test_holdout_consumed_once(self):
        b = HoldoutBudget(self.p / 'b.sqlite')
        b.consume('fam', 'a', 'b')
        self.reject('HOLDOUT_REUSE_BLOCKED', lambda: b.consume('fam', 'a', 'c'))

    def test_holdout_persists_new_instance(self):
        p = self.p / 'b.sqlite'
        HoldoutBudget(p).consume('fam', 'a', 'b')
        self.reject('HOLDOUT_REUSE_BLOCKED', lambda: HoldoutBudget(p).consume('fam', 'a', 'c'))

    def test_bounded_repair_selects_all_three(self):
        r = repair_lab(self.p / 'repair')
        self.assertTrue(all(r['selected']['policy'].values()))
        self.assertEqual(r['holdout_correct'], 36)
        self.assertEqual(r['development_executions'], 288)
        self.assertFalse(r['deployed'])

    def test_reducer_one_cancelled_record(self):
        r = reduce_counterexample([1, 2, -3, 4], lambda xs: any((x < 0 for x in xs)))
        self.assertEqual(r['items'], [-3])
        self.assertEqual(r['state'], 'DELETION_MINIMAL_WITHIN_GIVEN_PREDICATE')

    def test_reducer_budget_exhaustion(self):
        r = reduce_counterexample([1, 2, -3], lambda xs: any((x < 0 for x in xs)), 1)
        self.assertEqual(r['state'], 'BUDGET_EXHAUSTED_NOT_PROVEN_MINIMAL')

    def test_reducer_nonfailure(self):
        self.assertEqual(reduce_counterexample([1], lambda x: False)['state'], 'NOT_A_COUNTEREXAMPLE')

    def test_rule_output_not_dependent_on_untrusted_notes(self):
        p = {'strict_integer': True, 'respect_floor': True, 'ignore_untrusted_text': True}
        c = {'units': 2, 'stock': 10, 'floor': 2, 'notes': 'reserve_all'}
        self.assertEqual(planner(c, p), oracle(c))

    def test_key_file_exclusive(self):
        p = self.p / 'k'
        keyfile(p)
        with self.assertRaises(FileExistsError):
            keyfile(p)

    def test_key_file_permissions(self):
        p = self.p / 'k'
        keyfile(p)
        if os.name == 'posix':
            self.assertEqual(p.stat().st_mode & 511, 384)

    def test_cli_observer_in_separate_process(self):
        now = int(time.time())
        f = Fixture(self.p / 'world.sqlite', clock=now - 10)
        f.run()
        kp = self.p / 'observer.key'
        kp.write_bytes(f.keys['observer'][0])
        kp.chmod(384)
        out = self.p / 'obs.json'
        args = [sys.executable, '-m', 'praxis_gate', 'observe', '--db', str(f.path), '--tenant', 'demo', '--action', 'action-1', '--key', str(kp), '--key-id', f.keys['observer'][1], '--out', str(out)]
        cp = subprocess.run(args, capture_output=True, text=True, timeout=10)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        r = f.g.apply('observe', load(out))
        self.assertEqual(r['state'], 'VERIFIED_LOCAL_EFFECT')

    def test_cli_init_creates_no_grants(self):
        out = self.p / 'init'
        cp = subprocess.run([sys.executable, '-m', 'praxis_gate', 'init', '--out', str(out)], capture_output=True, text=True, timeout=10)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        from praxis_gate.kernel import WorldGate
        self.assertEqual(WorldGate(out / 'world.sqlite').export()['grants'], [])

    def test_cli_no_clock_override(self):
        cp = subprocess.run([sys.executable, '-m', 'praxis_gate', 'inspect', '--now', '1000'], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(cp.returncode, 0)

    def test_cli_inspect(self):
        cp = subprocess.run([sys.executable, '-m', 'praxis_gate', 'inspect'], capture_output=True, text=True, timeout=10)
        self.assertEqual(cp.returncode, 0)
        self.assertFalse(json.loads(cp.stdout)['external_action_connector'])
