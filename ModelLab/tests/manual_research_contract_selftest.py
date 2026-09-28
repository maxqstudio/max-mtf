from __future__ import annotations

from pathlib import Path

from models.model_lab import load_cfg
from research.research_control import default_manual_candidate, compile_manual_runtime, provenance, research_mode

ROOT=Path(__file__).resolve().parents[1]


def main():
    cfg=load_cfg(ROOT/'config/config.json')
    cfg.setdefault('champion_factory',{})['research_mode']='MANUAL'
    cfg['champion_factory']['manual_research']={
        'enabled':True,
        'take_threshold':0.67,
        'minimum_wfa_survivors':1,
        'candidates':[default_manual_candidate('lightgbm',1)],
    }
    rt,cands=compile_manual_runtime(cfg)
    assert len(cands)==1
    assert rt['champion_factory']['research_mode']=='MANUAL'
    assert rt['agent']['llm']['enabled'] is False
    assert rt['agent']['manual_research']['llm_used'] is False
    assert rt['agent']['manual_research']['deterministic_discovery_used'] is False
    assert rt['agent']['manual_research']['validation_authority']=='DETERMINISTIC'
    assert rt['agent']['fidelity_ladder']['enabled'] is False
    assert rt['agent']['policy_discovery']['enabled'] is False
    assert rt['agent']['research_plan']['selection_source']=='OWNER_MANUAL_EXACT'
    assert rt['agent']['research_plan']['active_families']==['lightgbm']
    assert rt['deployment']['take_threshold_grid']==[0.67]
    assert rt['agent']['max_experiments']==1 and rt['agent']['max_rounds']==1

    # Dynamic hybrid exact candidates are valid MANUAL inputs too.
    cfg_h=load_cfg(ROOT/'config/config.json')
    cfg_h.setdefault('champion_factory',{})['research_mode']='MANUAL'
    hybrid=default_manual_candidate('hybrid::gru::lightgbm',1)
    cfg_h['champion_factory']['manual_research']={'enabled':True,'take_threshold':0.61,'minimum_wfa_survivors':1,'candidates':[hybrid]}
    rt_h,cands_h=compile_manual_runtime(cfg_h)
    assert cands_h[0]['family']=='hybrid::gru::lightgbm'
    assert rt_h['agent']['research_plan']['active_families']==['hybrid::gru::lightgbm']
    assert any(k.startswith('temporal_') for k in cands_h[0]['params'])
    assert any(k.startswith('policy_') for k in cands_h[0]['params'])

    # MANUAL is exact and fail-closed: a missing required parameter cannot be inferred.
    bad=default_manual_candidate('lightgbm',1)
    bad['params'].pop(next(iter(bad['params'])))
    cfg_bad=load_cfg(ROOT/'config/config.json')
    cfg_bad.setdefault('champion_factory',{})['research_mode']='MANUAL'
    cfg_bad['champion_factory']['manual_research']={'enabled':True,'candidates':[bad]}
    try:
        compile_manual_runtime(cfg_bad)
    except ValueError:
        pass
    else:
        raise AssertionError('MANUAL missing parameter must fail closed')

    # Corrupt/ambiguous mode must fail closed instead of silently entering AUTO.
    try:
        research_mode({'champion_factory':{'research_mode':'AUT0'}})
    except ValueError:
        pass
    else:
        raise AssertionError('invalid research_mode must fail closed')

    p=provenance('MANUAL')
    assert p['proposal_authority']=='OWNER' and p['llm_used'] is False and p['deterministic_discovery_used'] is False

    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    assert 'OWNER_MANUAL_EXACT' in sup
    assert 'if manual_mode:' in sup
    assert 'OWNER_MANUAL_CANDIDATES_COMPLETE' in sup
    champ=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    assert 'MANUAL_WFA_NO_SURVIVOR' in champ
    assert 'deterministic_discovery_used":False if manual_mode else True' in champ
    orch=(ROOT/'factory/factory_orchestrator.py').read_text(encoding='utf-8')
    assert 'def run_manual_factory' in orch
    assert 'llm_api_key=None' in orch
    worker=(ROOT/'factory/factory_worker.py').read_text(encoding='utf-8')
    assert 'action=="MANUAL"' in worker and 'run_manual_factory' in worker
    print('MANUAL RESEARCH CONTRACT PASS')

if __name__=='__main__':
    main()
