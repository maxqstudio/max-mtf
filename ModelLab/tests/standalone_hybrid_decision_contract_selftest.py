from __future__ import annotations

import numpy as np

from research.gru_research import GRUClassifier
from research.hybrid_research import HybridStackClassifier, augment_policy_features
from models.models import CandidateSpec, candidate_runtime_contract, predict_model_proba


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)
    print('PASS ',msg)


def main():
    rng=np.random.default_rng(7513)
    n=380
    X=rng.normal(size=(n,32)).astype(np.float32)
    lag=np.r_[0.0,X[:-1,0]]
    signal=X[:,0]+0.75*lag+0.20*X[:,2]
    quality=X[:,3]-0.30*np.abs(X[:,4])
    y=np.where((signal>0.30)&(quality>-0.65),2,np.where((signal<-0.30)&(quality>-0.65),0,1)).astype(np.int64)
    req(set(np.unique(y).tolist())=={0,1,2},'shared synthetic authority contains SELL/SKIP/BUY')
    train=320
    history=X[:train]; target=X[train:]

    single=GRUClassifier(sequence_length=8,hidden_size=16,num_layers=1,dropout=0.0,learning_rate=0.002,batch_size=64,epochs=1,weight_decay=0.0,patience=1,random_state=17,threads=1)
    single.fit(history,y[:train])
    ps=predict_model_proba(single,'gru',history,target)
    req(ps.shape==(len(target),3) and np.isfinite(ps).all(),'standalone DL emits [N,3] final probabilities on target rows')
    req(np.max(np.abs(ps.sum(axis=1)-1.0))<1e-6,'standalone DL SELL/SKIP/BUY probabilities are normalized')

    hybrid=HybridStackClassifier(
        'random_forest',temporal_family='gru',random_state=17,threads=1,patience=1,inner_folds=2,
        temporal_sequence_length=8,temporal_hidden_size=16,temporal_num_layers=1,temporal_dropout=0.0,
        temporal_learning_rate=0.002,temporal_batch_size=64,temporal_epochs=1,temporal_weight_decay=0.0,
        policy_n_estimators=30,policy_max_depth=5,policy_min_samples_leaf=2,policy_max_features=0.7,
    )
    hybrid.fit(history,y[:train])
    ph=predict_model_proba(hybrid,'hybrid::gru::random_forest',history,target)
    req(ph.shape==ps.shape and np.isfinite(ph).all(),'hybrid emits the same [N,3] final decision schema on the same target rows')
    req(np.max(np.abs(ph.sum(axis=1)-1.0))<1e-8,'hybrid SELL/SKIP/BUY probabilities are normalized')
    req(list(hybrid.classes_)==[0,1,2],'hybrid final class order is SELL/SKIP/BUY')
    req(hybrid.stacking_schema_=='OOF_DIRECTION_STACK_V2_PURGED_INDEXED' and 0.20<hybrid.oof_coverage_ratio_<1.0,'hybrid policy is trained from bounded OOF temporal predictions')

    p2=hybrid.direction_proba_with_context(history,target)
    meta=augment_policy_features(target,p2)
    req(p2.shape==(len(target),2),'hybrid temporal leg emits DOWN/UP only')
    req(meta.shape==(len(target),36),'hybrid cooperation appends four temporal meta-features to CP32')
    req(np.allclose(meta[:,:32],target),'hybrid policy receives the exact same CP32 target rows')
    req(np.allclose(meta[:,32],p2[:,0]) and np.allclose(meta[:,33],p2[:,1]),'hybrid policy receives P(DOWN) and P(UP)')
    req(np.allclose(meta[:,34],p2[:,1]-p2[:,0]),'hybrid policy receives directional P(UP)-P(DOWN)')
    req(np.allclose(meta[:,35],np.maximum(p2[:,0],p2[:,1])),'hybrid policy receives temporal confidence')

    single_spec=CandidateSpec('gru','single_contract',{'sequence_length':8})
    hybrid_spec=CandidateSpec('hybrid::gru::random_forest','hybrid_contract',{'temporal_sequence_length':8})
    sr=candidate_runtime_contract(single_spec,32); hr=candidate_runtime_contract(hybrid_spec,32)
    req(sr['output']==[1,3] and hr['policy_output']==[1,3],'standalone and hybrid deployment contracts converge to the same 3-class final output')
    req(hr['temporal_output']==[1,2] and hr['policy_input']==[1,36],'hybrid internal cooperation remains explicit [DOWN,UP] -> CP32+4 -> final 3-class')

    class TwoClassDummy:
        classes_=np.asarray([0,2],dtype=np.int64)
        def predict_proba(self, X):
            return np.tile(np.asarray([[0.4,0.6]],dtype=np.float64),(len(X),1))
    pd=predict_model_proba(TwoClassDummy(),'random_forest',history,target[:3])
    req(pd.shape==(3,3) and np.allclose(pd[:,1],0.0) and np.allclose(pd[:,0],0.4) and np.allclose(pd[:,2],0.6),'canonical final contract aligns missing tree classes into SELL/SKIP/BUY')
    print('\nSTANDALONE/HYBRID DECISION CONTRACT SELF-TEST PASS')


if __name__=='__main__':
    main()
