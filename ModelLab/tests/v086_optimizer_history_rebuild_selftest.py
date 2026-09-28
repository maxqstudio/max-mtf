from __future__ import annotations
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EA=ROOT.parent/'EA_v1_06'/'Max.mq5'

def req(x,msg):
    if not x:
        raise AssertionError(msg)


def main():
    ea=EA.read_text(encoding='utf-8')
    req('StrategyOptimizerRebuildHistoryMetrics()' in ea,'OnTester history rebuild exists')
    ontester=ea.split('double OnTester()',1)[1]
    req('bool rebuilt=StrategyOptimizerRebuildHistoryMetrics();' in ontester,'OnTester rebuilds complete history before fitness validation')
    req('mt5_trades==(long)g_optimizerClosedTrades' in ontester,'MT5 trade parity remains fail-closed')
    req('weighted_r=g_optimizerSumNet/g_optimizerSumRisk' in ontester,'Weighted R remains system-edge metric')

    rebuild=ea.split('bool StrategyOptimizerRebuildHistoryMetrics()',1)[1].split('\ndouble Clamp(',1)[0]
    risk=ea.split('bool StrategyOptimizerInitialRiskFromDeal',1)[1].split('\nbool StrategyOptimizerRebuildHistoryMetrics()',1)[0]
    req('HistorySelect(0,to_time)' in rebuild,'complete tester history is selected once')
    req('HistoryDealSelect(' not in rebuild and 'HistoryDealSelect(' not in risk,'history iteration cannot collapse the HistorySelect deal list')
    req('HistoryDealGetTicket(i)' in rebuild,'history deals are traversed by ticket')
    req('DEAL_ENTRY_IN' in rebuild and 'DEAL_ENTRY_OUT' in rebuild,'entry and exit deals are reconciled')
    req('HistoryDealGetInteger(deal,DEAL_MAGIC)!=InpMagic' in rebuild,'ledger is seeded only by this EA entries')
    # Exit accounting is position-authoritative after entry; do not require exit deal magic.
    second=rebuild.split('// Pass 2:',1)[1]
    req('HistoryDealGetInteger(deal,DEAL_MAGIC)' not in second,'SL/TP exits are not discarded because of exit-deal magic semantics')
    req('HistoryOrderGetDouble(order_ticket,ORDER_SL)' in risk,'initial risk binds entry-order SL')
    req('HistoryDealGetDouble(deal,DEAL_SL)' in risk,'entry deal SL is deterministic fallback')
    req('OrderCalcProfit(action,_Symbol,volume,entry_price,stop_price,stop_pnl)' in risk,'initial stop risk is converted in account currency')
    req('ledgers[idx].sum_initial_risk+=risk_money' in rebuild,'partial entry fills accumulate initial risk')
    req('ledgers[idx].sum_net+=HistoryDealGetDouble(deal,DEAL_COMMISSION)' in rebuild,'net includes commission')
    req('ledgers[idx].sum_net+=HistoryDealGetDouble(deal,DEAL_SWAP)' in rebuild,'net includes swap')
    req('ledgers[idx].sum_net+=HistoryDealGetDouble(deal,DEAL_FEE)' in rebuild,'net includes fee')

    trans=ea.split('void OnTradeTransaction',1)[1].split('\nvoid StrategyOptimizerProcessMetricFrames()',1)[0]
    forbidden=('g_optimizerSumR+=','g_optimizerSumNet+=','g_optimizerSumRisk+=','g_optimizerClosedTrades++','g_optimizerAccountingErrors++')
    req(not any(x in trans for x in forbidden),'OnTradeTransaction no longer owns scientific fitness accounting')
    req('tester event ordering is not a' in trans,'event-ordering rationale is documented in source')

    worker=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
    req('all(float(r.expectancy_r) <= -1.0e8 for r in rows)' in worker,'all-sentinel runtime remains fail-closed in Python')
    print('V086_OPTIMIZER_HISTORY_REBUILD_PASS')

if __name__=='__main__':
    main()
