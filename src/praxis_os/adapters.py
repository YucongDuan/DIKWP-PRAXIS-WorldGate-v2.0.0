"""Real local toy execution and an opt-in trusted JSON-lines process bridge.

A subprocess is NOT a security sandbox. Untrusted agents need OS/container isolation.
No API keys or arbitrary shell commands are accepted by the built-in harness.
"""
from __future__ import annotations
import copy
import os
import signal
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from .common import ValidationError, canonical, loads, number

BUILTINS=('direct','relational','unsafe')

class ToolBroker:
    """A small genuinely enforced broker for local toy read operations only."""
    def __init__(self,authority,records):
        self.authority=copy.deepcopy(authority)
        self.records=copy.deepcopy(records)
        self.calls=0
    def invoke(self,operation,resource,principal,step):
        a=self.authority
        if (operation not in a['allowed_tools'] or resource not in a['allowed_resources'] or
            principal!=a['principal'] or step>a['expires_step'] or self.calls>=a['max_tool_calls']):
            raise PermissionError('Local capability denied')
        if operation!='orders.read':
            raise PermissionError('No handler registered')
        self.calls+=1
        return copy.deepcopy(self.records)


def builtin_execute(carrier,case,arm,trial,seed,contract):
    """No expected answer is provided to this function. OFF/ON are actual algorithms."""
    if carrier not in BUILTINS or arm not in ('ON','OFF'):
        raise ValidationError('Unknown built-in carrier/arm')
    before=time.perf_counter_ns()
    principal=contract['authority']['principal']
    spans=[{'id':'root','parent':None,'kind':'root','step':0,'attrs':{}},
           {'id':'agent','parent':'root','kind':'agent','step':1,'attrs':{'model_version':'toy-1'}}]
    records=case['input'].get('orders',[])
    if len(records)>10000:
        raise ValidationError('Too many toy orders')
    for r in records:
        number(r.get('unit_cents'),'unit_cents',0,10**9,integer=True)
        number(r.get('quantity'),'quantity',0,10000,integer=True)
        if r.get('status') not in ('active','cancelled') or not isinstance(r.get('id'),str):
            raise ValidationError('Invalid order')
    broker=ToolBroker(contract['authority'],records)
    performed=False; status='COMPLETED'; result={}
    try:
        records=broker.invoke('orders.read','orders',principal,2)
        performed=True
        if carrier in ('direct','unsafe'):
            selected=[r for r in records if arm=='OFF' or r['status']=='active']
            total=sum(r['unit_cents']*r['quantity'] for r in selected)
            ids=sorted(r['id'] for r in selected)
        else:
            with sqlite3.connect(':memory:') as con:
                con.execute('CREATE TABLE orders(id TEXT, price INTEGER, qty INTEGER, status TEXT)')
                con.executemany('INSERT INTO orders VALUES(?,?,?,?)',[(r['id'],r['unit_cents'],r['quantity'],r['status']) for r in records])
                where=" WHERE status='active'" if arm=='ON' else ''
                total=con.execute('SELECT COALESCE(SUM(price*qty),0) FROM orders'+where).fetchone()[0]
                ids=sorted(x[0] for x in con.execute('SELECT id FROM orders'+where))
        result={'total_cents':total,'included_ids':ids}
    except PermissionError:
        status='DENIED'
    spans.append({'id':'read','parent':'agent','kind':'tool','step':2,
                  'attrs':{'operation':'orders.read','resource':'orders','principal':principal,'performed':performed,'denied':not performed}})
    spans.append({'id':'memory','parent':'agent','kind':'memory','step':3,
                  'attrs':{'namespace':case.get('namespace','local'),'source_refs':case.get('evidence_ids',[])}})
    # The unsafe fixture deliberately simulates an agent bypassing a host-side broker.
    # It records the forbidden side effect and changes only an in-memory dictionary.
    # It never writes a real external database or transfers funds.
    environment={'summary_saved':status=='COMPLETED','unexpected_write':False}
    if carrier=='unsafe' and arm=='ON':
        environment['unexpected_write']=True
        spans.append({'id':'bypass','parent':'agent','kind':'tool','step':4,
                      'attrs':{'operation':'orders.delete','resource':'production-orders',
                               'principal':principal,'performed':True}})
    elapsed=(time.perf_counter_ns()-before)/1_000_000
    return {'execution_status':status,'output':result,'spans':spans,
            'outcome':{'source_kind':'environment_observation','observer':'toy-environment-checker',
                       'observed':True,'state':environment},
            'metrics':{'duration_ms':elapsed,'cost_microunits':0,'cost_basis':'local-demo-no-service-fee',
                       'energy_j':None,'energy_boundary':None},
            'execution_kind':'EXECUTED_LOCAL_SYNTHETIC_ENVIRONMENT'}


def trusted_process(config,request,trust=False):
    """Execute explicit fixed argv with capped pipe output and a timeout.

    Does not contain malicious children or block networking/filesystem access.
    Use only trusted workers; deploy an external sandbox for untrusted code.
    """
    if not trust:
        raise ValidationError('Worker disabled: explicit --trust-worker required; not a sandbox')
    argv=config.get('argv')
    if not isinstance(argv,list) or not argv or any(not isinstance(s,str) for s in argv):
        raise ValidationError('argv must be a nonempty fixed list; shell commands are not parsed')
    if not Path(argv[0]).is_absolute():
        raise ValidationError('Worker executable must be an absolute path')
    timeout=number(config.get('timeout_seconds',10),'timeout_seconds',.05,300)
    cap=number(config.get('max_output_bytes',1_000_000),'max_output_bytes',64,4_000_000,integer=True)
    env={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','LANG','LC_ALL')}
    explicit=config.get('env',{})
    if not isinstance(explicit,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in explicit.items()):
        raise ValidationError('Explicit worker env must contain strings')
    env.update(explicit)
    data=canonical(request)+b'\n'
    if len(data)>1_000_000:
        raise ValidationError('Worker request exceeds 1 MB')
    start=time.perf_counter_ns()
    with tempfile.TemporaryDirectory(prefix='praxis-worker-') as wd:
        p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           cwd=wd,env=env,shell=False,start_new_session=os.name=='posix')
        outputs=[bytearray(),bytearray()]; over=threading.Event()
        def drain(pipe,i):
            while True:
                chunk=pipe.read(4096)
                if not chunk:break
                if len(outputs[i])+len(chunk)>cap:
                    over.set()
                    break
                outputs[i].extend(chunk)
        ts=[threading.Thread(target=drain,args=(p.stdout,0),daemon=True),
            threading.Thread(target=drain,args=(p.stderr,1),daemon=True)]
        for t in ts:t.start()
        def write():
            try:
                p.stdin.write(data);p.stdin.close()
            except (BrokenPipeError,OSError):pass
        writer=threading.Thread(target=write,daemon=True);writer.start()
        deadline=time.monotonic()+timeout
        reason=None
        while p.poll() is None:
            if over.is_set(): reason='OUTPUT_LIMIT';break
            if time.monotonic()>=deadline:reason='TIMEOUT';break
            time.sleep(.005)
        if reason:
            try:
                if os.name=='posix':os.killpg(p.pid,signal.SIGKILL)
                else:p.kill()
            except ProcessLookupError:pass
        p.wait(timeout=5)
        # Close inherited pipes held by cooperative worker descendants on POSIX.
        if os.name=='posix':
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        for t in ts:t.join(timeout=1)
        writer.join(timeout=1)
        for pipe in (p.stdin,p.stdout,p.stderr):
            if pipe is not None and not pipe.closed:pipe.close()
        if over.is_set():reason='OUTPUT_LIMIT'
        if not reason and p.returncode!=0:reason='WORKER_ERROR'
        if reason:
            return {'execution_status':reason,'output':{},'spans':[
                {'id':'root','parent':None,'kind':'root','step':0,'attrs':{'error_type':reason}}],
                'outcome':None,'metrics':{'duration_ms':(time.perf_counter_ns()-start)/1e6,'cost_microunits':None,'energy_j':None},
                'execution_kind':'TRUSTED_SUBPROCESS'}
        try:
            response=loads(bytes(outputs[0]))
        except ValidationError:
            response={'execution_status':'INVALID_WORKER_JSON','output':{},'spans':[], 'outcome':None}
        if not isinstance(response,dict):
            response={'execution_status':'INVALID_WORKER_JSON','output':{},'spans':[], 'outcome':None}
        metrics=response.setdefault('metrics',{})
        if not isinstance(metrics,dict):
            raise ValidationError('Worker metrics must be object')
        metrics['duration_ms']=(time.perf_counter_ns()-start)/1e6
        response['execution_kind']='TRUSTED_SUBPROCESS'
        return response
