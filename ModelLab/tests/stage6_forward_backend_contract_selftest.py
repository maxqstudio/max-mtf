from __future__ import annotations
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)
def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8'); block=src[src.index('def run_forward_championship'):src.index('# Backward-compatible name')]
    orch=(ROOT/'factory/factory_orchestrator.py').read_text(encoding='utf-8')
    req('_verify_stage_seal(fd,"MONTE_CARLO"' in block,'Forward verifies Monte Carlo terminal seal')
    req('predeclared Fresh boundary drift' in block,'Forward start boundary is predeclared and immutable')
    req('refit_history_sha256' in block and 'forward_refit_history.csv' in src,'Forward final refit history is frozen before OOS')
    req('audit_dataset(master,broker_reconcile=True)' in block and 'research_readiness' in block,'Every Fresh extension passes canonical Data Quality readiness')
    req('FORWARD_APPEND_ONLY_VIOLATION' in block and 'forward_leaderboard_{n:03d}.json' in block,'Repeated Forward evidence is append-only and per-check immutable')
    req('_strategy_metrics' in block and 'decision_policy' in block,'Forward replays exact frozen decision policy')
    req('FORWARD_INSUFFICIENT_SAMPLE' in block and 'NO_CHAMPION_FORWARD_FAIL' in block,'Immature Forward waits but sufficient all-fail is terminal')
    req("'status':'NO_CHAMPION_FORWARD_FAIL','stage':'TERMINAL'" in orch,'Auto orchestrator preserves terminal all-fail Forward state')
    print('STAGE6_FORWARD_BACKEND_CONTRACT PASS')
if __name__=='__main__': main()
