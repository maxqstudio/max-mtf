from __future__ import annotations
import tempfile, json
from pathlib import Path
import factory.champion_factory as cf
ROOT=Path(__file__).resolve().parents[1]
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)
def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8'); block=src[src.index('elif passed:'):src.index('else:\n        status="NO_CHAMPION_FORWARD_FAIL"',src.index('elif passed:'))]
    req('CP_CHAMPION_RUNTIME_V2' in block,'Champion writes explicit runtime manifest authority')
    req('feature_order' in block and 'class_order' in block and '["SELL","SKIP","BUY"]' in block,'Champion locks CP32 feature order and class order')
    req('max_abs_error' in block and 'max_onnx_abs_error' in block,'Champion promotion requires ONNX parity tolerance')
    req('champion_promotion' in block and 'Champion promotion blocked:' in block,'Champion uses deterministic promotion profile instead of a sixth statistical backtest gate')
    req('ALL_UPSTREAM_PASS' in block and 'ARTIFACT_INTEGRITY' in block and 'NO_POST_FORWARD_TUNING' in block and 'ONNX_EXPORT' in block and 'ONNX_PARITY' in block,'Champion promotion evidence covers upstream/integrity/freeze/export/parity')
    req('decision_policy.csv' in block and 'decision_policy_sha256' in block,'Policy-qualified Champion exports separate hashed policy runtime artifact')
    req('refit_history_sha256' in block and 'forward_snapshot_sha256' in block,'Champion provenance binds historical refit and locked Forward snapshot')
    req('_stage_seal(fd,"CHAMPION"' in block and 'champion_terminal_seal' not in block.split('_stage_seal(fd,"CHAMPION"',1)[1],'Champion seal is not invalidated by self-referential champion.json rewrite')
    with tempfile.TemporaryDirectory() as td:
        fd=Path(td); (fd/'champion.json').write_text(json.dumps({'pool_id':'C1'}),encoding='utf-8'); c={'winner_identity':{'pool_id':'C1'}}
        cf._stage_seal(fd,'CHAMPION',contract=c,files=['champion.json']); req(bool(cf._verify_stage_seal(fd,'CHAMPION',expected=c)),'Champion seal verifies immutable artifact and contract')
    print('STAGE7_CHAMPION_BACKEND_CONTRACT PASS')
if __name__=='__main__': main()
