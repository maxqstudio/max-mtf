from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from strategy.strategy_geometry import extract_dataset_strategy_geometry, synchronize_cfg_with_dataset_geometry, persist_optimizer_champion_authority
from data.labels import build_labels
from research.scientific_hypotheses import validate_hypothesis


def req(cond,msg):
    if not cond: raise AssertionError(msg)


def frame(sl=2.6,tp=4.2,hold=54,n=80):
    x=np.arange(n,dtype=float)
    return pd.DataFrame({
        'high':100+x*.01+1.0,'low':100+x*.01-1.0,'close':100+x*.01,
        'atr':np.ones(n),'decision_bid':100+x*.01,'decision_ask':100+x*.01+.01,
        'sl_atr':np.full(n,sl),'tp_atr':np.full(n,tp),'max_hold_bars':np.full(n,hold),
    })


def main():
    cfg={'label':{'min_edge_r':.15,'min_margin_r':.1,'ambiguous_policy':'drop'},'split':{'purge_bars':24,'embargo_bars':24}}
    df=frame()
    g=extract_dataset_strategy_geometry(df)
    req(g['sl_atr']==2.6 and g['tp_atr']==4.2 and g['max_hold_bars']==54,'dataset geometry extraction')
    synced,_=synchronize_cfg_with_dataset_geometry(cfg,df,require_runtime_authority_match=False)
    req(all(k not in synced['label'] for k in ('horizon_bars','sl_atr','tp_atr')),'Model Research label policy must not duplicate execution geometry')
    req(synced['strategy_geometry']['sl_atr']==2.6 and synced['strategy_geometry']['tp_atr']==4.2 and synced['strategy_geometry']['max_hold_bars']==54,'runtime config inherits dataset execution geometry under strategy authority')
    req(synced['split']['purge_bars']==54 and synced['split']['embargo_bars']==54,'temporal guards auto-follow MaxHold')
    lab=build_labels(df,synced)
    req(len(lab)>0,'synchronized geometry should produce labels')
    mixed=df.copy(); mixed.loc[10,'sl_atr']=1.8
    try: extract_dataset_strategy_geometry(mixed)
    except ValueError as e: req('MIXED_DATASET' in str(e),'mixed dataset must fail closed')
    else: raise AssertionError('mixed geometry silently accepted')

    h=validate_hypothesis({'kind':'LABEL_GEOMETRY','payload':{'sl_atr':3.1,'tp_atr':5.0,'horizon_bars':72,'min_edge_r':.2}},synced,1)
    req(h and h['payload']=={'min_edge_r':.2},'Scientist must not mutate execution geometry')

    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'authority.json'
        obj=persist_optimizer_champion_authority(params={'InpSL_ATR':2.6,'InpTP_ATR':4.2,'InpMaxHoldBars':54},ea_sha256='a'*64,job_id='job',champion_pass=9182,path=p)
        req(obj['geometry']=={'sl_atr':2.6,'tp_atr':4.2,'max_hold_bars':54},'champion authority geometry')
        req(json.loads(p.read_text())['champion_pass']==9182,'authority persistence')

    ea=(ROOT.parent/'EA_v1_06'/'Max.mq5').read_text(encoding='utf-8')
    req('InpTrainingFile           = "Max_Training.csv"' in ea,'canonical Max training filename')
    req('InpTelemetryFile         = "Max_Telemetry.csv"' in ea,'canonical Max telemetry filename')
    req('InpOptimizerMetricsFile   = "Max_metrics.csv"' in ea,'canonical Max optimizer metrics filename')
    req("ComplexPolicy_ONNX_Telemetry.csv" not in ea,'legacy telemetry filename removed from Max EA runtime')
    req('TesterStatistics(STAT_TRADES)' in ea and 'MAX_EXPECTANCY_R_FAIL_CLOSED' in ea,'R accounting parity fail-closed')
    worker=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
    req('persist_optimizer_champion_authority' in worker,'Optimizer Champion must persist Python strategy authority')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('Horizon · Strategy locked' not in app and 'SL × ATR · Strategy locked' not in app and 'TP × ATR · Strategy locked' not in app,'Model Research UI removes duplicate Strategy Optimizer geometry controls')
    audit=(ROOT/'data/feature_label_audit.py').read_text(encoding='utf-8')
    req('Only classification separation thresholds may vary' in audit,'feature/label audit must freeze execution geometry')
    print('V085_STRATEGY_GEOMETRY_SYNC_PASS')

if __name__=='__main__': main()
