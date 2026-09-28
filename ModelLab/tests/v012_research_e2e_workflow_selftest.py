from __future__ import annotations
import json, tempfile
from pathlib import Path
import pandas as pd
from research.research_e2e import golden_cp32, e2e_config, PROFILE

ROOT=Path(__file__).resolve().parents[1]
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def main():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); ds=td/'golden.csv'; info=golden_cp32(ds,3600)
        df=pd.read_csv(ds)
        req(len(df)==3600 and set(['sl_atr','tp_atr','max_hold_bars']).issubset(df.columns),'Golden CP32 is materialized with strategy geometry')
        req((df['sl_atr']==3.2).all() and (df['tp_atr']==4.8).all() and (df['max_hold_bars']==54).all(),'Golden geometry matches current Strategy Champion')
        cp=td/'cfg.json'; cfg=e2e_config(ROOT/'config/config.json',ds,cp)
        req(cfg['champion_factory']['research_mode']=='MANUAL' and len(cfg['champion_factory']['manual_research']['candidates'])==1,'E2E uses one exact real RandomForest candidate, no discovery roulette')
        req(cfg['champion_factory']['monte_carlo_simulations']==100,'E2E still runs Monte Carlo with bounded minimum simulations')
        req(cfg['gate_kpis']['discovery']['cv_min_overall_expectancy_r']==0.0 and cfg['gate_kpis']['fresh_forward']['min_expectancy_r']==0.0,'E2E performance KPI floor is deliberately low')
        req(all(not s.get('enabled',True) for s in cfg['gate_kpis']['discovery']['risk_kpis'].values()),'Advanced risk KPI are disabled only inside E2E profile')
        req(cfg['agent']['data_quality_context'].get('e2e_only') is True and cfg['champion_factory']['e2e_workflow_test']['profile']==PROFILE,'E2E artifacts are explicitly non-production evidence')
    src=(ROOT/'research/research_e2e.py').read_text(encoding='utf-8')
    req('run_manual_factory' in src and 'register_eligible_challenger' in src and 'promote(' in src,'E2E lane spans Factory core -> Challenger registry -> sandbox promotion')
    req('sandbox_terminal' in src and 'production_evidence' in src,'E2E promotion is isolated from production terminal and registry')
    print('V012_RESEARCH_E2E_WORKFLOW_SELFTEST PASS')

if __name__=='__main__': main()
