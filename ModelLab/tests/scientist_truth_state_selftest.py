from __future__ import annotations
import json
from pathlib import Path
from scientist.core.scientist import LLMScientist
from models.model_lab import load_cfg

ROOT=Path(__file__).resolve().parents[1]
CFG=load_cfg(ROOT/'config/config.json')

class FakeScientist(LLMScientist):
    def __init__(self):
        super().__init__({'base_url':'http://fake','model':'fake','provider':'custom','temperature':0.1})
        self.last_messages=None
    def _call(self,messages):
        self.last_messages=messages
        return json.dumps({
            'summary':'OPTIMAL_FAMILY_CONVERGENCE pada hybrid GRU LightGBM',
            'report':{'condition':'OPTIMAL_FAMILY_CONVERGENCE','interpretation':'frontier terlihat kuat','next_action':'refine','confidence':0.92},
            'strategy':{'family_priorities':{'hybrid_gru_lightgbm':2.0}},'proposals':[],'hypotheses':[],'stop_research':False,
        })

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    s=FakeScientist()
    out=s.propose({'wfa_pass_count':0,'wfa_total_count':26,'first_failed_gate_counts':{'CV_WORST_FOLD_RECOVERY':11},'top_results':[]},CFG,max_n=0)
    req(out.get('deterministic_state')=='NO_WFA_SURVIVOR','Scientist carries deterministic all-FAIL state')
    req((out.get('report') or {}).get('condition')=='NO_WFA_SURVIVOR','LLM cannot label an all-FAIL frontier as optimal/converged')
    req(str(out.get('summary')).startswith('NO_WFA_SURVIVOR'),'operator summary is prefixed with deterministic truth')
    payload=json.loads(s.last_messages[-1]['content'])
    req(payload.get('wfa_pass_count')==0 and payload.get('wfa_total_count')==26,'Scientist receives explicit PASS/FAIL counts')
    req(payload.get('first_failed_gate_counts',{}).get('CV_WORST_FOLD_RECOVERY')==11,'Scientist receives failure gate distribution')
    print('SCIENTIST_TRUTH_STATE_SELFTEST PASS')

if __name__=='__main__':
    main()
