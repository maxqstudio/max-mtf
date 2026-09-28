from __future__ import annotations
import json, tempfile
from pathlib import Path
import joblib
import numpy as np

from research.hybrid_research import HybridStackClassifier, augment_policy_features
from models.models import CandidateSpec, candidate_runtime_contract, generate_initial_population, make_model, predict_model_proba
from research.research_planner import adaptive_family_weights, plan_next_candidates
from models.model_registry import enabled_families, family_registry

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text())


def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)


def params(policy='random_forest'):
    p={
      'gru_sequence_length':8,'gru_hidden_size':8,'gru_num_layers':1,'gru_dropout':0.0,
      'gru_learning_rate':0.002,'gru_batch_size':64,'gru_epochs':1,'gru_weight_decay':0.0,
      'training_memory_months':12,
      'policy_n_estimators':20,'policy_max_depth':4,
    }
    if policy=='random_forest': p.update(policy_min_samples_leaf=2,policy_max_features=0.7)
    elif policy=='xgboost': p.update(policy_learning_rate=0.08,policy_min_child_weight=1.0,policy_subsample=0.9,policy_colsample_bytree=0.9)
    else: p.update(policy_learning_rate=0.08,policy_num_leaves=7,policy_min_child_samples=10,policy_subsample=0.9,policy_colsample_bytree=0.9)
    return p


def main():
    fams=enabled_families(CFG)
    req('hybrid_gru_xgboost' in fams and 'hybrid_gru_lightgbm' in fams,'hybrid GRU→XGB/LGBM enabled by default')
    req('hybrid_gru_random_forest' not in fams,'hybrid RandomForest remains optional by default')
    initial=generate_initial_population(CFG,count=6,round_no=1)
    req(initial and all(s.family in {'hybrid_gru_xgboost','hybrid_gru_lightgbm'} for s in initial),'round-1 discovery uses the two active hybrid families directly')
    active_weights=adaptive_family_weights([],CFG)
    req(set(active_weights)=={'hybrid_gru_xgboost','hybrid_gru_lightgbm'},'hybrid-only planner needs no standalone GRU unlock')
    fake_gru=CandidateSpec('gru','gru_seed',{'sequence_length':16,'hidden_size':32,'num_layers':1,'dropout':0.1,'learning_rate':0.001,'batch_size':64,'epochs':5,'weight_decay':0.0001,'training_memory_months':18})
    fake_board=[{'family':'gru','name':'gru_seed','selection_score':1.0,'cv_gate_pass':False,'median_profit_factor':1.2,'median_expectancy_r':0.1,'median_recovery_factor':1.0,'positive_fold_ratio':0.67,'expectancy_std_r':0.1,'total_fit_seconds':1.0}]
    planned,meta=plan_next_candidates(fake_board,{'gru_seed':fake_gru},CFG,round_no=2,n=12,llm_strategy={'family_priorities':{'hybrid_gru_xgboost':3.0,'hybrid_gru_lightgbm':3.0}})
    req(len(planned)==12 and all(s.family.startswith('hybrid_gru_') for s in planned),'hybrid-only planner preserves the requested round budget')
    req(meta['hybrid_stage_unlocked'] and meta['hybrid_only_mode'] and meta['hybrid_candidates']==len(planned),'planner evidence records first-class hybrid-only mode')
    seeded=[s for s in planned if s.family.startswith('hybrid_gru_')]
    if seeded:
        req(all(8<=int(s.params['gru_sequence_length'])<=24 for s in seeded),'hybrid temporal parameters remain inside registry bounds after GRU seeding')
    reg=family_registry()
    req(all(k in reg for k in ('hybrid_gru_xgboost','hybrid_gru_lightgbm','hybrid_gru_random_forest')),'all three hybrid classical policy families are registered')

    rng=np.random.default_rng(6606); n=420
    X=rng.normal(size=(n,32)).astype(np.float32)
    lag=np.r_[0.0,X[:-1,0]]
    temporal=X[:,0]+0.85*lag
    quality=X[:,3]-0.35*np.abs(X[:,4])
    y=np.where((temporal>0.35)&(quality>-0.6),2,np.where((temporal<-0.35)&(quality>-0.6),0,1)).astype(np.int64)
    req(set(np.unique(y).tolist())=={0,1,2},'hybrid synthetic dataset has SELL/SKIP/BUY')

    m=HybridStackClassifier('random_forest',random_state=7,threads=1,patience=1,**{k:v for k,v in params('random_forest').items() if k!='training_memory_months'})
    m.fit(X[:340],y[:340])
    req(m.stacking_schema_=='OOF_DIRECTION_STACK_V2_PURGED_INDEXED' and 0.2<m.oof_coverage_ratio_<1.0,'classical policy is trained on bounded OOF GRU signals, not in-sample GRU predictions')
    req(m.direction_authority_=='DOWN_UP_ONLY' and m.risk_authority_=='DETERMINISTIC_EA','authority split is GRU direction only + deterministic risk')
    p=predict_model_proba(m,'hybrid_gru_random_forest',X[:340],X[340:])
    req(p.shape==(80,3) and np.isfinite(p).all(),'hybrid emits final SELL/SKIP/BUY probabilities')
    req(np.max(np.abs(p.sum(1)-1.0))<1e-8,'hybrid final probabilities are normalized')
    d=m.direction_model_.predict_proba_with_context(X[:340],X[340:])
    meta=augment_policy_features(X[340:],d)
    req(meta.shape==(80,36),'hybrid classical policy contract is CP32 + four temporal features = 36')
    req(np.allclose(meta[:,34],d[:,1]-d[:,0]),'meta directional feature is P(UP)-P(DOWN)')

    with tempfile.TemporaryDirectory() as td:
        f=Path(td)/'hybrid.joblib'; joblib.dump(m,f); m2=joblib.load(f)
        p2=m2.predict_proba_with_context(X[:340],X[340:])
        req(np.max(np.abs(p2-p))<1e-8,'hybrid frozen joblib roundtrip preserves two-stage inference')

    spec=CandidateSpec('hybrid_gru_xgboost','hybrid_contract',params('xgboost'))
    rc=candidate_runtime_contract(spec,32)
    req(rc['temporal_input']==[1,8,32] and rc['temporal_output']==[1,2] and rc['policy_input']==[1,36] and rc['policy_output']==[1,3],'manifest freezes two-model hybrid runtime shapes')
    req(rc['risk_authority']=='DETERMINISTIC_EA','manifest freezes deterministic risk authority')

    ea=(ROOT.parent/'EA_v1_06'/'Max.mq5').read_text(encoding='utf-8')
    for token in ['InpChampionHybrid','InpChallengerHybrid','RunDirectionOnnx','RunHybridOnnx','HYBRID_POLICY_FEATURE_COUNT 36','InpRiskPct','InpSL_ATR','InpTP_ATR','InpMaxDailyLossPct']:
        req(token in ea,f'EA v1.06 hybrid/risk contract contains {token}')
    req('input_tensor[0][32]=(float)p_down' in ea and 'input_tensor[0][35]=(float)temporal_confidence' in ea,'EA hybrid feature ordering matches Python [CP32,pDown,pUp,direction,confidence]')

    onnx=(ROOT/'models/onnx_export.py').read_text(encoding='utf-8')
    req('export_hybrid' in onnx and 'verify_hybrid_onnx' in onnx and 'challenger_temporal.onnx' not in onnx,'hybrid exporter is generic and parity-aware')
    print('\nHYBRID GRU→CLASSICAL SELF-TEST PASS')

if __name__=='__main__': main()
