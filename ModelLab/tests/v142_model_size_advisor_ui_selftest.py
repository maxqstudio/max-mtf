from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from models.model_registry import get_bounds, effective_bounds
from models.model_size_advisor import build_advisor, current_family_resolution
from research.sample_policy import scaled_trade_requirement


def req(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    cfg=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
    cfg['compute']['mode']='CPU'
    before=copy.deepcopy(cfg)
    req(int(cfg['trade_sample_policy']['base_h1_trades_per_month'])==8,'Research H1 baseline must remain 8/month')
    req(int(cfg['strategy_optimizer']['kpi']['base_h1_trades_per_month'])==20,'Optimizer H1 baseline must remain 20/month')
    sample=scaled_trade_requirement('H1','2026-01-01','2026-01-31',base_h1_trades_per_month=8)
    req(int(sample['scaled_trades_per_month'])==8,'H1 Research monthly requirement must resolve to 8')

    identity={'rows':35000,'symbol':'TEST','period':'H1','start':'2020-01-01','end':'2025-01-01'}
    profile={
        'memory':{'total_gib':32.0,'available_gib':24.0},
        'nvidia':{'devices':[]},
        'torch':{'cuda_available':False},
        'cpu':{'physical_cores':6,'logical_threads':12},
    }
    adv=build_advisor(identity,cfg,profile,families=['lightgbm','gru','tcn','transformer'])
    req(adv['authority']=='ADVISORY_ONLY_NEVER_AUTO_APPLY','advisor must be advisory only')
    req(int(adv['capacity']['configured_min_train_rows'])==int(cfg['split']['min_train_rows'])==1000,'advisor must use actual WFA min_train_rows authority')
    req(adv['capacity']['minimum_wfa_train_rows']>=1000,'advisor WFA basis invalid')
    req(cfg==before,'advisor must not mutate Owner config')

    safe=adv['safe_envelopes']
    for fam in ('lightgbm','gru','tcn','transformer'):
        s=adv['families'][fam]['suggestion']['suggested_priority']
        req(s is not None and 0.0<=float(s)<=1.0 and abs(round(float(s)/0.05)*0.05-float(s))<1e-9,f'{fam} suggestion must be 0.05-grid')
        lo=current_family_resolution(fam,0.0,safe)
        hi=current_family_resolution(fam,1.0,safe)
        preview_cfg={'agent':{'research_plan':{'parameter_envelopes':{fam:safe.get(fam,{})},'family_size_priorities':{fam:0.0}}},'research_architecture':{'family_size_priorities':{fam:0.0}}}
        canonical=effective_bounds(preview_cfg,fam)
        req(lo['current_bounds']=={k:[v[0],v[1]] for k,v in canonical.items()},f'{fam} tooltip must use canonical effective_bounds engine')
        for key in lo['size_parameters']:
            a=lo['current_bounds'][key]; b=hi['current_bounds'][key]
            req(float(a[0])<=float(b[0]) and float(a[1])<=float(b[1]),f'{fam}.{key} Small->Large range must move upward')
        for key,row in adv['families'][fam]['manual_parameter_ranges'].items():
            sg=row['suggested']; allowed=row['allowed']
            req(float(allowed[0])<=float(sg[0])<=float(sg[1])<=float(allowed[1]),f'{fam}.{key} suggested range must stay legal')
    pc=current_family_resolution('gru',0.50,safe)['estimated_parameter_count_range']
    req(isinstance(pc,list) and len(pc)==2 and int(pc[0])>0 and int(pc[1])>=int(pc[0]),'GRU tooltip must expose executable parameter-count estimate')
    req(current_family_resolution('lightgbm',0.50,safe)['estimated_parameter_count_range'] is None,'Tree family must not fabricate neural parameter count')

    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    sup=(ROOT/'factory/supervisor_agent.py').read_text(encoding='utf-8')
    req('row[0].caption(f"Suggested {float(_suggested):.2f}"' in app and 'Current slider range' in app,'AUTO suggestion + current-slider tooltip missing')
    req('Suggested range for {key}' in app and 'MANUAL remains exact Owner authority' in app,'MANUAL per-parameter suggestion tooltip missing')
    req('Research H1 min trades / month' in app and 'Optimizer H1 baseline' in app,'Research min-trades KPI setup missing')
    req('x["Exp R"]=r.get("Overall R")' in app,'historical Exp R display fallback missing')
    req('_ui_discovery_identity_cached' in app and 'advisor_row_scope"]="DISCOVERY_WINDOW' in app,'advisor must use selected Discovery window rows')
    req('"Exp R":round(float(row.get(\'overall_expectancy_r\'' in sup,'new telemetry must emit Exp R directly')

    print('V142_MODEL_SIZE_ADVISOR_UI_SELFTEST PASS')


if __name__=='__main__':
    main()
