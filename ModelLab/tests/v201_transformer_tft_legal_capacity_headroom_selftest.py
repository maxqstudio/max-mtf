from __future__ import annotations

import gc
import hashlib
import json
import random
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

import models.models as models_module
from models.capacity_governor import build_dataset_capacity_profile
from models.model_registry import effective_bounds, get_bounds
from models.models import (
    CandidateSpec,
    architecture_capacity_fingerprint,
    candidate_capacity_contract,
    estimate_candidate_parameter_count,
    legal_capacity_headroom_evidence,
    random_candidate,
    strict_scientist_candidate_admission,
)
from research.research_architect import apply_research_plan, compile_research_plan
from research.research_control import bind_manual_capacity_authority, compile_manual_runtime
from research.temporal_research import TemporalNet

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
OUT=ROOT/'evidence/current/V201_TRANSFORMER_TFT_LEGAL_CAPACITY_HEADROOM.json'

OLD_TRANSFORMER_REACHABLE=25_493_507
OLD_TFT_REACHABLE=4_814_627
OTHER_FAMILY_REGISTRY_HASH='df4997f7cad16725d7ad2e371e9e9d56f78faf67487c9a471764dcae73c75202'
OTHER_REACHABLE={
    'gru':5_568_003,
    'lstm':7_423_491,
    'tcn':7_361_539,
    'patchtst':14_984_835,
    'itransformer':14_401_539,
    'transformer_moe':208_170_035,
}
OTHER_HARD_LEGAL={
    'gru':5_568_003,
    'lstm':7_423_491,
    'tcn':7_361_539,
    'patchtst':14_247_555,
    'itransformer':14_217_219,
    'transformer_moe':207_916_083,
}


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def profile(*,ram=128.0,available=110.0,cuda=True,vram=48.0,vram_free=46.0,cores=24):
    return {
        'profile_hash':f'HEADROOM_{ram}_{vram}_{cores}',
        'cpu':{'name':'fixture','physical_cores':cores,'logical_threads':cores*2,'planning_cores':cores},
        'memory':{'total_gib':ram,'available_gib':available,'source':'fixture'},
        'nvidia':{'detected':bool(cuda),'devices':([{'name':'fixture GPU','memory_total_gib':vram,'memory_free_gib':vram_free}] if cuda else [])},
        'torch':{'installed':True,'cuda_available':bool(cuda)},
    }


def planned_cfg(family:str,*,rows=2_000_000,years=10,hardware=None,priority=1.0,max_minutes=100_000):
    cfg=deepcopy(BASE)
    ra=cfg.setdefault('research_architecture',{})
    ra['family_selection_mode']='MANUAL'
    ra['allowed_families']=[family]
    ra['topology_selection_mode']='OWNER_FIXED'
    ra['hybrid_priority']=0.0
    ra['require_baseline']=False
    ra['max_single_experiment_minutes']=int(max_minutes)
    ra.setdefault('family_size_priorities',{})[family]=float(priority)
    cfg.setdefault('split',{})['purge_bars']=54
    cfg['split']['embargo_bars']=54
    cfg.setdefault('label',{})['max_hold_bars']=54
    cfg.setdefault('agent',{})['max_experiments']=8
    cfg['agent']['round_size']=8
    ident={'rows':int(rows),'start':'2016-01-01','end':f'{2016+int(years)}-01-01','symbol':'XAUUSD','period':'M5'}
    cap=build_dataset_capacity_profile(ident,cfg)
    hw=hardware or profile()
    plan=compile_research_plan({'active_families':[family]},hw,cfg,cap)
    return apply_research_plan(cfg,plan),cap,plan,hw


def params_from_bounds(family:str,bounds:dict,**overrides):
    p={}
    for key,(lo,hi,typ) in bounds.items():
        # Conservative non-architecture defaults; overrides carry the capacity shape.
        v=lo
        if key=='learning_rate': v=max(float(lo),min(float(hi),0.001))
        if key=='dropout': v=max(float(lo),min(float(hi),0.10))
        if key=='weight_decay': v=max(float(lo),min(float(hi),0.001))
        if key=='epochs': v=max(int(lo),min(int(hi),8))
        if key=='batch_size': v=int(lo)
        if key=='training_memory_months': v=int(hi)
        p[key]=int(v) if typ is int else float(v)
    p.update(overrides)
    return p


def spec_for(cfg:dict,family:str,name:str,**overrides):
    return CandidateSpec(family,name,params_from_bounds(family,effective_bounds(cfg,family),**overrides))


def direct_spec(family:str,name:str,**overrides):
    return CandidateSpec(family,name,params_from_bounds(family,get_bounds([family])[family],**overrides))


def forward_proof(family:str,params:dict,seq:int):
    p=dict(params);p['sequence_length']=seq
    model=TemporalNet(
        architecture=family,n_features=32,n_classes=3,
        hidden_size=int(p.get('hidden_size',64)),num_layers=int(p.get('num_layers',1)),dropout=float(p.get('dropout',0.0)),
        tcn_channels=int(p.get('tcn_channels',p.get('hidden_size',64))),tcn_blocks=int(p.get('tcn_blocks',3)),kernel_size=int(p.get('kernel_size',3)),
        d_model=int(p.get('d_model',p.get('hidden_size',64))),attention_heads=int(p.get('attention_heads',4)),ffn_mult=int(p.get('ffn_mult',2)),
        expert_ffn=int(p.get('expert_ffn',max(64,int(p.get('d_model',64))*2))),num_experts=int(p.get('num_experts',4)),top_k=int(p.get('top_k',1)),
        router_temperature=float(p.get('router_temperature',1.0)),load_balance_coef=float(p.get('load_balance_coef',0.01)),
        patch_len=int(p.get('patch_len',16)),patch_stride=int(p.get('patch_stride',8)),tft_lstm_layers=int(p.get('tft_lstm_layers',1)),
        sequence_length=int(seq),mean=np.zeros(32,np.float32),std=np.ones(32,np.float32),
    )
    with torch.no_grad():
        y=model(torch.zeros((1,seq,32),dtype=torch.float32))
    count=int(sum(x.numel() for x in model.parameters()))
    req(tuple(y.shape)==(1,3) and torch.isfinite(y).all().item() and abs(float(y.sum())-1.0)<1e-5,f'{family} upper-region constructor/forward/output contract')
    del y,model;gc.collect()
    return count


def manual_exact_accept(family:str,params:dict,hw:dict):
    cfg=deepcopy(BASE)
    cfg.setdefault('research_architecture',{})['max_single_experiment_minutes']=100_000
    cfg['research_architecture']['safe_ram_fraction']=0.95
    cfg['research_architecture']['safe_vram_fraction']=0.95
    cfg.setdefault('champion_factory',{})['research_mode']='MANUAL'
    cfg['champion_factory']['manual_research']={'enabled':True,'candidates':[{'family':family,'name':f'manual_{family}_new_region','params':deepcopy(params)}]}
    runtime,rows=compile_manual_runtime(cfg)
    ident={'rows':2_000_000,'start':'2016-01-01','end':'2026-01-01','symbol':'XAUUSD','period':'M5'}
    cap=build_dataset_capacity_profile(ident,runtime)
    runtime,evidence=bind_manual_capacity_authority(runtime,rows,hw,cap)
    return rows[0],evidence[0]['capacity_contract']


def actual_registry_max(family:str)->int:
    b=get_bounds([family])[family]
    p={k:hi for k,(_lo,hi,_typ) in b.items()}
    spec=CandidateSpec(family,f'{family}_registry_max',p)
    count=estimate_candidate_parameter_count(spec)
    del spec;gc.collect()
    return int(count)


def main():
    strong=profile()
    tcfg,_,_,_=planned_cfg('transformer',hardware=strong)
    fcfg,_,_,_=planned_cfg('tft',hardware=strong)
    cases={}

    te=legal_capacity_headroom_evidence('transformer')
    fe=legal_capacity_headroom_evidence('tft')
    req(te['legal_ceiling_matches_reachable_max'] and te['legal_architecture_bounds']['d_model']==[16,816],'Transformer registry/constructor/legal ceiling agree at d_model<=816')
    req(fe['legal_ceiling_matches_reachable_max'] and fe['legal_architecture_bounds']['d_model']==[16,480],'TFT registry/constructor/legal ceiling agree at d_model<=480')

    # CASE A — old Transformer boundary stays valid.
    ta=spec_for(tcfg,'transformer','case_a',sequence_length=16,d_model=512,num_layers=6,attention_heads=8,ffn_mult=6)
    tac=candidate_capacity_contract(ta,tcfg); tacount=estimate_candidate_parameter_count(ta)
    req(tacount==25_239_555 and tac['passed'],'CASE A old Transformer hard-boundary configuration remains valid')
    cases['A']={'parameter_count':tacount,'passed':tac['passed']}

    # CASE B — materially above old reachable maximum is legal when other ceilings permit.
    tb=spec_for(tcfg,'transformer','case_b',sequence_length=16,d_model=576,num_layers=6,attention_heads=8,ffn_mult=6)
    tbc=candidate_capacity_contract(tb,tcfg);tbcount=estimate_candidate_parameter_count(tb)
    req(tbcount>OLD_TRANSFORMER_REACHABLE and tbc['passed'],'CASE B Transformer new legal region is executable/admitted')
    cases['B']={'parameter_count':tbcount,'effective_ceiling':tbc['effective_ceiling']}

    # CASE C — target headroom comes from actual executable count.
    req(60_000_000<=te['reachable_max_parameter_count']<=70_000_000,'CASE C Transformer reachable maximum is in 60M-70M target region')
    forward_t=direct_spec('transformer','transformer_forward_target',sequence_length=16,d_model=816,num_layers=6,attention_heads=8,ffn_mult=6)
    forward_t_count=forward_proof('transformer',forward_t.params,16)
    req(60_000_000<=forward_t_count<=70_000_000,'CASE C Transformer upper-region shape instantiates and forwards without huge training')
    cases['C']={'reachable_max_parameter_count':te['reachable_max_parameter_count'],'forward_parameter_count':forward_t_count}

    # CASE D — above new hard legal parameter ceiling fails closed even if constructed directly.
    td=direct_spec('transformer','case_d',sequence_length=512,d_model=824,num_layers=6,attention_heads=8,ffn_mult=6)
    tdc=candidate_capacity_contract(td,tcfg)
    req((not tdc['passed']) and tdc['rejecting_authority']=='LEGAL' and tdc['actual_parameter_count']>tdc['legal_ceiling'],'CASE D Transformer above new legal ceiling fails closed')
    cases['D']={'actual_parameter_count':tdc['actual_parameter_count'],'legal_ceiling':tdc['legal_ceiling']}

    # CASE E — multiple materially distinct upper-capacity Transformer shapes exist.
    tshapes=[
        spec_for(tcfg,'transformer','shape_32m',sequence_length=16,d_model=576,num_layers=6,attention_heads=8,ffn_mult=6),
        spec_for(tcfg,'transformer','shape_48m',sequence_length=16,d_model=704,num_layers=6,attention_heads=8,ffn_mult=6),
        spec_for(tcfg,'transformer','shape_64m',sequence_length=16,d_model=816,num_layers=6,attention_heads=8,ffn_mult=6),
    ]
    tcounts=[estimate_candidate_parameter_count(x) for x in tshapes]
    req(len({architecture_capacity_fingerprint(x) for x in tshapes})==3 and tcounts[0]>OLD_TRANSFORMER_REACHABLE and tcounts[2]>60_000_000,'CASE E Transformer upper region has multiple material architecture fingerprints')
    cases['E']={'parameter_counts':tcounts,'fingerprints':[architecture_capacity_fingerprint(x) for x in tshapes]}

    # CASE F — old TFT boundary remains valid.
    tf=spec_for(fcfg,'tft','case_f',sequence_length=32,d_model=256,num_layers=4,attention_heads=8,ffn_mult=4,tft_lstm_layers=3)
    tfc=candidate_capacity_contract(tf,fcfg);tfcount=estimate_candidate_parameter_count(tf)
    req(tfcount==OLD_TFT_REACHABLE and tfc['passed'],'CASE F old TFT boundary remains valid')
    cases['F']={'parameter_count':tfcount,'passed':tfc['passed']}

    # CASE G/H — TFT new region and target headroom.
    tg=spec_for(fcfg,'tft','case_g',sequence_length=32,d_model=320,num_layers=4,attention_heads=8,ffn_mult=4,tft_lstm_layers=3)
    tgc=candidate_capacity_contract(tg,fcfg);tgcount=estimate_candidate_parameter_count(tg)
    req(tgcount>OLD_TFT_REACHABLE and tgc['passed'],'CASE G TFT new legal region is executable/admitted')
    req(14_000_000<=fe['reachable_max_parameter_count']<=18_000_000,'CASE H TFT reachable maximum is in 14M-18M target region')
    forward_f=direct_spec('tft','tft_forward_target',sequence_length=32,d_model=480,num_layers=4,attention_heads=8,ffn_mult=4,tft_lstm_layers=3)
    forward_f_count=forward_proof('tft',forward_f.params,32)
    req(14_000_000<=forward_f_count<=18_000_000,'CASE H TFT target shape instantiates and forwards without huge training')
    cases['G']={'parameter_count':tgcount,'effective_ceiling':tgc['effective_ceiling']}
    cases['H']={'reachable_max_parameter_count':fe['reachable_max_parameter_count'],'forward_parameter_count':forward_f_count}

    # CASE I — above new TFT legal architecture/count fails closed.
    ti=direct_spec('tft','case_i',sequence_length=32,d_model=488,num_layers=4,attention_heads=8,ffn_mult=4,tft_lstm_layers=3)
    tic=candidate_capacity_contract(ti,fcfg)
    req((not tic['passed']) and tic['rejecting_authority']=='LEGAL' and tic['actual_parameter_count']>tic['legal_ceiling'],'CASE I TFT above new legal ceiling fails closed')
    cases['I']={'actual_parameter_count':tic['actual_parameter_count'],'legal_ceiling':tic['legal_ceiling']}

    # CASE J/K/L — exact min(LEGAL, RESOURCE, SCIENTIFIC) dominance remains unchanged.
    probe=spec_for(tcfg,'transformer','three_ceiling_probe',sequence_length=16,d_model=576,num_layers=6,attention_heads=8,ffn_mult=6)
    def sci(v):
        return {'available':True,'scientific_parameter_ceiling':int(v),'preferred_parameter_range':[1,max(1,int(v)//2)],'training_memory_months':72,'sequence_length':16,'minimum_temporal_train_rows':1,'effective_sample_estimate':1,'authority':'TEST_FIXTURE'}
    def res(v):
        return {'available':True,'resource_parameter_ceiling':int(v),'authority':'TEST_FIXTURE','binding_gates':[]}
    with patch.object(models_module,'candidate_resource_parameter_ceiling',side_effect=lambda *a,**k:res(40_000_000)), patch.object(models_module,'candidate_scientific_capacity',side_effect=lambda *a,**k:sci(8_000_000)):
        cj=candidate_capacity_contract(probe,tcfg)
    req(cj['effective_ceiling']==8_000_000 and (not cj['passed']) and cj['rejecting_authority']=='SCIENTIFIC','CASE J scientific 8M dominates legal ~64M/resource 40M')
    probe_k=spec_for(tcfg,'transformer','resource_probe',sequence_length=16,d_model=384,num_layers=6,attention_heads=8,ffn_mult=6)
    with patch.object(models_module,'candidate_resource_parameter_ceiling',side_effect=lambda *a,**k:res(10_000_000)), patch.object(models_module,'candidate_scientific_capacity',side_effect=lambda *a,**k:sci(30_000_000)):
        ck=candidate_capacity_contract(probe_k,tcfg)
    req(ck['effective_ceiling']==10_000_000 and (not ck['passed']) and ck['rejecting_authority']=='RESOURCE','CASE K resource 10M dominates legal ~64M/scientific 30M')
    probe_l=spec_for(tcfg,'transformer','legal_probe',sequence_length=16,d_model=128,num_layers=2,attention_heads=8,ffn_mult=2)
    with patch.object(models_module,'candidate_resource_parameter_ceiling',side_effect=lambda *a,**k:res(100_000_000)), patch.object(models_module,'candidate_scientific_capacity',side_effect=lambda *a,**k:sci(100_000_000)):
        cl=candidate_capacity_contract(probe_l,tcfg)
    req(cl['effective_ceiling']==te['legal_parameter_ceiling'] and cl['passed'],'CASE L new legal ceiling dominates only when resource/scientific are higher')
    cases['J']={'effective_ceiling':cj['effective_ceiling'],'rejecting_authority':cj['rejecting_authority']}
    cases['K']={'effective_ceiling':ck['effective_ceiling'],'rejecting_authority':ck['rejecting_authority']}
    cases['L']={'effective_ceiling':cl['effective_ceiling'],'legal_ceiling':cl['legal_ceiling']}

    # CASE M — MANUAL exact values in the new legal region survive unchanged.
    manual_t=direct_spec('transformer','manual_t',sequence_length=16,d_model=576,num_layers=6,attention_heads=8,ffn_mult=6,training_memory_months=72)
    manual_f=direct_spec('tft','manual_f',sequence_length=32,d_model=320,num_layers=4,attention_heads=8,ffn_mult=4,tft_lstm_layers=3,training_memory_months=72)
    mt,mtc=manual_exact_accept('transformer',manual_t.params,strong)
    mf,mfc=manual_exact_accept('tft',manual_f.params,strong)
    req(mt['params']==manual_t.params and mtc['passed'] and mtc['actual_parameter_count']>OLD_TRANSFORMER_REACHABLE,'CASE M Manual exact Transformer above old ceiling accepted without coercion')
    req(mf['params']==manual_f.params and mfc['passed'] and mfc['actual_parameter_count']>OLD_TFT_REACHABLE,'CASE M Manual exact TFT above old ceiling accepted without coercion')
    cases['M']={'transformer_parameter_count':mtc['actual_parameter_count'],'tft_parameter_count':mfc['actual_parameter_count']}

    # CASE N — Scientist shares deterministic new legal authority and cannot bypass effective ceiling.
    sci_t=spec_for(tcfg,'transformer','scientist_t',sequence_length=16,d_model=576,num_layers=6,attention_heads=8,ffn_mult=6)
    accepted,ae=strict_scientist_candidate_admission({'family':'transformer','name':'scientist_new_region','params':deepcopy(sci_t.params)},tcfg)
    req(accepted is not None and accepted.params==sci_t.params,'CASE N Scientist candidate above old legal region accepted exactly when inside effective ceiling')
    constrained,_,_,_=planned_cfg('transformer',rows=4_000,years=5,hardware=strong,max_minutes=100_000)
    sci_bad=spec_for(constrained,'transformer','scientist_bad',sequence_length=16,d_model=576,num_layers=6,attention_heads=8,ffn_mult=6)
    rejected,re=strict_scientist_candidate_admission({'family':'transformer','name':'scientist_over_effective','params':deepcopy(sci_bad.params)},constrained)
    req(rejected is None and re['rejection_reason']=='CANDIDATE_CAPACITY_CONTRACT_REJECTED' and (re.get('capacity') or {}).get('rejecting_authority') in {'SCIENTIFIC','RESOURCE'},'CASE N Scientist above effective ceiling remains fail-closed')
    cases['N']={'accepted_parameter_count':estimate_candidate_parameter_count(accepted),'rejected_authority':(re.get('capacity') or {}).get('rejecting_authority')}

    # CASE O — AUTO can reach new region only when effective capacity permits it.
    auto_hi_contracts=[]
    keys=list(effective_bounds(tcfg,'transformer'))
    for i in range(16):
        # Deterministic upper-stratum batch. Candidate-specific diversity/backoff is
        # preserved rather than forcing every Large draw to the same extreme shape.
        high_u={k:0.82+0.17*((i*7+j*3)%17)/16 for j,k in enumerate(keys)}
        cand=random_candidate(tcfg,'transformer',random.Random(91+i),f'auto_huge_{i}',high_u)
        auto_hi_contracts.append(candidate_capacity_contract(cand,tcfg))
    req(all(x['passed'] for x in auto_hi_contracts) and max(x['actual_parameter_count'] for x in auto_hi_contracts)>OLD_TRANSFORMER_REACHABLE,'CASE O huge-resource/data AUTO can reach materially above old Transformer ceiling')
    ordinary,_,_,_=planned_cfg('transformer',rows=70_000,years=10,hardware=profile(ram=32,available=24,cuda=False,vram=0,vram_free=0,cores=12),priority=1.0,max_minutes=120)
    ordinary_u={k:0.98 for k in effective_bounds(ordinary,'transformer')}
    auto_lo=random_candidate(ordinary,'transformer',random.Random(91),'auto_ordinary',ordinary_u)
    auto_lo_c=candidate_capacity_contract(auto_lo,ordinary)
    req(auto_lo_c['passed'] and auto_lo_c['effective_ceiling']<OLD_TRANSFORMER_REACHABLE and auto_lo_c['actual_parameter_count']<OLD_TRANSFORMER_REACHABLE,'CASE O ordinary AUTO does not scale merely because legal maximum increased')
    cases['O']={'huge_max_actual':max(x['actual_parameter_count'] for x in auto_hi_contracts),'huge_min_effective':min(x['effective_ceiling'] for x in auto_hi_contracts),'ordinary_actual':auto_lo_c['actual_parameter_count'],'ordinary_effective':auto_lo_c['effective_ceiling']}

    # CASE P — all non-target temporal families preserve exact registry bounds and maxima.
    registry=json.loads((ROOT/'config/models/model_registry.json').read_text(encoding='utf-8'))['families']
    other=list(OTHER_REACHABLE)
    blob={f:registry[f]['search'] for f in other}
    bounds_hash=hashlib.sha256(json.dumps(blob,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    req(bounds_hash==OTHER_FAMILY_REGISTRY_HASH,'CASE P other-family legal architecture bounds are byte-semantically unchanged')
    reachable={f:actual_registry_max(f) for f in other}
    req(reachable==OTHER_REACHABLE,'CASE P other-family actual reachable maxima are unchanged')
    hard={f:models_module._LEGAL_TEMPORAL_PARAMETER_CEILING_V1[f] for f in other}
    req(hard==OTHER_HARD_LEGAL,'CASE P other-family hard parameter ceilings are unchanged')
    cases['P']={'registry_bounds_sha256':bounds_hash,'reachable_max_parameter_count':reachable,'hard_legal_ceiling':hard}

    # Architecture/training implementation was not modified to manufacture the headroom.
    protected={
        'ModelLab/research/temporal_research.py':'c7582b745235d0d34255a8095752ea4280e031079619352f871f67a7c4c5935b',
        'ModelLab/models/capacity_governor.py':'9b1554a7485d570e94b9e6137f3d957b33c3b606a05e719be55d0e7b4d10ada1',
        'ModelLab/host/resource_preflight.py':'d9bbb3954ceb53c36384d8a8366b7e6c2ab1572f8e9e15c1616abcf44d540745',
        'ModelLab/research/research_architect.py':'0804e2bbc591d4178e059d1d3d39865b293f25cd8cec5dfc35440bac24b4317e',
    }
    for rel,sha in protected.items():
        req(hashlib.sha256((PKG/rel).read_bytes()).hexdigest()==sha,f'protected methodology unchanged: {rel}')

    evidence={
        'schema':'MAX_V201_TRANSFORMER_TFT_LEGAL_CAPACITY_HEADROOM_ACCEPTANCE_V1',
        'project':'Max MTF','version':'2.0.1','status':'PASS',
        'authority':'ACTUAL_EXECUTABLE_MODEL_PARAMETER_COUNT_PLUS_THREE_CEILING_FAIL_CLOSED',
        'families':{'transformer':te,'tft':fe},
        'cases':cases,
        'protected_methodology_sha256':protected,
        'other_family_registry_bounds_sha256':bounds_hash,
        'note':'Legal architecture headroom only. Recommended starting envelopes, resource/scientific ceilings, cumulative family evidence and training methodology are unchanged.',
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print('V201_TRANSFORMER_TFT_LEGAL_CAPACITY_HEADROOM PASS')


if __name__=='__main__':
    main()
