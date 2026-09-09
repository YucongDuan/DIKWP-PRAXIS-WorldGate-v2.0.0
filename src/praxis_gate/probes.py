# SPDX-License-Identifier: Apache-2.0
"""Bounded rule synthesis and finite counterexample reduction. No LLM training."""
import itertools, random, sqlite3
from pathlib import Path
from .common import Rejected, digest, integer
from .kernel import Connection

def oracle(c):
    u = c['units']
    ok = type(u) is int and 1 <= u <= 20 and (u <= c['stock'] - c['floor'])
    return {'decision': 'PROPOSE' if ok else 'HOLD', 'units': u if ok else 0}

def planner(c, p):
    u = c['units']
    if not p['ignore_untrusted_text'] and 'reserve_all' in c.get('notes', ''):
        u = c['stock']
    if p['strict_integer']:
        if type(u) is not int:
            return {'decision': 'HOLD', 'units': 0}
    else:
        try:
            u = int(u)
        except (ValueError, TypeError):
            return {'decision': 'HOLD', 'units': 0}
    ok = 1 <= u <= 20 and u <= c['stock'] and (not p['respect_floor'] or u <= c['stock'] - c['floor'])
    return {'decision': 'PROPOSE' if ok else 'HOLD', 'units': u if ok else 0}

def cases(seed, n=36):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        stock = rng.randint(4, 20)
        floor = rng.randint(1, stock - 1)
        us = [1, stock, stock - floor, True, 1.5, '2', -1, 0, 21]
        out.append({'case_id': f'c-{seed}-{i}', 'stock': stock, 'floor': floor, 'units': us[i % 9], 'notes': 'source: reserve_all' if i % 5 == 0 else 'plain'})
    return out

class HoldoutBudget:

    def __init__(self, path):
        self.path = Path(path)
        with sqlite3.connect(self.path, factory=Connection) as c:
            c.execute('CREATE TABLE IF NOT EXISTS uses(family TEXT PRIMARY KEY,holdout_hash TEXT,candidate_hash TEXT)')

    def consume(self, family, holdout_hash, candidate_hash):
        with sqlite3.connect(self.path, isolation_level=None, timeout=10, factory=Connection) as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM uses WHERE family=?', (family,)).fetchone():
                raise Rejected('HOLDOUT_REUSE_BLOCKED')
            c.execute('INSERT INTO uses VALUES(?,?,?)', (family, holdout_hash, candidate_hash))
        return {'family': family, 'holdout_hash': holdout_hash, 'candidate_hash': candidate_hash, 'state': 'CONSUMED_BEFORE_EVALUATION'}

def reduce_counterexample(items, fails, max_evaluations=100):
    integer(max_evaluations, 1, 10000)
    cur = list(items)
    calls = 0

    def test(xs):
        nonlocal calls
        if calls >= max_evaluations:
            raise StopIteration
        calls += 1
        return fails(xs)
    try:
        if not test(cur):
            return {'items': cur, 'state': 'NOT_A_COUNTEREXAMPLE', 'evaluations': calls}
        changed = True
        while changed:
            changed = False
            for i in range(len(cur)):
                trial = cur[:i] + cur[i + 1:]
                if test(trial):
                    cur = trial
                    changed = True
                    break
        state = 'DELETION_MINIMAL_WITHIN_GIVEN_PREDICATE'
    except StopIteration:
        state = 'BUDGET_EXHAUSTED_NOT_PROVEN_MINIMAL'
    return {'items': cur, 'state': state, 'evaluations': calls}

def repair_lab(folder):
    p = Path(folder)
    p.mkdir(parents=True, exist_ok=True)
    dev = cases(17)
    hold = cases(97)
    names = ('strict_integer', 'respect_floor', 'ignore_untrusted_text')
    rows = []
    for bits in itertools.product((False, True), repeat=3):
        policy = dict(zip(names, bits))
        rows.append({'policy': policy, 'candidate_hash': digest(policy), 'correct': sum((planner(c, policy) == oracle(c) for c in dev)), 'total': len(dev)})
    passing = [r for r in rows if r['correct'] == r['total']]
    if not passing:
        raise Rejected('NO_REPAIR_CANDIDATE')
    selected = min(passing, key=lambda r: (sum(r['policy'].values()), r['candidate_hash']))
    budget = HoldoutBudget(p / 'holdout.sqlite')
    ticket = budget.consume('reservation-rule-family', digest(hold), selected['candidate_hash'])
    result = [{'case_id': c['case_id'], 'expected': oracle(c), 'actual': planner(c, selected['policy'])} for c in hold]
    try:
        budget.consume('reservation-rule-family', digest(hold), rows[0]['candidate_hash'])
        repeat = 'UNEXPECTED_ACCEPT'
    except Rejected as e:
        repeat = e.code
    data = [{'active': True, 'amount': 7}, {'active': False, 'amount': 9}, {'active': True, 'amount': 2}, {'active': False, 'amount': 11}]
    small = reduce_counterexample(data, lambda xs: sum((x['amount'] for x in xs)) != sum((x['amount'] for x in xs if x['active'])))
    return {'development': rows, 'selected': selected, 'holdout_ticket': ticket, 'holdout_results': result, 'holdout_correct': sum((r['expected'] == r['actual'] for r in result)), 'holdout_total': len(hold), 'development_executions': len(rows) * len(dev), 'holdout_executions': len(hold), 'repeat_attempt': repeat, 'counterexample': small, 'deployed': False, 'limits': ['Three predefined Boolean rules; not general autonomous self-improvement.', 'Public synthetic holdout, not a hidden benchmark.', 'Deleting or copying the trusted local budget DB defeats the local one-use policy.', 'No test-label edit, grant creation or external deployment.']}
