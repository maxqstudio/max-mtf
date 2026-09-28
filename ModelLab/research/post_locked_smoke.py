from __future__ import annotations
from core.project_paths import MODELLAB_ROOT
import json, tempfile
from pathlib import Path
import numpy as np
import pandas as pd

from core.contract import FEATURES, CONTRACT_ID
from data.labels import build_labels
from models.model_lab import load_cfg, sha256_file
from factory.supervisor_agent import run_post_locked_policy_discovery
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry

ROOT=MODELLAB_ROOT
EVIDENCE=ROOT/'evidence/history/POST_LOCKED_SMOKE_v0_6_6.json'

def main():
    rng=np.random.default_rng(123)
    n=3200
    ret=rng.normal(0,0.35,n)
    close=2000+np.cumsum(ret)
    high=close+np.abs(rng.normal(.45,.2,n)); low=close-np.abs(rng.normal(.45,.2,n)); open_=np.r_[close[0],close[:-1]]
    times=pd.date_range('2020-01-01',periods=n,freq='h')
    raw=pd.DataFrame({'contract':CONTRACT_ID,'signal_time':times,'decision_bar_time':times,'symbol':'XAUUSD','period':60,
        'open':open_,'high':high,'low':low,'close':close,'atr':1.0,'decision_bid':close,'decision_ask':close+0.05,
        'spread_points':5.0,'sl_atr':1.8,'tp_atr':2.7,'max_hold_bars':24,'consensus':0.8})
    for f in FEATURES: raw[f]=rng.normal(0,0.3,n)
    raw['adx_scaled']=rng.uniform(0,0.5,n); raw['range_atr']=high-low; raw['rule_meta_score']=np.clip(rng.normal(0,.5,n),-1,1)
    future=np.roll(close,-24)-close
    raw['ret1_atr']=np.tanh(future/2)+rng.normal(0,.2,n)

    with tempfile.TemporaryDirectory() as td0:
        td=Path(td0); csv=td/'train.csv'; raw.to_csv(csv,sep=';',index=False)
        cfg=load_cfg(ROOT/'config'/'config.json'); cfg,_=synchronize_cfg_with_dataset_geometry(cfg,raw,require_runtime_authority_match=False); cfg['agent']['policy_discovery']['max_policies']=12; cfg['agent']['llm']['enabled']=False
        # Smoke purpose: make qualification deliberately easy so this test exercises the
        # post-locked recovery state transition, not production research strictness.
        # v1.3.2 uses stage-specific gate_kpis plus AUTO trade-sample authority, so the
        # fixture must relax the Discovery profile explicitly rather than mutating only
        # the legacy acceptance bridge. Production defaults remain untouched.
        a=cfg['acceptance']; a.update({
            'cv_min_validation_trades':1,'cv_min_median_profit_factor':0.0,'cv_min_median_expectancy_r':-10.0,'cv_min_worst_expectancy_r':-10.0,
            'cv_min_positive_fold_ratio':0.0,'cv_min_median_recovery_factor':-10.0,'cv_min_worst_fold_recovery_factor':-10.0,
            'max_drawdown_r':1e9,'cv_max_worst_fold_drawdown_r':1e9,'min_positive_month_ratio':0.0,'min_positive_quarter_ratio':0.0,
            'max_dominant_positive_regime_share':1.0,'max_top10_win_profit_share':1.0,'sensitivity_min_profitable_ratio':0.0,
            'stress_min_expectancy_r':{'spread_x1.25':-10.0,'spread_x1.50':-10.0},'schema':'KPI_V5_HIERARCHICAL'})
        disc=cfg['gate_kpis']['discovery']
        disc.update({
            'cv_min_median_profit_factor':0.0,'cv_min_overall_expectancy_r':-10.0,'cv_min_median_expectancy_r':-10.0,'cv_min_worst_expectancy_r':-10.0,
            'cv_min_positive_fold_ratio':0.0,'cv_min_median_recovery_factor':-10.0,'cv_min_worst_fold_recovery_factor':-10.0,
            'max_drawdown_r':1e9,'cv_max_worst_fold_drawdown_r':1e9,'min_positive_month_ratio':0.0,'min_positive_quarter_ratio':0.0,
            'max_dominant_positive_regime_share':1.0,'max_top10_win_profit_share':1.0,'sensitivity_min_profitable_ratio':0.0,
            'stress_min_expectancy_r':{'spread_x1.25':-10.0,'spread_x1.50':-10.0},
        })
        for spec0 in (disc.get('risk_kpis') or {}).values():
            if isinstance(spec0,dict): spec0['enabled']=False
        cfg['trade_sample_policy']['base_h1_trades_per_month']=1
        cfgp=td/'cfg.json'; cfgp.write_text(json.dumps(cfg),encoding='utf-8')
        src=td/'runs'/'SOURCE'; src.mkdir(parents=True)
        (src/'run_config.json').write_text(json.dumps(cfg),encoding='utf-8')
        build_labels(raw,cfg).to_csv(src/'labeled_dataset.csv',index=False)
        manifest={'run_id':'SOURCE','status':'REJECTED','cv_acceptance':{'passed':True},'agent':{'locked_test_opened_once':True},
            'locked_test_trading':{'profit_factor':0.8},'source_csv_sha256':sha256_file(csv),'model_family':'xgboost','model_name':'smoke_xgb',
            'hyperparameters':{'n_estimators':40,'max_depth':2,'learning_rate':0.05,'min_child_weight':5.0,'subsample':0.8,'colsample_bytree':0.8},
            'take_threshold':0.65,'cv_selection':{}}
        (src/'model_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        res=run_post_locked_policy_discovery(src,csv,cfgp,td/'runs')
        out=Path(res['run']); om=json.loads((out/'model_manifest.json').read_text(encoding='utf-8'))
        assert res['status']=='POLICY_CV_PASS_NEEDS_FRESH_HOLDOUT'
        assert om['retired_locked_test_accessed'] is False
        assert (out/'policy_leaderboard.json').exists()
        assert (out/'frozen_policy.csv').exists()
        assert om['source_run_id']=='SOURCE'
        assert om['decision_policy']
    EVIDENCE.write_text(json.dumps({'schema':'POST_LOCKED_SMOKE_V1','status':'PASS','first_failed_gate':None,
        'checks':['SOURCE_HASH_VERIFIED','FROZEN_MODEL','OOF_POLICY_SEARCH','RETIRED_LOCKED_NOT_ACCESSED','POLICY_CV_PASS','FROZEN_POLICY_ARTIFACT']},indent=2),encoding='utf-8')
    print('POST-LOCKED OOF SMOKE PASS')

if __name__=='__main__':
    try: main()
    except Exception as e:
        EVIDENCE.write_text(json.dumps({'schema':'POST_LOCKED_SMOKE_V1','status':'FAIL','first_failed_gate':str(e)},indent=2),encoding='utf-8')
        raise
