from __future__ import annotations
import json
import numpy as np
from models.model_registry import family_spec, dynamic_hybrid_families
from models.models import CandidateSpec, make_model, estimate_candidate_parameter_count, canonicalize_candidate_params


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def main():
    cfg=json.loads((__import__('pathlib').Path(__file__).resolve().parents[1]/'config/config.json').read_text(encoding='utf-8'))
    cfg.setdefault('agent',{})['research_plan']={'active_families':['patchtst','itransformer','tft']}
    rng=np.random.default_rng(57); X=rng.normal(size=(210,8)).astype(np.float32); y=(np.arange(210)%3).astype(np.int64)
    params={
      'patchtst': dict(sequence_length=12,hidden_size=12,d_model=12,num_layers=1,attention_heads=3,ffn_mult=2,patch_len=4,patch_stride=2,dropout=0.0,learning_rate=.001,batch_size=64,epochs=1,weight_decay=.0001,training_memory_months=12),
      'itransformer': dict(sequence_length=12,hidden_size=12,d_model=12,num_layers=1,attention_heads=3,ffn_mult=2,dropout=0.0,learning_rate=.001,batch_size=64,epochs=1,weight_decay=.0001,training_memory_months=12),
      'tft': dict(sequence_length=12,hidden_size=12,d_model=12,num_layers=1,attention_heads=3,ffn_mult=2,tft_lstm_layers=1,dropout=0.0,learning_rate=.001,batch_size=64,epochs=1,weight_decay=.0001,training_memory_months=12),
    }
    for fam,p in params.items():
        meta=family_spec(fam) or {}
        req(meta.get('role')=='temporal' and meta.get('deployable') is True,f'{fam} executable temporal registry')
        req(bool(meta.get('architecture_note')),f'{fam} Scientist architecture note')
        spec=CandidateSpec(fam,f'{fam}_smoke',p)
        count=estimate_candidate_parameter_count(spec,8)
        req(isinstance(count,int) and count>500,f'{fam} exact parameter count')
        m=make_model(spec,cfg); m.fit(X,y)
        prob=m.predict_proba_with_context(X[:180],X[180:])
        req(prob.shape==(30,3),f'{fam} probability shape')
        req(np.all(np.isfinite(prob)) and np.max(np.abs(prob.sum(axis=1)-1.0))<1e-5,f'{fam} normalized probabilities')
        req(m.parameter_count_==count,f'{fam} count parity')
        req(m.train_report_ and m.train_report_.architecture==fam,f'{fam} training provenance')
    c=canonicalize_candidate_params('patchtst',dict(sequence_length=8,d_model=8,attention_heads=3,patch_len=99,patch_stride=99))
    req(c['patch_len']==8 and c['patch_stride']==8,'PatchTST patch geometry canonicalized fail-closed')
    dyn=set(dynamic_hybrid_families())
    for fam in params:
        req(f'hybrid::{fam}::lightgbm' in dyn,f'{fam} dynamic hybrid grammar')
    print('TRANSFORMER_FAMILY_EXPANSION_SELFTEST PASS')

if __name__=='__main__': main()
