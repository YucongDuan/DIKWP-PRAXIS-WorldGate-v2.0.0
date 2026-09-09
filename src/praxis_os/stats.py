"""Case-clustered paired comparisons, honest denominators and judge calibration."""
from __future__ import annotations
from collections import defaultdict
import math
import random
from statistics import mean
from .common import ValidationError, number, nonempty


def wilson(successes: int, n: int, z: float = 1.959963984540054):
    number(n, 'n', 0, integer=True)
    number(successes, 'successes', 0, n, integer=True)
    number(z, 'z', 0.001)
    if n == 0:
        return None
    p = successes / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n))/d
    h = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return [0.0 if successes==0 else max(0.0,c-h), 1.0 if successes==n else min(1.0,c+h)]


def quantile(values, q):
    vals = sorted(values)
    if not vals:
        return None
    at = (len(vals)-1)*q
    a = int(at)
    return vals[a] + (vals[min(a+1, len(vals)-1)]-vals[a])*(at-a)


def paired_cluster(rows, samples=2000, seed=23):
    """Rows: group_id, case_id, trial, arm ON/OFF, passed. Equal group weights.

    All repeated trials in a provenance group stay together. Percentile bootstrap
    is descriptive for the declared sample; it cannot repair selection bias.
    """
    number(samples, 'samples', 200, 20000, integer=True)
    number(seed, 'seed', 0, integer=True)
    pairs = {}
    for r in rows:
        key = (nonempty(r['group_id'],'group_id'),nonempty(r['case_id'],'case_id'),r['trial'])
        number(r['trial'], 'trial', 0, integer=True)
        if r['arm'] not in ('ON','OFF') or type(r['passed']) is not bool:
            raise ValidationError('Invalid comparison row')
        d = pairs.setdefault(key, {})
        if r['arm'] in d:
            raise ValidationError('Duplicate arm for matched case/trial')
        d[r['arm']] = int(r['passed'])
    incomplete = [k for k,v in pairs.items() if set(v) != {'ON','OFF'}]
    if incomplete:
        raise ValidationError(f'Missing matched arm: {incomplete[0]}')
    by_group = defaultdict(list)
    for k,v in pairs.items():
        by_group[k[0]].append(v)
    grouped = [{'group_id': k, 'off': mean(x['OFF'] for x in v),
                'on': mean(x['ON'] for x in v),
                'delta': mean(x['ON']-x['OFF'] for x in v),
                'pairs': len(v)} for k,v in sorted(by_group.items())]
    if not grouped:
        return {'status':'INSUFFICIENT_DATA','independent_groups':0,'paired_trials':0,'ci95':None}
    rng = random.Random(seed)
    ds = [g['delta'] for g in grouped]
    n = len(ds)
    ci = None
    if n >= 2:
        boot = [mean(ds[rng.randrange(n)] for _ in range(n)) for _ in range(samples)]
        ci = [quantile(boot,.025),quantile(boot,.975)]
    return {'status':'DESCRIPTIVE_PAIRED_COMPARISON','independent_groups': n,
            'paired_trials':len(pairs), 'off_rate':mean(g['off'] for g in grouped),
            'on_rate':mean(g['on'] for g in grouped),'delta':mean(ds),'ci95':ci,
            'groups':grouped,'bootstrap_samples':samples,'seed':seed,
            'estimand':'Equal-weight mean of provenance-group mean paired differences',
            'warnings': ['No population generalization without a representative independent group sample.',
                         'Repeated trials are not new independent tasks; no sequential-testing correction.'] +
                        (['Small group count; interval coverage may be poor.'] if n<20 else [])}


def judge_audit(data):
    rows = data.get('rows',[])
    if not rows:
        raise ValidationError('At least one calibration row is required')
    version = nonempty(data.get('judge_version'),'judge_version')
    by_item = {}
    counts = {'tp':0,'tn':0,'fp':0,'fn':0,'abstain':0}
    scores = []
    for r in rows:
        key = nonempty(r.get('item_id'),'item_id')
        if key in by_item:
            raise ValidationError('Duplicate calibration item; one observation per item required')
        by_item[key]=r
        if type(r.get('truth')) is not bool or (r.get('prediction') is not None and type(r['prediction']) is not bool):
            raise ValidationError('Truth must be boolean; prediction boolean or null')
        p = r.get('probability')
        if p is not None:
            number(p,'probability',0,1)
            scores.append((p-int(r['truth']))**2)
        pred = r.get('prediction')
        if pred is None:
            counts['abstain']+=1
        else:
            counts[{(True,True):'tp',(False,False):'tn',(False,True):'fp',(True,False):'fn'}[(r['truth'],pred)]]+=1
    covered=len(rows)-counts['abstain']
    positives=counts['tp']+counts['fn']
    negatives=counts['tn']+counts['fp']
    return {'judge_version':version,'n':len(rows),'covered':covered,'coverage':covered/len(rows),
            'confusion':counts,'agreement':(counts['tp']+counts['tn'])/covered if covered else None,
            'agreement_ci95':wilson(counts['tp']+counts['tn'],covered),
            'false_accept_rate': counts['fp']/negatives if negatives else None,
            'false_accept_ci95':wilson(counts['fp'],negatives),
            'false_reject_rate':counts['fn']/positives if positives else None,
            'false_reject_ci95':wilson(counts['fn'],positives),
            'brier':mean(scores) if scores else None,'probability_count':len(scores),
            'boundary':'Conditional on covered, supplied gold labels and representative independent items. Human labels are not automatically truth.'}


def judge_panel(votes):
    """No majority gate; reveal correlation-family and contradiction metadata."""
    if not votes:
        return {'status':'UNKNOWN','families':0,'votes':0}
    seen=set()
    for v in votes:
        name=nonempty(v.get('judge_id'),'judge_id')
        if name in seen:
            raise ValidationError('Duplicate judge id')
        seen.add(name)
        nonempty(v.get('family'),'family')
        if v.get('verdict') not in ('PASS','FAIL','ABSTAIN'):
            raise ValidationError('Invalid judge verdict')
    verdicts={v['verdict'] for v in votes if v['verdict']!='ABSTAIN'}
    families={v['family'] for v in votes}
    status='DISAGREEMENT_REQUIRES_REVIEW' if len(verdicts)>1 else 'ADVISORY_CONSENSUS' if verdicts else 'UNKNOWN'
    return {'status':status,'families':len(families),'votes':len(votes),
            'independence_established':False,'release_authority':False,
            'warning':'Different family names do not prove independent errors.'}


def sampling_audit(rows):
    """Show the effect of nonuniform sampling; do not invent design-based CIs.

    Hajek ratio requires correctly declared nonzero inclusion probabilities. It
    does not resolve cluster sampling, missing strata or an unobserved population.
    """
    if not rows:raise ValidationError('Sampling rows required')
    seen=set();known=True
    for r in rows:
        if r.get('id') in seen:raise ValidationError('Duplicate sampled item')
        seen.add(nonempty(r.get('id'),'sample.id'))
        if type(r.get('passed')) is not bool:raise ValidationError('Boolean sampled result required')
        if r.get('inclusion_probability') is None:known=False
        else:number(r['inclusion_probability'],'inclusion_probability',1e-9,1)
    out={'n':len(rows),'unweighted_rate':mean(int(r['passed']) for r in rows),
         'weighted_rate':None,'weight_effective_sample_size':None,'population_ci':None,
         'scope':'Sampling-design metadata must be externally correct; ESS is not an independent case count.'}
    if known:
        weights=[1/r['inclusion_probability'] for r in rows];sw=sum(weights)
        out.update(weighted_rate=sum(w*int(r['passed']) for w,r in zip(weights,rows))/sw,
                   weight_effective_sample_size=sw*sw/sum(w*w for w in weights),
                   state='HAJEK_RATIO_UNDER_DECLARED_INCLUSION_PROBABILITIES')
    else:out['state']='DESCRIPTIVE_ONLY_UNKNOWN_SAMPLING_PROBABILITIES'
    return out
