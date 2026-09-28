from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def req(x,m):
    if not x: raise AssertionError(m)


def _base_cfg():
    cfg=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
    return cfg


def _sim_df(n=8):
    t=pd.date_range('2026-01-01',periods=n,freq='h')
    return pd.DataFrame({
        'signal_time':t,'source_row_id':np.arange(n),
        'high':np.full(n,100.2),'low':np.full(n,99.8),'close':np.full(n,100.0),
        'atr':np.full(n,10.0),'decision_bid':np.full(n,100.0),'decision_ask':np.full(n,100.1),
        'spread_points':np.full(n,10.0),'range_atr':np.full(n,0.5),'consensus':np.full(n,0.9),
        'rule_meta_score':np.zeros(n),
    })


def main():
    cfg=_base_cfg()

    # SCI-01: exact promoted Strategy execution-policy authority overwrites stale local copies.
    import strategy.strategy_geometry as sg
    with tempfile.TemporaryDirectory() as td:
        ap=Path(td)/'strategy_authority.json'
        auth={
            'geometry':{'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':54},
            'execution_policy':{'entry_threshold':0.18,'exit_reverse_threshold':0.25,'min_consensus':0.70,
                                'shock_halt_range_atr':3.5,'max_spread_points':45.0,'onnx_blend':0.65},
        }
        ap.write_text(json.dumps(auth),encoding='utf-8')
        old=sg.RUNTIME_AUTHORITY; sg.RUNTIME_AUTHORITY=ap
        try:
            d=pd.DataFrame({'sl_atr':[3.2]*2,'tp_atr':[4.8]*2,'max_hold_bars':[54]*2})
            stale=deepcopy(cfg); stale['deployment'].update({'entry_threshold':0.34,'min_consensus':0.30,'shock_halt_range_atr':4.0})
            synced,_=sg.synchronize_cfg_with_dataset_geometry(stale,d,require_runtime_authority_match=True)
            req(synced['deployment']['entry_threshold']==0.18 and synced['deployment']['min_consensus']==0.70 and synced['deployment']['shock_halt_range_atr']==3.5,'Strategy execution policy did not override stale Research values')
            req(synced['split']['purge_bars']>=54 and synced['split']['embargo_bars']>=54,'MaxHold temporal guard not enforced')
        finally:
            sg.RUNTIME_AUTHORITY=old

    # SCI-02/03: event-state replay is single-position and supports reverse exit.
    from research.evaluation import simulate_execution_from_actions
    scfg=deepcopy(cfg); scfg['strategy_geometry']={'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':3}; scfg['deployment']['exit_reverse_threshold']=0.25
    df=_sim_df(8); desired=np.asarray([1,1,-1,0,0,0,0,0],dtype=np.int8); final=np.asarray([1.0,1.0,-1.0,0,0,0,0,0],dtype=float)
    accepted,r,meta=simulate_execution_from_actions(desired,final,df,scfg)
    req(meta['production_parity'] and meta['single_position'],'Stateful simulator parity metadata missing')
    req(meta['exit_counts']['REVERSE_EXIT']>=1,'Reverse exit was not simulated')
    req(int(np.count_nonzero(accepted))==2 and accepted[1]==0,'Overlapping same-symbol entry was not suppressed')

    # SCI-05/06: labels preserve row chronology/context and mask structurally impossible targets.
    from data.labels import build_labels
    lcfg=deepcopy(scfg); lcfg['strategy_geometry']={'sl_atr':3.2,'tp_atr':4.8,'max_hold_bars':3}
    ldf=_sim_df(12); ldf['sl_atr']=3.2; ldf['tp_atr']=4.8; ldf['max_hold_bars']=3
    # Make row 2 impossible by consensus while retaining it as sequence context.
    ldf.loc[2,'consensus']=0.1
    lab=build_labels(ldf,lcfg)
    req(len(lab)==len(ldf),'Label builder physically dropped context rows')
    req(lab['source_row_id'].tolist()==list(range(len(ldf))),'source_row_id chronology was not preserved')
    req(float(lab.loc[2,'supervised_weight'])==0.0 and bool(lab.loc[2,'label_context_only']),'Non-executable row still has supervised authority')

    # KPI-02: ranking schema is fixed 100 and independent from Owner hard-gate toggles.
    from research.kpi import walk_forward_composite_score
    cv={
        'median_max_drawdown_r':8,'worst_fold_max_drawdown_r':12,'median_recovery_factor':2,'worst_fold_recovery_factor':1.2,
        'median_profit_factor':1.4,'overall_expectancy_r':0.2,'median_expectancy_r':0.18,'worst_expectancy_r':0.05,
        'positive_fold_ratio':1.0,'expectancy_std_r':0.05,'profit_factor_std':0.1,'total_validation_trades':120,'auto_min_validation_trades':90,
        'median_stress_x1_25_expectancy_r':0.15,'median_stress_x1_50_expectancy_r':0.10,'median_threshold_plateau':0.8,
        'median_positive_month_ratio':0.6,'median_positive_quarter_ratio':0.7,'median_regime_concentration':0.5,
        'median_win_rate':0.5,'median_payoff_ratio':1.4,'median_trade_r':0.1,'median_top10_win_profit_share':0.4,
        'mean_balanced_accuracy':0.4,'mean_macro_f1':0.4,'mean_log_loss':1.0,'mean_brier_score':0.55,'mean_expected_calibration_error':0.08,
        'median_sharpe_ratio':0.4,'median_sortino_ratio':0.6,'median_calmar_mar_ratio':1.2,'median_probabilistic_sharpe_ratio':0.9,
        'median_deflated_sharpe_ratio':0.8,'median_ulcer_index_r':4.0,'median_daily_cvar95_r':-1.0,
    }
    a=walk_forward_composite_score(cv,cfg)
    cfg2=deepcopy(cfg)
    for spec in cfg2['gate_kpis']['discovery']['risk_kpis'].values(): spec['enabled']=not bool(spec.get('enabled',True))
    b=walk_forward_composite_score(cv,cfg2)
    req(a['schema']=='CV_SCORE_V5_FIXED_100' and a['weight_total']==100.0,'Fixed 100 score schema missing')
    req(abs(a['score']-b['score'])<1e-12,'Hard KPI enable toggles changed ranking score')

    # KPI-01/03: signed CVaR guard and sample-aware advanced gates.
    from research.risk_kpi import ensure_risk_kpi_config, gate_rows
    bad=deepcopy(cfg); bad['acceptance']['risk_kpis']['cvar']['enabled']=True; bad['acceptance']['risk_kpis']['cvar']['threshold']=+0.8; bad['acceptance']['risk_kpis']['cvar']['allow_positive_tail_floor']=False
    try:
        ensure_risk_kpi_config(bad)
        raise AssertionError('Positive CVaR sign error was accepted without explicit opt-in')
    except ValueError as exc:
        req('CVAR_SIGN_SEMANTICS' in str(exc),'Wrong CVaR sign failure')
    rcfg=deepcopy(cfg); rcfg['acceptance']['risk_kpis']={k:deepcopy(v) for k,v in cfg['gate_kpis']['fresh_forward']['risk_kpis'].items()}
    rows=gate_rows({'trades':10,'active_trade_days':5,'daily_tail_sample_count':1,'sample_years':0.1},rcfg,mode='point',prefix='T')
    req(any(r['group']=='sample_sufficiency' and not r['passed'] for r in rows),'Small-sample risk KPI did not fail as evidence insufficiency')

    # KPI-04: Cheap Screen cannot use advanced risk KPI as qualification pressure.
    from research.research_engine_v3 import cheap_screen_cfg
    cheap=cheap_screen_cfg(cfg)
    req(all(not bool(x.get('enabled',True)) for x in cheap['gate_kpis']['discovery']['risk_kpis'].values()),'Cheap Screen retains hard advanced-risk authority')

    # KPI-05: Fresh is the production-grade economic bar.
    from research.gate_kpi import gate_profile
    fresh=gate_profile(deepcopy(cfg),'fresh_forward')
    req(float(fresh['min_expectancy_r'])>=0.50 and float(fresh['min_profit_factor'])>=1.50 and float(fresh['min_recovery_factor'])>=3.0 and float(fresh['max_drawdown_r'])<=10.0,'Fresh production KPI bar regressed')

    # CPCV-01: actual cross-strategy PBO is now computable; no candidate-local pseudo-PBO.
    from research.pbo import compute_cpcv_pbo
    prow=[]
    vals=[
        [0.8,0.7,0.6,-0.3,-0.2,-0.1],
        [0.4,0.3,0.2,0.5,0.4,0.3],
        [0.2,0.1,0.0,0.2,0.1,0.0],
        [0.1,0.2,0.1,0.1,0.2,0.1],
    ]
    for i,v in enumerate(vals):
        prow.append({'pool_id':f'P{i}','name':f'C{i}','evidence':{'pbo_group_expectancy_r':{str(g):x for g,x in enumerate(v)}}})
    pbo=compute_cpcv_pbo(prow,groups=6,min_candidates=4)
    req(pbo['status']=='COMPUTED' and pbo['partition_count']==10 and 0.0<=pbo['pbo']<=1.0,'Cross-strategy PBO computation unavailable')

    # WFA-01 and FEAT-01 source contracts.
    ml=(ROOT/'models/model_lab.py').read_text(encoding='utf-8')
    fla=(ROOT/'data/feature_label_audit.py').read_text(encoding='utf-8')
    req('min_train_rows=int(split.get("min_train_rows", 1000))' in ml,'WFA min_train_rows config is ignored')
    req('ABLATION · RULE_META_SCORE' in fla and 'rule_meta_score' in fla, 'Rule-meta double exposure ablation missing')

    print('V132_SCIENTIFIC_WORKFLOW_REPAIR_SELFTEST PASS')


if __name__=='__main__':
    main()
