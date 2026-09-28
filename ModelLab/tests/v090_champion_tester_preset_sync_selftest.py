from __future__ import annotations
import shutil, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
from strategy.strategy_optimizer import (
    EA_SOURCE, ABSOLUTE_BOUNDS, DEFAULT_SPACE,
    apply_champion_to_canonical_ea, write_champion_tester_preset,
    assert_champion_ea_set_parity, parse_set_optimizer_entries,
)


def req(cond,msg):
    if not cond:
        raise AssertionError(msg)

params={}
for name,(lo,hi,step,typ) in ABSOLUTE_BOUNDS.items():
    # Choose deterministic non-default values where possible so stale preset/defaults are detectable.
    v=min(hi,lo+step*2)
    params[name]=int(round(v)) if typ=='int' else float(v)

with tempfile.TemporaryDirectory() as td:
    base=Path(td)
    ea=base/'Max.mq5'; shutil.copy2(EA_SOURCE,ea)
    set_path=base/'Max.set'
    req_obj={
        'installation':{'data_dir':str(base)},
        'confirm_symbol':'XAGUSD',
        'search_space':DEFAULT_SPACE,
        'fixed_param_values':params,
    }
    apply_champion_to_canonical_ea(params,source=ea)
    manifest=write_champion_tester_preset(req_obj,params,path=set_path)
    req(manifest.get('preset_name')=='Max.set','Champion handoff must use canonical Max.set')
    req(manifest.get('all_values_match_champion') is True,'Champion Max.set must exactly match Champion parameters')
    req(manifest.get('all_optimization_flags_disabled') is True,'Champion Max.set must disable optimization flags')
    entries=parse_set_optimizer_entries(set_path.read_text(encoding='utf-8'))
    req(set(entries)==set(ABSOLUTE_BOUNDS),'Champion Max.set must contain every optimizer-owned input')
    req(all(v.get('optimize')=='N' for v in entries.values()),'No stale optimization range may remain active in Champion Max.set')
    parity=assert_champion_ea_set_parity(params,set_path,ea_source=ea)
    req(parity.get('ea_defaults_match_champion') and parity.get('tester_preset_matches_champion'),'EA defaults and Tester Max.set must both match Champion')

worker=(ROOT/'strategy/strategy_optimizer_worker.py').read_text(encoding='utf-8')
registry=(ROOT/'strategy/strategy_challenger_registry.py').read_text(encoding='utf-8')
req('register_optimizer_challenger' in worker and 'STRATEGY_CHALLENGER_FOUND' in worker,'Optimizer winner must become Strategy Challenger without canonical Champion mutation')
req('write_champion_tester_preset(req,params,path=tester_set)' in registry,'Explicit Strategy promotion must atomically commit canonical Tester Max.set')
req('assert_champion_ea_set_parity(params,tester_set,ea_source=EA_SOURCE)' in registry,'Explicit Strategy promotion must verify EA/Max.set parity before Champion authority changes')
req('before_set=tester_set.read_bytes() if tester_set.exists() else None' in registry,'Strategy promotion must snapshot prior Tester preset for rollback')
req('tester_set.write_bytes(before_set)' in registry and 'tester_set.unlink(missing_ok=True)' in registry,'Failed Strategy promotion must restore/remove Tester preset fail-closed')
req('DEMOTED_CHAMPION' in registry and 'promotion_history' in registry,'Promotion must demote the prior Champion with lineage evidence')

print('V090_CHAMPION_TESTER_PRESET_SYNC PASS')
