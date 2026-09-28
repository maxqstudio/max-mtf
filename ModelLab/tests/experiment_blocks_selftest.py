from pathlib import Path
import json
from research.experiment_blocks import *
from models.models import CandidateSpec
ROOT=Path(__file__).resolve().parents[1]; CFG=json.loads((ROOT/'config/config.json').read_text())
def req(c,m):
    if not c: raise AssertionError(m)
h={"kind":"TRAINING_MEMORY","title":"memory stability","payload":{"months":[12,24]},"executable":True}
life=reconcile_hypotheses([], [h], source="TEST", generation=1); req(len(life)==1 and life[0]["status"]=="PROPOSED","lifecycle create")
a=CandidateSpec('xgboost','a',{'n_estimators':300,'max_depth':4,'learning_rate':0.05,'min_child_weight':5.0,'subsample':0.8,'colsample_bytree':0.8,'training_memory_months':24})
b=compile_experiment_block(life[0],a,CFG,generation=1,block_no=1,budget=3); req(b['variable_keys']==['training_memory_months'],'training-memory block must freeze unrelated knobs')
s=CandidateSpec('xgboost','x',dict(a.params, max_depth=8,training_memory_months=12)); z=apply_block_to_spec(s,b,CFG,1); req(z.params['max_depth']==4 and z.params['training_memory_months']==12,'block freeze failed')
rows=[{'experiment_block_id':b['block_id'],'cv_gate_pass':False,'failure_margins':{'closest_failed_gate':{'relative_margin':-.1}}} for _ in range(3)]
req(evaluate_block(b,rows,CFG)['status']=='FALSIFIED','bounded falsification failed')
sa=(ROOT/'factory/supervisor_agent.py').read_text(); req('experiment_block_id' in sa and 'hypothesis_lifecycle.json' in sa,'Supervisor block wiring missing')
print('EXPERIMENT_BLOCKS_SELFTEST PASS')
