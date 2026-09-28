from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from models.model_lab import load_cfg
from research.future_learning_foundation import foundation_snapshot
from research.learning_policy import recommend_learning_actions
from scientist.skills.max_scientist_skills import load_manifest, skill_guidance
from research.structured_research_memory import refresh_structured_memory, hypothesis_to_experience

ROOT=Path(__file__).resolve().parents[1]

def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)

def hyp(hid,kind,status,gate,stage='DISCOVERY'):
    return {
        'hypothesis_id':hid,'kind':kind,'title':hid,'payload':{},'status':status,
        'source':'SCIENTIST','source_stage':stage,'source_generation':1,
        'source_failure_gate':gate,
    }

def main():
    cfg=load_cfg(ROOT/'config/config.json')
    foundation=foundation_snapshot(cfg)
    req(foundation['embedder']['enabled'] is False and foundation['rag']['enabled'] is False and foundation['rl']['enabled'] is False,'RL/RAG/Embedder foundation exists but is disabled')
    bad=deepcopy(cfg); bad['agent']['learning_system']['future_foundations']['rl']['enabled']=True
    try:
        foundation_snapshot(bad)
        raise AssertionError('RL foundation must fail closed when enabled before implementation')
    except RuntimeError as exc:
        req('FUTURE_LEARNING_FOUNDATION_NOT_IMPLEMENTED' in str(exc),'future RL/RAG/Embedder activation fails closed')

    manifest=load_manifest(verify=True)
    req(manifest['skill_count']==9,'MAX Data Scientist pack contains exactly 9 audited skills')
    req(all(r.get('max_authority')=='ADVISORY' and not r.get('may_emit_pass_fail') and not r.get('may_promote') and not r.get('may_trade') for r in manifest['skills']),'all Scientist skills are zero-authority methodology')
    g=skill_guidance({'failure_topology':{'dominant_first_failed_gate':'CV_MIN_TRADES'},'top_results':[{'name':'A'}]})
    req('max-research-data-scientist' in g['skill_ids'] and 'feature-label-research' in g['skill_ids'] and 'time-series-validation' in g['skill_ids'],'skill router selects core plus failure-relevant specialist doctrines')

    memory={'schema':'CP_RESEARCH_MEMORY_V1','hypothesis_lifecycle':[
        hyp('H1','SELECTIVITY_POLICY','SUPPORTED','CV_MIN_TRADES'),
        hyp('H2','SELECTIVITY_POLICY','PARTIALLY_SUPPORTED','CV_MIN_TRADES'),
        hyp('H3','MODEL_ARCHITECTURE','FALSIFIED','CV_MIN_TRADES'),
        hyp('H4','FEATURE_ABLATION','SUPPORTED','CV_WORST_EXPECTANCY'),
        hyp('H5','SELECTIVITY_POLICY','SUPPORTED','CV_MIN_TRADES','FRESH_FORWARD'),
    ]}
    refreshed=refresh_structured_memory(memory,memory['hypothesis_lifecycle'])
    req(len(refreshed['experience_ledger'])==4,'protected Fresh/Locked evidence is excluded from adaptive structured memory')
    req(all(not x['protected_evidence_used'] for x in refreshed['experience_ledger']),'structured experience ledger marks zero protected evidence use')
    req(refreshed['learning_policy_stats']['by_failure_gate']['CV_MIN_TRADES']['SELECTIVITY_POLICY']['attempts']==2,'learning stats aggregate exact failure-topology/action evidence')
    pol=recommend_learning_actions(refreshed,{'dominant_first_failed_gate':'CV_MIN_TRADES'},limit=5)
    req(pol['recommendations'][0]['action_kind']=='SELECTIVITY_POLICY','learning policy ranks historically supported selectivity action first for MIN_TRADES context')
    req(pol['may_emit_pass_fail'] is False and pol['may_promote'] is False and pol['may_read_protected_oos'] is False,'learning policy cannot emit verdict, promote, or read protected OOS')
    req(hypothesis_to_experience(hyp('PX','FEATURE_ABLATION','SUPPORTED','X','LOCKED_OOS')) is None,'protected-OOS hypothesis cannot enter learning replay/experience foundation')

    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    sci=(ROOT/'scientist/core/scientist.py').read_text(encoding='utf-8')
    req('recommend_learning_actions' in sup and 'skill_guidance' in sup and 'foundation_snapshot' in sup,'Supervisor wires skills, structured learning policy and future foundation')
    req('structured_learning_policy' in sci and 'max_data_scientist_skills' in sci,'Scientist prompt receives active skills and structured learning policy')
    req('RAGFoundation' in (ROOT/'research/future_learning_foundation.py').read_text() and 'RLPolicyFoundation' in (ROOT/'research/future_learning_foundation.py').read_text(),'RAG/RL extension interfaces are present for future build-on')
    print('V140_AGENTIC_LEARNING_FOUNDATION_SELFTEST PASS')

if __name__=='__main__': main()
