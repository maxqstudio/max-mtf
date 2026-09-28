from __future__ import annotations
import json, tempfile
from pathlib import Path
import factory.champion_factory as cf
ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def main():
    cfg=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
    req(cfg['champion_factory']['fresh_to_mode']=='AUTO_NEWEST','Forward end authority defaults AUTO_NEWEST')
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    block=src[src.index('def run_forward_championship'):src.index('# Backward-compatible name')]
    req('_verify_stage_seal(fd,"MONTE_CARLO"' in block,'Forward verifies terminal Monte Carlo seal')
    req('FORWARD_APPEND_ONLY_VIOLATION' in block and 'forward_leaderboard_{n:03d}.json' in block,'Forward checks are append-only and keep immutable per-check leaderboards')
    req('_strategy_metrics(' in block and 'decision_policy' in block,'Forward replays exact base/policy strategy identity')
    req('audit_dataset(master,broker_reconcile=True)' in block and 'research_readiness' in block,'Forward fresh rows pass canonical Data Quality authority')
    req('FORWARD_INSUFFICIENT_SAMPLE' in block and 'NO_CHAMPION_FORWARD_FAIL' in block,'Forward distinguishes immature wait from sufficient-sample terminal failure')
    req('forward_refit_history.csv' in src and 'refit_history_sha256' in block,'Forward uses frozen predeclared refit history')
    with tempfile.TemporaryDirectory() as td:
        fd=Path(td)
        # Missing MC contract/seal must fail closed before any scoring.
        (fd/'factory_manifest.json').write_text(json.dumps({'status':'MONTE_CARLO_SURVIVORS_READY','forward_checks':[]}),encoding='utf-8')
        (fd/'monte_carlo_survivors.json').write_text(json.dumps([{'pool_id':'CAND_01'}]),encoding='utf-8')
        try:
            cf.run_forward_championship(fd,fd/'master.csv',ROOT/'config/config.json')
            raise AssertionError('Forward accepted unsealed MC input')
        except RuntimeError as e:
            req('Monte Carlo stage contract missing' in str(e),'Forward rejects legacy/unsealed Monte Carlo fixture')
    print('FORWARD_CHAMPIONSHIP_SELFTEST PASS')

if __name__=='__main__': main()
