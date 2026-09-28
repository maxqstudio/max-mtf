from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from copy import deepcopy

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def req(cond,msg):
    if not cond: raise AssertionError(msg)

# Owner-locked zero floor for both WFA and CPCV.
a=CFG['acceptance']
req(float(a['cv_min_worst_expectancy_r'])==0.0,'WFA Worst R zero floor')
req(float(a['cpcv_min_worst_expectancy_r'])==0.0,'CPCV Worst R zero floor')
req(float(a.get('worst_expectancy_epsilon',0))>0,'shared floating epsilon configured')

# v0.7.6 separates statistical threshold ownership by Research gate while preserving
# the legacy profile on first migration. Research trade sufficiency is H1=8/month.
from research.gate_kpi import GATES, ensure_gate_kpi_profiles, gate_profile
req(int(CFG["trade_sample_policy"]["base_h1_trades_per_month"])==8,"Research H1 sample baseline = 8 trades/month")
req(float(CFG["trade_sample_policy"]["sufficiency_ratio"])==1.0,"Research trade minimum has no hidden sufficiency haircut")
req(set(GATES)=={"discovery","cpcv","tournament","monte_carlo","fresh_forward","champion_promotion"},"five statistical profiles plus Champion promotion registered")
for gate in GATES:
    req(isinstance(gate_profile(CFG,gate),dict),f"{gate} profile available")

legacy=deepcopy(CFG); legacy.pop("gate_kpis",None)
legacy["acceptance"]["min_profit_factor"]=1.91
legacy["acceptance"]["cv_min_median_profit_factor"]=1.44
legacy["acceptance"]["risk_kpis"]["sharpe"]["threshold"]=0.77
legacy["agent"]["promotion"]["min_shadow_profit_factor"]=1.73
profiles=ensure_gate_kpi_profiles(legacy)
req(abs(float(profiles["discovery"]["cv_min_median_profit_factor"])-1.44)<1e-12,"legacy Discovery KPI migrates without reset")
req(abs(float(profiles["tournament"]["min_profit_factor"])-1.91)<1e-12,"legacy Tournament KPI migrates without reset")
req(abs(float(profiles["monte_carlo"]["min_p05_profit_factor"])-1.73)<1e-12 and abs(float(profiles["fresh_forward"]["min_profit_factor"])-1.73)<1e-12,"legacy promotion KPI migrates into MC/Fresh")
req(abs(float(profiles["cpcv"]["risk_kpis"]["sharpe"]["threshold"])-0.77)<1e-12,"legacy risk threshold migrates into per-gate profile")
profiles["discovery"]["cv_min_median_profit_factor"]=9.0
req(abs(float(profiles["cpcv"]["cv_min_median_profit_factor"])-1.44)<1e-12,"per-gate KPI profiles are independent after migration")

# v1.3.2 risk authority is stage-aware and sample-aware. Advanced statistics are
# always computed, but only robust metrics receive hard authority in early gates.
from research.gate_kpi import risk_cfg_for_gate
stage_expect={
    'discovery': {'sharpe':(.15,True),'sortino':(.25,True),'ulcer':(8.0,True),'cvar':(-2.0,False),'psr':(.95,False),'dsr':(.95,False),'calmar':(1.0,False)},
    'cpcv': {'sharpe':(.20,True),'sortino':(.30,True),'ulcer':(8.0,True),'cvar':(-2.5,True),'psr':(.95,False),'dsr':(.95,False),'calmar':(1.0,False)},
    'tournament': {'sharpe':(.30,True),'sortino':(.50,True),'calmar':(1.0,True),'psr':(.80,True),'ulcer':(6.0,True),'cvar':(-2.0,True),'dsr':(.95,False)},
    'fresh_forward': {'sharpe':(.40,True),'sortino':(.65,True),'calmar':(1.25,True),'psr':(.85,True),'ulcer':(5.0,True),'cvar':(-1.5,True),'dsr':(.95,False)},
}
for gate,expected in stage_expect.items():
    rk=gate_profile(CFG,gate)['risk_kpis']
    for k,(th,enabled) in expected.items():
        req(abs(float(rk[k]['threshold'])-th)<1e-12,f'{gate} {k} threshold')
        req(bool(rk[k]['enabled']) is enabled,f'{gate} {k} authority')

# CVaR gate basis must be daily aggregated R, not legacy per-trade stop-loss tail.
from research.evaluation import metrics_from_trades
tr=np.array([1.0,-1.0,-1.0,1.5,-1.0,0.5],float)
ts=pd.to_datetime(['2026-01-01 01:00','2026-01-02 01:00','2026-01-02 02:00','2026-01-03 01:00','2026-01-03 02:00','2026-01-04 01:00'])
m=metrics_from_trades(tr,timestamps=ts,multiple_testing_trials=10,benchmark_sharpe=.2)
req(m['daily_cvar95_r'] is not None,'daily CVaR emitted')
req(abs(float(m['daily_cvar95_r'])-(-2.0))<1e-12,'daily CVaR aggregates same-day trades')
req(float(m['cvar95_r'])==-1.0,'legacy per-trade CVaR remains diagnostic')

# Discovery WFA uses only its three early-stage hard risk gates; later-stage
# statistics remain diagnostics and cannot mechanically dilute selection score.
from research.kpi import walk_forward_acceptance
cv={
 'auto_min_validation_trades':90,'total_validation_trades':180,
 'median_max_drawdown_r':5,'worst_fold_max_drawdown_r':7,'median_recovery_factor':3,'worst_fold_recovery_factor':2,
 'median_profit_factor':2,'overall_expectancy_r':.4,'total_validation_r':72.0,'median_expectancy_r':.4,'worst_expectancy_r':0.0,'positive_fold_ratio':1.0,
 'median_positive_month_ratio':.8,'median_positive_quarter_ratio':.8,'median_regime_concentration':.4,'median_top10_win_profit_share':.3,
 'median_stress_x1_25_expectancy_r':.3,'median_stress_x1_50_expectancy_r':.2,'median_threshold_plateau':.9,
 'folds':3,'median_fold_trades':120,'median_active_trade_days':80,'median_daily_tail_sample_count':4,'median_sample_years':1.0,
 'median_sharpe_ratio':.16,'median_sortino_ratio':.26,'median_calmar_mar_ratio':1.01,
 'median_probabilistic_sharpe_ratio':.96,'median_deflated_sharpe_ratio':.96,'median_ulcer_index_r':7.9,'median_daily_cvar95_r':-3.0,
}
acc=walk_forward_acceptance(cv,CFG)
req(acc['passed'],'Discovery hard-risk subset passes WFA')
req(len([g for g in acc['gates'] if g.get('group')=='risk_adjusted'])==3,'Discovery has exactly three hard risk gates')
cv_bad=dict(cv); cv_bad['median_sharpe_ratio']=.14
bad=walk_forward_acceptance(cv_bad,CFG)
req(not bad['passed'] and 'CV_SHARPE' in bad['reasons'],'Discovery Sharpe hard gate active')
cv_noise=dict(cv); cv_noise['worst_expectancy_r']=-1e-10
req(walk_forward_acceptance(cv_noise,CFG)['passed'],'tiny negative Worst R passes epsilon')
cv_neg=dict(cv); cv_neg['worst_expectancy_r']=-0.001
req(not walk_forward_acceptance(cv_neg,CFG)['passed'],'material negative Worst R fails zero floor')

# Canonical CPCV hard-risk gates use the CPCV profile and sample sufficiency.
from research.risk_kpi import canonical_gate_rows
paths=[]
for i in range(5):
    paths.append({'trades':150,'active_trade_days':80,'daily_tail_sample_count':4,'sample_years':1.0,'sharpe_ratio':.35,'sortino_ratio':.5,'calmar_mar_ratio':1.2,'probabilistic_sharpe_ratio':.98,'deflated_sharpe_ratio':.97,'ulcer_index_r':4.0,'daily_cvar95_r':-1.5})
cpcv_cfg=risk_cfg_for_gate(CFG,'cpcv')
rows,summary=canonical_gate_rows(paths,cpcv_cfg)
active=[r for r in rows if r.get('enabled',True)]
req(len(active)==4 and all(r['passed'] for r in active),'four canonical CPCV hard-risk gates pass')
paths[0]['daily_cvar95_r']=-3.0
rows,_=canonical_gate_rows(paths,cpcv_cfg)
req(not next(r for r in rows if r['kpi_key']=='cvar')['passed'],'canonical CPCV CVaR uses worst path')

# LLM stack: retry only on fallback-safe provider errors and retain provenance.
import scientist.core.scientist as sm
from host.provider_catalog import ProviderRequestError
orig=sm.chat_completion
calls=[]
def fake(base,model,key,messages,**kwargs):
    calls.append(model)
    if model=='primary':
        raise ProviderRequestError('HTTP 429: quota exhausted',status_code=429)
    return {'choices':[{'message':{'content':'{"ok":true,"role":"research_scientist"}'}}], 'usage':{'prompt_tokens':120,'completion_tokens':30,'total_tokens':150,'prompt_tokens_details':{'cached_tokens':20}}}
sm.chat_completion=fake
try:
    sc=sm.LLMScientist({'timeout_sec':1,'temperature':0,'pricing_usd_per_1m':{'gemini|fallback':{'enabled':True,'input':1.0,'output':2.0,'cached_input':0.5}},'stack':[{'provider':'gemini','base_url':'https://example/v1/','model':'primary'},{'provider':'gemini','base_url':'https://example/v1/','model':'fallback'}]},api_key='x')
    out=sc.test()
    req(out['ok'] and calls==['primary','fallback'],'quota fallback reaches second model')
    prov=out['llm_provenance']; req(prov['fallback_used'] and prov['selected_model']=='fallback','fallback provenance recorded')
    req(prov['usage']['input_tokens']==120 and prov['usage']['output_tokens']==30 and prov['usage']['total_tokens']==150,'provider token usage recorded')
    req(prov['usage']['source']=='PROVIDER_REPORTED','provider usage source labelled')
    req(prov['cost']['configured'] and abs(float(prov['cost']['estimated_cost_usd'])-0.00017)<1e-12,'configurable API cost estimate uses cached/input/output rates')
finally:
    sm.chat_completion=orig

calls=[]
def bad_auth(base,model,key,messages,**kwargs):
    calls.append(model); raise ProviderRequestError('HTTP 401: invalid key',status_code=401)
sm.chat_completion=bad_auth
try:
    sc=sm.LLMScientist({'stack':[{'provider':'gemini','base_url':'https://example/v1/','model':'primary'},{'provider':'gemini','base_url':'https://example/v1/','model':'fallback'}]},api_key='x')
    try: sc.test(); raise AssertionError('401 must fail closed')
    except ProviderRequestError: pass
    req(calls==['primary'],'non-fallback auth error must not try next model')
finally:
    sm.chat_completion=orig

app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
req('LLM call provenance' in app and 'API cost' in app and 'token source' in app,'Scientist UI exposes model route/token/cost provenance')
req('LLM USAGE · CURRENT JOURNAL' in app,'Scientist journal exposes aggregate usage cockpit')
req('Token pricing · optional cost estimator' in app,'Advanced exposes configurable token pricing')
req('**OBSERVATION**' in app and '**HYPOTHESIS**' in app and '**EXPERIMENT**' in app and '**FALSIFICATION**' in app and '**CONCLUSION**' in app,'cockpit preserves complete scientific method information')

print('R6 KPI GATE + LLM STACK SELFTEST PASS')
