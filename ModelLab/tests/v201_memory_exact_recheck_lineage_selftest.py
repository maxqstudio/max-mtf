from copy import deepcopy
from pathlib import Path
from models.model_lab import load_cfg
from models.model_registry import effective_bounds
from research.research_memory import seed_candidates_from_memory

ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)

def cfg_with_bound():
    cfg=load_cfg(ROOT/'config/config.json')
    plan=cfg.setdefault('agent',{}).setdefault('research_plan',{})
    plan['active_families']=['random_forest']
    plan['parameter_envelopes']={'random_forest':{'max_depth':[4,8]}}
    return cfg

def main():
    cfg=cfg_with_bound()
    base={}
    for key,(lo,hi,typ) in effective_bounds(cfg,'random_forest').items():
        v=(float(lo)+float(hi))/2.0
        base[key]=int(round(v)) if typ is int else float(v)
    old=deepcopy(base); old['max_depth']=20
    memory={'elites':[{'family':'random_forest','name':'old_elite','params':old}]}
    seeds,ev=seed_candidates_from_memory(memory,cfg,1,return_evidence=True)
    req(seeds==[],'transformed historical elite was mislabeled as recheck')
    req(len(ev)==1 and ev[0]['admission_status']=='REJECTED','rejected elite admission missing')
    req(ev[0]['source_params']['max_depth']==20,'source intent was overwritten')
    req(ev[0]['executable_params']['max_depth']==8,'current executable descendant not recorded')
    req(ev[0]['exact_recheck'] is False,'transformed elite marked exact')
    req(ev[0]['rejection_reason']=='CURRENT_CONTRACT_REQUIRES_TRANSFORMATION','wrong transformation reason')

    exact=deepcopy(base); exact['max_depth']=8
    memory2={'elites':[{'family':'random_forest','name':'exact_elite','params':exact}]}
    seeds2,ev2=seed_candidates_from_memory(memory2,cfg,1,return_evidence=True)
    req(len(seeds2)==1 and seeds2[0].params['max_depth']==8,'exact current-contract elite not rechecked')
    req(ev2[0]['exact_recheck'] is True and ev2[0]['scientific_attribution']=='EXACT_MEMORY_ELITE_RECHECK','exact recheck provenance invalid')

    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    req('memory_recheck_admission' in sup and 'return_evidence=True' in sup,'Supervisor does not journal memory recheck admission')
    print('V201_MEMORY_EXACT_RECHECK_LINEAGE PASS')

if __name__=='__main__': main()
