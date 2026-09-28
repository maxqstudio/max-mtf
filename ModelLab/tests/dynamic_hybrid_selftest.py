from __future__ import annotations
import numpy as np
from research.hybrid_research import HybridStackClassifier
from models.model_registry import hybrid_parts

def req(cond,msg):
    if not cond: raise AssertionError(msg)

def main():
    req(hybrid_parts('hybrid::tcn::lightgbm')==('tcn','lightgbm'),'hybrid parser failed')
    rng=np.random.default_rng(13); n=360; f=8
    X=rng.normal(size=(n,f)).astype(np.float32); y=(np.arange(n)%3).astype(np.int64)
    m=HybridStackClassifier('lightgbm',temporal_family='tcn',random_state=13,threads=1,patience=1,inner_folds=2,
        compute_plan={'temporal_dl':{'torch_device':'cpu','backend':'CPU'},'lightgbm':{'backend':'CPU'}},
        temporal_sequence_length=8,temporal_hidden_size=8,temporal_tcn_channels=8,temporal_tcn_blocks=2,
        temporal_kernel_size=3,temporal_dropout=0.0,temporal_learning_rate=0.001,temporal_batch_size=64,
        temporal_epochs=1,temporal_weight_decay=0.0001,
        policy_n_estimators=20,policy_learning_rate=0.05,policy_num_leaves=7,policy_max_depth=3,
        policy_min_child_samples=10,policy_subsample=0.9,policy_colsample_bytree=0.9,policy_reg_alpha=0.0,policy_reg_lambda=1.0)
    m.fit(X,y)
    p=m.predict_proba_with_context(X[:330],X[330:])
    req(p.shape==(30,3),'dynamic hybrid probability shape wrong')
    req(np.max(np.abs(p.sum(axis=1)-1.0))<1e-5,'dynamic hybrid probabilities not normalized')
    req(m.temporal_family=='tcn' and m.policy_family=='lightgbm','component provenance wrong')
    req(m.oof_coverage_ratio_>0.0,'OOF stack did not produce coverage')
    print('DYNAMIC_HYBRID_SELFTEST PASS')
    return 0
if __name__=='__main__': raise SystemExit(main())
