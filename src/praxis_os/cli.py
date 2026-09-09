from __future__ import annotations
import argparse
import copy
import os
import sys
import sqlite3
from pathlib import Path
from . import __version__
from .common import ValidationError,load,save,new_output,digest,canonical,file_manifest,write_jsonl,read_jsonl
from .fixtures import demo_project,adversarial_diagnostics,judge_fixture,otlp_fixture
from .harness import execute,replay,bundle,gate_record
from .stats import judge_audit,judge_panel,sampling_audit
from .lineage import reopen
from .causal import finite_interventions
from .telemetry import import_otlp
from .feedback import proposals
from .lifecycle import Registry,approval,sign


def registry_demo(path,certificate):
    path=Path(path);path.mkdir(parents=True)
    key=b'ONLY-SYNTHETIC-DEMO-NOT-A-PRODUCTION-KEY'
    roles={'author':'author','reviewer':'reviewer','operator':'operator','observer':'observer'}
    reg=Registry(path/'registry.sqlite',key,roles)
    artifact=certificate['candidate_hash']
    reg.create('demo-release',artifact,'author',certificate)
    state=reg.get('demo-release')['state']
    if state=='EVALUATED':
        steps=[('SHADOW','reviewer',{'independent_review':True,'rollback_plan':'Restore predecessor manifest; confirm outcome.'}),
               ('CANARY','operator',{'phase':'SHADOW','artifact_hash':artifact,'observer':'observer','source_kind':'synthetic',
                                     'n':12,'harm_events':0,'accepted':True,'expires':2000}),
               ('ACTIVE','operator',{'phase':'CANARY','artifact_hash':artifact,'observer':'observer','source_kind':'synthetic',
                                     'n':12,'harm_events':0,'accepted':True,'expires':2000})]
        for i,(to,who,e) in enumerate(steps):
            tok=approval(key,'demo-release',artifact,state,to,who,e,2000,'demo-'+str(i))
            reg.transition('demo-release',to,e,tok,now=1000);state=to
        outcome={'status':'HARM','source_kind':'synthetic','evidence_ref':'post-release-fixture-1',
                 'description':'A new observed adverse fixture reopens acceptance and rolls back LOCAL registry state.'}
        tok=sign(key,{'release_id':'demo-release','artifact_hash':artifact,'principal':'observer','expires':2000,
                      'nonce':'demo-observe','outcome_hash':digest(outcome)})
        reg.observe('demo-release',outcome,tok,now=1000)
    out=reg.export();out['verified']=reg.verify()
    out['time_basis']='Synthetic clock epoch=1000. No claim of real approvals, field samples or external deployment.'
    reg.close();save(path/'workflow.json',out)
    return out


def demo(out):
    root=new_output(out)
    p=demo_project()
    s=execute(p,root/'experiment')
    rep=replay(root/'experiment')
    adv=adversarial_diagnostics();j=judge_audit(judge_fixture())
    panel=judge_panel([{'judge_id':'a','family':'shared','verdict':'PASS'},
                       {'judge_id':'b','family':'shared','verdict':'PASS'},
                       {'judge_id':'c','family':'other','verdict':'FAIL'}])
    save(root/'replay.json',rep)
    save(root/'diagnostics.json',adv)
    save(root/'judge_calibration.json',j)
    save(root/'judge_panel.json',panel)
    save(root/'feedback_proposals.json',proposals(s))
    causal=finite_interventions();save(root/'causal_interventions.json',causal)
    sampling=sampling_audit([{'id':str(i),'passed':i>=8,'inclusion_probability':1.0 if i<8 else .1} for i in range(10)])
    save(root/'sampling_audit.json',sampling)
    lg={'nodes':[{'id':'source-a','kind':'source','depends_on':[]},{'id':'source-b','kind':'source','depends_on':[]},
                 {'id':'claim-a','kind':'claim','depends_on':['source-a']},{'id':'report-a','kind':'report','depends_on':['claim-a']},
                 {'id':'release-a','kind':'release','depends_on':['report-a']},{'id':'report-b','kind':'report','depends_on':['source-b']}]}
    correction=reopen(lg,{'target':'source-a','actor':'local-reviewer','reason':'Original source corrected','status':'SUPERSEDED'})
    save(root/'correction_propagation.json',correction)
    save(root/'otlp_import.json',import_otlp(otlp_fixture()))
    wf=registry_demo(root/'workflow',gate_record(s,'direct'))
    dashboard={'system':'DIKWP-PRAXIS-OS','version':__version__,'origin':s['evidence_origin'],
               'carriers':s['carriers'],'diagnostics':adv['scenarios'],'judge':j,'panel':panel,
               'workflow':wf,'replay':rep,'causal':causal,'sampling':sampling,'correction':correction,'sample_runs':s['assessments'][:12],
               'limitations':s['limits']}
    save(root/'dashboard.json',dashboard)
    save(root/'manifest.json',file_manifest(root))
    return {'output':str(root),'runs':rep['count'],'replay':rep['state'],'workflow_verified':wf['verified']}


def init_project(out):
    p=new_output(out)
    project=demo_project();save(p/'project.json',project)
    save(p/'contract.json',project['contract']);write_jsonl(p/'cases.jsonl',project['cases'])
    save(p/'eval.json',{'experiment':project['experiment'],'carriers':project['carriers']})
    (p/'skill.md').write_text('# Active-order summary\n\nCount only active orders. Keep source records unchanged.\n\nThis is a human-reviewable description; project.json is the executable source of truth.\nNo arbitrary checks.py is executed.\n',encoding='utf-8')
    (p/'README.md').write_text('Edit project.json, then run: python praxis.pyz run project.json --out run-001\nThe other files are starter views; changes to them do not silently modify project.json.\n',encoding='utf-8')
    return {'output':str(p),'next':'Edit project.json and run; generated examples are synthetic, not untouched holdout data.'}


def main(argv=None):
    ap=argparse.ArgumentParser(prog='praxis',description='DIKWP-PRAXIS-OS: evidence-to-outcome agent assurance')
    ap.add_argument('--version',action='version',version=__version__)
    sp=ap.add_subparsers(dest='cmd',required=True)
    sp.add_parser('inspect')
    for cmd in ('demo','init'):
        a=sp.add_parser(cmd);a.add_argument('--out',required=True)
    a=sp.add_parser('run');a.add_argument('project');a.add_argument('--out',required=True);a.add_argument('--worker');a.add_argument('--trust-worker',action='store_true')
    a=sp.add_parser('audit');a.add_argument('project');a.add_argument('runs');a.add_argument('--out',required=True)
    a=sp.add_parser('replay');a.add_argument('directory')
    for cmd in ('judge','panel','import-otel','sampling'):
        a=sp.add_parser(cmd);a.add_argument('input');a.add_argument('--out',required=True)
    a=sp.add_parser('correct');a.add_argument('graph');a.add_argument('correction');a.add_argument('--out',required=True)
    a=sp.add_parser('registry');a.add_argument('action',choices=['init','create','sign','transition','observe','show','verify'])
    a.add_argument('--db');a.add_argument('--key',required=True);a.add_argument('--roles');a.add_argument('--release');a.add_argument('--artifact');a.add_argument('--author')
    a.add_argument('--bundle');a.add_argument('--carrier');a.add_argument('--certificate');a.add_argument('--payload');a.add_argument('--evidence');a.add_argument('--token');a.add_argument('--to');a.add_argument('--out')
    args=ap.parse_args(argv)
    try:
        if args.cmd=='inspect':
            result={'system':'DIKWP-PRAXIS-OS','version':__version__,'runtime_dependencies':[],
                    'external_action_authority':False,'aggregate_score':None,
                    'builtins':['direct','relational','unsafe'],'private_chain_of_thought_collection':False,
                    'warning':'Opt-in subprocesses are trusted code, not security sandboxes. Local data is not encrypted.'}
        elif args.cmd=='demo':result=demo(args.out)
        elif args.cmd=='init':result=init_project(args.out)
        elif args.cmd=='run':
            s=execute(load(args.project),args.out,load(args.worker) if args.worker else None,args.trust_worker)
            result={'output':args.out,'gates':{k:v['gate'] for k,v in s['carriers'].items()}}
        elif args.cmd=='audit':
            s=bundle(load(args.project),read_jsonl(args.runs),args.out)
            result={'output':args.out,'project_hash':s['project_hash']}
        elif args.cmd=='replay':result=replay(args.directory)
        elif args.cmd=='correct':
            result=reopen(load(args.graph),load(args.correction))
            if Path(args.out).exists():raise ValidationError('Output exists')
            save(args.out,result)
        elif args.cmd in ('judge','panel','import-otel','sampling'):
            data=load(args.input)
            result={'judge':judge_audit,'panel':judge_panel,'import-otel':import_otlp,'sampling':sampling_audit}[args.cmd](data)
            if Path(args.out).exists():raise ValidationError('Output exists')
            save(args.out,result)
        else:
            if args.action=='init':
                if not args.db or not args.roles:raise ValidationError('--db and --roles required')
                kp=Path(args.key)
                if kp.exists() or Path(args.db).exists():raise ValidationError('Do not overwrite registry/key')
                key=os.urandom(32)
                kp.parent.mkdir(parents=True,exist_ok=True)
                fd=os.open(str(kp),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,'wb') as f:f.write(key)
                reg=Registry(args.db,key,load(args.roles));result={'state':'LOCAL_REGISTRY_CREATED'};reg.close()
            elif args.action=='sign':
                if not args.payload or not args.out:raise ValidationError('--payload and --out required')
                if Path(args.out).exists():raise ValidationError('Output exists')
                result=sign(Path(args.key).read_bytes(),load(args.payload));save(args.out,result)
            else:
                if not args.db:raise ValidationError('--db required')
                reg=Registry(args.db,Path(args.key).read_bytes())
                try:
                    if args.action=='create':
                        if not args.bundle or not args.carrier:raise ValidationError('--bundle and --carrier required; input must be replayed')
                        replay(args.bundle)
                        cert=gate_record(load(Path(args.bundle)/'assessment.json'),args.carrier)
                        result={'state':reg.create(args.release,cert['candidate_hash'],args.author,cert),'candidate_hash':cert['candidate_hash']}
                    elif args.action=='transition':result=reg.transition(args.release,args.to,load(args.evidence),load(args.token))
                    elif args.action=='observe':result=reg.observe(args.release,load(args.evidence),load(args.token))
                    elif args.action=='show':result=reg.export()
                    else:result={'verified':reg.verify()}
                finally:reg.close()
                if args.out:
                    if Path(args.out).exists():raise ValidationError('Output exists')
                    save(args.out,result)
        print(canonical(result).decode())
        return 0
    except (ValidationError,OSError,KeyError,TypeError,ValueError,sqlite3.Error) as e:
        print(canonical({'error':type(e).__name__,'message':str(e)}).decode(),file=sys.stderr)
        return 2
