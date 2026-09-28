from __future__ import annotations
import json
import numpy as np
from models.model_registry import family_spec, effective_bounds
from models.models import CandidateSpec, make_model, estimate_candidate_parameter_count


def req(x,msg):
    if not x: raise AssertionError(msg)


def main():
    cfg=json.load(open('config.json','r',encoding='utf-8'))
    cfg.setdefault('agent',{})['research_plan']={
        'active_families':['transformer_moe'],
        'parameter_envelopes':{'transformer_moe':{
            'sequence_length':[8,16],'hidden_size':[16,32],'d_model':[16,32],'num_layers':[1,2],
            'attention_heads':[2,4],'expert_ffn':[32,64],'num_experts':[3,4],'top_k':[1,2],
            'router_temperature':[0.5,1.5],'load_balance_coef':[0.001,0.05],'dropout':[0.0,0.2],
            'learning_rate':[0.0005,0.002],'batch_size':[16,64],'epochs':[1,3],'weight_decay':[0.0,0.01],
            'training_memory_months':[6,24],
        }}
    }
    spec_meta=family_spec('transformer_moe') or {}
    req(spec_meta.get('role')=='temporal','transformer_moe registry role')
    eb=effective_bounds(cfg,'transformer_moe')
    req(eb['d_model'][0]==16 and eb['d_model'][1]==32,'compiled envelope not effective')
    p=dict(sequence_length=8,hidden_size=16,d_model=16,num_layers=1,attention_heads=2,expert_ffn=32,num_experts=4,top_k=1,
           router_temperature=1.0,load_balance_coef=.01,dropout=.05,learning_rate=.001,batch_size=32,epochs=2,weight_decay=.0001,training_memory_months=12)
    spec=CandidateSpec('transformer_moe','moe_smoke',p)
    count=estimate_candidate_parameter_count(spec,32)
    req(isinstance(count,int) and count>1000,'parameter count unavailable')
    model=make_model(spec,cfg)
    rng=np.random.default_rng(42); X=rng.normal(size=(240,32)).astype(np.float32); y=np.tile(np.array([0,1,2],dtype=np.int64),80)
    model.fit(X,y)
    prob=model.predict_proba(X[:17])
    req(prob.shape==(17,3),'probability shape')
    req(np.max(np.abs(prob.sum(axis=1)-1.0))<1e-5,'probabilities not normalized')
    req(model.parameter_count_==count,'exact parameter count mismatch')
    usage=model.expert_usage()
    req(usage is not None and len(usage)==4,'expert usage missing')
    req(abs(sum(usage)-1.0)<1e-4,'expert usage does not sum to one')
    print('TRANSFORMER_MOE_SELFTEST PASS',count,usage)

if __name__=='__main__': main()
