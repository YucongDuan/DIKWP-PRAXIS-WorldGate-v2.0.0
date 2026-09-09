"""Failures become reviewable proposals, never automatically trusted test labels."""
from .common import digest


def proposals(summary):
    result=[]
    for a in summary['assessments']:
        if a['arm']!='ON' or a['verdict']=='PASS_WITHIN_SCOPE':continue
        failures=[k for k,v in a['coordinates'].items() if v['state'] in ('FAIL','UNKNOWN')]
        entry={'status':'QUARANTINED_PROPOSAL','source_run':a['run_id'],'case_id':a['case_id'],
               'carrier':a['carrier'],'failures':failures,'expected_answer':None,
               'source_assessment_hash':digest(a),'target':'training-or-new-review-pool',
               'holdout_mutation_allowed':False,'requires':'Independent label review, provenance check, then a new dataset version'}
        entry['id']=digest(entry)[:20]
        result.append(entry)
    return {'proposals':result,'state':'NOT_MERGED','automatic_patch_or_deployment':False}
