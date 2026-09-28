from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
from models.model_registry import dynamic_hybrid_families, family_spec, hybrid_parts, get_bounds
from research.research_architect import capability_catalog, compile_research_plan, recommended_parameter_envelopes

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def req(cond,msg):
    if not cond: raise AssertionError(msg)

def fake_profile(cuda=True,vram=8.0):
    return {
        'profile_hash':'FAKE_RTX2060S' if cuda else 'FAKE_CPU',
        'cpu':{'name':'test cpu','physical_cores':8,'logical_threads':16},
        'memory':{'total_gib':32.0,'available_gib':24.0},
        'nvidia':{'detected':cuda,'devices':[{'name':'NVIDIA GeForce RTX 2060 SUPER','memory_total_gib':vram,'memory_free_gib':vram-1}] if cuda else []},
        'torch':{'installed':True,'cuda_available':cuda},
    }

def main():
    reg_names={'lightgbm','xgboost','gru','lstm','tcn','transformer'}
    for f in reg_names:
        req(family_spec(f) is not None,f'{f} missing from registry')
    dyn=set(dynamic_hybrid_families())
    req('hybrid::tcn::lightgbm' in dyn,'TCN→LightGBM dynamic composition missing')
    req('hybrid::transformer::xgboost' in dyn,'Transformer→XGBoost dynamic composition missing')
    req(hybrid_parts('hybrid::lstm::xgboost')==('lstm','xgboost'),'dynamic hybrid parser wrong')
    req(get_bounds()['hybrid::tcn::lightgbm'],'dynamic hybrid bounds empty')

    legacy_cfg=deepcopy(CFG)
    legacy_cfg.setdefault('research_architecture',{})['family_selection_mode']='AUTO'
    legacy_cfg['research_architecture']['topology_selection_mode']='OWNER_FIXED'
    gpu=fake_profile(True,8.0); caps=capability_catalog(gpu,legacy_cfg); env=recommended_parameter_envelopes(gpu)
    req((caps['families']['tcn']['feasible'] and caps['families']['transformer']['feasible']),'RTX-capable temporal families should be feasible when torch exists')
    req(env['transformer']['d_model'][1]>=128,'RTX envelope failed to expand Transformer capacity')
    strategy={
      'active_families':['lightgbm','xgboost','tcn','gru','lstm','transformer'],
      'hybrid_compositions':[{'temporal':'tcn','policy':'lightgbm'},{'temporal':'transformer','policy':'xgboost'}],
      'focus':'hardware-adaptive diversity',
    }
    plan=compile_research_plan(strategy,gpu,legacy_cfg); active=set(plan['active_families'])
    req('hybrid::tcn::lightgbm' in active and 'hybrid::transformer::xgboost' in active,'Scientist hybrid plan not compiled')
    req({'tcn','gru','lstm','transformer'}.issubset(active),'Scientist temporal portfolio constrained unexpectedly')
    req(any(f in active for f in ('lightgbm','xgboost')),'cheap baseline disappeared')
    req(plan['selection_source']=='SCIENTIST','Scientist plan source not preserved')

    cpu=fake_profile(False,0.0); fallback=compile_research_plan({},cpu,legacy_cfg)
    req(fallback['active_families'],'CPU deterministic fallback produced empty research universe')
    req(fallback['selection_source']=='DETERMINISTIC_FALLBACK','fallback provenance wrong')
    print('HARDWARE_ADAPTIVE_RESEARCH_SELFTEST PASS')
    return 0

if __name__=='__main__': raise SystemExit(main())
