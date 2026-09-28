from pathlib import Path
from models.model_lab import load_cfg
from research.scientific_hypotheses import strict_scientist_hypothesis_admission
from core.contract import FEATURES
from models.model_registry import get_bounds, hybrid_parts, effective_bounds

ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)

def main():
    cfg=load_cfg(ROOT/'config/config.json')
    cfg.setdefault('agent',{}).setdefault('research_plan',{})['parameter_envelopes']={'transformer_moe':{'d_model':[32,80]}}

    bad={'kind':'MODEL_ARCHITECTURE','title':'illegal width','payload':{'parameter_ranges_by_family':{'transformer_moe':{'d_model':[120,160]}}}}
    h,e=strict_scientist_hypothesis_admission(bad,cfg,1)
    req(h is None and e['admission_status']=='REJECTED','wholly out-of-bound hypothesis was admitted')
    req(e['requested_payload']['parameter_ranges_by_family']['transformer_moe']['d_model']==[120,160],'requested hypothesis overwritten')
    req('OUTSIDE_EFFECTIVE_PARAMETER_BOUNDS' in e['rejection_reason'],'wrong OOB rejection')

    partial={'kind':'MODEL_ARCHITECTURE','title':'partial width','payload':{'parameter_ranges_by_family':{'transformer_moe':{'d_model':[64,128]}}}}
    h2,e2=strict_scientist_hypothesis_admission(partial,cfg,2)
    req(h2 is None and e2['admission_status']=='REJECTED','partial range was silently intersected')

    good={'kind':'MODEL_ARCHITECTURE','title':'legal width','payload':{'parameter_ranges_by_family':{'transformer_moe':{'d_model':[64,80]}}}}
    h3,e3=strict_scientist_hypothesis_admission(good,cfg,3)
    req(h3 is not None and h3['payload']['parameter_ranges_by_family']['transformer_moe']['d_model']==[64,80],'legal hypothesis changed')
    req(e3['admission_status']=='ACCEPTED' and e3['exact_hypothesis'] is True,'legal hypothesis provenance not exact')

    h4,e4=strict_scientist_hypothesis_admission({'kind':'TRAINING_MEMORY','payload':{'months':[12,100]}},cfg,4)
    req(h4 is None and e4['admission_status']=='REJECTED','training-memory hypothesis silently clamped')
    h5,e5=strict_scientist_hypothesis_admission({'kind':'SELECTIVITY_POLICY','payload':{'take_thresholds':[0.60,0.99]}},cfg,5)
    req(h5 is None and e5['admission_status']=='REJECTED','selectivity hypothesis silently clamped')

    # Cardinality must fail closed before the legacy deterministic compiler can
    # truncate an LLM hypothesis and falsely mark the result exact.
    overflow_cases=[
        ({'kind':'FEATURE_ABLATION','payload':{'zero_features':list(FEATURES[:9])}},'FEATURE_ABLATION.zero_features',9,8),
        ({'kind':'TRAINING_MEMORY','payload':{'months':[6,12,18,24,30,36,42,48,54]}},'TRAINING_MEMORY.windows',9,8),
        ({'kind':'SELECTIVITY_POLICY','payload':{'take_thresholds':[round(0.40+i*0.01,2) for i in range(13)]}},'SELECTIVITY_POLICY.take_thresholds',13,12),
    ]
    moe_keys=[k for k in effective_bounds(cfg,'transformer_moe') if k!='training_memory_months'][:13]
    req(len(moe_keys)==13,'fixture requires >=13 legal Transformer MoE variable keys')
    overflow_cases.append((
        {'kind':'MODEL_ARCHITECTURE','payload':{'variable_keys_by_family':{'transformer_moe':moe_keys}}},
        'MODEL_ARCHITECTURE.variable_keys:transformer_moe',13,12
    ))
    hybrids=[f for f in get_bounds() if hybrid_parts(f)][:9]
    req(len(hybrids)==9,'fixture requires >=9 legal hybrid families')
    overflow_cases.append(({'kind':'HYBRID_ABLATION','payload':{'families':hybrids}},'HYBRID_ABLATION.families',9,8))
    seed_families=list(get_bounds())[:9]
    req(len(seed_families)==9,'fixture requires >=9 legal seed-stability families')
    overflow_cases.append(({'kind':'SEED_STABILITY','payload':{'families':seed_families}},'SEED_STABILITY.families',9,8))

    for serial,(raw_card,field,count,limit) in enumerate(overflow_cases,10):
        hc,ec=strict_scientist_hypothesis_admission(raw_card,cfg,serial)
        req(hc is None and ec['admission_status']=='REJECTED',f'{field} overflow was admitted')
        req(ec['exact_hypothesis'] is False,f'{field} overflow falsely marked exact')
        req(ec['requested_payload']==raw_card['payload'],f'{field} requested payload was mutated')
        reason=str(ec.get('rejection_reason') or '')
        req(reason.startswith('HYPOTHESIS_CARDINALITY_EXCEEDS_EXECUTABLE_CONTRACT:'),f'{field} wrong cardinality rejection: {reason}')
        req(field in reason and f'requested={count}' in reason and f'max={limit}' in reason,f'{field} cardinality provenance incomplete')

    # Boundary cardinalities remain executable and exact.
    hb,eb=strict_scientist_hypothesis_admission(
        {'kind':'FEATURE_ABLATION','payload':{'zero_features':list(FEATURES[:8])}},cfg,30
    )
    req(hb is not None and len(hb['payload']['zero_features'])==8,'legal feature-ablation boundary rejected')
    req(eb['admission_status']=='ACCEPTED' and eb['exact_hypothesis'] is True,'legal cardinality boundary not exact')

    sci=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
    req(sci.count('strict_scientist_hypothesis_admission')>=3,'Scientist/Director do not use strict hypothesis admission')
    req('hypothesis_admission' in sci,'Scientist hypothesis provenance not surfaced')
    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    req('hypothesis_admission' in sup,'Supervisor journal drops hypothesis admission provenance')
    print('V201_SCIENTIST_HYPOTHESIS_ADMISSION PASS')

if __name__=='__main__': main()
