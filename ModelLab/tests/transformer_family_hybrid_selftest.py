from __future__ import annotations
import json
import numpy as np
from models.model_registry import family_spec
from models.models import CandidateSpec, make_model


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def main():
    for temporal in ('patchtst','itransformer','tft'):
        fam=f'hybrid::{temporal}::lightgbm'
        spec=family_spec(fam) or {}
        req(spec.get('role')=='composed_hybrid' and spec.get('temporal_family')==temporal,f'{fam} registry composition')
    family='hybrid::patchtst::lightgbm'
    cfg=json.load(open('config.json','r',encoding='utf-8'))
    cfg.setdefault('agent',{})['research_plan']={'active_families':[family]}
    p={
      'temporal_sequence_length':8,'temporal_hidden_size':8,'temporal_d_model':8,'temporal_num_layers':1,'temporal_attention_heads':2,
      'temporal_ffn_mult':2,'temporal_patch_len':4,'temporal_patch_stride':2,'temporal_dropout':0.0,'temporal_learning_rate':.001,
      'temporal_batch_size':64,'temporal_epochs':1,'temporal_weight_decay':.0001,
      'policy_n_estimators':20,'policy_learning_rate':.08,'policy_num_leaves':7,'policy_max_depth':3,'policy_min_child_samples':10,
      'policy_subsample':.9,'policy_colsample_bytree':.9,'policy_reg_alpha':0.0,'policy_reg_lambda':1.0,'training_memory_months':12,
    }
    model=make_model(CandidateSpec(family,'patch_hybrid_smoke',p),cfg)
    rng=np.random.default_rng(91); X=rng.normal(size=(420,32)).astype(np.float32); y=np.tile(np.array([0,1,2],dtype=np.int64),140)
    model.fit(X,y); prob=model.predict_proba_with_context(X[:390],X[390:])
    req(prob.shape==(30,3),'PatchTST→LightGBM hybrid runtime shape')
    req(np.max(np.abs(prob.sum(axis=1)-1.0))<1e-5,'PatchTST hybrid normalized probabilities')
    req(model.temporal_family=='patchtst' and model.policy_family=='lightgbm','PatchTST hybrid provenance')
    print('TRANSFORMER_FAMILY_HYBRID_SELFTEST PASS')

if __name__=='__main__': main()
