from __future__ import annotations
from core.project_paths import MODELLAB_ROOT
import json, tempfile
from pathlib import Path
import numpy as np, pandas as pd

from core.contract import FEATURES, CONTRACT_ID
from data.feature_label_audit import run_feature_label_audit
from models.model_lab import sha256_file
from host.preflight import period_label

ROOT=MODELLAB_ROOT

def synth_csv(path: Path, n=1800):
    rng=np.random.default_rng(903)
    close=100+np.cumsum(rng.normal(0,0.55,n))
    high=close+np.abs(rng.normal(0.7,0.30,n)); low=close-np.abs(rng.normal(0.7,0.30,n)); op=np.r_[close[0],close[:-1]]
    df=pd.DataFrame({
        'contract':CONTRACT_ID,'signal_time':pd.date_range('2022-01-01',periods=n,freq='h'),
        'decision_bar_time':pd.date_range('2022-01-01',periods=n,freq='h'),'symbol':'SMOKE','period':16385,
        'open':op,'high':high,'low':low,'close':close,'atr':1.0,'decision_bid':close,'decision_ask':close+0.05,
        'spread_points':5.0,'sl_atr':1.8,'tp_atr':2.7,'max_hold_bars':24,'consensus':0.8,
    })
    for f in FEATURES: df[f]=rng.normal(0,1,n)
    # Give the frozen model a little stable structure without making the smoke depend on profitable trading.
    df['ret1_atr']=np.r_[0,np.diff(close)]
    df['ret3_atr']=pd.Series(close).diff(3).fillna(0).to_numpy()
    df['ret6_atr']=pd.Series(close).diff(6).fillna(0).to_numpy()
    df['adx_scaled']=np.clip(rng.normal(.25,.08,n),0,1); df['range_atr']=high-low
    df.to_csv(path,sep=';',index=False)


def main():
    cfg=json.loads((ROOT/'config'/'config.json').read_text())
    cfg['cpu_threads']=2; cfg['agent']['feature_label_audit']['max_label_candidates']=2
    with tempfile.TemporaryDirectory() as td:
        base=Path(td); csv=base/'training.csv'; synth_csv(csv)
        config=base/'config.json'; config.write_text(json.dumps(cfg,indent=2))
        policy=base/'runs'/'POLICY_SMOKE'; policy.mkdir(parents=True)
        (policy/'run_config.json').write_text(json.dumps(cfg,indent=2))
        manifest={
            'run_id':'POLICY_SMOKE','run_type':'POST_LOCKED_POLICY_DISCOVERY','status':'POLICY_CV_REJECTED',
            'source_locked_test_retired':True,'retired_locked_test_accessed':False,
            'source_csv_sha256':sha256_file(csv),'dataset_provenance':{'symbol':'SMOKE','period':16385,'timeframe':'H1'},
            'model_family':'random_forest','model_name':'rf_smoke','hyperparameters':{'n_estimators':20,'max_depth':6,'min_samples_leaf':5,'max_features':0.5},
            'cv_selection':{'total_validation_trades':16,'profit_factor_std':467.74,'median_regime_concentration':1.0,'fold_diagnostics':[{'trades':10},{'trades':1},{'trades':5}]}
        }
        (policy/'model_manifest.json').write_text(json.dumps(manifest,indent=2))
        res=run_feature_label_audit(policy,csv,config,base/'runs')
        out=Path(res['run']); m=json.loads((out/'model_manifest.json').read_text()); report=json.loads((out/'audit_report.json').read_text())
        assert m['run_type']=='FEATURE_LABEL_AUDIT'
        assert m['retired_locked_test_accessed'] is False
        assert m['timeframe']=='H1' and period_label(16385)=='H1'
        assert report['overselection_risk']['severity']=='HIGH'
        assert (out/'feature_audit.csv').exists() and (out/'label_audit.csv').exists()
        print('FEATURE-LABEL AUDIT SMOKE PASS')

if __name__=='__main__': main()
