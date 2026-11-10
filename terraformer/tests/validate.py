#!/usr/bin/env python3
"""Local authoring validation for TerraFormer; no runtime enforcement claim."""
import json, sys
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT=Path(__file__).resolve().parents[1]
NAME='terraformer'
PACKET='terraformer_integration_packet'

def die(message): raise AssertionError(message)

def main():
    manifest=yaml.safe_load((ROOT/'manifest.yaml').read_text())
    transitions=yaml.safe_load((ROOT/'transitions.yaml').read_text())
    assert manifest['id']==NAME and manifest['domain']=='architectural_recomposition'
    assert manifest['composition']['requires']==[]
    cfw=manifest['integrations']['cognitiveframeworks']
    assert cfw['required']==[] and {'owl','anchor','dox','fuse','ward','flow','sispis'} <= set(cfw['enhancements'])
    assert manifest['emits']==[PACKET] and manifest['handoff']==PACKET and manifest['inputs']['required']==['task_context']
    assert (ROOT/manifest['entrypoint']).is_file() and (ROOT/manifest['engine']['contract']).is_file()
    states=set(transitions['states'])
    assert set(transitions['completion_states']).issubset(states)
    assert set(transitions['normal_path']).issubset(states)
    ids=set(); edges=[]
    kind=yaml.safe_load((ROOT/'contracts/evidence-kinds.yaml').read_text())['kinds']
    for edge in transitions['transitions']:
        assert edge['id'] not in ids;ids.add(edge['id'])
        assert edge['from']=='*' or edge['from'] in states
        assert edge['to'] in states
        assert edge['required_evidence']
        if edge.get('consequential'):
            assert all(e in kind for e in edge['required_evidence'])
        if edge['to'] in transitions['completion_states']:
            assert edge['progress_class']=='TERMINAL'
        else:
            assert edge['progress_class']!='TERMINAL'
        edges.append((edge['from'],edge['to']))
    for left,right in zip(transitions['normal_path'],transitions['normal_path'][1:]):
        assert (left,right) in edges,(left,right)
    flows=list((ROOT/'flows').glob('*/flow.md'))
    assert len(flows)>=8
    assert sum('fallback: true' in f.read_text().lower() for f in flows)==1
    for f in flows:
        content=f.read_text();assert content.startswith('---\n'),f
        fm=yaml.safe_load(content.split('---',2)[1]); assert fm['flow']==f.parent.name
        assert 'required_specialists' in fm and 'optional_specialists' in fm
        if f.parent.name!='triage': assert fm['when']['field']=='operation'
    schemas={}
    for p in (ROOT/'contracts/schemas').glob('*.schema.json'):
        doc=json.loads(p.read_text());Draft202012Validator.check_schema(doc);schemas[doc['$id']]=doc
    reg=Registry()
    for url,doc in schemas.items(): reg=reg.with_resource(url,Resource.from_contents(doc))
    packet_schema=schemas['https://cognitivestatework.dev/schemas/'+PACKET+'.schema.json']
    validator=Draft202012Validator(packet_schema,registry=reg,format_checker=FormatChecker())
    positive=json.loads((ROOT/'qualification/packet-valid.example.json').read_text())
    validator.validate(positive)
    negatives=list((ROOT/'qualification/negative').glob('*.json'))
    assert len(negatives)>=4
    for p in negatives:
        payload=json.loads(p.read_text())
        assert list(validator.iter_errors(payload)),f'negative fixture passed: {p.name}'
    abp=yaml.safe_load((ROOT/'templates/architecture-boundary.example.yaml').read_text())
    abp_schema=schemas['https://cognitivestatework.dev/schemas/architecture-boundary-v1.schema.json']
    Draft202012Validator(abp_schema,registry=reg,format_checker=FormatChecker()).validate(abp)
    cases=yaml.safe_load((ROOT/'qualification/cases.yaml').read_text())['cases']
    assert len(cases)>=6 and len({x['id'] for x in cases})==len(cases)
    case_ids={x['id'] for x in cases}
    assert {'already-coherent','unnecessary-adapter',
            'conflicting-ownership','partial-lifecycle'} <= case_ids
    print(f'PASS {NAME}: manifest, edges={len(edges)}, flows={len(flows)}, schemas={len(schemas)}, packet positive + {len(negatives)} negative fixtures, scenarios={len(cases)}')
    print('SCOPE: Local bundle checks only; host transition enforcement is covered by the CSW qualification suite.')

if __name__=='__main__':main()
