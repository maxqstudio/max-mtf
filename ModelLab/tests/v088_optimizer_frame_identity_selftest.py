from __future__ import annotations
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))

from strategy.strategy_optimizer import ABSOLUTE_BOUNDS, parse_optimizer_metrics_csv, parse_optimization_xml


def req(ok,msg):
    if not ok: raise AssertionError(msg)


def base_params(trend:float)->dict:
    return {
        "InpWeightTrend":trend,"InpWeightRange":1.0,"InpWeightBreakout":1.0,"InpWeightPullback":1.0,
        "InpWeightSession":0.5,"InpWeightShock":0.5,"InpWeightRelative":0.5,
        "InpEntryThreshold":0.3,"InpExitReverseThreshold":0.4,"InpMinConsensus":0.3,
        "InpSL_ATR":2.0,"InpTP_ATR":3.0,"InpMaxHoldBars":24,"InpShockHaltATR":4.0,
        "InpRelativeLookback":20,"InpMinRelativeCorr":0.3,
    }


def frame_blob(params:dict)->str:
    # FrameInputs also returns fixed EA inputs in production. The parser must only
    # require the 16 Strategy Optimizer parameters and safely ignore extra fields.
    return "|".join([*(f"{k}={params[k]}" for k in ABSOLUTE_BOUNDS),"InpAllowLiveTrading=true"])


def sidecar()->str:
    # These two exact uint64 ids collapse to the same value if routed through float.
    ids=(5790963814160864255,5790963814160864256)
    rows=[
        (ids[0],base_params(1.0),0.12,0.08,2000,500.00,6250.0),
        (ids[1],base_params(1.1),0.20,0.15,2100,900.00,6000.0),
    ]
    out=["frame_pass_id,frame_inputs,mean_expectancy_r,weighted_r,mt5_trades,r_accounted_trades,sum_net,sum_initial_risk,accounting_errors,run_nonce"]
    for fid,params,mean,weighted,trades,net,risk in rows:
        out.append(f"{fid},{frame_blob(params)},{mean},{weighted},{trades},{trades},{net},{risk},0,123")
    return "\n".join(out)+"\n"


def xml()->str:
    headers=["Pass","Result","Profit","Expected Payoff","Profit Factor","Recovery Factor","Sharpe Ratio","Custom","Equity DD %","Trades"]+list(ABSOLUTE_BOUNDS)
    # Reverse parameter/result order relative to sidecar to prove row-order is not authority.
    specs=[(0,base_params(1.1),0.20,900.00,2100),(1,base_params(1.0),0.12,500.00,2000)]
    def cell(v):
        return f'<Cell><Data ss:Type="Number">{v}</Data></Cell>'
    body=[]
    body.append('<Row>'+''.join(f'<Cell><Data ss:Type="String">{h}</Data></Cell>' for h in headers)+'</Row>')
    for pass_no,params,mean,profit,trades in specs:
        vals=[pass_no,mean,profit,profit/trades,1.4,1.2,0.5,mean,5.0,trades]+[params[k] for k in ABSOLUTE_BOUNDS]
        body.append('<Row>'+''.join(cell(v) for v in vals)+'</Row>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
            '<Worksheet ss:Name="Tester Optimizator Results"><Table>'+''.join(body)+'</Table></Worksheet></Workbook>')


def main():
    req(int(float("5790963814160864255"))==int(float("5790963814160864256")),"fixture must reproduce IEEE-754 collision")
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); mp=td/'Max_metrics.csv'; xp=td/'Max.xml'
        mp.write_text(sidecar(),encoding='utf-8'); xp.write_text(xml(),encoding='utf-8')
        evidence=parse_optimizer_metrics_csv(mp,expected_nonce=123)
        req(len(evidence)==2,"adjacent uint64 frame ids must remain distinct without float conversion")
        rows=parse_optimization_xml(xp,round_no=1,metrics_path=mp,expected_nonce=123,require_weighted_metrics=True)
        req(len(rows)==2,"both XML rows must receive Weighted-R evidence")
        by_pass={r.pass_no:r for r in rows}
        req(abs(by_pass[0].weighted_r-0.15)<1e-12 and abs(by_pass[1].weighted_r-0.08)<1e-12,"FrameInputs parameter vector, not opaque frame pass or row order, must join evidence")
        req(abs(by_pass[0].expectancy_r-0.20)<1e-12 and abs(by_pass[1].expectancy_r-0.12)<1e-12,"Mean-R parity preserved after parameter-vector join")
    ea=(ROOT.parent/'EA_v1_06'/'Max.mq5').read_text(encoding='utf-8')
    req('FrameInputs(pass,parameters,parameters_count)' in ea,"EA must export exact FrameInputs identity")
    req('StringFormat("%I64u",pass)' in ea,"opaque uint64 frame id must be serialized as text")
    parser=(ROOT/'strategy/strategy_optimizer.py').read_text(encoding='utf-8')
    req('int(float(row["pass"]))' not in parser,"64-bit frame id must never pass through float")
    print('V088_OPTIMIZER_FRAME_IDENTITY_PASS')

if __name__=='__main__':
    main()
