# SPDX-License-Identifier: Apache-2.0
"""Fresh-world replay of successful signed commands, not new real-world observation."""
from pathlib import Path
import tempfile
from .common import Rejected, digest
from .kernel import WorldGate, verify_export

def replay_world(export, anchor=None, trusted_registry=None):
    checked = verify_export(export, anchor, trusted_registry)
    ev = export['events']
    if not ev or ev[0]['body']['stage'] != 'bootstrap':
        raise Rejected('BOOTSTRAP_REQUIRED')
    if ev[0]['body']['trust_hash'] != digest(export['trust']):
        raise Rejected('TRUST_ANCHOR_MISMATCH')
    done = denied = 0
    with tempfile.TemporaryDirectory(prefix='praxis-replay-') as td:
        g = WorldGate.create(Path(td) / 'world.sqlite', export['trust'], ev[0]['body']['resources'])
        for e in ev[1:]:
            b = e['body']
            if b['stage'] == 'denied':
                denied += 1
                continue
            r = g.apply(b['stage'], b['input'], b['at'])
            if digest(r) != b['result_hash']:
                raise Rejected('REPLAY_RESULT_MISMATCH', b['stage'])
            done += 1
        actual = g.export()
        for k in ('inventory', 'actions', 'grants', 'objects'):
            if export[k] != actual[k]:
                raise Rejected('REPLAY_FINAL_STATE_MISMATCH', k)
    return {**checked, 'state': 'RECORDED_COMMAND_REPLAY_MATCH', 'commands_reexecuted': done, 'hash_only_denials_not_reexecuted': denied, 'limits': ['Not a fresh agent run.', 'Denials retain hashes, so their original inputs are not replayed.', 'Retain the latest public trust root and signed anchor independently to detect wholesale rollback.']}

def semantic_graph(export):
    roles = {'bootstrap': 'D', 'contract': 'P', 'evidence': 'D', 'grant': 'W', 'prepare': 'P', 'commit': 'K', 'observe': 'D', 'compensate': 'P', 'revoke': 'I', 'denied': 'I'}
    rec = []
    routes = []
    grants = {}
    actions = {}
    evidence = {}
    for e in export['events']:
        b = e['body']
        stage = b['stage']
        id = 'event-' + str(e['seq'])
        role = roles[stage]
        rec.append({'id': id, 'role': role, 'event_hash': e['hash'], 'content': b})
        if stage in ('bootstrap', 'denied'):
            continue
        p = b['input']['review']['payload'] if stage == 'grant' else b['input']['payload']
        if stage == 'evidence':
            evidence[digest(p)] = id
        if stage == 'grant':
            grants[p['grant_id']] = id
            routes.append({'source': evidence[p['evidence_hash']], 'target': id, 'content': 'Evidence constrains this grant.'})
        if stage == 'prepare':
            actions[p['action_id']] = id
            routes.append({'source': grants[p['grant_id']], 'target': id, 'content': 'Value and permission constraints control the proposed action.'})
        if stage in ('commit', 'observe', 'compensate'):
            routes.append({'source': actions[p['action_id']], 'target': id, 'content': 'Explicit action, effect, observation or correction relation.'})
            actions[p['action_id']] = id
    return {'records': rec, 'routes': routes, 'allowed_route_types': [a + '->' + b for a in 'DIKWP' for b in 'DIKWP'], 'boundary': 'Engineering event mapping; only actual routes are claimed. Reverse replay establishes declared local state correspondence, not external truth.'}
