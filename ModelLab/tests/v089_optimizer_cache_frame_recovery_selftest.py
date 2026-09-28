from __future__ import annotations
import math
import tempfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from strategy.strategy_optimizer import ABSOLUTE_BOUNDS, parse_optimization_xml, select_champion, best_near_miss


def req(ok,msg):
    if not ok: raise AssertionError(msg)
    print('PASS ',msg)


def params(trend:float)->dict:
    return {
        "InpWeightTrend":trend,"InpWeightRange":1.0,"InpWeightBreakout":1.0,"InpWeightPullback":1.0,
        "InpWeightSession":0.5,"InpWeightShock":0.5,"InpWeightRelative":0.5,
        "InpEntryThreshold":0.3,"InpExitReverseThreshold":0.4,"InpMinConsensus":0.3,
        "InpSL_ATR":3.2,"InpTP_ATR":4.8,"InpMaxHoldBars":72,"InpShockHaltATR":6.0,
        "InpRelativeLookback":24,"InpMinRelativeCorr":0.55,
    }


def blob(p:dict)->str:
    return '|'.join([*(f'{k}={p[k]}' for k in ABSOLUTE_BOUNDS),'InpOptimizerRunNonce=456'])


def xml()->str:
    headers=["Pass","Result","Profit","Expected Payoff","Profit Factor","Recovery Factor","Sharpe Ratio","Custom","Equity DD %","Trades"]+list(ABSOLUTE_BOUNDS)
    specs=[
        # Strong XML-only contender: simulates an MT5 cached row whose frame is not replayed.
        (9413,params(1.5),0.0135,985.55,1.0302,0.8445,1685),
        # Complete but weaker row with sidecar evidence.
        (100,params(1.0),0.0010,100.0,1.0100,0.1000,1500),
    ]
    def cell(v): return f'<Cell><Data ss:Type="Number">{v}</Data></Cell>'
    body=['<Row>'+''.join(f'<Cell><Data ss:Type="String">{h}</Data></Cell>' for h in headers)+'</Row>']
    for pass_no,p,mean,profit,pf,rf,trades in specs:
        vals=[pass_no,mean,profit,profit/trades,pf,rf,0.2,mean,10.0,trades]+[p[k] for k in ABSOLUTE_BOUNDS]
        body.append('<Row>'+''.join(cell(v) for v in vals)+'</Row>')
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
            '<Worksheet ss:Name="Tester Optimizator Results"><Table>'+''.join(body)+'</Table></Worksheet></Workbook>')


def sidecar()->str:
    p=params(1.0)
    return ('frame_pass_id,frame_inputs,mean_expectancy_r,weighted_r,mt5_trades,r_accounted_trades,sum_net,sum_initial_risk,accounting_errors,run_nonce\n'
            f'9000000000000000001,{blob(p)},0.001,0.002,1500,1500,100.0,50000.0,0,456\n')


def main():
    ea=(ROOT.parent/'EA_v1_06'/'Max.mq5').read_text(encoding='utf-8')
    req('#property tester_no_cache' in ea,'EA disables MT5 optimization cache so fresh passes replay R-metric frames')
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); xp=td/'Max.xml'; mp=td/'Max_metrics.csv'
        xp.write_text(xml(),encoding='utf-8'); mp.write_text(sidecar(),encoding='utf-8')
        rows=parse_optimization_xml(xp,round_no=1,metrics_path=mp,expected_nonce=456,require_weighted_metrics=True)
        req(len(rows)==2,'partial frame evidence does not destroy the completed MT5 XML round')
        for r in rows:
            r.minimum_trades_required=1370
            r.min_profit_factor_required=1.0
            r.min_recovery_factor_required=0.0
            r.min_expectancy_r_required=0.0
            r.min_weighted_r_required=0.0
        by={r.pass_no:r for r in rows}
        req(math.isnan(by[9413].weighted_r),'cached XML-only contender remains explicitly incomplete')
        req(math.isfinite(by[100].weighted_r),'fresh frame-backed row retains Weighted-R evidence')
        req(select_champion(rows) is None,'no Champion may be promoted while a non-weighted-gate contender lacks Weighted-R evidence')
        near=best_near_miss(rows)
        req(near is not None and near.pass_no==9413,'best incomplete contender is preserved for deterministic/Scientist next-round refinement')
    print('V089_OPTIMIZER_CACHE_FRAME_RECOVERY_PASS')

if __name__=='__main__': main()
