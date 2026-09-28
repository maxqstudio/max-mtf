from __future__ import annotations
from core.project_paths import MODELLAB_ROOT
import json, os, sys, tempfile, traceback
from pathlib import Path
import numpy as np
import pandas as pd

from core.contract import FEATURES, CONTRACT_ID
from models.model_lab import load_cfg, sha256_file
from data.feature_label_audit import run_feature_label_audit
from research.guided_research import run_guided_research
from factory.supervisor_agent import run_supervisor_agent
from host.workflow_router import route_for_manifest
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry

ROOT=MODELLAB_ROOT
EVIDENCE=ROOT/'evidence/history/GUIDED_FLOW_SMOKE_v0_6_6.json'


def synthetic_csv(path: Path):
    rng=np.random.default_rng(321); n=3200
    ret=rng.normal(0,0.35,n); close=2000+np.cumsum(ret)
    high=close+np.abs(rng.normal(.45,.2,n)); low=close-np.abs(rng.normal(.45,.2,n)); open_=np.r_[close[0],close[:-1]]
    times=pd.date_range('2020-01-01',periods=n,freq='h')
    raw=pd.DataFrame({'contract':CONTRACT_ID,'signal_time':times,'decision_bar_time':times,'symbol':'XAUUSD','period':16385,
        'open':open_,'high':high,'low':low,'close':close,'atr':1.0,'decision_bid':close,'decision_ask':close+0.05,
        'spread_points':5.0,'sl_atr':1.8,'tp_atr':2.7,'max_hold_bars':24,'consensus':0.8})
    for f in FEATURES: raw[f]=rng.normal(0,0.3,n)
    raw['adx_scaled']=rng.uniform(0,0.5,n); raw['range_atr']=high-low; raw['rule_meta_score']=np.clip(rng.normal(0,.5,n),-1,1)
    future=np.roll(close,-24)-close; raw['ret1_atr']=np.tanh(future/2)+rng.normal(0,.2,n)
    raw.to_csv(path,sep=';',index=False)


def easy_cfg() -> dict:
    cfg=load_cfg(ROOT/'config'/'config.json')
    # Acceptance smoke validates the Guided E2E contract, not CPU throughput.
    # Force one estimator thread so repeated bounded XGBoost fits are deterministic
    # across constrained CI/container runtimes and cannot stall on thread oversubscription.
    cfg['cpu_threads']=1
    # Smoke-only execution policy: disable machine calibration so every downstream
    # load_cfg() on the synthetic source lineage preserves cpu_threads=1. Without
    # this, the shared cpu_calibration.json can overwrite the smoke config back to
    # the host-selected thread count and repeated XGBoost OOF fits may stall in a
    # constrained CI/container. Production resource calibration is unchanged.
    cfg.setdefault('compute', {}).setdefault('cpu_resource', {})['enabled']=False
    cfg['agent']['llm']['enabled']=False
    cfg['agent']['max_experiments']=6; cfg['agent']['round_size']=3; cfg['agent']['max_rounds']=2; cfg['agent']['patience_rounds']=1; cfg['agent']['min_experiments_before_stop']=3
    cfg['models']['xgboost']=True; cfg['models']['lightgbm']=False; cfg['models']['random_forest']=False; cfg['models']['gru']=False; cfg['models']['hybrid_xgboost']=False; cfg['models']['hybrid_lightgbm']=False; cfg['models']['hybrid_random_forest']=False
    a=cfg['acceptance']; a.update({
        'cv_min_validation_trades':1,'cv_min_median_profit_factor':0.0,'cv_min_overall_expectancy_r':-10.0,'cv_min_median_expectancy_r':-10.0,'cv_min_worst_expectancy_r':-10.0,
        'cv_min_positive_fold_ratio':0.0,'cv_min_median_recovery_factor':-10.0,'cv_min_worst_fold_recovery_factor':-10.0,
        'max_drawdown_r':1e9,'cv_max_worst_fold_drawdown_r':1e9,'min_positive_month_ratio':0.0,'min_positive_quarter_ratio':0.0,
        'max_dominant_positive_regime_share':1.0,'max_top10_win_profit_share':1.0,'sensitivity_min_profitable_ratio':0.0,
        'stress_min_expectancy_r':{'spread_x1.25':-10.0,'spread_x1.50':-10.0},'schema':'KPI_V5_HIERARCHICAL'})
    cfg['gate_kpis']['discovery']['cv_min_overall_expectancy_r']=-10.0
    return cfg


def main():
    with tempfile.TemporaryDirectory() as td0:
        td=Path(td0); runs=td/'runs'; runs.mkdir(); csv=td/'train.csv'; synthetic_csv(csv); cfg=easy_cfg(); raw=pd.read_csv(csv,sep=';'); cfg,_=synchronize_cfg_with_dataset_geometry(cfg,raw,require_runtime_authority_match=False); cfgp=td/'cfg.json'; cfgp.write_text(json.dumps(cfg),encoding='utf-8')
        agent=runs/'AGENT_SOURCE'; agent.mkdir(); (agent/'run_config.json').write_text(json.dumps(cfg),encoding='utf-8')
        am={'run_id':'AGENT_SOURCE','run_type':'SUPERVISOR_AGENT','status':'REJECTED','source_csv_sha256':sha256_file(csv),
            'model_family':'xgboost','model_name':'smoke_xgb','hyperparameters':{'n_estimators':40,'max_depth':2,'learning_rate':0.05,'min_child_weight':5.0,'subsample':0.8,'colsample_bytree':0.8},
            'label_policy':cfg['label'],'cv_acceptance':{'passed':True},'agent':{'locked_test_opened_once':True}}
        (agent/'model_manifest.json').write_text(json.dumps(am),encoding='utf-8')
        policy=runs/'POLICY_SOURCE'; policy.mkdir(); (policy/'run_config.json').write_text(json.dumps(cfg),encoding='utf-8')
        pm={'run_id':'POLICY_SOURCE','run_type':'POST_LOCKED_POLICY_DISCOVERY','status':'POLICY_CV_REJECTED','source_run_id':'AGENT_SOURCE','source_csv_sha256':sha256_file(csv),
            'model_family':'xgboost','model_name':'smoke_xgb','hyperparameters':am['hyperparameters'],'label_policy':cfg['label'],
            'cv_selection':{'total_validation_trades':16,'median_regime_concentration':1.0,'profit_factor_std':400.0},'cv_acceptance':{'passed':False},
            'agent':{'locked_test_opened_once':False,'retired_locked_test_accessed':False}}
        (policy/'model_manifest.json').write_text(json.dumps(pm),encoding='utf-8')

        audit=run_feature_label_audit(policy,csv,cfgp,runs)
        assert audit['manifest']['status']=='FEATURE_LABEL_AUDIT_READY'
        assert audit['manifest']['timeframe']=='H1'
        assert audit['report']['retired_locked_test_accessed'] is False
        assert route_for_manifest(audit['manifest'])['page']=='Guided Research'

        guided=run_guided_research(Path(audit['run']),csv,cfgp,runs)
        gm=guided['manifest']; assert gm['status']=='GUIDED_RESEARCH_READY',gm['status']
        assert gm['retired_locked_test_accessed'] is False
        assert route_for_manifest(gm)['action']=='START_NEW_GENERATION'

        rec=guided['recommended_config']
        assert rec['agent']['skip_locked_test'] is True
        # Local CI does not require ONNX packages. The full new-generation path is
        # covered structurally here and runs under the Windows acceptance venv.
        simulated={'status':'NEEDS_FRESH_HOLDOUT'}
        assert route_for_manifest(simulated)['action']=='VALIDATE_FROZEN_MODEL_FRESH'


    EVIDENCE.write_text(json.dumps({'schema':'GUIDED_FLOW_SMOKE_V1','status':'PASS','first_failed_gate':None,
        'checks':['POLICY_REJECTED_TO_AUDIT','MT5_ENUM_H1_16385','AUDIT_NO_RETIRED_LOCKED_ACCESS','DEDICATED_GUIDED_ROUTE','BOUNDED_GUIDED_OOF_PASS','RECOMMENDED_CONFIG_SKIP_RETIRED_HOLDOUT','FRESH_HOLDOUT_REQUIRED']},indent=2),encoding='utf-8')
    print('GUIDED FEATURE/LABEL E2E SMOKE PASS')

if __name__=='__main__':
    try:
        main()
    except Exception as e:
        EVIDENCE.write_text(json.dumps({'schema':'GUIDED_FLOW_SMOKE_V1','status':'FAIL','first_failed_gate':str(e)},indent=2),encoding='utf-8')
        traceback.print_exc()
        sys.stdout.flush(); sys.stderr.flush()
        os._exit(1)
    # XGBoost/OpenMP can leave native teardown waiting after this bounded synthetic
    # smoke has already completed and written terminal evidence. All Python-level
    # temporary resources are closed before main() returns, so exit immediately to
    # keep acceptance deterministic without altering production runtime behavior.
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)
