from __future__ import annotations
import json
from pathlib import Path
from models.model_lab import load_cfg
from scientist.core.scientist import LLMScientist

ROOT=Path(__file__).resolve().parents[1]
CFG=load_cfg(ROOT/'config/config.json')
LLM_CFG={'provider':'custom','base_url':'https://example.invalid/v1','model':'fake','temperature':0.2}
OWNER_BAD='''{"summary":"ok","report":{"condition":"ok","interpretation":"same","next_action":"continue","confidence":0.5},"strategy":{"policy_max_depth":kap 4},"proposals":[],"hypotheses":[],"stop_research":false}'''
PROPOSE_GOOD={"summary":"ok","report":{"condition":"ok","interpretation":"same","next_action":"continue","confidence":0.5},"strategy":{"policy_max_depth":4},"proposals":[],"hypotheses":[],"stop_research":False}
POLICY_GOOD={"summary":"ok","report":{"condition":"ok","interpretation":"same","next_action":"continue","confidence":0.5}}
DIRECTOR_GOOD={"summary":"ok","report":{"condition":"ok","interpretation":"same","next_action":"continue","confidence":0.5},"strategy":{},"hypotheses":[],"stop_research":False}
STAGE_GOOD={"summary":"ok","report":{"condition":"ok","interpretation":"same","next_action":"continue","confidence":0.5},"scientific_method":{"observation":"evidence","hypothesis":"h","experiment":"e","falsification":"f","conclusion":"pending"},"strategy":{},"hypotheses":[],"next_discovery_plan":{},"stop_research":False}


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def scientist_for(initial_phase, repaired_obj, initial_text=OWNER_BAD, second_malformed=False):
    sc=LLMScientist(LLM_CFG,api_key='x');calls=[]
    def fake(messages,**kwargs):
        phase=kwargs.get('phase');temp=kwargs.get('temperature');calls.append((phase,temp,messages))
        if phase==initial_phase:
            return initial_text
        if phase==initial_phase+'_JSON_REPAIR':
            return '{"still":kap 4}' if second_malformed else json.dumps(repaired_obj,separators=(',',':'))
        raise AssertionError('unexpected phase '+str(phase))
    sc._call=fake
    return sc,calls

# Exact Owner failure case in Discovery proposal: one and only one format-only retry.
sc,calls=scientist_for('DISCOVERY_HYPOTHESIS',PROPOSE_GOOD)
out=sc.propose({'wfa_pass_count':0,'wfa_total_count':0,'top_results':[]},CFG,max_n=0)
req([x[0] for x in calls]==['DISCOVERY_HYPOTHESIS','DISCOVERY_HYPOTHESIS_JSON_REPAIR'],'Owner :kap 4 proposal performs exactly one bounded repair call')
req(calls[1][1]==0.0,'proposal repair temperature is exactly zero')
req((out.get('response_format_recovery') or {}).get('used') is True,'proposal records format recovery provenance')

# Policy Review uses the same shared authority.
sc,calls=scientist_for('POLICY_REVIEW',POLICY_GOOD)
out=sc.policy_review({'model_frontier':{},'policy_frontier':{},'policy_passed':False,'next_required':'x'})
req([x[0] for x in calls]==['POLICY_REVIEW','POLICY_REVIEW_JSON_REPAIR'],'Policy Review uses shared bounded JSON recovery')
req(calls[1][1]==0.0 and out['response_format_recovery']['used'],'Policy Review repair is zero-temperature and recorded')

# Research Director uses the same helper rather than a separate ad-hoc implementation.
sc,calls=scientist_for('DIRECTOR_PREFLIGHT',DIRECTOR_GOOD)
out=sc.factory_preflight({'factory_id':'F','factory_generation':0,'dataset':{},'research_memory':{},'remaining_budget':1},CFG)
req([x[0] for x in calls]==['DIRECTOR_PREFLIGHT','DIRECTOR_PREFLIGHT_JSON_REPAIR'],'Research Director uses shared bounded JSON recovery')
req(calls[1][1]==0.0 and out['response_format_recovery']['used'],'Director repair is zero-temperature and recorded')

# Stage Review also uses the same authority.
sc,calls=scientist_for('STAGE_FORENSIC',STAGE_GOOD)
out=sc.stage_review('CPCV',{'status':'PASS','dataset':{},'stage_evidence':{},'failure_topology':{},'candidate_summaries':[],'research_memory':{}},CFG,learning_allowed=False)
req([x[0] for x in calls]==['STAGE_FORENSIC','STAGE_FORENSIC_JSON_REPAIR'],'Stage Review uses shared bounded JSON recovery')
req(calls[1][1]==0.0 and out['response_format_recovery']['used'],'Stage Review repair is zero-temperature and recorded')

# Second malformed response fails closed; no third LLM request is allowed.
sc,calls=scientist_for('DISCOVERY_HYPOTHESIS',PROPOSE_GOOD,second_malformed=True)
failed=False
try:
    sc.propose({'wfa_pass_count':0,'wfa_total_count':0,'top_results':[]},CFG,max_n=0)
except ValueError as exc:
    failed='bounded format-only retry failed' in str(exc)
req(failed,'second malformed response fails closed')
req(len(calls)==2,'bounded recovery never issues a third LLM request')

src=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
req('def _extract_json_with_bounded_format_repair' in src,'shared v1.4.6 recovery authority exists')
req('do not add, remove, reinterpret, summarize, optimize, correct scientific content' in src.lower(),'repair prompt forbids semantic modification')
print('V201_INHERITED_V146_SCIENTIST_JSON_RECOVERY PASS')
