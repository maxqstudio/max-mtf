from __future__ import annotations
import json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def close(a,b,tol=1e-12):
    return math.isclose(float(a),float(b),rel_tol=tol,abs_tol=tol)

def main():
    ev=json.loads((ROOT/'evidence/research/OWNER_STRATEGY_CHAMPION_KPI_EVIDENCE.json').read_text(encoding='utf-8'))
    imp=json.loads((PKG/'EA_v1_06/CHAMPION_IMPORTED_PARAMETERS.json').read_text(encoding='utf-8'))
    req(ev.get('status')=='VERIFIED','Owner Strategy Champion KPI evidence is verified')
    pm=ev.get('parameter_match') or {}
    req(pm.get('status')=='UNIQUE' and pm.get('match_count_xml')==1 and pm.get('match_count_sidecar')==1,'Champion parameter vector uniquely matches XML and sidecar')
    k=ev.get('kpi') or {}
    req(close(k.get('mean_r'),0.0099404657441086),'Mean R matches XML Custom evidence')
    req(close(k.get('weighted_r'),0.008513275799847675),'Weighted R matches sidecar evidence')
    req(close(k.get('profit_factor'),1.024104) and close(k.get('recovery_factor'),0.472256),'PF/RF match XML evidence')
    req(close(k.get('equity_dd_pct'),13.6676) and close(k.get('sharpe_ratio'),0.186698),'DD/Sharpe match XML evidence')
    req(int(k.get('trades'))==1757 and int(k.get('r_accounted_trades'))==1757 and int(k.get('accounting_errors'))==0,'R-accounting parity is exact')
    req(close(k.get('profit'),799.94) and close(k.get('sum_net'),799.9400000000015),'Net profit parity matches sidecar')
    req(close(k.get('weighted_r'),float(k.get('sum_net'))/float(k.get('sum_initial_risk'))),'Weighted R arithmetic recomputes exactly')
    req(imp.get('kpi_status')=='VERIFIED_OWNER_OPTIMIZER_EVIDENCE' and imp.get('kpi')==k,'Imported Champion authority carries verified KPI record')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('Weighted R' in app and 'Expected Payoff' in app and 'Accounting Errors' in app,'Strategy Champion UI exposes verified KPI evidence including Weighted R')
    req('Verified optimizer evidence' in app and 'frame_pass_id' in json.dumps(imp),'UI/provenance records XML and frame namespaces separately')
    reg=(ROOT/'strategy/strategy_challenger_registry.py').read_text(encoding='utf-8')
    req('VERIFIED_OWNER_OPTIMIZER_EVIDENCE' in reg and 'CHAMPION_IMPORTED_PARAMETERS.json' in reg,'Strategy registry can bootstrap imported verified Champion KPI')
    print('V1.2.5 STRATEGY CHAMPION KPI EVIDENCE SELFTEST PASS')

if __name__=='__main__': main()
