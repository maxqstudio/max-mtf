from __future__ import annotations
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)
def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8'); block=src[src.index('def run_tournament'):src.index('def _mc_distribution')]
    req('_verify_stage_seal(fd,"CPCV"' in block,'Tournament verifies terminal CPCV seal')
    req('tournament_immutable.csv' in block and 'snapshot_sha256' in block,'Tournament uses pre-frozen holdout snapshot')
    req('_assert_same_candidate' in block,'Tournament binds every row to exact CPCV survivor identity')
    req('_strategy_outcomes' in block and 'decision_policy' in block,'Tournament replays exact base/policy decisions')
    req('TOURNAMENT_SURVIVORS_READY' in block and '_stage_seal(fd,"TOURNAMENT"' in block,'Tournament seals terminal evidence before Monte Carlo')
    req('top_k' not in block.lower() and 'rank_rescue' not in block.lower(),'Tournament does not introduce top-k/rank-rescue authority')
    print('STAGE4_TOURNAMENT_BACKEND_CONTRACT PASS')
if __name__=='__main__': main()
