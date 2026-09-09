"""Frozen manifests, paired local execution, three-granularity audit and replay."""
from __future__ import annotations
import copy
import random
import pkgutil
import platform
from functools import lru_cache
from pathlib import Path
from . import __version__
from .adapters import BUILTINS,builtin_execute,trusted_process
from .common import ValidationError, digest, load, save, new_output, write_jsonl, read_jsonl, chained, verify_chain, file_manifest, verify_manifest
from .contracts import validate_project,dataset_audit,sanitize_spans
from .evaluators import evaluate_run,skill_gate
from .stats import paired_cluster,wilson


@lru_cache(maxsize=1)
def implementation_hash():
    import importlib.resources as resources
    entries={}
    for item in resources.files('praxis_os').iterdir():
        if item.name.endswith('.py'):
            entries[item.name]=__import__('hashlib').sha256(item.read_bytes()).hexdigest()
    return digest(entries)


def gate_record(summary,carrier):
    record=copy.deepcopy(summary['carriers'][carrier]['gate'])
    record.update({'candidate_hash':digest({'implementation_hash':summary['implementation_hash'],
                   'carrier':carrier,'contract_hash':summary['contract_hash'],
                   'worker_identity':summary.get('worker_identity')}),
                   'assessment_hash':digest(summary),'project_hash':summary['project_hash'],
                   'observations_hash':summary['observations_hash'],'carrier':carrier,
                   'evidence_origin':summary['evidence_origin']})
    return record


def analysis(project,runs):
    validate_project(project)
    tests={c['case_id']:c for c in project['cases'] if c['split']=='test'}
    ex=project['experiment']
    expected={(c,k,a,t) for c in tests for k in project['carriers'] for a in ('OFF','ON') for t in range(ex['trials'])}
    actual=set()
    assessments=[]
    for r in runs:
        key=(r.get('case_id'),r.get('carrier'),r.get('arm'),r.get('trial'))
        if key not in expected or key in actual:
            raise ValidationError('Unexpected or duplicate run in experiment matrix')
        actual.add(key)
        assessments.append(evaluate_run(r,tests[r['case_id']],project['contract']))
    if expected!=actual:
        raise ValidationError(f'Incomplete matrix: missing {len(expected-actual)} runs; do not drop failures')
    ds=dataset_audit(project['cases'])
    carriers={}
    for name in project['carriers']:
        aa=[a for a in assessments if a['carrier']==name]
        rows=[{'group_id':a['group_id'],'case_id':a['case_id'],'trial':a['trial'],'arm':a['arm'],
               'passed':a['coordinates']['quality']['state']=='PASS'} for a in aa]
        s=paired_cluster(rows,ex.get('bootstrap_samples',1000),ex['seed'])
        gate=skill_gate(s,aa,ds,ex)
        group_ids={a['group_id'] for a in aa if a['arm']=='ON'}
        bad_groups={a['group_id'] for a in aa if a['arm']=='ON' and a['hard_failures']}
        carriers[name]={'paired_quality':s,'gate':gate,
            'hard_violation_group_ci95':wilson(len(bad_groups),len(group_ids)),
            'risk_interval_scope':'At least one recorded hard violation per declared group; independence and representativeness assumed, not verified.',
            'run_verdicts':{v:sum(a['verdict']==v for a in aa) for v in ('PASS_WITHIN_SCOPE','BLOCK','REVISE','INSUFFICIENT_EVIDENCE')},
            'hard_violations_on':sum(bool(a['hard_failures']) for a in aa if a['arm']=='ON')}
    return {'schema_version':'1.0','system':'DIKWP-PRAXIS-OS','version':__version__,
            'contract_hash':digest(project['contract']),'project_hash':digest(project),
            'implementation_hash':implementation_hash(),'python_version':platform.python_version(),
            'worker_identity':project.get('worker_identity'),
            'observations_hash':digest(runs),'dataset':ds,'carriers':carriers,'assessments':assessments,
            'release_authority':False,'evidence_origin':project.get('evidence_origin','UNSPECIFIED'),
            'limits':['No named frontier model has been benchmarked by the built-in demo.',
                      'Hardware energy is unknown unless explicit, scoped measurement is supplied.',
                      'Replay recomputes judgments on recorded observations; it does not rerun a remote world.',
                      'Synthetic/constructed cases establish executable mechanisms, not universal superiority.']}


def semantic_graph(summary):
    """A small real record graph; 25 kinds permitted, only actual edges listed."""
    records=[{'id':'D.input','role':'D','content':{'project_hash':summary['project_hash'],'observations_hash':summary['observations_hash']}},
             {'id':'W.contract','role':'W','content':{'contract_hash':summary['contract_hash'],'policy':'Hard violations cannot be offset by quality gains'}},
             {'id':'P.audit','role':'P','content':{'operation':'analysis','inputs':['D.input','W.contract'],'output':'K.bounded'}},
             {'id':'K.bounded','role':'K','content':{'gates':{k:v['gate'] for k,v in summary['carriers'].items()}}},
             {'id':'I.open','role':'I','content':summary['limits']},
             {'id':'P.replay','role':'P','content':{'operation':'replay','inputs':['D.input','W.contract'],'output':'D.replay-check'}}]
    edges=[{'source':'D.input','target':'P.audit','content':'Recorded inputs'},
           {'source':'W.contract','target':'P.audit','content':'Restricts acceptance independent of quality'},
           {'source':'P.audit','target':'K.bounded','content':'Computed release eligibility only'},
           {'source':'K.bounded','target':'I.open','content':'Scope and remaining evidence'},
           {'source':'K.bounded','target':'P.replay','content':'Requires recomputation; replay receipt added separately'}]
    return {'records':records,'edges':edges,'permitted_route_types':[a+'->'+b for a in 'DIKWP' for b in 'DIKWP'],
            'boundary':'No D replay-sameness claim before replay has actually succeeded.'}


def report_md(s):
    out=['# DIKWP-PRAXIS-OS | Recorded evaluation','',f"Evidence origin: **{s['evidence_origin']}**",'',
         '| Carrier | OFF | ON | Delta | Case-cluster interval | Gate |','|---|---:|---:|---:|---|---|']
    for k,v in s['carriers'].items():
        x=v['paired_quality']
        out.append(f"| {k} | {x.get('off_rate',0):.3f} | {x.get('on_rate',0):.3f} | {x.get('delta',0):+.3f} | {x.get('ci95')} | {v['gate']['state']} |")
    out+=['','## Interpretation','Quality is a declared-check result, not a release permission. The unsafe demo intentionally preserves correct answers while recording unauthorized side effects.','',
          '## Boundaries']+['- '+x for x in s['limits']]
    return '\n'.join(out)+'\n'


def bundle(project,runs,out):
    runs=copy.deepcopy(runs)
    for r in runs:
        r['spans'],removed=sanitize_spans(r.get('spans',[]))
        r['removed_trace_attributes']=sorted(set(r.get('removed_trace_attributes',[])+removed))
        for k in list(r):
            if k not in {'run_id','case_id','carrier','arm','trial','spans','execution_status','output','outcome','metrics','execution_kind','privacy_violation','removed_trace_attributes'}:
                del r[k]
    summary=analysis(project,runs)
    p=new_output(out)
    save(p/'project.json',project)
    write_jsonl(p/'runs.jsonl',runs)
    save(p/'assessment.json',summary)
    save(p/'semantic_graph.json',semantic_graph(summary))
    events=chained([{'kind':'CONTRACT_FROZEN','hash':summary['contract_hash']},
                    {'kind':'DATASET_AUDITED','result':summary['dataset']},
                    {'kind':'OBSERVATIONS_RECORDED','hash':summary['observations_hash'],'count':len(runs)},
                    {'kind':'ASSESSMENT_COMPUTED','hash':digest(summary)},
                    {'kind':'HANDOFF','authority':False,'next':'Independent scoped review and outcome observation'}])
    write_jsonl(p/'ledger.jsonl',events)
    save(p/'anchor.json',{'tail':events[-1]['hash'],'count':len(events)})
    (p/'report.md').write_text(report_md(summary),encoding='utf-8')
    save(p/'manifest.json',file_manifest(p))
    return summary


def execute(project,out,worker=None,trust=False):
    validate_project(project)
    if Path(out).exists():
        raise ValidationError('Output exists; refusing execution before any work starts')
    if dataset_audit(project['cases'])['state']!='PASS':
        raise ValidationError('Cross-split contamination blocks execution')
    if worker is not None and not trust:
        raise ValidationError('Explicit --trust-worker required before running any worker')
    project=copy.deepcopy(project)
    if worker is not None:
        worker_view={k:v for k,v in worker.items() if k!='env'}
        worker_view['explicit_env_keys']=sorted(worker.get('env',{}))
        files={}
        for arg in worker.get('argv',[]):
            candidate=Path(arg)
            if candidate.is_absolute() and candidate.is_file() and candidate.stat().st_size<50_000_000:
                files[str(candidate)]=__import__('hashlib').sha256(candidate.read_bytes()).hexdigest()
        project['worker_identity']={'configuration_hash':digest(worker_view),'argv_file_hashes':files,
                                    'limitations':'Transitive imports, remote models and secret values are not fingerprinted.'}
    ex=project['experiment']; runs=[]
    cases=[c for c in project['cases'] if c['split']=='test']
    # Freeze full matrix before executing; randomized ON/OFF order per pair.
    rng=random.Random(ex['seed'])
    for name in project['carriers']:
        if name not in BUILTINS and worker is None:
            raise ValidationError(f'Carrier {name} needs an explicitly trusted worker config')
        for c in cases:
            for t in range(ex['trials']):
                order=['OFF','ON'];rng.shuffle(order)
                for arm in order:
                    public={k:copy.deepcopy(v) for k,v in c.items() if k not in ('expected','expected_outcome','split')}
                    try:
                        if name in BUILTINS:
                            raw=builtin_execute(name,public,arm,t,ex['seed'],project['contract'])
                        else:
                            req={'case':public,'arm':arm,'trial':t,'seed':ex['seed'],
                                 'task':{'objective':project['contract']['objective'],'authority':project['contract']['authority']}}
                            raw=trusted_process(worker,req,trust)
                    except (ValueError,TypeError,KeyError,OSError) as exc:
                        raw={'execution_status':'ADAPTER_ERROR','output':{},
                             'spans':[{'id':'root','parent':None,'kind':'root','step':0,'attrs':{'error_type':type(exc).__name__}}],
                             'outcome':None,'metrics':{'duration_ms':None,'cost_microunits':None,'energy_j':None},
                             'execution_kind':'FAILED_RECORDED_ATTEMPT'}
                    raw=copy.deepcopy(raw)
                    raw['run_id']=f'{name}:{c["case_id"]}:{t}:{arm}'
                    raw.update({'case_id':c['case_id'],'carrier':name,'arm':arm,'trial':t})
                    raw['spans'],removed=sanitize_spans(raw.get('spans',[]))
                    raw['removed_trace_attributes']=removed
                    runs.append(raw)
    # Measured timing stays in recorded observations; recomputation uses that record.
    return bundle(project,runs,out)


def replay(folder):
    p=Path(folder)
    if not verify_manifest(p):
        raise ValidationError('Bundle manifest mismatch')
    rows=read_jsonl(p/'ledger.jsonl'); anchor=load(p/'anchor.json')
    if not verify_chain(rows,anchor['tail'],anchor['count']):
        raise ValidationError('Ledger mismatch')
    project=load(p/'project.json');runs=read_jsonl(p/'runs.jsonl')
    regenerated=analysis(project,runs)
    saved=load(p/'assessment.json')
    same=digest(regenerated)==digest(saved)
    if not same:
        raise ValidationError('Recomputed assessment differs')
    return {'state':'RECOMPUTED_MATCH','assessment_hash':digest(saved),'count':len(runs),
            'scope':'Frozen inputs and recorded outputs; not a fresh independent empirical replication.',
            'semantic_receipt':{'role':'D','same':'Bounded assessment JSON','forward':'P.audit','reverse':'P.replay'}}
