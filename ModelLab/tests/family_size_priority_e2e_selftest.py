from __future__ import annotations
import json, random
from copy import deepcopy
from pathlib import Path

from models.models import random_candidate, validate_candidate
from models.model_registry import effective_bounds, configured_family_size_priorities

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)


def cfg_for(family,priority):
    cfg=deepcopy(BASE)
    cfg['research_architecture']['family_size_priorities'][family]=priority
    # Freeze plan like a real Factory and give a deliberately bounded safe envelope.
    env={
        'gru':{'hidden_size':[32,128],'num_layers':[1,3],'dropout':[0.0,0.4]},
        'tcn':{'tcn_channels':[16,96],'tcn_blocks':[2,6],'kernel_size':[2,5]},
        'transformer':{'d_model':[32,128],'num_layers':[1,4],'ffn_mult':[2,4]},
    }.get(family,{})
    cfg.setdefault('agent',{})['research_plan']={
        'active_families':[family],
        'parameter_envelopes':{family:env},
        'family_size_priorities':deepcopy(cfg['research_architecture']['family_size_priorities']),
        'capacity_guidance':{'preferred_total_params':[1,100_000_000],'extended_total_params':[1,200_000_000]},
    }
    return cfg


def mean_param(cfg,family,key):
    vals=[]
    for i in range(40):
        c=random_candidate(cfg,family,random.Random(1000+i),f'{family}_{i}')
        vals.append(float(c.params[key]))
    return sum(vals)/len(vals),min(vals),max(vals)


def main():
    # Deterministic generator must materially respond to sliders while 0.50 remains neutral.
    for family,key in [('gru','hidden_size'),('tcn','tcn_channels'),('transformer','d_model')]:
        small=cfg_for(family,0.0); neutral=cfg_for(family,0.5); large=cfg_for(family,1.0)
        ms,mins,maxs=mean_param(small,family,key); mn,minn,maxn=mean_param(neutral,family,key); ml,minl,maxl=mean_param(large,family,key)
        req(ms < mn < ml,f'{family} deterministic candidate size shifts Small < neutral < Large')
        sb=effective_bounds(small,family)[key]; nb=effective_bounds(neutral,family)[key]; lb=effective_bounds(large,family)[key]
        req(sb[:2]==nb[:2]==lb[:2],f'{family} size priority does not hard-slice executable bounds')

    # Deterministic canonicalization stays inside the compiled executable range; size priority is not a hard admission bound.
    cfg=cfg_for('gru',0.0)
    b=effective_bounds(cfg,'gru')
    raw={'family':'gru','name':'oversized_llm','params':{
        'sequence_length':64,'hidden_size':9999,'num_layers':4,'dropout':0.2,
        'learning_rate':0.001,'batch_size':64,'epochs':10,'weight_decay':0.001,'training_memory_months':12,
    }}
    c=validate_candidate(raw,cfg)
    req(c is not None and c.params['hidden_size']<=b['hidden_size'][1] and c.params['num_layers']<=b['num_layers'][1],'deterministic canonicalization stays inside compiled executable bounds')

    # UI, Scientist, Factory and persisted config are all wired, not a decorative slider.
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    sci=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
    fac=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    arch=(ROOT/'research/research_architect.py').read_text(encoding='utf-8')
    for fam in ('lightgbm','xgboost','random_forest','gru','lstm','tcn','transformer','patchtst','itransformer','tft','transformer_moe'):
        req(f'adaptive_size_priority_{{fam}}' in app or 'adaptive_size_priority_' in app,'UI uses per-family size slider key template')
        break
    req('Model size priority' in app and 'Small' in app and 'Large' in app,'Advanced UI exposes compact Small↔Large control')
    req('owner_family_size_priorities' in sci and 'effective_parameter_bounds' in sci,'Scientist receives Owner priorities plus compiled bounds')
    req('owner_family_size_priorities' in fac,'Factory context carries frozen size priorities')
    req('family_size_priorities' in sup,'Round Scientist context carries size priorities')
    req('family_size_priorities' in arch and 'OWNER_SEARCH_PREFERENCE_INSIDE_DYNAMIC_CAPACITY_NOT_HARD_BOUND_SLICE' in arch,'research plan freezes Owner size priorities as search preferences')


    # Hypothesis-directed experiments and cheap-screen fidelity must keep the same effective size authority.
    from research.scientific_hypotheses import validate_hypothesis
    from research.research_engine_v3 import cheap_screen_spec
    from research.research_planner import plan_next_candidates
    h=validate_hypothesis({
        'kind':'MODEL_ARCHITECTURE','title':'large gru probe','rationale':'capacity test','expected_observation':'bounded',
        'payload':{'family_priorities':{'gru':1.0},'variable_keys_by_family':{'gru':['hidden_size']},'parameter_ranges_by_family':{'gru':{'hidden_size':[1,9999]}}}
    },cfg_for('gru',0.0),1)
    hb=effective_bounds(cfg_for('gru',0.0),'gru')['hidden_size']
    req(h is not None and h['payload']['parameter_ranges_by_family']['gru']['hidden_size'][1] <= hb[1],'Scientist hypothesis range cannot escape executable bounds; Small preference does not invent a lower hard ceiling')

    large_cfg=cfg_for('gru',1.0)
    gc=random_candidate(large_cfg,'gru',random.Random(44),'large_gru')
    screen=cheap_screen_spec(gc,large_cfg)
    gb=effective_bounds(large_cfg,'gru')
    req(screen.params['hidden_size']==gc.params['hidden_size'],'cheap screen preserves generated Large architecture identity rather than enforcing a separate bound')

    planner_cfg=cfg_for('gru',0.0)
    planner_cfg['agent']['round_size']=2
    cands,plan=plan_next_candidates([],{},planner_cfg,round_no=1,n=2,llm_strategy={})
    req(plan.get('family_size_priority_schema')=='CP_FAMILY_SIZE_PRIORITY_V1' and plan.get('family_size_priorities',{}).get('gru')==0.0,'Discovery plan journals frozen family size priorities')

    cfg=deepcopy(BASE)
    pri=configured_family_size_priorities(cfg)
    req(len(pri)>=11 and all(0.0<=v<=1.0 for v in pri.values()),'config persistence exposes bounded priorities for every family')

    print('FAMILY_SIZE_PRIORITY_E2E_SELFTEST PASS')

if __name__=='__main__': main()
