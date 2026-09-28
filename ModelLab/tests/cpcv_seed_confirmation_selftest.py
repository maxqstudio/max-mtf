from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path

from factory.champion_factory import _cpcv_seed_list, _aggregate_seed_cpcv, _requires_cpcv_seed_confirmation

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def req(cond,msg):
    if not cond: raise AssertionError(msg)
    print('PASS ',msg)

def ev(passed=True, exp=0.2, dd=5.0, rec=2.0, gate=None):
    return {'passed':passed,'first_failed_gate':gate,'reasons':[] if passed else [gate or 'FAIL'],
            'summary':{'median_profit_factor':1.5 if passed else 0.8,'median_expectancy_r':exp,'worst_expectancy_r':exp,
                       'worst_max_drawdown_r':dd,'median_recovery_factor':rec,'worst_recovery_factor':rec},
            'combinations':15,'groups':6,'test_groups':2,'purge_bars':24,'embargo_bars':24,'gates':[],
            'methodology_audit':{'schema':'X'},'paths':[],'terminology':'COMBINATORIAL_PURGED_SPLITS','take_threshold':0.65}

def main():
    req(_requires_cpcv_seed_confirmation('patchtst'),'standalone DL requires CPCV seed confirmation')
    req(_requires_cpcv_seed_confirmation('hybrid::patchtst::lightgbm'),'DL→ML hybrid requires CPCV seed confirmation')
    req(not _requires_cpcv_seed_confirmation('lightgbm'),'tree-only model remains fixed-seed by default')
    req(_cpcv_seed_list(CFG,'patchtst')==[42,11,77],'CPCV uses predeclared fixed 42/11/77 seed set')
    req(_cpcv_seed_list(CFG,'lightgbm')==[42],'tree-only CPCV does not triple compute by default')

    ok=_aggregate_seed_cpcv([{'seed':42,'evidence':ev(True,.3,5,2.2)},{'seed':11,'evidence':ev(True,.2,6,2.0)},{'seed':77,'evidence':ev(True,.1,7,1.8)}])
    req(ok['passed'] and ok['summary']['seed_pass_count']==3,'3/3 fixed-seed PASS is required for seed-stable CPCV survivor')
    req(abs(ok['summary']['worst_expectancy_r']-0.1)<1e-12 and abs(ok['summary']['worst_max_drawdown_r']-7.0)<1e-12,'seed aggregation preserves conservative worst-tail evidence')
    bad=_aggregate_seed_cpcv([{'seed':42,'evidence':ev(True)},{'seed':11,'evidence':ev(False,-.1,9,0.8,'CPCV_WORST_EXPECTANCY')}])
    req(not bad['passed'] and str(bad['first_failed_gate']).startswith('SEED_11::'),'one failed confirmation seed is terminal, not majority-vote PASS')
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    req(('if not bool(sev.get("passed"))' in src or 'if not bool(_sev.get("passed"))' in src) and 'break' in src,'CPCV seed confirmation is progressive and stops compute after first failed seed')
    print('CPCV_SEED_CONFIRMATION_SELFTEST PASS')

if __name__=='__main__': main()
