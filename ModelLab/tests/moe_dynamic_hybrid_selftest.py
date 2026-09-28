from __future__ import annotations
import json
import numpy as np
from models.model_registry import family_spec
from models.models import CandidateSpec, make_model


def req(x,msg):
    if not x: raise AssertionError(msg)


def main():
    family='hybrid::transformer_moe::lightgbm'
    req(family_spec(family) is not None,'dynamic MoE hybrid not in registry grammar')
    cfg=json.load(open('config.json','r',encoding='utf-8'))
    cfg.setdefault('agent',{})['research_plan']={'active_families':[family]}
    p={
      'temporal_sequence_length':8,'temporal_hidden_size':16,'temporal_d_model':16,'temporal_num_layers':1,'temporal_attention_heads':2,
      'temporal_expert_ffn':32,'temporal_num_experts':3,'temporal_top_k':1,'temporal_router_temperature':1.0,'temporal_load_balance_coef':.01,
      'temporal_dropout':0.0,'temporal_learning_rate':.001,'temporal_batch_size':32,'temporal_epochs':1,'temporal_weight_decay':.0001,
      'policy_n_estimators':40,'policy_learning_rate':.05,'policy_num_leaves':15,'policy_max_depth':4,'policy_min_child_samples':12,
      'policy_subsample':.9,'policy_colsample_bytree':.9,'policy_reg_alpha':0.0,'policy_reg_lambda':1.0,'training_memory_months':12,
    }
    spec=CandidateSpec(family,'hybrid_moe_smoke',p); model=make_model(spec,cfg)
    rng=np.random.default_rng(7); X=rng.normal(size=(420,32)).astype(np.float32); y=np.tile(np.array([0,1,2],dtype=np.int64),140)
    model.fit(X,y); prob=model.predict_proba(X[:11])
    req(prob.shape==(11,3),'hybrid MoE probability shape')
    req(np.max(np.abs(prob.sum(axis=1)-1.0))<1e-5,'hybrid probabilities not normalized')
    print('MOE_DYNAMIC_HYBRID_SELFTEST PASS')

if __name__=='__main__': main()
