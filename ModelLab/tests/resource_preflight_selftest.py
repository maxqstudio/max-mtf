from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path

from research.research_architect import compile_research_plan
from models.models import CandidateSpec, candidate_capacity_contract, random_candidate

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)


def profile(cuda=True,ram=32.0,ram_free=24.0,vram=8.0,vram_free=7.0):
    return {
        'profile_hash':f'R14_RESOURCE_{cuda}_{ram}_{vram}',
        'cpu':{'physical_cores':8,'logical_threads':16},
        'memory':{'total_gib':ram,'available_gib':ram_free},
        'nvidia':{'devices':[{'name':'RTX','memory_total_gib':vram,'memory_free_gib':vram_free}] if cuda else []},
        'torch':{'cuda_available':cuda},
    }


def capacity():
    return {
        'dataset':{'rows_per_month':1000.0},
        'wfa':{'median_train_rows':10000,'fold_count':3},
        'reference_scenario':{
            'preferred_total_params':[100000,400000],
            'extended_total_params':[80000,800000],
            'estimated_train_rows':10000,'sequence_length':128,'training_memory_months':18,
        },
    }


def main():
    # Normal safe candidate: resource evidence exists and passes frozen Owner budgets.
    cfg=deepcopy(BASE)
    plan=compile_research_plan({'active_families':['gru','lightgbm']},profile(),cfg,capacity())
    cfg.setdefault('agent',{})['research_plan']=plan
    c=random_candidate(cfg,'gru',__import__('random').Random(77),'normal_gru')
    cc=candidate_capacity_contract(c,cfg)
    req(cc['passed'] and cc['resource_estimate'].get('available'),'normal candidate passes executable resource preflight')
    req(cc['resource_limits'].get('ram_gib') is not None and cc['resource_limits'].get('vram_gib') is not None,'frozen RAM and VRAM limits are explicit evidence')
    req(cc['resource_estimate'].get('estimated_wfa_minutes') is not None,'candidate evidence contains estimated WFA runtime')

    # Isolate resource gates from the statistical parameter-count gate.
    plan['capacity_guidance']['preferred_total_params']=[1,999_999_999]
    plan['capacity_guidance']['extended_total_params']=[1,999_999_999]
    huge=CandidateSpec('transformer','huge_attention',{
        'sequence_length':512,'d_model':512,'num_layers':6,'attention_heads':8,'ffn_mult':6,
        'dropout':0.1,'learning_rate':0.001,'batch_size':512,'epochs':150,
        'weight_decay':0.001,'training_memory_months':12,
    })
    hc=candidate_capacity_contract(huge,cfg)
    req(not hc['passed'] and 'ESTIMATED_PEAK_VRAM_EXCEEDS_OWNER_BUDGET' in hc['failed_gates'],'oversized attention candidate fails VRAM before training')
    req('ESTIMATED_WFA_RUNTIME_EXCEEDS_OWNER_BUDGET' in hc['failed_gates'],'oversized attention candidate also fails Owner runtime budget')

    # RAM budget is a real hard gate for tree candidates too, not neural-only authority.
    low=deepcopy(BASE)
    low['research_architecture']['safe_ram_fraction']=0.75
    lowplan=compile_research_plan({'active_families':['xgboost']},profile(False,8.0,1.0,0.0,0.0),low,capacity())
    lowplan['capacity_guidance']['preferred_total_params']=[1,999_999_999]
    lowplan['capacity_guidance']['extended_total_params']=[1,999_999_999]
    low.setdefault('agent',{})['research_plan']=lowplan
    tree=CandidateSpec('xgboost','ram_pressure',{
        'n_estimators':5000,'max_depth':16,'learning_rate':0.01,'min_child_weight':0.1,
        'subsample':1.0,'colsample_bytree':1.0,'reg_alpha':0.0,'reg_lambda':1.0,
        'training_memory_months':12,
    })
    tc=candidate_capacity_contract(tree,low)
    req(not tc['passed'] and tc['first_failed_gate']=='ESTIMATED_PEAK_RAM_EXCEEDS_OWNER_BUDGET','tree candidate fails frozen RAM budget before training')

    # Time budget must execute even on CPU where no VRAM gate exists.
    timed=deepcopy(BASE)
    timed['research_architecture']['max_single_experiment_minutes']=1
    tplan=compile_research_plan({'active_families':['gru']},profile(False,32.0,24.0,0.0,0.0),timed,capacity())
    tplan['capacity_guidance']['preferred_total_params']=[1,999_999_999]
    tplan['capacity_guidance']['extended_total_params']=[1,999_999_999]
    timed.setdefault('agent',{})['research_plan']=tplan
    slow=CandidateSpec('gru','cpu_time_pressure',{
        'sequence_length':128,'hidden_size':128,'num_layers':3,'dropout':0.2,
        'learning_rate':0.001,'batch_size':128,'epochs':100,'weight_decay':0.001,
        'training_memory_months':12,
    })
    sc=candidate_capacity_contract(slow,timed)
    req(not sc['passed'] and 'ESTIMATED_WFA_RUNTIME_EXCEEDS_OWNER_BUDGET' in sc['failed_gates'],'CPU candidate fails explicit estimated-time budget')
    req(sc['resource_limits'].get('vram_gib') is None,'CPU plan does not invent a VRAM limit')

    # Legacy run remains backward compatible and does not fabricate resource evidence.
    legacy=deepcopy(BASE)
    legacy.setdefault('agent',{})['research_plan']={'active_families':['gru'],'capacity_guidance':{'preferred_total_params':[1,9999999],'extended_total_params':[1,99999999]}}
    lc=candidate_capacity_contract(CandidateSpec('gru','legacy',{'sequence_length':32,'hidden_size':32,'num_layers':1}),legacy)
    req(lc['resource_estimate'].get('status')=='NOT_APPLICABLE_OR_LEGACY','legacy run remains resource-preflight compatible without fake limits')

    print('RESOURCE_PREFLIGHT_SELFTEST PASS')

if __name__=='__main__': main()
