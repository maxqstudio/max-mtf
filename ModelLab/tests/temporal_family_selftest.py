from __future__ import annotations
import numpy as np
from research.temporal_research import TemporalClassifier

def req(cond,msg):
    if not cond: raise AssertionError(msg)

def main():
    rng=np.random.default_rng(7); n=180; f=6
    X=rng.normal(size=(n,f)).astype(np.float32); y=(np.arange(n)%3).astype(np.int64)
    for arch in ('lstm','tcn','transformer'):
        m=TemporalClassifier(architecture=arch,sequence_length=8,hidden_size=8,num_layers=1,dropout=0.0,
            learning_rate=0.001,batch_size=64,epochs=1,patience=1,threads=1,device='cpu',
            tcn_channels=8,tcn_blocks=2,kernel_size=3,d_model=8,attention_heads=2,ffn_mult=2)
        m.fit(X,y)
        p=m.predict_proba_with_context(X[:150],X[150:])
        req(p.shape==(30,3),f'{arch} probability shape {p.shape}')
        req(np.all(np.isfinite(p)),f'{arch} non-finite probability')
        req(np.max(np.abs(p.sum(axis=1)-1.0))<1e-5,f'{arch} probabilities not normalized')
        req(m.train_report_ and m.train_report_.architecture==arch,f'{arch} train provenance missing')
    print('TEMPORAL_FAMILY_SELFTEST PASS')
    return 0
if __name__=='__main__': raise SystemExit(main())
