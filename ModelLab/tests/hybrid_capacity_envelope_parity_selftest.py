from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path

from models.model_registry import dynamic_hybrid_families, family_spec, effective_bounds
from research.research_architect import (
    recommended_parameter_envelopes, hybrid_recommended_parameter_envelope,
    compile_research_plan, apply_strategy_parameter_envelopes,
)

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)


def profile():
    return {
        'profile_hash':'R14_REPAIR_HYBRID_GPU8',
        'cpu':{'physical_cores':8,'logical_threads':16},
        'memory':{'total_gib':32.0,'available_gib':24.0},
        'nvidia':{'devices':[{'name':'RTX','memory_total_gib':8.0,'memory_free_gib':7.0}]},
        'torch':{'cuda_available':True},
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


def same_range(a,b):
    return int(a[0])==int(b[0]) and int(a[1])==int(b[1]) if all(float(x).is_integer() for x in [float(a[0]),float(a[1]),float(b[0]),float(b[1])]) else abs(float(a[0])-float(b[0]))<1e-12 and abs(float(a[1])-float(b[1]))<1e-12


def main():
    rec=recommended_parameter_envelopes(profile(),capacity())
    # Every dynamic hybrid must be built from the same safe component envelopes,
    # never from the wider raw registry search space.
    for fam in dynamic_hybrid_families():
        temporal,policy=fam.split('::')[1:]
        h=hybrid_recommended_parameter_envelope(fam,rec)
        req(bool(h),f'{fam} has composed safe envelope')
        for key,rng in rec[temporal].items():
            if key=='training_memory_months': continue
            hk='temporal_'+key
            if hk in (family_spec(fam).get('search') or {}):
                req(hk in h and same_range(h[hk],rng),f'{fam} temporal {key} equals standalone safe range')
        for key,rng in rec[policy].items():
            if key=='training_memory_months': continue
            hk='policy_'+key
            if hk in (family_spec(fam).get('search') or {}):
                req(hk in h and same_range(h[hk],rng),f'{fam} policy {key} equals standalone safe range')
        tr=rec[temporal].get('training_memory_months'); pr=rec[policy].get('training_memory_months')
        if tr and pr:
            exp=[max(float(tr[0]),float(pr[0])),min(float(tr[1]),float(pr[1]))]
            req('training_memory_months' in h and same_range(h['training_memory_months'],exp),f'{fam} shared training memory is component intersection')

    # Reproduce the concrete defect reported by Control Room.
    cfg=deepcopy(BASE)
    cfg['research_architecture']['family_size_priorities']['patchtst']=0.0
    cfg['research_architecture']['family_size_priorities']['lightgbm']=1.0
    strategy={
        'active_families':['patchtst','lightgbm'],
        'hybrid_compositions':[{'temporal':'patchtst','policy':'lightgbm'}],
        # Deliberately try to widen the hybrid beyond both component recommendations.
        'parameter_envelopes':{'hybrid::patchtst::lightgbm':{
            'temporal_d_model':[1,9999],'temporal_num_layers':[1,99],
            'policy_n_estimators':[1,999999],'policy_num_leaves':[1,999999],
            'training_memory_months':[1,999],
        }},
    }
    plan=compile_research_plan(strategy,profile(),cfg,capacity())
    cfg.setdefault('agent',{})['research_plan']=plan
    sb=effective_bounds(cfg,'patchtst'); pb=effective_bounds(cfg,'lightgbm'); hb=effective_bounds(cfg,'hybrid::patchtst::lightgbm')
    req(hb['temporal_d_model'][:2]==sb['d_model'][:2],'hybrid PatchTST d_model cannot exceed standalone safe+Small envelope')
    req(hb['temporal_num_layers'][:2]==sb['num_layers'][:2],'hybrid PatchTST layers cannot exceed standalone safe+Small envelope')
    req(hb['policy_n_estimators'][:2]==pb['n_estimators'][:2],'hybrid LightGBM estimators equal standalone safe+Large envelope')
    req(hb['policy_num_leaves'][:2]==pb['num_leaves'][:2],'hybrid LightGBM leaves equal standalone safe+Large envelope')
    req(hb['training_memory_months'][1] <= min(sb['training_memory_months'][1],pb['training_memory_months'][1]),'hybrid shared training memory cannot exceed either component')

    # Later Research Director generations may only narrow the frozen safe hybrid envelope.
    widened=apply_strategy_parameter_envelopes(plan,{'parameter_envelopes':{'hybrid::patchtst::lightgbm':{
        'temporal_d_model':[1,9999],'policy_n_estimators':[1,999999]
    }}})
    cfg['agent']['research_plan']=widened
    hb2=effective_bounds(cfg,'hybrid::patchtst::lightgbm')
    req(hb2['temporal_d_model'][:2]==hb['temporal_d_model'][:2],'later Scientist cannot widen temporal component envelope')
    req(hb2['policy_n_estimators'][:2]==hb['policy_n_estimators'][:2],'later Scientist cannot widen policy component envelope')

    print('HYBRID_CAPACITY_ENVELOPE_PARITY_SELFTEST PASS')

if __name__=='__main__': main()
