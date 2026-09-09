"""Controlled intervention in a finite toy environment, not causal discovery from logs."""
import copy
from .fixtures import demo_project
from .adapters import builtin_execute
from .common import digest


def finite_interventions():
    project=demo_project();results=[]
    for carrier in ('direct','relational'):
        trials=[]
        for case in project['cases']:
            contract=copy.deepcopy(project['contract'])
            base=builtin_execute(carrier,case,'ON',0,27,contract)
            blocked=copy.deepcopy(contract);blocked['authority']['allowed_tools']=[]
            removal=builtin_execute(carrier,case,'ON',0,27,blocked)
            # Negative control: memory annotations do not drive this stateless calculation.
            memoryless=copy.deepcopy(case);memoryless['evidence_ids']=[]
            control=builtin_execute(carrier,memoryless,'ON',0,27,contract)
            trials.append({'case_id':case['case_id'],
                           'base_correct':digest(base['output'])==digest(case['expected']),
                           'read_removal_correct':digest(removal['output'])==digest(case['expected']),
                           'memory_metadata_removal_correct':digest(control['output'])==digest(case['expected']),
                           'tool_denial_enforced':removal['execution_status']=='DENIED'})
        results.append({'carrier':carrier,'trials':trials,'n':len(trials),
                        'correct_base':sum(x['base_correct'] for x in trials),
                        'correct_without_read':sum(x['read_removal_correct'] for x in trials),
                        'correct_without_memory_metadata':sum(x['memory_metadata_removal_correct'] for x in trials)})
    return {'scope':'EXECUTED_FINITE_SYNTHETIC_INTERVENTION','results':results,
            'interpretation':'Read capability is necessary for these two toy implementations. Memory trace metadata is not necessary for their arithmetic output.',
            'cannot_infer':'No inference about general agents, human cognition or memory necessity. Trace correlations alone were not used as causal proof.'}
