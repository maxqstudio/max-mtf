from copy import deepcopy
import json
from pathlib import Path

from max_graph.evidence_tools import inspect_request, attribute_previous_proposals
from models.topology_allocation import effective_hybrid_priority
from research.research_architect import _selection_policy

ROOT=Path(__file__).resolve().parents[1]

def req(c,m):
    if not c: raise AssertionError(m)
    print('PASS',m)

cfg=json.loads((ROOT/'config/config.json').read_text())
ra=cfg.get('research_architecture') or {}
req(ra.get('family_selection_mode')=='SCIENTIST_DIRECTED','Default v1.3 family mode is Scientist-directed allow-list')
req(ra.get('topology_selection_mode')=='SCIENTIST_DIRECTED','Default v1.3 topology mode is Scientist-directed')
mode,allowed=_selection_policy(cfg,set(ra.get('allowed_families') or []))
req(mode=='SCIENTIST_DIRECTED' and len(allowed)>=2,'Scientist-directed mode preserves Owner allow-list')

cfg2=deepcopy(cfg)
cfg2.setdefault('agent',{})['research_plan']={'topology_priority':{'mode':'SCIENTIST_DIRECTED','hybrid':0.5,'single':0.5,'allowed_topologies':['SINGLE','HYBRID']}}
req(abs(effective_hybrid_priority(cfg2,{'hybrid_priority':0.8})-0.8)<1e-12,'Scientist can move topology allocation inside allowed universe')
req(abs(effective_hybrid_priority(cfg2,{'hybrid_priority':-5})-0.0)<1e-12,'Topology direction remains deterministically clamped')

ctx={'top_results':[{'name':'A','cv_gate_pass':False,'cv_first_failed_gate':'CV_MIN_TRADES'}], 'fold_forensics':[{'name':'A','trades':27}], 'failure_topology':{'dominant_first_failed_gate':'CV_MIN_TRADES'}}
req(inspect_request(ctx,{'tool':'FOLD_FORENSICS','candidate':'A'}).get('status')=='PASS','Bounded evidence tool can inspect candidate folds')
req(inspect_request(ctx,{'tool':'RUN_MT5'}).get('status')=='REJECTED','Execution tool request is rejected')
lin=[{'proposal_id':'P1','candidate_name':'A','fate':'PROPOSED_VALIDATED'}]
out=attribute_previous_proposals(ctx,lin)
req(out[0].get('fate')=='FULL_WFA_OBSERVED','Prior Scientist proposal receives deterministic result attribution')
req(out[0].get('observed',{}).get('cv_first_failed_gate')=='CV_MIN_TRADES','Attribution carries actual failed gate')
print('v1.3.0 agentic Scientist contract selftest PASS')
