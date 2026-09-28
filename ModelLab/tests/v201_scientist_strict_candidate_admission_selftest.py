from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from models.model_registry import effective_bounds
from models.models import CandidateSpec, strict_scientist_candidate_admission
from factory.supervisor_agent import _scientist_execution_provenance
from scientist.core.scientist import LLMScientist

ROOT=Path(__file__).resolve().parents[1]


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)


def cfg_for_test():
    cfg=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
    cfg=deepcopy(cfg)
    cfg.setdefault('agent',{})['research_plan']={
        'active_families':['transformer_moe'],
        'parameter_envelopes':{'transformer_moe':{'d_model':[32,80],'top_k':[1,2]}},
        'family_size_priorities':{'transformer_moe':0.50},
    }
    return cfg


def valid_params(cfg):
    eb=effective_bounds(cfg,'transformer_moe')
    out={}
    for k,(lo,hi,typ) in eb.items():
        value=(float(lo)+float(hi))/2.0
        out[k]=int(round(value)) if typ is int else float(value)
    out['d_model']=80
    # choose an executable head that divides d_model and remains in effective bounds
    hlo,hhi,_=eb['attention_heads']
    heads=[h for h in range(int(hlo),int(hhi)+1) if 80 % h == 0]
    req(bool(heads),'test fixture has no legal attention head for d_model=80')
    out['attention_heads']=heads[-1]
    out['top_k']=min(2,int(eb['top_k'][1]))
    out['num_experts']=max(int(eb['num_experts'][0]),out['top_k'])
    return out


class FakeScientist(LLMScientist):
    def __init__(self,payload):
        self.cfg={}; self.timeout=1; self.temperature=0.0; self.default_env='X'; self.api_key='x'
        self.last_call_provenance={'attempts':[{'status':'PASS','fixture':True}]}
        self.health_enabled=False; self.health_path=None; self.transient_cooldown_sec=1
        self.stack=[{'provider':'fixture','base_url':'https://fixture.invalid/v1','model':'fixture','api_key_env':'X','pricing':{}}]
        self.base_url=self.stack[0]['base_url']; self.provider='fixture'; self.model='fixture'
        self.payload=payload
        self.messages=[]
    def _call_with_phase(self,messages,*,temperature=None,phase='GENERAL'):
        self.messages.append({'phase':phase,'messages':messages})
        return json.dumps(self.payload)


def llm_payload(params):
    return {
        'summary':'fixture','report':{'condition':'fixture','interpretation':'fixture','next_action':'fixture','confidence':0.5},
        'stop_research':False,'strategy':{},
        'proposals':[{'family':'transformer_moe','name':'scientist_fixture','params':params}],
        'hypotheses':[],
    }


def main():
    cfg=cfg_for_test(); params=valid_params(cfg)
    eb=effective_bounds(cfg,'transformer_moe')
    req(eb['d_model'][:2]==(32,80),'fixture effective d_model authority drifted')
    req(eb['top_k'][:2]==(1,2),'fixture effective top_k authority drifted')

    bad=deepcopy(params); bad['d_model']=120
    spec,e=strict_scientist_candidate_admission({'family':'transformer_moe','name':'bad_d','params':bad},cfg,1)
    req(spec is None and e['admission_status']=='REJECTED','d_model=120 was not rejected')
    req('OUTSIDE_EFFECTIVE_PARAMETER_BOUNDS:d_model' in str(e['rejection_reason']),'d_model rejection reason missing')
    req(e['requested_params']['d_model']==120 and e['executable_params'] is None,'rejected request provenance mutated')

    bad=deepcopy(params); bad['top_k']=99
    spec,e=strict_scientist_candidate_admission({'family':'transformer_moe','name':'bad_k','params':bad},cfg,2)
    req(spec is None and 'OUTSIDE_EFFECTIVE_PARAMETER_BOUNDS:top_k' in str(e['rejection_reason']),'top_k=99 was not fail-closed')

    good=deepcopy(params); good['d_model']=80
    spec,e=strict_scientist_candidate_admission({'family':'transformer_moe','name':'good','params':good},cfg,3)
    req(spec is not None and e['admission_status']=='ACCEPTED','legal boundary proposal rejected')
    req(spec.params['d_model']==80 and e['executable_params']['d_model']==80,'legal d_model changed')
    for k,v in e['executable_params'].items():
        if k in e['requested_params'] and not any(x.get('parameter')==k for x in e['canonicalization']):
            req(v==e['requested_params'][k],f'accepted Scientist parameter silently changed: {k}')

    # Exercise production LLMScientist.propose(), not merely the helper.
    sc=FakeScientist(llm_payload({**params,'d_model':120}))
    out=sc.propose({'wfa_pass_count':0,'wfa_total_count':0},cfg,max_n=3)
    req(out['proposals']==[],'production Scientist admitted clamped out-of-bounds proposal')
    adm=out.get('proposal_admission') or []
    req(len(adm)==1 and adm[0]['requested_params']['d_model']==120,'production rejection provenance missing requested params')
    req(adm[0]['executable_params'] is None and adm[0]['admission_status']=='REJECTED','production rejection incorrectly created executable candidate')

    sc2=FakeScientist(llm_payload(good))
    out2=sc2.propose({'wfa_pass_count':0,'wfa_total_count':0},cfg,max_n=3)
    req(len(out2['proposals'])==1 and out2['proposals'][0].params['d_model']==80,'production Scientist failed exact legal admission')
    adm2=(out2.get('proposal_admission') or [])[0]
    req(adm2['admission_status']=='ACCEPTED' and adm2['executable_params']['d_model']==80,'accepted production provenance incorrect')
    prompt=' '.join(str(m) for call in sc2.messages for m in call['messages'])
    req('effective_parameter_bounds' in prompt and 'deterministic dynamic capacity contract' in prompt and 'LEGAL/RESOURCE/SCIENTIFIC' in prompt,'Scientist prompt does not state shared dynamic-capacity authority')

    graph=(ROOT/'max_graph/scientist_director_graph.py').read_text(encoding='utf-8')
    req(graph.count('strict_scientist_candidate_admission')>=3,'LangGraph Scientist validation/rebuild is not strict end-to-end')
    supervisor=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    req('final_queue_admission' in supervisor and 'strict_scientist_candidate_admission' in supervisor,'Supervisor final LLM queue admission is not strict/provenanced')

    # A deterministic hypothesis-directed experiment may intentionally transform a
    # legal Scientist proposal. That trial must be attributed to the experiment block,
    # never silently presented as exact execution of the LLM proposal.
    src=CandidateSpec('transformer_moe','scientist_source',deepcopy(good))
    exe_params=deepcopy(good); exe_params['d_model']=64
    exe=CandidateSpec('transformer_moe','block_trial',exe_params)
    emap=_scientist_execution_provenance(src,exe,experiment_block={'block_id':'EB_TEST','kind':'MODEL_ARCHITECTURE'})
    req(emap['parameters_transformed'] is True and emap['exact_llm_proposal_executed'] is False,'experiment-block transform falsely attributed as exact LLM execution')
    req(emap['execution_authority']=='DETERMINISTIC_EXPERIMENT_BLOCK' and emap['scientific_attribution']=='EXPERIMENT_BLOCK_INTERVENTION_NOT_LLM_EXACT','experiment-block transform provenance authority incorrect')
    exact=_scientist_execution_provenance(src,src,experiment_block=None)
    req(exact['exact_llm_proposal_executed'] is True and exact['scientific_attribution']=='LLM_PROPOSAL_EXACT','normal strict Scientist proposal lost exact-execution attribution')
    try:
        _scientist_execution_provenance(src,exe,experiment_block=None)
    except RuntimeError as exc:
        req('SCIENTIST_EXECUTABLE_IDENTITY_DRIFT' in str(exc),'wrong exact-proposal drift failure')
    else:
        raise AssertionError('non-block Scientist identity drift was not fail-closed')

    print('V201_SCIENTIST_STRICT_CANDIDATE_ADMISSION PASS')


if __name__=='__main__':
    main()
