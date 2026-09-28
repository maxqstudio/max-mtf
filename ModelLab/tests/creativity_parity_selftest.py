from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
from research.creativity_governor import adaptive_creativity_profile, apply_llm_priority_influence, llm_research_influence

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'config/config.json').read_text())
low=deepcopy(cfg); high=deepcopy(cfg)
low['agent']['search']['scientific_creativity']=0.10
high['agent']['search']['scientific_creativity']=0.90
pl=adaptive_creativity_profile(low)
ph=adaptive_creativity_profile(high)
assert ph['architecture_breadth'] > pl['architecture_breadth']
assert ph['family_exploration'] > pl['family_exploration']
assert ph['target_exploration_ratio'] > pl['target_exploration_ratio']
assert ph['phase_temperatures']['DISCOVERY_HYPOTHESIS'] > pl['phase_temperatures']['DISCOVERY_HYPOTHESIS']
assert ph['phase_temperatures']['STAGE_FORENSIC'] == pl['phase_temperatures']['STAGE_FORENSIC'] == 0.05

seed_topo={'first_failed_gate_counts':{'CPCV_SEED_STABILITY':1},'candidate_rows':[{'family':'patchtst','seed_confirmation':{'required':True,'passed':False,'planned_seeds':[42,11,77],'seed_results':[{'seed':42,'passed':True},{'seed':11,'passed':False}]}}]}
ps=adaptive_creativity_profile(high,failure_topology=seed_topo,stale_rounds=2)
assert ps['mode']=='STABILITY_REPAIR' and ps['seed_instability_detected'] is True
assert 'CPCV_SEED_SET' in ps['immutable_authority'] and 'PASS_FAIL' in ps['immutable_authority']

before=(deepcopy(high['acceptance']),deepcopy(high['split']),deepcopy(high['champion_factory']['cpcv_stage']['seed_confirmation']))
_ = adaptive_creativity_profile(high,failure_topology=seed_topo,stale_rounds=4)
after=(high['acceptance'],high['split'],high['champion_factory']['cpcv_stage']['seed_confirmation'])
assert before==after

assert abs(apply_llm_priority_influence(3.0,0.0)-1.0)<1e-12
assert abs(apply_llm_priority_influence(3.0,1.0)-3.0)<1e-12
high['agent']['search']['llm_research_influence']=0.0
assert llm_research_influence(high)==0.0
print('CREATIVITY_PARITY_SELFTEST PASS')
