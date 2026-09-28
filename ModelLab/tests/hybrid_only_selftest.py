from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path

from models.model_registry import enabled_families
from models.models import generate_initial_population
from research.research_planner import adaptive_family_weights, plan_next_candidates

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def main():
    cfg=deepcopy(CFG)
    m=cfg.setdefault('models',{})
    m['xgboost']=False; m['lightgbm']=False; m['random_forest']=False; m['gru']=False
    m['hybrid_xgboost']=True; m['hybrid_lightgbm']=True; m['hybrid_random_forest']=True
    fams=enabled_families(cfg)
    req(set(fams)=={'hybrid_gru_xgboost','hybrid_gru_lightgbm','hybrid_gru_random_forest'},'hybrid-only config resolves exactly three enabled hybrid families')

    initial=generate_initial_population(cfg,count=6,round_no=1)
    req(len(initial)==6 and all(s.family.startswith('hybrid_gru_') for s in initial),'hybrid-only round 1 generates hybrid candidates without standalone GRU')

    board=[]
    specs={}
    # Mimic a completed positive first round without any standalone GRU evidence.
    for i,s in enumerate(initial[:3],1):
        specs[s.name]=s
        board.append({
            'family':s.family,'name':s.name,'selection_score':70.0-i,
            'cv_gate_pass':True,'median_profit_factor':2.0+i*0.2,
            'median_expectancy_r':0.25,'median_recovery_factor':2.5,
            'positive_fold_ratio':1.0,'expectancy_std_r':0.08,'total_fit_seconds':1.0,
        })
    weights=adaptive_family_weights(board,cfg)
    req(weights and set(weights)==set(fams),'hybrid-only planner keeps all enabled hybrid families eligible after round 1')
    req(abs(sum(weights.values())-1.0)<1e-9,'hybrid-only family weights remain normalized')

    planned,meta=plan_next_candidates(board,specs,cfg,round_no=2,n=6,llm_strategy={
        'family_priorities':{'hybrid_gru_xgboost':3.0,'hybrid_gru_lightgbm':2.0,'hybrid_gru_random_forest':1.0},
        'exploration_ratio':0.35,
    })
    req(len(planned)==6,'hybrid-only round 2 preserves requested research budget')
    req(all(s.family.startswith('hybrid_gru_') for s in planned),'hybrid-only round 2 never requires fallback non-hybrid family')
    req(meta.get('hybrid_only_mode') is True and meta.get('hybrid_stage_unlocked') is True,'planner records hybrid-only first-class mode')
    req(meta.get('hybrid_candidates')==6,'hybrid-only mode does not starve candidates via hybrid cap')
    print('\nHYBRID-ONLY RESEARCH SELF-TEST PASS')


if __name__=='__main__':
    main()
