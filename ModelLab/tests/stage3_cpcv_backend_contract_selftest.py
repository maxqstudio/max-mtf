from __future__ import annotations
import json
from pathlib import Path
from copy import deepcopy
import factory.champion_factory as cf
ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)
def ev(ok=True,gate=None):
    return {'passed':ok,'first_failed_gate':gate,'reasons':[] if ok else [gate or 'FAIL'],'summary':{'median_profit_factor':1.5,'median_expectancy_r':.2 if ok else -.1,'worst_expectancy_r':.2 if ok else -.1,'worst_max_drawdown_r':5.0,'median_recovery_factor':2.0,'worst_recovery_factor':2.0},'combinations':15,'groups':6,'test_groups':2,'purge_bars':24,'embargo_bars':24,'gates':{'CPCV_WORST_EXPECTANCY':ok},'methodology_audit':{}}
def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8'); csrc=(ROOT/'research/cpcv.py').read_text(encoding='utf-8')
    block=src[src.index('def run_cpcv_qualification'):src.index('def run_tournament')]
    req('CPCV_MANDATORY_EXACT' in block and '(6,2,15)' in block,'CPCV is mandatory exact 6 groups / 2 test groups / 15 combinations')
    req('_verify_stage_seal(fd,"DISCOVERY"' in block,'CPCV verifies sealed Discovery input')
    req('_assert_temporal_leakage_guard(cfg,require_embargo=True)' in block,'CPCV enforces purge and embargo against label horizon')
    req(cf._cpcv_seed_list(CFG,'patchtst')==[42,11,77],'Temporal CPCV fixed seed sequence is 42→11→77')
    ok=cf._aggregate_seed_cpcv([{'seed':42,'evidence':ev()},{'seed':11,'evidence':ev()},{'seed':77,'evidence':ev()}],[42,11,77]); req(ok['passed'],'All three fixed temporal seeds are required and accepted')
    bad=cf._aggregate_seed_cpcv([{'seed':42,'evidence':ev()},{'seed':11,'evidence':ev(False,'CPCV_WORST_EXPECTANCY')}],[42,11,77]); req(not bad['passed'] and str(bad['first_failed_gate']).startswith('SEED_11::'),'First failed confirmation seed makes aggregate fail closed')
    req('decision_policy' in csrc and 'policy_trading_metrics' in csrc,'CPCV replays frozen CP_POLICY_V1 strategy')
    req('_write(fd/"cpcv_survivors.json",survivors)' in block and '_write(fd/"candidate_pool.json"' not in block,'CPCV keeps separate survivor authority without mutating Discovery Pool')
    req('cpcv_live_split_results.json' in block and 'training_seed' in block and 'split_done' in block,'CPCV live split telemetry is persisted per seed without mutating frozen Pool')
    print('STAGE3_CPCV_BACKEND_CONTRACT PASS')
if __name__=='__main__': main()
