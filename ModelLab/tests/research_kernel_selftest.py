from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from research.gru_research import sequence_tensor_for_indices
from research.hybrid_research import HybridStackClassifier
from models.models import CandidateSpec, canonicalize_candidate_params, spec_fingerprint
from models.model_lab import research_region
from research.scientific_hypotheses import validate_hypothesis
from core.temporal_index import inner_oof_folds, contiguous_chunks
from factory.champion_factory import _load_global_contract, _record_downstream_failure, _research_contract, RESEARCH_KERNEL_SCHEMA

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def main():
    # Discontinuous temporal topology: row 10 must not inherit row 2 as fake history.
    X=np.arange(20,dtype=np.float32).reshape(-1,1)
    seq,rows=sequence_tensor_for_indices(X,np.asarray([0,1,2,10,11,12]),3)
    pos={int(r):i for i,r in enumerate(rows)}
    req(np.allclose(seq[pos[10],:,0],[10,10,10]),'temporal sequence resets at an excluded CPCV gap')
    req(np.allclose(seq[pos[12],:,0],[10,11,12]),'temporal sequence remains causal inside a legal chunk')
    req(len(contiguous_chunks([0,1,2,10,11,12]))==2,'original row topology remains explicit')

    # Inner stacking must purge targets immediately before validation.
    idx=np.arange(500,dtype=int)
    folds=inner_oof_folds(idx,2,24)
    req(bool(folds),'purged hybrid inner OOF folds are constructible')
    for tr,va in folds:
        for chunk in contiguous_chunks(va):
            req(not np.any((tr>=int(chunk[0])-24)&(tr<int(chunk[0]))),'hybrid inner OOF purges label-overlap boundary')

    # No-op dropout variants canonicalize to one effective experiment.
    a=CandidateSpec('gru','a',{'num_layers':1,'dropout':0.05,'sequence_length':12})
    b=CandidateSpec('gru','b',{'num_layers':1,'dropout':0.30,'sequence_length':12})
    req(spec_fingerprint(a)==spec_fingerprint(b),'single-layer GRU no-op dropout does not create fake research novelty')
    hp=canonicalize_candidate_params('hybrid_gru_xgboost',{'gru_num_layers':1,'gru_dropout':0.2})
    req(float(hp['gru_dropout'])==0.0,'single-layer hybrid GRU dropout canonicalizes to zero')

    # Hybrid indexed fit must preserve an outer discontinuity instead of compressing it.
    rng=np.random.default_rng(77); Xh=rng.normal(size=(420,32)).astype(np.float32)
    lag=np.r_[0.0,Xh[:-1,0]]; q=Xh[:,3]-0.25*np.abs(Xh[:,4]); z=Xh[:,0]+0.7*lag
    yh=np.where((z>0.25)&(q>-0.7),2,np.where((z<-0.25)&(q>-0.7),0,1)).astype(np.int64)
    allowed=np.r_[np.arange(0,180),np.arange(240,420)]
    hm=HybridStackClassifier('random_forest',random_state=9,threads=1,patience=1,inner_folds=2,
        gru_sequence_length=8,gru_hidden_size=8,gru_num_layers=1,gru_dropout=0.0,gru_learning_rate=0.003,
        gru_batch_size=64,gru_epochs=1,gru_weight_decay=0.0,policy_n_estimators=20,policy_max_depth=4,
        policy_min_samples_leaf=2,policy_max_features=0.7)
    hm.fit_indexed(Xh,yh,allowed,purge_bars=12,embargo_bars=12)
    req(hm.temporal_train_chunks_==2 and hm.inner_purge_bars_==12,'hybrid CPCV-style indexed fit preserves train chunks and purge authority')

    # Factory Discovery and Guided/Audit share one research-region rule.
    df=pd.DataFrame({'signal_time':pd.date_range('2020-01-01',periods=1500,freq='h')})
    cc=json.loads(json.dumps(CFG)); cc.setdefault('agent',{})['discovery_full_oof_only']=True
    pre,retired,meta=research_region(df,cc)
    req(len(pre)==1500 and len(retired)==0 and meta['mode']=='FULL_DISCOVERY_OOF','Factory research region is full immutable Discovery OOF')

    # Scientist must never call an unimplemented hybrid ablation executable.
    h=validate_hypothesis({'kind':'HYBRID_ABLATION','title':'test','payload':{'families':['hybrid_gru_xgboost']}},CFG)
    req(h is not None and h['executable'] is True and h['execution_stage']=='CURRENT_OR_NEXT_MODEL_SEARCH' and h.get('payload',{}).get('pairs'),'dynamic hybrid ablation is now an executable paired experiment, not stale backlog')

    # Kernel semantics are part of the research-contract hash; old research memory cannot alias this release.
    with TemporaryDirectory() as td_contract:
        sp=Path(td_contract)/'snap.csv'; sp.write_text('x\n1\n',encoding='utf-8')
        ch,cp=_research_contract(sp,CFG,{'symbol':'X','period':60})
        req(cp.get('research_kernel_schema')==RESEARCH_KERNEL_SCHEMA and bool(ch),'research contract fingerprints Research Kernel V2 semantics')
    cfsrc=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req('Factory dibuat dengan research-kernel semantics lama' in cfsrc,'legacy Factory resume fails closed across kernel-semantics change')

    # Downstream evaluation failure remains auditable but cannot enter learning_memory.
    with TemporaryDirectory() as td:
        root=Path(td); hsh='contract'; fd=root/'FACTORY_X'; fd.mkdir()
        (fd/'factory_manifest.json').write_text(json.dumps({'research_contract_hash':hsh}),encoding='utf-8')
        _record_downstream_failure(fd,'FORWARD_CHAMPIONSHIP',{'passed':0})
        _,rec=_load_global_contract(root,hsh)
        req(not (rec.get('learning_memory') or {}).get('downstream_failures'),'downstream holdout evidence is excluded from Discovery learning memory')
        req((rec.get('evaluation_vault') or {}).get('last_failure_stage')=='FORWARD_CHAMPIONSHIP','downstream holdout failure remains sealed and auditable')
        req((fd/'evaluation_vault.json').exists(),'Factory writes a local sealed evaluation-vault artifact')

    print('RESEARCH_KERNEL_CONSOLIDATION_SELFTEST PASS')

if __name__=='__main__': main()
