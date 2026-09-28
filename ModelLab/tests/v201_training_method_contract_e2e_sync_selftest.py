from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from models.model_registry import registry_for_scientist
from research.research_architect import compile_research_plan
from research.research_control import compile_manual_runtime, default_manual_candidate
from scientist.core.scientist import LLMScientist
from scientist.chat.scientist_chat import build_read_only_context
from scientist.knowledge.scientist_knowledge import load_knowledge
from core.training_method_contract import load_training_method_contract, training_method_context, training_method_contract_hash

ROOT=Path(__file__).resolve().parents[1]


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)


class CaptureScientist(LLMScientist):
    def __init__(self,payload):
        self.cfg={}; self.timeout=1; self.temperature=0.0; self.default_env='X'; self.api_key='x'
        self.last_call_provenance={'attempts':[{'status':'PASS','fixture':True}]}
        self.health_enabled=False; self.health_path=None; self.transient_cooldown_sec=1
        self.stack=[{'provider':'fixture','base_url':'https://fixture.invalid/v1','model':'fixture','api_key_env':'X','pricing':{}}]
        self.base_url=self.stack[0]['base_url']; self.provider='fixture'; self.model='fixture'
        self.payload=payload; self.messages=[]
    def _call_with_phase(self,messages,*,temperature=None,phase='GENERAL'):
        self.messages.append({'phase':phase,'messages':deepcopy(messages)})
        return json.dumps(self.payload)


def user_payload_for_phase(sc, phase):
    for call in reversed(sc.messages):
        if call['phase']==phase:
            for msg in call['messages']:
                if msg.get('role')=='user':
                    return json.loads(msg['content'])
    raise AssertionError(f'no captured user payload for {phase}')


def main():
    contract=load_training_method_contract(); compact=training_method_context(); sha=training_method_contract_hash()
    req(contract['schema']=='MODEL_TRAINING_METHOD_CONTRACT_V1','canonical training method schema missing')
    req(compact['contract_sha256']==sha,'canonical contract hash mismatch')
    req(contract['candidate_admission']['llm_concrete_proposal']=='STRICT_EFFECTIVE_BOUNDS_FAIL_CLOSED','strict LLM admission absent from canonical method contract')
    req(contract['temporal_early_stop']['authority']=='PURGED_INTERNAL_EARLY_VALIDATION','DL internal purge truth absent')
    req(contract['moe_diagnostics']['authority']=='PER_MOE_BLOCK_FROM_RESTORED_BEST_CHECKPOINT','per-block best-checkpoint MoE authority absent')
    req(contract['moe_routing']['expert_identity']=='LATENT_LEARNED_EXPERTS_0_TO_N_MINUS_1','latent expert truth absent')
    req(contract['hybrid_stacking']['authority']=='TEMPORAL_TO_TREE_PURGED_OOF_STACKING','hybrid OOF truth absent')

    cfg=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

    # AUTO deterministic plan consumes the exact same contract.
    profile={'profile_hash':'fixture','memory':{'total_gib':32.0,'available_gib':24.0},'nvidia':{'devices':[]},'torch':{'cuda_available':False},'cpu':{'physical_cores':6,'logical_threads':12,'planning_cores':6}}
    capacity={'dataset':{'rows_per_month':518},'wfa':{'median_train_rows':8200,'fold_count':3},'reference_scenario':{'estimated_train_rows':8200}}
    auto_plan=compile_research_plan({},profile,deepcopy(cfg),capacity)
    req((auto_plan.get('model_training_method_contract') or {}).get('contract_sha256')==sha,'AUTO plan training method contract drift')

    # MANUAL plan consumes the exact same read-only method authority.
    manual_cfg=deepcopy(cfg)
    manual_cfg.setdefault('champion_factory',{})['research_mode']='MANUAL'
    manual_cfg['champion_factory']['manual_research']={'enabled':True,'candidates':[default_manual_candidate('random_forest',1)],'take_threshold':0.65,'minimum_wfa_survivors':1}
    manual_runtime,_=compile_manual_runtime(manual_cfg)
    manual_method=(((manual_runtime.get('agent') or {}).get('research_plan') or {}).get('model_training_method_contract') or {})
    req(manual_method.get('contract_sha256')==sha,'MANUAL runtime training method contract drift')

    # Per-round Scientist receives canonical method truth in the actual production prompt.
    round_payload={'summary':'fixture','report':{'condition':'fixture','interpretation':'fixture','next_action':'fixture','confidence':0.5},'strategy':{},'proposals':[],'hypotheses':[],'stop_research':False}
    sc=CaptureScientist(round_payload)
    out=sc.propose({'wfa_pass_count':0,'wfa_total_count':0},cfg,max_n=0)
    user=user_payload_for_phase(sc,'DISCOVERY_HYPOTHESIS')
    req((user.get('model_training_method_contract') or {}).get('contract_sha256')==sha,'round Scientist training method context drift')
    req((out.get('model_training_method_contract') or {}).get('contract_sha256')==sha,'round Scientist response provenance lacks method contract')

    # Factory Director receives the same contract rather than a copied prose variant.
    director_payload={'summary':'fixture','report':{'condition':'fixture','interpretation':'fixture','next_action':'fixture','confidence':0.5},'strategy':{},'hypotheses':[],'stop_research':False}
    fd=CaptureScientist(director_payload)
    fd.factory_preflight({'factory_id':'F','factory_generation':0},cfg)
    duser=user_payload_for_phase(fd,'DIRECTOR_PREFLIGHT')
    req((duser.get('model_training_method_contract') or {}).get('contract_sha256')==sha,'Factory Director training method context drift')

    # Registry semantics must explicitly tell Scientist that MoE experts are latent.
    reg=registry_for_scientist(); moe=(reg.get('base_families') or {}).get('transformer_moe') or {}
    req(moe.get('expert_identity')=='LATENT_LEARNED_EXPERTS_0_TO_N_MINUS_1','Scientist registry hides latent MoE expert identity')
    req(moe.get('strategy_expert_prior_semantics')=='DESCRIPTIVE_PRIOR_ONLY_NOT_SUPERVISED_EXPERT_IDENTITY','Scientist registry hides descriptive-prior semantics')

    # Persisted Scientist Knowledge + Chat must expose the same exact hash.
    kb=load_knowledge(); km=kb.get('model_training_method_contract') or {}
    req(km.get('contract_sha256')==sha,'SCIENTIST_KNOWLEDGE_BASE training method contract stale')
    chat_ctx=build_read_only_context(None)
    cm=((chat_ctx.get('max_knowledge') or {}).get('model_training_method_contract') or {})
    req(cm.get('contract_sha256')==sha,'Scientist Chat context training method contract drift')

    # Contract is tied back to repaired production trainer authority, not standalone prose.
    temporal=(ROOT/'research/temporal_research.py').read_text(encoding='utf-8')
    hybrid=(ROOT/'research/hybrid_research.py').read_text(encoding='utf-8')
    models=(ROOT/'models/models.py').read_text(encoding='utf-8')
    req('purged_internal_earlystop_split' in temporal and 'MAX_DL_INTERNAL_EARLYSTOP_PURGE_V1' in temporal,'canonical early-stop method not present in production temporal trainer')
    req("'authority':'PER_MOE_BLOCK'" in temporal and 'RESTORED_BEST_EARLYSTOP_CHECKPOINT_DETERMINISTIC_OBJECTIVE_PROBE' in temporal,'canonical MoE diagnostic method not present in production trainer')
    req('router_balance_loss' in temporal and 'load_balance_coef' in temporal,'canonical MoE balance method not present in production trainer')
    req('purged_internal_earlystop_split' in hybrid,'hybrid encoder does not inherit internal purge')
    req('strict_scientist_candidate_admission' in models,'strict Scientist admission production authority missing')

    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('MODEL_TRAINING_METHOD_CONTRACT_V1' in app,'Manual/AUTO UI does not identify canonical read-only training method authority')

    print('V201_TRAINING_METHOD_CONTRACT_E2E_SYNC PASS')


if __name__=='__main__':
    main()
