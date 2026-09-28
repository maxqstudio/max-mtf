from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.inherited_v147 import provisional_cpcv_summary


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

rows=[
 {'split':1,'profit_factor':1.2,'expectancy_r':0.10,'max_drawdown_r':0.40,'recovery_factor':2.0},
 {'split':2,'profit_factor':1.6,'expectancy_r':0.30,'max_drawdown_r':0.70,'recovery_factor':1.4},
 {'split':3,'profit_factor':1.4,'expectancy_r':-0.05,'max_drawdown_r':0.50,'recovery_factor':1.8},
]
s=provisional_cpcv_summary(rows)
req(s['authority']=='PROVISIONAL_COMPLETED_SPLITS_ONLY' and s['provisional'] is True,'live KPI authority is explicitly provisional')
req(s['completed_split_records']==3,'three completed split records are counted')
req(abs(s['median_profit_factor']-1.4)<1e-12 and abs(s['median_expectancy_r']-0.10)<1e-12,'provisional median PF/expectancy are derived from completed splits')
req(abs(s['worst_expectancy_r']-(-0.05))<1e-12 and abs(s['worst_max_drawdown_r']-0.70)<1e-12 and abs(s['worst_recovery_factor']-1.4)<1e-12,'provisional worst Exp/DD/Recovery are visible')
req('passed' not in s and 'status' not in s and 'first_failed_gate' not in s,'provisional telemetry cannot emit final CPCV PASS/FAIL authority')

app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
req('PROVISIONAL · completed splits only' in app,'CPCV table labels live KPI telemetry as provisional')
req('provisional_cpcv_summary(_lr)' in app and 'stat="RUNNING"' in app,'RUNNING candidate consumes completed split telemetry without becoming terminal')
req('m=_prov; splits=int(_prov.get("completed_split_records",0) or 0); kpi_authority="PROVISIONAL · completed splits only"' in app,'live metrics and completed split count come from the same provisional evidence set')
req('split_total=int(live.get("split_total",15) or 15)*max(1,int(live.get("seed_total",1) or 1))' in app,'live split denominator includes all required seed-split records')
req('FINAL · canonical reconstructed CPCV' in app,'completed candidates remain tied to canonical final CPCV authority')
print('V201_CPCV_LIVE_KPI_TELEMETRY PASS')
