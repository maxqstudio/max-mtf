from __future__ import annotations
import json
from pathlib import Path
from scientist.core.scientist import LLMScientist

ROOT=Path(__file__).resolve().parents[1]
cfg=json.loads((ROOT/'config/config.json').read_text())
# Keep a small explicit universe for deterministic prompt assertions.
cfg['agent']['research_plan']={'active_families':['patchtst','lightgbm','hybrid::patchtst::lightgbm']}
llm_cfg={'provider':'custom','base_url':'http://example.invalid/v1','model':'fake','temperature':0.99,'max_proposals_per_round':5}
sc=LLMScientist(llm_cfg)
calls=[]
def fake_call(messages,**kwargs):
    calls.append((messages,kwargs))
    return json.dumps({'summary':'ok','report':{'condition':'ok','interpretation':'bounded','next_action':'test','confidence':0.5},'strategy':{},'proposals':[],'hypotheses':[],'stop_research':False})
sc._call=fake_call
ctx={
 'round':2,'budget_remaining':12,'dataset':{'rows':35000},'top_results':[],'family_stats':{},'fold_forensics':[],
 'research_memory':{},'scientific_agenda':[],'supervisor_plan':{'estimated_compute_allocation':{'hybrid_estimated_share':0.6}},
 'wfa_pass_count':0,'wfa_total_count':3,'first_failed_gate_counts':{'CV_WORST_EXPECTANCY':3},'failure_topology':{'first_failed_gate_counts':{'CV_WORST_EXPECTANCY':3}},
 'factory_context':{'hardware_profile':{'gpu':'RTX'},'dataset_capacity_profile':{'reference_training_rows':10000},'capacity_guidance':{'preferred_total_params':[150000,400000]}},
 'topology_allocation':{'configured_hybrid_priority':0.5,'target_single_candidates':3,'target_hybrid_candidates':3},
 'compute_allocation':{'single_estimated_share':0.4,'hybrid_estimated_share':0.6},
 'seed_policy':{'seeds':[42,11,77],'require_all_pass':True},
}
res=sc.propose(ctx,cfg,max_n=2)
assert res['deterministic_state']=='NO_WFA_SURVIVOR'
msg=json.loads(calls[-1][0][1]['content'])
for k in ('effective_parameter_bounds','factory_context','topology_allocation','compute_allocation','cpcv_seed_policy','creativity_profile'):
    assert k in msg, k
assert calls[-1][1]['phase']=='DISCOVERY_HYPOTHESIS'
assert calls[-1][1]['temperature'] < 0.7

# Stage review must receive full seed evidence and inject a bounded stability hypothesis
# if the LLM forgets to propose one.
topo={'first_failed_gate_counts':{'CPCV_SEED_STABILITY':1},'all_failed_gate_counts':{'CPCV_SEED_STABILITY':1},'candidate_rows':[{'family':'patchtst','seed_confirmation':{'required':True,'passed':False,'planned_seeds':[42,11,77],'seed_results':[{'seed':42,'passed':True},{'seed':11,'passed':False}]}}]}
def fake_stage(messages,**kwargs):
    calls.append((messages,kwargs))
    return json.dumps({'summary':'seed unstable','report':{'condition':'FAIL','interpretation':'initialization sensitive','next_action':'stability repair','confidence':0.7},'scientific_method':{'hypothesis':'seed sensitivity','experiment':'regularize','falsification':'fixed seeds remain unstable'},'strategy':{},'hypotheses':[],'next_discovery_plan':{'objective':'repair seed stability','freeze':['seed set'],'change':['capacity/regularization'],'falsification':'fixed seed set remains unstable','do_not_do':'seed mining'},'stop_research':False})
sc._call=fake_stage
out=sc.stage_review('CPCV',{'status':'CPCV_FAIL','dataset':{},'stage_evidence':{'evaluated':1},'failure_topology':topo,'candidate_summaries':topo['candidate_rows'],'research_memory':{},'seed_policy':{'seeds':[42,11,77]}},cfg,learning_allowed=True)
assert any(h.get('kind')=='SEED_STABILITY' for h in out['hypotheses'])
assert calls[-1][1]['phase']=='FAILURE_LEARNING'
stage_msg=json.loads(calls[-1][0][1]['content'])
assert stage_msg['failure_topology']['candidate_rows'][0]['seed_confirmation']['planned_seeds']==[42,11,77]
assert 'effective_parameter_bounds' in stage_msg and 'cpcv_seed_policy' in stage_msg
print('SCIENTIST_CONTEXT_PARITY_SELFTEST PASS')
