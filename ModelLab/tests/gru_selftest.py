from __future__ import annotations
import json, tempfile
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

from research.gru_research import GRUClassifier, sequence_tensor, sequence_tensor_with_context
from models.models import CandidateSpec, make_model, candidate_input_shape
from models.model_registry import enabled_families, family_registry
from models.model_lab import apply_candidate_memory
from core.contract import FEATURES
from data.feature_label_audit import _importance_stability

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text())

def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    req(CFG['models'].get('gru') is False,'standalone GRU retained but dormant by default')
    req('gru' not in enabled_families(CFG) and 'gru' in family_registry(),'standalone GRU remains registered as a reserve temporal family')
    spec=CandidateSpec('gru','gru_selftest',{'sequence_length':8,'hidden_size':16,'num_layers':1,'dropout':0.0,'learning_rate':0.002,'batch_size':64,'epochs':3,'weight_decay':0.0})
    req(candidate_input_shape(spec,32)==[1,8,32],'GRU manifest input contract is [1,T,32]')
    rng=np.random.default_rng(7); n=360
    X=rng.normal(size=(n,32)).astype(np.float32)
    # learnable temporal signal using current + lagged feature
    lag=np.r_[0.0,X[:-1,0]]; z=X[:,0]+0.7*lag
    y=np.where(z>0.45,2,np.where(z<-0.45,0,1)).astype(np.int64)
    # guarantee classes
    req(set(np.unique(y).tolist())=={0,1,2},'synthetic GRU dataset has all three classes')
    seq=sequence_tensor(X,8)
    req(seq.shape==(n,8,32),'causal sequence builder emits [N,T,32]')
    req(np.allclose(seq[0,0],X[0]) and np.allclose(seq[0,-1],X[0]),'warmup padding matches EA oldest-row policy')
    ctx=sequence_tensor_with_context(X[:200],X[200:205],8)
    req(np.allclose(ctx[0,-1],X[200]) and np.allclose(ctx[0,-2],X[199]),'validation sequence uses causal pre-fold history')
    m=make_model(spec,CFG); m.fit(X,y); p=m.predict_proba(X[-40:])
    req(p.shape==(40,3),'GRU predict_proba emits [N,3]')
    req(np.isfinite(p).all() and np.max(np.abs(p.sum(1)-1.0))<1e-5,'GRU probabilities are finite and normalized')
    with tempfile.TemporaryDirectory() as td:
        f=Path(td)/'gru.joblib'; joblib.dump(m,f); m2=joblib.load(f); p2=m2.predict_proba(X[-20:])
        req(np.max(np.abs(p2-m.predict_proba(X[-20:])))<1e-7,'GRU joblib roundtrip preserves frozen model')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('GRU Temporal' in app and 'hybrid_xgboost' in app,'GRU + hybrid UI toggles are enabled')
    ea=(ROOT.parent/'EA_v1_06'/'Max.mq5').read_text(encoding='utf-8')
    for token in ['InpChampionSequenceLength','InpChallengerSequenceLength','PushFeatureHistory(features)','input_shape3[3]','RunOnnx(g_onnxChampion,features,InpChampionSequenceLength)']:
        req(token in ea,f'EA v1.06 standalone sequence contract contains {token}')
    req(0.90 in [float(x) for x in CFG['deployment']['take_threshold_grid']],'base CV searches high-selectivity coverage through 0.90')
    registry=family_registry()
    req(all('training_memory_months' in (v.get('search') or {}) for v in registry.values()),'every deployable family searches training-memory months')
    # The outer operator source window remains fixed; candidate memory may only shrink
    # the supplied research dataframe from its right edge.
    mem_df=pd.DataFrame({'signal_time':pd.date_range('2024-01-01',periods=5000,freq='2h')})
    mem_spec=CandidateSpec('gru','memory_test',dict(spec.params,training_memory_months=6))
    mem_slice,mem_info=apply_candidate_memory(mem_df,mem_spec,CFG)
    req(bool(mem_info.get('applied')) and 400<=len(mem_slice)<len(mem_df),'integrated training-memory search applies inside the supplied research window')
    req(pd.Timestamp(mem_slice['signal_time'].max())==pd.Timestamp(mem_df['signal_time'].max()),'training-memory slice is causal and anchored to research-window end')
    ml=(ROOT/'models/model_lab.py').read_text(encoding='utf-8')
    req('trade_coverage_ratio' in ml and 'hostile_regimes' in ml and 'failed_survival_gates' in ml,'fold forensics + coverage diagnostics are wired')
    audit=(ROOT/'data/feature_label_audit.py').read_text(encoding='utf-8')
    req('bounded permutation importance' in audit.lower() and 'log_loss' in audit,'GRU Feature/Label Audit has bounded permutation-importance fallback')
    audit_cfg=json.loads(json.dumps(CFG)); audit_cfg['split']['walk_forward_folds']=1; audit_cfg['split']['purge_bars']=4; audit_cfg['split']['min_train_rows']=200; audit_cfg['models']['gru_patience']=1
    na=430; Xa=rng.normal(size=(na,len(FEATURES))).astype(np.float32)
    audit_df=pd.DataFrame(Xa,columns=FEATURES); audit_df['signal_time']=pd.date_range('2026-01-01',periods=na,freq='h')
    za=Xa[:,0]+0.6*np.r_[0.0,Xa[:-1,1]]; audit_df['label']=np.where(za>0.45,2,np.where(za<-0.45,0,1)).astype(np.int64)
    audit_spec=CandidateSpec('gru','audit_smoke',{'sequence_length':8,'hidden_size':8,'num_layers':1,'dropout':0.0,'learning_rate':0.002,'batch_size':64,'epochs':1,'weight_decay':0.0,'training_memory_months':6})
    imp=_importance_stability(audit_df,audit_spec,audit_cfg)
    req(len(imp)==len(FEATURES) and any(float(x['mean_importance'])>0 for x in imp),'real GRU feature-audit permutation path emits non-zero bounded importance')
    print('\nGRU + SELECTIVITY + WINDOW DISCOVERY SELF-TEST PASS')

if __name__=='__main__': main()
