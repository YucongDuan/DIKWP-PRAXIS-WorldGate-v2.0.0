"""Versioned contracts, deterministic split-leakage checks and privacy-minimal traces."""
from __future__ import annotations
from collections import defaultdict
import re
from .common import ValidationError, canonical, digest, nonempty, number

CHECK_KINDS={'equals_expected','required_keys','citations_present'}
ARMS={'ON','OFF'}
SPAN_KINDS={'root','agent','model','tool','retrieval','memory','embedding','guardrail','outcome'}


def validate_project(project):
    canonical(project)
    if project.get('schema_version')!='1.0':
        raise ValidationError('Unsupported project schema version')
    c=project.get('contract',{})
    for f in ('id','owner','objective','version'):
        nonempty(c.get(f),f'contract.{f}')
    a=c.get('authority',{})
    nonempty(a.get('principal'),'authority.principal')
    for key in ('allowed_tools','allowed_resources'):
        if not isinstance(a.get(key),list) or any(not isinstance(x,str) for x in a[key]):
            raise ValidationError(f'authority.{key}: list of strings required')
    number(a.get('max_tool_calls'),'max_tool_calls',0,10000,integer=True)
    number(a.get('expires_step'),'expires_step',0,10**9,integer=True)
    checks=c.get('checks')
    if not isinstance(checks,list) or not checks:
        raise ValidationError('At least one declarative output check required')
    ids=set()
    for check in checks:
        cid=nonempty(check.get('id'),'check.id')
        if cid in ids:
            raise ValidationError('Duplicate check id')
        ids.add(cid)
        if check.get('kind') not in CHECK_KINDS:
            raise ValidationError('Unrecognized check kind; executable code is not accepted')
        nonempty(check.get('field'),'check.field')
    lim=c.get('limits',{})
    for k in ('duration_ms','cost_microunits','energy_j'):
        if lim.get(k) is not None:
            number(lim[k],f'limits.{k}',0)
    ex=project.get('experiment',{})
    number(ex.get('trials'),'trials',1,30,integer=True)
    number(ex.get('seed'),'seed',0,10**9,integer=True)
    number(ex.get('bootstrap_samples',1000),'bootstrap_samples',200,20000,integer=True)
    number(ex.get('min_groups',12),'min_groups',2,10000,integer=True)
    number(ex.get('min_delta',0),'min_delta',-1,1)
    cases=project.get('cases',[])
    if not isinstance(cases,list) or not cases or len(cases)>5000:
        raise ValidationError('1..5000 cases required')
    ids=set()
    for case in cases:
        cid=nonempty(case.get('case_id'),'case_id')
        nonempty(case.get('group_id'),'group_id')
        if cid in ids:
            raise ValidationError('Duplicate case id')
        ids.add(cid)
        if case.get('split') not in ('train','calibration','test'):
            raise ValidationError('Invalid dataset split')
        if not isinstance(case.get('input'),dict) or not isinstance(case.get('expected'),dict):
            raise ValidationError('Case input/expected objects required')
    if not any(x['split']=='test' for x in cases):
        raise ValidationError('Test split cannot be empty')
    if not project.get('carriers') or len(set(project['carriers'])) != len(project['carriers']):
        raise ValidationError('Unique carriers required')
    return project


def dataset_audit(cases):
    inputs=defaultdict(set)
    groups=defaultdict(set)
    for c in cases:
        inputs[digest(c['input'])].add(c['split'])
        groups[c['group_id']].add(c['split'])
    exact=[h for h,s in inputs.items() if len(s)>1]
    related=[g for g,s in groups.items() if len(s)>1]
    return {'state':'BLOCK' if exact or related else 'PASS',
            'exact_cross_split_hashes':sorted(exact),'cross_split_groups':sorted(related),
            'counts':{s:sum(c['split']==s for c in cases) for s in ('train','calibration','test')},
            'manifest_hash':digest(cases),
            'limitations':['Exact hashing and declared provenance groups only; no semantic near-duplicate detection.',
                           'No proof that model pretraining excluded these examples.',
                           'Holdout reuse and undocumented label leakage require human process controls.']}

# Defense in depth, not a general PII detector. Trace content collection is allowlisted.
SAFE_ATTRS={'operation','resource','principal','performed','authorized','denied','namespace',
            'source_refs','token_input','token_output','provider','model_version','policy_version',
            'count','reason_code','error_type','retrieval_ids','evidence_ref','source_kind'}
FORBIDDEN_KEY=re.compile(r'(chain.?of.?thought|private.?thought|reasoning_content|authorization|password|api.?key|secret|token$)',re.I)
EMAIL=re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
BEARER=re.compile(r'(?i)bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}')


def redact_text(s):
    return BEARER.sub('[REDACTED_SECRET]',EMAIL.sub('[REDACTED_EMAIL]',str(s)))


def sanitize_spans(spans):
    """Drop all non-allowlisted trace attributes; never store hidden chain-of-thought."""
    result=[]
    removed=[]
    for span in spans:
        attrs={}
        for k,v in span.get('attrs',{}).items():
            if k not in SAFE_ATTRS or FORBIDDEN_KEY.search(k):
                removed.append(k)
                continue
            if isinstance(v,str):
                attrs[k]=redact_text(v)
            elif isinstance(v,list):
                attrs[k]=[redact_text(x) for x in v if isinstance(x,str)]
            elif v is None or type(v) in (bool,int,float):
                attrs[k]=v
        result.append({'id':span.get('id'),'parent':span.get('parent'),'kind':span.get('kind'),
                       'step':span.get('step',0),'attrs':attrs})
    return result, sorted(set(removed))


def validate_spans(spans):
    if not isinstance(spans,list) or not spans or len(spans)>10000:
        raise ValidationError('1..10000 spans required')
    by_id={}
    for s in spans:
        sid=nonempty(s.get('id'),'span.id')
        if sid in by_id:
            raise ValidationError('Duplicate span id')
        if s.get('kind') not in SPAN_KINDS:
            raise ValidationError('Unknown span kind')
        number(s.get('step',0),'span.step',0,integer=True)
        if not isinstance(s.get('attrs',{}),dict):
            raise ValidationError('Span attributes must be an object')
        if 'performed' in s.get('attrs',{}) and type(s['attrs']['performed']) is not bool:
            raise ValidationError('performed must be boolean')
        by_id[sid]=s
    roots=[s for s in spans if s.get('parent') is None]
    if len(roots)!=1 or roots[0]['kind']!='root':
        raise ValidationError('Exactly one root span required')
    for s in spans:
        p=s.get('parent')
        if p is not None and p not in by_id:
            raise ValidationError('Missing parent span')
    # Iterative cycle detection avoids recursion limits on hostile input.
    finished=set()
    for sid in by_id:
        active=set()
        cur=sid
        while cur is not None and cur not in finished:
            if cur in active:
                raise ValidationError('Trace contains a cycle')
            active.add(cur)
            cur=by_id[cur].get('parent')
        finished.update(active)
    return True
