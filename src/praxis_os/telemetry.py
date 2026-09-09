"""Read a documented subset of OTLP/JSON. This is not an OTel collector/SDK."""
from __future__ import annotations
from .common import ValidationError, number
from .contracts import sanitize_spans, validate_spans


def _value(v):
    if not isinstance(v,dict):return None
    if 'stringValue' in v:return v['stringValue']
    if 'intValue' in v:
        try:return int(v['intValue'])
        except (ValueError,TypeError):return None
    if 'boolValue' in v and type(v['boolValue']) is bool:return v['boolValue']
    if 'doubleValue' in v:
        number(v['doubleValue'],'doubleValue')
        return v['doubleValue']
    return None


def import_otlp(data):
    """Trace grouping, local span metadata and explicit mapping-loss report.

    Core OTLP span structure is accepted. Vendor fields are not treated as
    authorization or causal truth. No prompt, response, raw tool argument or CoT
    content is retained in the imported trace.
    """
    grouped={}; dropped=set(); unknown=set(); converted=0
    resources=data.get('resourceSpans',[])
    if not isinstance(resources,list):raise ValidationError('resourceSpans list required')
    for r in resources:
        for scope in r.get('scopeSpans',[]):
            for s in scope.get('spans',[]):
                converted+=1
                if converted>10000:raise ValidationError('Span limit exceeded')
                tid=s.get('traceId');sid=s.get('spanId')
                if not isinstance(tid,str) or not isinstance(sid,str):raise ValidationError('Trace/span IDs required')
                attrs={a['key']:_value(a.get('value',{})) for a in s.get('attributes',[]) if isinstance(a,dict) and 'key' in a}
                op=attrs.get('gen_ai.operation.name')
                kind=attrs.get('praxis.span.kind')
                if kind is None:
                    kind={'execute_tool':'tool','chat':'model','generate_content':'model','embeddings':'embedding',
                          'retrieval':'retrieval','invoke_agent':'agent'}.get(op,'agent')
                parent=s.get('parentSpanId') or None
                if parent is None:kind='root'
                mapped={}
                mappings={'gen_ai.request.model':'model_version','gen_ai.provider.name':'provider',
                          'gen_ai.usage.input_tokens':'token_input','gen_ai.usage.output_tokens':'token_output',
                          'gen_ai.tool.name':'operation','praxis.resource':'resource',
                          'praxis.principal':'principal','praxis.performed':'performed',
                          'praxis.namespace':'namespace'}
                for k,v in attrs.items():
                    if k in mappings:mapped[mappings[k]]=v
                    elif k in ('gen_ai.operation.name','praxis.span.kind','praxis.step'):pass
                    elif any(x in k.lower() for x in ('message','prompt','argument','result','thought','secret','authorization')):dropped.add(k)
                    else:unknown.add(k)
                try:step=int(attrs.get('praxis.step',0))
                except (TypeError,ValueError):raise ValidationError('Invalid praxis.step')
                entry={'id':sid,'parent':parent,'kind':kind,'step':step,'attrs':mapped}
                grouped.setdefault(tid,[]).append(entry)
    if not grouped:raise ValidationError('No spans found')
    traces=[]
    for tid,spans in sorted(grouped.items()):
        sanitized,removed=sanitize_spans(spans)
        dropped.update(removed)
        errors=[]
        try:validate_spans(sanitized)
        except ValidationError as e:errors.append(str(e))
        traces.append({'trace_id':tid,'spans':sanitized,'structural_errors':errors})
    return {'format':'OTLP_JSON_SUBSET_IMPORT','traces':traces,'dropped_content_keys':sorted(dropped),
            'unmapped_keys':sorted(unknown),'loss_report':[
                'No full OTLP protobuf, collector, metrics, links or resource semantics support.',
                'An imported causal-looking parent link is execution structure, not proof of causality.',
                'Missing praxis authority/outcome metadata stays missing; no automatic pass.',
                'GenAI convention version must be pinned by the deploying integration.']}
