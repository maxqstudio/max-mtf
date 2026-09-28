from __future__ import annotations
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))

from strategy.strategy_optimizer import (
    DEFAULT_SPACE, OptimizationPass, optimizer_kpi_policy, build_set_text,
    parse_optimization_xml, select_champion, validate_request,
)

def req(ok,msg):
    if not ok: raise AssertionError(msg)

def xml_one(pass_no:int=1, custom:float=0.12, pf:float=1.4, rf:float=1.2, trades:int=2000)->str:
    params={
        "InpSL_ATR":2.0,"InpTP_ATR":3.0,"InpMaxHoldBars":24,"InpShockHaltATR":4.0,
        "InpEntryThreshold":0.3,"InpExitReverseThreshold":0.4,"InpMinConsensus":0.3,
        "InpWeightTrend":1.0,"InpWeightRange":1.0,"InpWeightBreakout":1.0,"InpWeightPullback":1.0,
        "InpWeightSession":0.5,"InpWeightShock":0.5,"InpWeightRelative":0.5,
        "InpRelativeLookback":20,"InpMinRelativeCorr":0.3,
    }
    headers=["Pass","Result","Profit","Expected Payoff","Profit Factor","Recovery Factor","Sharpe Ratio","Custom","Equity DD %","Trades"]+list(params)
    vals=[pass_no,custom,500,0.25,pf,rf,0.5,custom,5.0,trades]+list(params.values())
    def cell(v):
        typ="Number" if not isinstance(v,str) else "String"
        return f'<Cell><Data ss:Type="{typ}">{v}</Data></Cell>'
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n'
            '<DocumentProperties xmlns="urn:schemas-microsoft-com:office:office"><Title>Max EURUSD,H1 2021.01.01-2024.12.31</Title></DocumentProperties>\n'
            '<Worksheet ss:Name="Tester Optimizator Results"><Table>\n<Row>'
            + ''.join(cell(x) for x in headers) + '</Row>\n<Row>'
            + ''.join(cell(x) for x in vals) + '</Row>\n</Table></Worksheet></Workbook>')

def sidecar(pass_no:int=1, mean:float=0.12, weighted:float=0.08, nonce:int=123)->str:
    net=500.0
    risk=net/weighted
    params={
        "InpSL_ATR":2.0,"InpTP_ATR":3.0,"InpMaxHoldBars":24,"InpShockHaltATR":4.0,
        "InpEntryThreshold":0.3,"InpExitReverseThreshold":0.4,"InpMinConsensus":0.3,
        "InpWeightTrend":1.0,"InpWeightRange":1.0,"InpWeightBreakout":1.0,"InpWeightPullback":1.0,
        "InpWeightSession":0.5,"InpWeightShock":0.5,"InpWeightRelative":0.5,
        "InpRelativeLookback":20,"InpMinRelativeCorr":0.3,
    }
    blob="|".join(f"{k}={v}" for k,v in params.items())
    return (
        "frame_pass_id,frame_inputs,mean_expectancy_r,weighted_r,mt5_trades,r_accounted_trades,sum_net,sum_initial_risk,accounting_errors,run_nonce\n"
        f"{pass_no},{blob},{mean},{weighted},2000,2000,{net},{risk},0,{nonce}\n"
    )

def main():
    cfg={"strategy_optimizer":{"kpi":{"min_profit_factor":1.0,"min_recovery_factor":0.0,"min_expectancy_r":0.0,"min_weighted_r":0.05,"base_h1_trades_per_month":20}}}
    k=optimizer_kpi_policy(cfg)
    req(k["schema"]=="MAX_STRATEGY_OPTIMIZER_KPI_V2","KPI schema v2")
    req(k["min_weighted_r"]==0.05,"Weighted R threshold in KPI policy")

    st=(ROOT/"core/settings_store.py").read_text(encoding="utf-8")
    app=(ROOT/"ui/app.py").read_text(encoding="utf-8")
    worker=(ROOT/"strategy/strategy_optimizer_worker.py").read_text(encoding="utf-8")
    ea=(ROOT.parent/"EA_v1_06"/"Max.mq5").read_text(encoding="utf-8")
    req('"strategy_opt_kpi_weighted_r"' in st,"Weighted R UI setting is durable")
    req('number_input("Min Weighted R"' in app,"Weighted R setting visible in Strategy Optimizer")
    req('"min_weighted_r":float(st.session_state.get("strategy_opt_kpi_weighted_r"' in app,"Weighted R frozen from live UI")
    req('row.min_weighted_r_required=float(kpi.get("min_weighted_r",0.0))' in worker,"worker enforces frozen Weighted R")
    req('"weighted_r":sum(1 for r in rows' in worker,"eligibility evidence counts Weighted R")
    req('FrameAdd("MAX_R_METRICS"' in ea,"EA exports per-pass R metrics through MT5 frame channel")
    req('weighted_r=g_optimizerSumNet/g_optimizerSumRisk' in ea,"EA computes capital-weighted R")
    req('StrategyOptimizerInitialRiskFromDeal' in ea and 'OrderCalcProfit' in ea,"EA initial R denominator uses account-currency stop loss calculation")
    req('DEAL_PRICE' in ea and 'ORDER_SL' in ea and 'DEAL_SL' in ea,"EA R accounting binds actual entry fill and initial stop")
    req('StrategyOptimizerRebuildHistoryMetrics()' in ea and 'TesterStatistics(STAT_TRADES)' in ea and 'mt5_trades==(long)g_optimizerClosedTrades' in ea,"EA history-rebuilt R-accounting parity fail closed")
    req('InpOptimizerRunNonce' in ea and 'InpOptimizerMetricsFile' in ea,"EA has frozen optimizer evidence identity inputs")
    req('OnTesterDeinit()' in ea and 'FrameNext(' in ea,"late optimization frames are drained")
    req('FrameInputs(pass,parameters,parameters_count)' in ea and '"frame_pass_id","frame_inputs"' in ea,"Weighted-R sidecar is bound to exact MT5 FrameInputs identity")

    set_text=build_set_text(DEFAULT_SPACE,confirm_symbol="DXY",optimizer_metrics_file="Max_metrics.csv",optimizer_run_nonce=123)
    req("InpOptimizerMetricsFile=Max_metrics.csv" in set_text,"metrics file frozen in set")
    req("InpOptimizerRunNonce=123" in set_text,"nonce frozen in set")

    with tempfile.TemporaryDirectory() as td:
        td=Path(td); xp=td/"Max.xml"; mp=td/"Max_metrics.csv"
        xp.write_text(xml_one(),encoding="utf-8"); mp.write_text(sidecar(),encoding="utf-8")
        rows=parse_optimization_xml(xp,round_no=1,metrics_path=mp,expected_nonce=123,require_weighted_metrics=True)
        req(len(rows)==1 and abs(rows[0].weighted_r-0.08)<1e-12,"Weighted R parsed from sidecar")
        r=rows[0]
        r.minimum_trades_required=100
        r.min_profit_factor_required=1.0
        r.min_recovery_factor_required=0.0
        r.min_expectancy_r_required=0.0
        r.min_weighted_r_required=0.10
        req(not r.passed,"Mean R positive cannot bypass failing Weighted R")
        r.min_weighted_r_required=0.05
        req(r.passed and select_champion(rows) is r,"Weighted R gate participates in Champion eligibility")

    base=dict(round_no=1,profit_factor=1.5,recovery_factor=2.0,expectancy_r=0.20,profit=100,trades=1000,params={k:1 for k in DEFAULT_SPACE},raw={},
              minimum_trades_required=10,min_profit_factor_required=1.0,min_recovery_factor_required=0.0,min_expectancy_r_required=0.0,min_weighted_r_required=0.0)
    a=OptimizationPass(pass_no=1,weighted_r=0.05,**base)
    b=OptimizationPass(pass_no=2,weighted_r=0.10,**base)
    req(select_champion([a,b]).pass_no==2,"Champion ranking prioritizes Weighted R after hard gates")

    fake=Path(tempfile.gettempdir())
    req_data={
        "symbol":"EURUSD","confirm_symbol":"DXY","period":"H1","from_date":"2021.01.01","to_date":"2024.12.31",
        "installation":{"terminal":str(fake/"terminal64.exe"),"metaeditor":str(fake/"metaeditor64.exe"),"data_dir":str(fake)},
        "search_space":DEFAULT_SPACE,"optimizer_kpi":cfg["strategy_optimizer"]["kpi"],
    }
    frozen=validate_request(req_data)
    req(frozen["optimizer_kpi"]["min_weighted_r"]==0.05,"frozen request preserves Weighted R")
    req(frozen["mt5_optimization_criterion"]["weighted_r_authority"]=="MAX_OPTIMIZATION_FRAME_SIDECAR","request records Weighted R provenance")

    print("V085_WEIGHTED_R_OPTIMIZER_PASS")

if __name__=="__main__":
    main()
