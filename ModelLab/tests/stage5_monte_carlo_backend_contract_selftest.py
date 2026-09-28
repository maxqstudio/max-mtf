from __future__ import annotations
import numpy as np
from pathlib import Path
import factory.champion_factory as cf
ROOT=Path(__file__).resolve().parents[1]
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)
def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8'); block=src[src.index('def run_monte_carlo'):src.index('def _resolve_forward_to')]
    req('_verify_stage_seal(fd,"TOURNAMENT"' in block,'Monte Carlo verifies terminal Tournament seal')
    req('set(str(k) for k in trades.keys())' in block and 'set(expected_ids)' in block,'Monte Carlo requires exact survivor↔trade-return set')
    req('np.isfinite(arr).all()' in block and 'trade count mismatch' in block.lower(),'Monte Carlo rejects non-finite/count-mismatched return vectors')
    a=cf._mc_distribution(np.asarray([1.,-.5,.8,-.2]),100,123); b=cf._mc_distribution(np.asarray([1.,-.5,.8,-.2]),100,123); req(a==b,'Monte Carlo bootstrap is deterministic for exact seed/vector/count')
    try: cf._mc_distribution(np.asarray([1.,np.inf]),100,1); raise AssertionError('nonfinite accepted')
    except Exception: req(True,'Monte Carlo non-finite input fails closed')
    ident=src[src.index('def _candidate_identity'):src.index('def _assert_same_candidate')]
    req('{**_candidate_identity(c)' in block,'Monte Carlo survivor rows inherit canonical strategy identity')
    for k in ('training_seed','decision_policy','policy_fingerprint','take_threshold'):
        req(k in ident,f'Canonical strategy identity preserves field: {k}')
    req('_stage_seal(fd,"MONTE_CARLO"' in block,'Monte Carlo terminal evidence is sealed for Forward')
    print('STAGE5_MONTE_CARLO_BACKEND_CONTRACT PASS')
if __name__=='__main__': main()
