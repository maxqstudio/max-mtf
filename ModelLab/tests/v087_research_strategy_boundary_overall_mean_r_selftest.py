from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry
from data.labels import build_labels
from core.temporal_index import contract_from_cfg
from research.kpi import walk_forward_acceptance


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def frame(n=96,sl=2.6,tp=4.2,hold=54):
    x=np.arange(n,dtype=float)
    return pd.DataFrame({
        'high':100+x*.01+1.0,'low':100+x*.01-1.0,'close':100+x*.01,
        'atr':np.ones(n),'decision_bid':100+x*.01,'decision_ask':100+x*.01+.01,
        'sl_atr':np.full(n,sl),'tp_atr':np.full(n,tp),'max_hold_bars':np.full(n,hold),
    })


def good_cv():
    return {
        'auto_min_validation_trades':90,'total_validation_trades':180,'total_validation_r':36.0,'overall_expectancy_r':.20,
        'median_max_drawdown_r':5,'worst_fold_max_drawdown_r':7,'median_recovery_factor':3,'worst_fold_recovery_factor':2,
        'median_profit_factor':2,'median_expectancy_r':.20,'worst_expectancy_r':.01,'positive_fold_ratio':1.0,
        'median_positive_month_ratio':.8,'median_positive_quarter_ratio':.8,'median_regime_concentration':.4,'median_top10_win_profit_share':.3,
        'median_stress_x1_25_expectancy_r':.3,'median_stress_x1_50_expectancy_r':.2,'median_threshold_plateau':.9,
        'median_sharpe_ratio':.5,'median_sortino_ratio':.6,'median_calmar_mar_ratio':1.2,
        'median_probabilistic_sharpe_ratio':.98,'median_deflated_sharpe_ratio':.98,'median_ulcer_index_r':4.0,'median_daily_cvar95_r':-1.5,
    }


def main():
    cfg=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
    req({'min_edge_r','min_margin_r','ambiguous_policy'}.issubset(set(cfg['label'])) and all(k not in cfg['label'] for k in ('sl_atr','tp_atr','horizon_bars','max_hold_bars')), 'canonical Model Research label policy contains no SL/TP/MaxHold duplicate authority')
    df=frame()
    effective,g=synchronize_cfg_with_dataset_geometry(cfg,df,require_runtime_authority_match=False)
    req(g['max_hold_bars']==54 and effective['strategy_geometry']['max_hold_bars']==54,'CP32 strategy geometry becomes read-only effective runtime authority')
    req(all(k not in effective['label'] for k in ('sl_atr','tp_atr','horizon_bars')),'effective label policy remains strategy-geometry free')
    t=contract_from_cfg(effective)
    req(t.label_horizon_bars==54 and t.purge_bars>=54 and t.embargo_bars>=54,'purge and embargo automatically follow upstream MaxHold')
    req(len(build_labels(df,effective))>0,'labels consume CP32 SL/TP/MaxHold without duplicate research knobs')

    cv=good_cv(); acc=walk_forward_acceptance(cv,effective)
    req(acc['passed'],'Overall + Median + Worst Mean R good candidate passes expectancy trio')
    for key,value,gate in [
        ('overall_expectancy_r',.05,'CV_OVERALL_EXPECTANCY'),
        ('median_expectancy_r',.05,'CV_MEDIAN_EXPECTANCY'),
        ('worst_expectancy_r',-.02,'CV_WORST_EXPECTANCY'),
    ]:
        bad=deepcopy(cv); bad[key]=value
        out=walk_forward_acceptance(bad,effective)
        req((not out['passed']) and gate in out['reasons'],f'{gate} independently mandatory')

    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('WFA overall Mean R' in app and 'cv_min_overall_expectancy_r' in app,'Overall Mean R threshold is editable in Research KPI UI')
    req('Horizon · Strategy locked' not in app and 'SL × ATR · Strategy locked' not in app and 'TP × ATR · Strategy locked' not in app,'Research UI exposes no duplicate Strategy Optimizer geometry fields')
    print('V087_RESEARCH_STRATEGY_BOUNDARY_OVERALL_MEAN_R_PASS')

if __name__=='__main__': main()
