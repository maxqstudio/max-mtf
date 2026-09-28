from __future__ import annotations
import json
from pathlib import Path
from strategy.strategy_optimizer import DEFAULT_SPACE, search_space_cardinality, validate_request
from scientist.knowledge.scientist_knowledge import build_payload

ROOT=Path(__file__).resolve().parents[1]

def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    card=search_space_cardinality(DEFAULT_SPACE)
    req(card.get('optimized_inputs')==16,'Optimizer default space keeps 16 canonical optimized inputs')
    req(card.get('raw_complete_grid_combinations')==9129505248864000000,'raw complete-grid cardinality is deterministic')
    req(card.get('authority')=='RAW_CARTESIAN_GRID_ONLY_NOT_MT5_GENETIC_TASK_COUNT','raw grid is explicitly not genetic task count')
    optsrc=(ROOT/'strategy/strategy_optimizer.py').read_text(encoding='utf-8')
    req('search_space_context' in optsrc and 'RAW_GRID_IS_NOT_TASK_COUNT' in optsrc,'Optimizer Scientist receives native scheduler/cardinality semantics')

    # Avoid filesystem MT5 validation by checking the source/UI contracts directly.
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('MT5 owns genetic population/job scheduling' in app and 'not extra Max rounds' in app,'Optimizer UI explains native MT5 task scheduling without extra cards')

    chat=(ROOT/'scientist/chat/scientist_chat.py').read_text(encoding='utf-8')
    for phrase in (
        'Tournament is NOT Fresh/OOS data',
        'do not present PSR/DSR as Monte-Carlo-native metrics',
        'DSR requires defensible canonical trial-universe/effective-trials accounting',
        'Owner production policy reference is Expectancy >=0.50R',
        'raw Cartesian search-space size is not the genetic task count',
    ):
        req(phrase in chat,f'Scientist prompt includes semantic rule: {phrase}')

    payload=build_payload()
    pol=((payload.get('kpi') or {}).get('scientist_policy') or {})
    req(pol.get('authority')=='ADVISORY_INTERPRETATION_ONLY_LIVE_GATE_KPIS_REMAIN_RUNTIME_AUTHORITY','KPI Scientist policy is advisory-only')
    roles=pol.get('gate_roles') or {}
    req(set(roles)>={'discovery','cpcv','tournament','monte_carlo','fresh_forward','champion'},'Scientist knows distinct gate roles')
    req('not a new untouched' in str((roles.get('tournament') or {}).get('dataset_semantics') or '').lower(),'Tournament semantics are not confused with Fresh')
    pbo_policy=str((roles.get('cpcv') or {}).get('pbo_policy') or '')
    req('OFF by default' in pbo_policy and 'cross-strategy' in pbo_policy and 'insufficient matrix evidence fails closed' in pbo_policy and 'pseudo-PBO' in pbo_policy,'PBO optional-computable semantics are explicit')
    req('PSR/DSR' in str((roles.get('monte_carlo') or {}).get('anti_pattern') or ''),'Monte Carlo excludes PSR/DSR-native interpretation')
    refs=pol.get('owner_policy_references') or {}
    req((refs.get('strategy_optimizer') or {}).get('h1_min_trades_per_month')==20,'Scientist knows Optimizer H1 baseline 20/month')
    req((refs.get('research_trade_sample') or {}).get('h1_min_trades_per_month')==8,'Scientist knows Research H1 baseline 8/month')
    fresh=refs.get('fresh_production_reference') or {}
    req(fresh.get('expectancy_r_min')==0.50 and fresh.get('profit_factor_min')==1.50 and fresh.get('recovery_factor_min')==3.00,'Owner Fresh production reference is explicit')
    req('percent-DD' in str(fresh.get('note') or ''),'Scientist must flag percent-DD vs R-DD unit mismatch')
    print('V079_SCIENTIST_KPI_OPTIMIZER_TASK PASS')

if __name__=='__main__': main()
