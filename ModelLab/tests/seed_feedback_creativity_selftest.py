from __future__ import annotations
import json
from pathlib import Path
from research.research_feedback import cpcv_failure_topology
from research.scientific_hypotheses import seed_stability_hypothesis_from_topology
from research.experiment_blocks import compile_experiment_block
from models.models import CandidateSpec

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'config/config.json').read_text())
row={
 'pool_id':'CAND_01','family':'patchtst','name':'p1','passed':False,'first_failed_gate':'CPCV_SEED_STABILITY','reasons':['CPCV_SEED_STABILITY'],
 'params':{},'summary':{},
 'evidence':{'combinations':15,'paths':[],'seed_confirmation':{'required':True,'passed':False,'status':'FAIL','planned_seeds':[42,11,77],'seed_results':[{'seed':42,'passed':True},{'seed':11,'passed':False}]}}
}
topo=cpcv_failure_topology([row],cfg)
cr=topo['candidate_rows'][0]
assert cr['seed_confirmation']['planned_seeds']==[42,11,77]
assert topo['seed_stability']['required_candidates']==1
assert topo['seed_stability']['unstable_fail']==1
assert topo['seed_stability']['failed_seed_counts'].get(11)==1
h=seed_stability_hypothesis_from_topology(topo,cfg)
assert h and h['kind']=='SEED_STABILITY' and h['executable'] is True
assert 'patchtst' in h['payload']['families']
# Compile against an actual family anchor; only stability knobs may vary.
# Use registry-default-compatible params from a validated-like anchor is unnecessary for compilation.
from models.model_registry import get_bounds
params={k:(int((lo+hi)//2) if typ is int else (float(lo)+float(hi))/2) for k,(lo,hi,typ) in get_bounds(['patchtst'])['patchtst'].items()}
anchor=CandidateSpec('patchtst','anchor',params)
block=compile_experiment_block(h,anchor,cfg,generation=2,block_no=1,budget=6)
assert block['mode']=='HYPOTHESIS_DIRECTED'
assert block['kind']=='SEED_STABILITY'
assert any(k in block['variable_keys'] for k in ('dropout','weight_decay','learning_rate','d_model'))
print('SEED_FEEDBACK_CREATIVITY_SELFTEST PASS')
