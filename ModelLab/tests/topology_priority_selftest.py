from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from models.model_registry import is_hybrid_family
from models.models import generate_initial_population
from research.research_architect import compile_research_plan
from research.research_planner import plan_next_candidates

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def fake_profile():
    return {
        'profile_hash':'R3_TOPOLOGY_GPU',
        'cpu':{'name':'test','physical_cores':8,'logical_threads':16},
        'memory':{'total_gib':32.0,'available_gib':24.0},
        'nvidia':{'detected':True,'devices':[{'name':'RTX 2060 SUPER','memory_total_gib':8.0,'memory_free_gib':7.0}]},
        'torch':{'installed':True,'cuda_available':True},
    }


def planner_cfg(priority: float):
    cfg=deepcopy(BASE)
    cfg.setdefault('research_architecture',{})['hybrid_priority']=priority
    cfg.setdefault('agent',{})['research_plan']={
        'active_families':['tcn','lightgbm','hybrid::tcn::lightgbm'],
        'topology_priority':{'schema':'CP_TOPOLOGY_PRIORITY_V1','single':1.0-priority,'hybrid':priority,'authority':'OWNER_SLIDER_0_TO_1'},
    }
    return cfg


def counts(specs):
    h=sum(1 for s in specs if is_hybrid_family(s.family))
    return len(specs)-h,h


def main():
    req(abs(float((BASE.get('research_architecture') or {}).get('hybrid_priority'))-0.50)<1e-12,'default topology priority is 0.50')
    expected={0.0:(12,0),0.25:(9,3),0.50:(6,6),0.75:(3,9),1.0:(0,12)}
    for p,want in expected.items():
        cfg=planner_cfg(p)
        specs,meta=plan_next_candidates([],{},cfg,round_no=1,n=12,llm_strategy={})
        req(len(specs)==12,f'priority {p:.2f} preserves 12-candidate round budget')
        req(counts(specs)==want,f'priority {p:.2f} allocates SINGLE/HYBRID exactly {want[0]}/{want[1]}')
        req(meta['target_single_candidates']==want[0] and meta['target_hybrid_candidates']==want[1],f'priority {p:.2f} target evidence is persisted')
        req(meta['single_candidates']==want[0] and meta['hybrid_candidates']==want[1],f'priority {p:.2f} actual evidence matches target')
        if p==0.50:
            req(float(meta['estimated_compute_allocation']['hybrid_estimated_share'])>0.50,'50/50 candidate allocation reports separate higher hybrid compute estimate')
        fallback=generate_initial_population(cfg,count=12,round_no=1)
        req(counts(fallback)==want,f'fallback generator also honors priority {p:.2f}')

    cfg=deepcopy(BASE)
    cfg.setdefault('research_architecture',{})['family_selection_mode']='AUTO'
    cfg['research_architecture']['topology_selection_mode']='OWNER_FIXED'
    cfg['research_architecture']['hybrid_priority']=0.50
    plan=compile_research_plan({'active_families':['tcn','lightgbm']},fake_profile(),cfg)
    req(abs(plan['topology_priority']['single']-0.50)<1e-12 and abs(plan['topology_priority']['hybrid']-0.50)<1e-12,'compiled plan freezes Owner 50/50 authority')
    req('hybrid::tcn::lightgbm' in plan['active_families'],'compiler auto-composes legal hybrid when hybrid share is requested')
    req(plan['topology_priority']['authority']=='OWNER_SLIDER_0_TO_1','compiled plan records slider authority')

    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('adaptive_hybrid_priority' in app and 'Single ↔ Hybrid' in app,'Advanced UI exposes compact Single↔Hybrid slider')
    req('This does not blend model predictions' in app,'UI explicitly separates research allocation from prediction blending')
    print('\nTOPOLOGY PRIORITY SELF-TEST PASS')


if __name__=='__main__':
    main()
