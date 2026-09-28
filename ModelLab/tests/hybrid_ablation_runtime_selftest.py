from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
from models.models import CandidateSpec
from research.scientific_hypotheses import validate_hypothesis
from research.experiment_blocks import compile_experiment_block, evaluate_block
from research.research_planner import plan_next_candidates
from models.model_registry import is_hybrid_family

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'config/config.json').read_text())
cfg['agent']['research_plan']={'active_families':['patchtst','lightgbm','hybrid::patchtst::lightgbm']}
cfg.setdefault('research_architecture',{})['hybrid_priority']=0.50
h=validate_hypothesis({'kind':'HYBRID_ABLATION','title':'PatchTST policy-head ablation','rationale':'test whether tree decision head adds robust edge','expected_observation':'hybrid improves lower-tail evidence','payload':{'families':['hybrid::patchtst::lightgbm']}},cfg)
assert h and h['executable'] and h['payload']['pairs'][0]['single']=='patchtst'
block=compile_experiment_block(h,None,cfg,generation=1,block_no=1,budget=6)
assert block['mode']=='HYBRID_ABLATION' and block['status']=='ACTIVE'
specs,plan=plan_next_candidates([],{},cfg,1,6,{},experiment_block=block)
assert len(specs)==6
assert sum(is_hybrid_family(x.family) for x in specs)==3
assert sum(not is_hybrid_family(x.family) for x in specs)==3
assert plan['decision_contract']=='FINAL_[PSELL,PSKIP,PBUY]_SAME_AUTHORITY'
# At least one ablation group must have both arms and matching temporal sequence length.
groups={}
for x in specs:
    parts=x.name.split('_g')
    if len(parts)>1:
        gid=parts[1].split('_')[0]
        groups.setdefault(gid,[]).append(x)
matched=False
for xs in groups.values():
    single=next((x for x in xs if not is_hybrid_family(x.family)),None)
    hybrid=next((x for x in xs if is_hybrid_family(x.family)),None)
    if single and hybrid:
        assert int(single.params['sequence_length'])==int(hybrid.params['temporal_sequence_length'])
        matched=True; break
assert matched
rows=[]
for i,x in enumerate(specs):
    rows.append({'experiment_block_id':block['block_id'],'family':x.family,'selection_score':float(i),'cv_gate_pass':i%2==0,'failure_margins':{}})
out=evaluate_block(block,rows,cfg)
assert out['ablation_arms']['SINGLE']['n']==3 and out['ablation_arms']['HYBRID']['n']==3
assert out['paired_contract']=='SAME_FINAL_SELL_SKIP_BUY_AUTHORITY'
assert out['ablation_decision_rule']=='HYBRID_PASS_RATE_GT_SINGLE_PASS_RATE'
# A block cannot claim support merely because *some* arm passed; hybrid must improve
# gate-survival rate over its temporal-only control.
rows_falsified=[]
for i,x in enumerate(specs):
    rows_falsified.append({'experiment_block_id':block['block_id'],'family':x.family,'selection_score':float(i),'cv_gate_pass':not is_hybrid_family(x.family),'failure_margins':{}})
out_f=evaluate_block(block,rows_falsified,cfg)
assert out_f['proxy_status']=='FALSIFIED' and out_f['status']=='FALSIFIED'
rows_supported=[]
for i,x in enumerate(specs):
    rows_supported.append({'experiment_block_id':block['block_id'],'family':x.family,'selection_score':float(i),'cv_gate_pass':is_hybrid_family(x.family),'failure_margins':{}})
out_s=evaluate_block(block,rows_supported,cfg)
assert out_s['proxy_status']=='SUPPORTED' and out_s['status']=='SUPPORTED'

cfg2=deepcopy(cfg); cfg2['research_architecture']['hybrid_priority']=1.0
block2=compile_experiment_block(h,None,cfg2,generation=1,block_no=1,budget=6)
assert block2['mode']=='HYPOTHESIS_DEFERRED' and 'OWNER_TOPOLOGY' in block2['deferred_reason']
print('HYBRID_ABLATION_RUNTIME_SELFTEST PASS')
