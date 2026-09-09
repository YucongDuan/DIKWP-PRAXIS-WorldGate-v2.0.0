"""Correction propagation without silent overwrite or automatic truth replacement."""
from __future__ import annotations
import copy
from collections import defaultdict,deque
from .common import ValidationError,nonempty,digest


def reopen(graph,correction):
    nodes=copy.deepcopy(graph.get('nodes',[]))
    byid={};children=defaultdict(list);degree={}
    for n in nodes:
        nid=nonempty(n.get('id'),'node.id')
        if nid in byid:raise ValidationError('Duplicate lineage id')
        if n.get('kind') not in ('source','claim','check','report','release'):
            raise ValidationError('Invalid lineage kind')
        if not isinstance(n.get('depends_on'),list) or len(n['depends_on'])!=len(set(n['depends_on'])):
            raise ValidationError('Unique dependency list required')
        byid[nid]=n
    for n in nodes:
        for parent in n['depends_on']:
            if parent not in byid:raise ValidationError('Missing lineage parent')
            children[parent].append(n['id'])
        degree[n['id']]=len(n['depends_on'])
    queue=deque(k for k,v in degree.items() if v==0);visited=0
    while queue:
        p=queue.popleft();visited+=1
        for child in children[p]:
            degree[child]-=1
            if degree[child]==0:queue.append(child)
    if visited!=len(nodes):raise ValidationError('Cyclic provenance graph')
    target=correction.get('target')
    if target not in byid:raise ValidationError('Unknown correction target')
    nonempty(correction.get('actor'),'correction.actor')
    nonempty(correction.get('reason'),'correction.reason')
    if correction.get('status') not in ('DISPUTED','RETRACTED','SUPERSEDED'):
        raise ValidationError('Invalid correction status')
    affected=set();q=deque(children[target])
    while q:
        child=q.popleft()
        if child in affected:continue
        affected.add(child);q.extend(children[child])
    annotations=[{'node_id':target,'status':correction['status'],'evidence':correction}]
    annotations += [{'node_id':n,'status':'NEEDS_REVIEW','trigger':target} for n in sorted(affected)]
    return {'original_graph_hash':digest(graph),'nodes':nodes,'successor_annotations':annotations,
            'affected':sorted(affected),'independent_preserved':sorted(set(byid)-affected-{target}),
            'new_answer_generated':False,'external_revocation_performed':False,
            'authority_boundary':'A local analytical proposal from a declared actor; not authenticated external source withdrawal.'}
