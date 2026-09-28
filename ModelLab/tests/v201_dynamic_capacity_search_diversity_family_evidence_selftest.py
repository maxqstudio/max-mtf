from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import random
import numpy as np

from models.capacity_governor import (
    CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY,
    build_dataset_capacity_profile,
    cumulative_committed_full_wfa_capacity_rows,
    summarize_capacity_evidence,
    summarize_capacity_evidence_by_family,
)
from models.models import (
    architecture_capacity_fingerprint,
    candidate_capacity_contract,
    estimate_candidate_parameter_count,
    generate_initial_population,
    random_candidate,
)
from research.research_architect import compile_research_plan, apply_research_plan

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def hardware(*,ram=2048.0,available=1800.0,cores=128):
    return {
        'profile_hash':f'DIV_{ram}_{available}_{cores}',
        'cpu':{'name':'fixture','physical_cores':cores,'logical_threads':cores*2,'planning_cores':cores},
        'memory':{'total_gib':ram,'available_gib':available,'source':'fixture'},
        'nvidia':{'detected':False,'devices':[]},
        'torch':{'installed':True,'cuda_available':False},
    }


def planned(priority=0.5, *, rows=35_000, count=8, status='HOLD', delta=0.0, ram=2048.0, available=1800.0):
    cfg=deepcopy(BASE)
    ra=cfg.setdefault('research_architecture',{})
    ra['family_selection_mode']='MANUAL'; ra['allowed_families']=['transformer']
    ra['topology_selection_mode']='OWNER_FIXED'; ra['hybrid_priority']=0.0; ra['require_baseline']=False; ra['max_single_experiment_minutes']=1000000
    ra.setdefault('family_size_priorities',{})['transformer']=float(priority)
    cfg.setdefault('agent',{})['round_size']=int(count); cfg['agent']['max_experiments']=int(count)
    cfg.setdefault('split',{})['purge_bars']=54; cfg['split']['embargo_bars']=54
    cfg.setdefault('label',{})['max_hold_bars']=54
    ident={'rows':int(rows),'start':'2016-01-01','end':'2026-01-01','symbol':'XAUUSD','period':'M5'}
    cap=build_dataset_capacity_profile(ident,cfg)
    plan=compile_research_plan({'active_families':['transformer']},hardware(ram=ram,available=available),cfg,cap)
    sig=plan['capacity_evidence_by_family']['families']['transformer']
    sig.update({'status':status,'search_bias_delta':float(delta),'target_quantile_shift':float(delta),'expansion_factor':1.0+float(delta)})
    return apply_research_plan(cfg,plan)


def counts(cfg,round_no=7,count=8):
    arr=generate_initial_population(cfg,count=count,round_no=round_no)
    return arr,[int(estimate_candidate_parameter_count(x) or 0) for x in arr]


def full_row(family,pc,score,passed,fp,*,fidelity='FULL_WFA'):
    return {
        'family':family,
        'parameter_count':int(pc),
        'selection_score':float(score),
        'cv_gate_pass':bool(passed),
        'experiment_fingerprint':str(fp),
        'fidelity_stage':str(fidelity),
    }


def block(generation,*rows,run_id=None):
    return {'generation':int(generation),'run_id':run_id or f'GEN_{generation:02d}','rows':[deepcopy(x) for x in rows]}


def cumulative_signal(blocks,families):
    rows=cumulative_committed_full_wfa_capacity_rows(blocks)
    return rows,summarize_capacity_evidence_by_family(rows,families,authority=CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY)


def main():
    transformer=[
        full_row('transformer',200_000,.10,True,'t1'),
        full_row('transformer',300_000,.12,True,'t2'),
        full_row('transformer',1_500_000,.24,True,'t3'),
        full_row('transformer',2_000_000,.27,True,'t4'),
    ]
    tblocks=[block(i+1,row) for i,row in enumerate(transformer)]

    # CASE A — one committed Full-WFA observation per generation accumulates.
    expected_status=['HOLD','HOLD','HOLD','EXPAND']
    for n,status in enumerate(expected_status,start=1):
        rows,by=cumulative_signal(tblocks[:n],['transformer'])
        sig=by['families']['transformer']
        req(sig['sample_count']==n,f'CASE A Gen{n} cumulative sample_count={n}')
        req(sig['status']==status,f'CASE A Gen{n} cumulative status={status}')
        req(sig['generation_first']==1 and sig['generation_last']==n,f'CASE A Gen{n} generation range retained')
        req(sig['unique_experiment_count']==n,f'CASE A Gen{n} unique experiment count retained')
    _,by4=cumulative_signal(tblocks,['transformer'])
    tsig=by4['families']['transformer']
    req(abs(float(tsig['score_delta'])-0.145)<1e-12,'CASE A Gen4 cumulative Transformer score_delta=+0.145')
    req(tsig['authority']==CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY and by4['authority']==CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY,'CASE A cumulative committed Full-WFA authority is explicit')
    factory_src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req('cumulative_committed_full_wfa_capacity_rows(leaderboards)' in factory_src,'CASE A Factory runtime consumes cumulative committed generation leaderboards')
    req('summarize_capacity_evidence_by_family(lb,_active_families)' not in factory_src,'CASE B current-generation-only capacity callsite is removed')

    # CASE B — generation 4 cannot forget generations 1..3.
    req(tsig['sample_count']==4 and tsig['generation_first']==1 and tsig['generation_last']==4,'CASE B current generation retains prior committed generation evidence')

    # CASE C — exact-family isolation across generations, including hybrid identity.
    gru=[
        full_row('gru',80_000,.23,True,'g1'),
        full_row('gru',120_000,.22,True,'g2'),
        full_row('gru',260_000,.08,False,'g3'),
        full_row('gru',320_000,.07,False,'g4'),
    ]
    hybrid=[
        full_row('hybrid::gru::lightgbm',180_000,.10,True,'h1'),
        full_row('hybrid::gru::lightgbm',220_000,.11,True,'h2'),
        full_row('hybrid::gru::lightgbm',400_000,.20,True,'h3'),
        full_row('hybrid::gru::lightgbm',500_000,.21,True,'h4'),
    ]
    mixed=[block(i+1,transformer[i],gru[i],hybrid[i]) for i in range(4)]
    mixed_rows,mixed_by=cumulative_signal(mixed,['transformer','gru','tft','hybrid::gru::lightgbm'])
    fams=mixed_by['families']
    req(fams['transformer']['status']=='EXPAND','CASE C Transformer cumulative evidence => EXPAND')
    req(fams['gru']['status']=='CONTRACT','CASE C GRU cumulative evidence => CONTRACT')
    req(fams['tft']['status']=='HOLD' and fams['tft']['sample_count']==0,'CASE C TFT without evidence remains HOLD')
    req(fams['hybrid::gru::lightgbm']['status']=='EXPAND' and fams['gru']['status']=='CONTRACT','CASE C hybrid identity cannot contaminate standalone GRU')
    req(summarize_capacity_evidence(mixed_rows)['status']=='NO_GLOBAL_SIGNAL','CASE C global cross-family parameter comparison remains disabled')

    # CASE D — CHEAP_SCREEN telemetry is never cumulative capacity evidence.
    cheap_extremes=[full_row('transformer',50_000_000,99.0,True,f'cheap{i}',fidelity='CHEAP_SCREEN') for i in range(12)]
    dirty=deepcopy(tblocks)
    dirty[-1]['rows'].extend(cheap_extremes)
    dirty_rows,dirty_by=cumulative_signal(dirty,['transformer'])
    dirty_sig=dirty_by['families']['transformer']
    req(len(dirty_rows)==4 and dirty_sig['sample_count']==4 and dirty_sig['score_delta']==tsig['score_delta'],'CASE D CHEAP_SCREEN rows cannot alter capacity evidence')

    # CASE E — resume/reload of the same committed generation is idempotent.
    resumed=deepcopy(tblocks)+[deepcopy(tblocks[-1])]
    resume_rows,resume_by=cumulative_signal(resumed,['transformer'])
    rsig=resume_by['families']['transformer']
    req(len(resume_rows)==4 and rsig['sample_count']==4 and rsig['status']==tsig['status'] and rsig['score_delta']==tsig['score_delta'],'CASE E resume mirror cannot double-count committed evidence')

    # CASE F — duplicate authoritative fingerprint through evidence mirrors counts once.
    dup=deepcopy(tblocks)
    dup[1]['rows'].append(full_row('transformer',300_000,.12,True,'t2'))
    dup_rows,dup_by=cumulative_signal(dup,['transformer'])
    req(len(dup_rows)==4 and dup_by['families']['transformer']['unique_experiment_count']==4,'CASE F duplicate experiment_fingerprint counts once')

    # CASE G — same-size independent experiments remain independent observations.
    same_size=[block(1,
        full_row('transformer',400_000,.10,True,'same_a'),
        full_row('transformer',400_000,.11,True,'same_b'))]
    same_rows,same_by=cumulative_signal(same_size,['transformer'])
    ssig=same_by['families']['transformer']
    req(len(same_rows)==2 and ssig['sample_count']==2 and ssig['unique_experiment_count']==2,'CASE G distinct same-size experiment_fingerprint rows both remain valid')

    # CASE H — cumulative EXPAND changes search location only, never candidate hard ceilings.
    hold_cfg=planned(.5,status='HOLD',delta=0.0)
    expand_cfg=planned(.5,status='EXPAND',delta=.18)
    hold_candidates,_=counts(hold_cfg)
    probe=hold_candidates[len(hold_candidates)//2]
    hold_cap=candidate_capacity_contract(probe,hold_cfg)
    exp_cap=candidate_capacity_contract(probe,expand_cfg)
    req((hold_cap['legal_ceiling'],hold_cap['resource_ceiling'],hold_cap['scientific_ceiling'],hold_cap['effective_ceiling']) ==
        (exp_cap['legal_ceiling'],exp_cap['resource_ceiling'],exp_cap['scientific_ceiling'],exp_cap['effective_ceiling']),
        'CASE H cumulative evidence cannot widen LEGAL/RESOURCE/SCIENTIFIC/effective ceilings')

    # CASE I — EXPAND/HOLD/CONTRACT move only the next search distribution.
    # Use a deliberately non-binding capacity fixture here so this gate isolates
    # search-location movement rather than measuring hard-ceiling backoff saturation.
    contract_cfg=planned(.5,status='CONTRACT',delta=-.18,rows=2_000_000)
    hold_move_cfg=planned(.5,status='HOLD',delta=0.0,rows=2_000_000)
    expand_move_cfg=planned(.5,status='EXPAND',delta=.18,rows=2_000_000)
    contract_candidates,contract_counts=counts(contract_cfg)
    _,hold_counts=counts(hold_move_cfg)
    expand_candidates,expand_counts=counts(expand_move_cfg)
    req(float(np.median(contract_counts)) < float(np.median(hold_counts)) < float(np.median(expand_counts)),'CASE I CONTRACT < HOLD < EXPAND at distribution level')
    req(all(candidate_capacity_contract(x,expand_move_cfg)['passed'] for x in expand_candidates),'CASE I EXPAND search movement remains dynamically admitted')
    req(all(candidate_capacity_contract(x,contract_cfg)['passed'] for x in contract_candidates),'CASE I CONTRACT search movement remains dynamically admitted')

    # CASE J — repaired Large Transformer search remains diverse and deterministic.
    large_cfg=planned(1.0,count=8,rows=35_000)
    large_a=generate_initial_population(large_cfg,count=8,round_no=11)
    large_b=generate_initial_population(large_cfg,count=8,round_no=11)
    fingerprints=[architecture_capacity_fingerprint(x) for x in large_a]
    relevant=[(x.params.get('d_model'),x.params.get('num_layers'),x.params.get('ffn_mult'),x.params.get('sequence_length'),x.params.get('training_memory_months')) for x in large_a]
    req(all(candidate_capacity_contract(x,large_cfg)['passed'] for x in large_a),'CASE J all Large/backoff candidates pass dynamic capacity')
    req(len(set(fingerprints)) >= 6 and len(set(relevant)) >= 6,'CASE J eight-candidate Large Transformer search remains materially diverse')
    req([(x.family,x.name,x.params) for x in large_a] == [(x.family,x.name,x.params) for x in large_b],'CASE J deterministic replay reproduces exact diverse candidates')
    high_us={k:.985 for k in (large_cfg['agent']['research_plan']['parameter_envelopes']['transformer'] or {})}
    recovered=random_candidate(large_cfg,'transformer',random.Random(991),'forced_backoff_identity',high_us)
    req(candidate_capacity_contract(recovered,large_cfg)['passed'],'CASE J candidate-specific deterministic capacity backoff remains intact')

    # Existing Small/Balanced/Large monotonic preference contract remains intact.
    # Size-priority preference is likewise measured with capacity headroom available;
    # the constrained Large/backoff behavior is already covered immediately above.
    small_cfg=planned(0.0,count=8,rows=2_000_000); balanced_cfg=planned(.5,count=8,rows=2_000_000); big_cfg=planned(1.0,count=8,rows=2_000_000)
    _,small_counts=counts(small_cfg,round_no=5,count=8); _,bal_counts=counts(balanced_cfg,round_no=5,count=8); _,big_counts=counts(big_cfg,round_no=5,count=8)
    req(float(np.median(small_counts)) < float(np.median(bal_counts)) <= float(np.median(big_counts)),'Small/Balanced/Large preserve increasing model-size preference statistically')

    print('V201_DYNAMIC_CAPACITY_SEARCH_DIVERSITY_FAMILY_EVIDENCE PASS')


if __name__=='__main__':
    main()
