# SPDX-License-Identifier: Apache-2.0
"""A predeclared finite-mixture Bernoulli test supermartingale, not a safety score."""
import math
from .common import Rejected, fields, integer, ident, hexhash, prob, digest

def monitor(cfg, rows):
    fields(cfg, ('monitor_id', 'p0', 'alternatives', 'family_alpha', 'family_size', 'protocol_hash'))
    ident(cfg['monitor_id'])
    hexhash(cfg['protocol_hash'])
    p0 = prob(cfg['p0'], True)
    alpha = prob(cfg['family_alpha'], True)
    integer(cfg['family_size'], 1, 10000)
    if not isinstance(cfg['alternatives'], list) or not cfg['alternatives']:
        raise Rejected('ALTERNATIVES')
    qs = [prob(q, True) for q in cfg['alternatives']]
    if len(qs) != len(set(qs)) or any((q <= p0 for q in qs)):
        raise Rejected('ALTERNATIVES')
    per = alpha / cfg['family_size']
    threshold = math.log(1 / per)
    logs = [0.0] * len(qs)
    seen = set()
    pending = False
    series = []
    alarm = None
    for i, r in enumerate(rows, 1):
        fields(r, ('sequence', 'group_id', 'failed'))
        integer(r['sequence'], 1)
        ident(r['group_id'])
        if r['sequence'] != i or r['group_id'] in seen:
            raise Rejected('ORDER_OR_GROUP_DUPLICATE')
        seen.add(r['group_id'])
        if r['failed'] is not None and type(r['failed']) is not bool:
            raise Rejected('BINARY_OR_MISSING_REQUIRED')
        if r['failed'] is None:
            pending = True
        if pending:
            continue
        x = int(r['failed'])
        logs = [l + x * math.log(q / p0) + (1 - x) * math.log((1 - q) / (1 - p0)) for l, q in zip(logs, qs)]
        m = max(logs)
        log_e = m + math.log(sum((math.exp(l - m) for l in logs))) - math.log(len(logs))
        hit = log_e >= threshold
        if hit and alarm is None:
            alarm = i
        series.append({'sequence': i, 'group_id': r['group_id'], 'failed': r['failed'], 'log_e': log_e, 'e_value_capped': math.exp(min(700, log_e)), 'crossed': hit})
    return {'config': cfg, 'config_hash': digest(cfg), 'threshold': 1 / per, 'processed_ordered_groups': len(series), 'submitted_groups': len(rows), 'first_alarm_at': alarm, 'series': series, 'state': 'RISK_BOUND_REJECTED' if alarm else 'AWAITING_ORDERED_OUTCOME' if pending else 'NO_REJECTION_NOT_A_SAFETY_CERTIFICATE', 'assumptions': ['Configuration and alternative mixture fixed before data.', 'Under H0, P(failure in group g | past) <= p0.', 'Declared family size covers all streams; no post-hoc exclusions.', 'Group labels do not establish representativeness.'], 'limits': ['Pending outcomes block the ordered prefix rather than disappear.', 'No rejection is not proof of safety.', 'Critical incidents can suspend actions without waiting for significance.', 'No automatic connection from this calculator to production permissions.']}
