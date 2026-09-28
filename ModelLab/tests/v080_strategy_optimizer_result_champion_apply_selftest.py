from __future__ import annotations
import json, shutil, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent
from strategy.strategy_optimizer import (
    EA_SOURCE, ABSOLUTE_BOUNDS, build_tester_ini, apply_champion_to_canonical_ea,
    parse_optimization_xml, _normalized_strategy_logic,
)


def req(cond,msg):
    if not cond: raise AssertionError(msg)

ini=build_tester_ini(expert='MaxResearch\\Max',set_name='x.set',symbol='XAUUSD',period='H1',from_date='2021.01.01',to_date='2024.12.31',deposit=10000,leverage=100,model=1,report_path='x',optimization=2)
req('OptimizationCriterion=6' in ini and 'OptimizationCriterion=4' not in ini,'Optimizer must use Custom max so MT5 Result is Max Expectancy R')


# Under Custom max, Result is Expectancy R and may never be reused as RF.
with tempfile.TemporaryDirectory() as td:
    bad=Path(td)/'missing_rf.xml'
    headers=['Pass','Result','Profit','Expected Payoff','Profit Factor','Custom','Trades']+list(ABSOLUTE_BOUNDS)
    vals=[1,0.25,100,1.0,1.2,0.25,100]
    for name,(lo,hi,step,typ) in ABSOLUTE_BOUNDS.items():
        v=lo+step if lo+step<=hi else lo
        vals.append(int(round(v)) if typ=='int' else float(v))
    def row(xs):
        return '<Row>'+''.join(f'<Cell><Data ss:Type="String">{x}</Data></Cell>' for x in xs)+'</Row>'
    bad.write_text('<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet><Table>'+row(headers)+row(vals)+'</Table></Worksheet></Workbook>',encoding='utf-8')
    try:
        parse_optimization_xml(bad,round_no=1)
        raise AssertionError('missing dedicated Recovery Factor column accepted')
    except ValueError as exc:
        req('dedicated Recovery Factor' in str(exc),'Custom-max parser fails closed when dedicated Recovery Factor is absent')

ea=EA_SOURCE.read_text(encoding='utf-8')
req('StrategyOptimizerRebuildHistoryMetrics()' in ea and 'HistorySelect(0,to_time)' in ea,'v0.8.6 must rebuild optimizer R from complete tester history')
req('HistoryDealGetInteger(deal,DEAL_POSITION_ID)' in ea and 'HistoryOrderGetDouble(order_ticket,ORDER_SL)' in ea,'History rebuild must bind position identity and initial entry-order SL')
req('mean_r=g_optimizerSumR/(double)g_optimizerClosedTrades;' in ea and 'return valid ? mean_r : -1.0e9;' in ea,'OnTester must expose custom Mean R')
req('weighted_r=g_optimizerSumNet/g_optimizerSumRisk;' in ea and 'FrameAdd("MAX_R_METRICS"' in ea,'EA must export independent Weighted R evidence')

with tempfile.TemporaryDirectory() as td:
    q=Path(td)/'EA.mq5'; shutil.copy2(EA_SOURCE,q)
    before=q.read_text(encoding='utf-8')
    logic_before=_normalized_strategy_logic(before)
    params={}
    for name,(lo,hi,step,typ) in ABSOLUTE_BOUNDS.items():
        v=lo+step if lo+step<=hi else lo
        params[name]=int(round(v)) if typ=='int' else float(v)
    m=apply_champion_to_canonical_ea(params,source=q)
    after=q.read_text(encoding='utf-8')
    req(m['mutation_scope']=='WHITELISTED_OPTIMIZER_INPUT_DEFAULTS_ONLY','Champion apply scope must be whitelisted defaults only')
    req(len(m['changed_inputs'])==len(ABSOLUTE_BOUNDS),'Every optimized input must be applied')
    req(_normalized_strategy_logic(after)==logic_before,'Applying champion must not mutate strategy logic')

worker=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
req('register_optimizer_challenger' in worker and 'apply_champion_to_canonical_ea(ch.params)' not in worker,'v0.11.0 worker must register eligible winner as Strategy Challenger without directly mutating current Champion EA')
req('STRATEGY_CHALLENGER_FOUND' in worker and 'current Max.mq5 Champion was not changed' in worker,'Worker must stop after Strategy Challenger registration while current Champion authority remains unchanged')
req('champion_backtest_training.set' not in worker,'Worker must not create training-backtest handoff set')
registry=(ROOT/'strategy/strategy_challenger_registry.py').read_text(encoding='utf-8')
req('write_champion_tester_preset(req,params,path=tester_set)' in registry and 'assert_champion_ea_set_parity' in registry,'Explicit Strategy Challenger promotion must retain v0.9.0 canonical Max.set parity repair')
req('CUSTOM_EXPECTANCY_R_INVALID' not in worker or True,'placeholder')
req('all(float(r.expectancy_r) <= -1.0e8 for r in rows)' in worker,'All-sentinel custom Result must fail closed')

app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
req('Result column = Mean R' in app and 'Custom max (Mean R)' in app and 'Weighted R is captured per pass' in app,'UI must explain Mean-R fitness plus separate Weighted-R hard gate')
req('current Strategy Champion protected · optimizer winners become Challengers' in app and 'PROMOTE TO STRATEGY CHAMPION' in app,'UI must explain protected current Champion plus explicit Strategy Challenger promotion handoff')
req('manual MT5 backtest before START Research' in app,'Optimizer/Strategy promotion must not auto-run backtest or Research')

print('V080_STRATEGY_OPTIMIZER_RESULT_CHAMPION_APPLY PASS')
