from __future__ import annotations
import tempfile
from pathlib import Path

import data.data_quality as dq
import host.mt5_gap_repair as gr
ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'ui/app.py').read_text(encoding='utf-8')
FW=(ROOT/'factory/factory_worker.py').read_text(encoding='utf-8')
GAP=(ROOT/'host/mt5_gap_repair.py').read_text(encoding='utf-8')


def req(x,msg):
    if not x:
        raise AssertionError(msg)


def main():
    # UI/manual audit must be local/cached only. MT5 is reserved for REPAIR/VERIFY.
    dq_block=APP.split('def _render_data_quality',1)[1].split('\ndef ',1)[0]
    req('audit_dataset(dataset,broker_reconcile=False,use_cached_broker_proof=True)' in dq_block,
        'AUDIT DATA QUALITY must never launch MT5')
    req('REPAIR / VERIFY WITH MT5' in dq_block and 'run_gap_repair_cycle' in dq_block,
        'manual staged repair entrypoint missing')

    # AUTO Research follows the same local PASS / repair-on-FAIL contract.
    helper=FW.split('def _prepare_auto_data_quality',1)[1].split('\ndef main',1)[0]
    req('broker_reconcile=False,use_cached_broker_proof=True' in helper,
        'AUTO initial audit is not local/cached')
    req(helper.index('broker_reconcile=False') < helper.index('run_gap_repair_cycle'),
        'AUTO may open MT5 before local audit fails')
    req('mt5_opened_only_after_local_fail' in helper,
        'AUTO completion evidence does not encode staged authority')

    # Exact-SHA proof cache lets unchanged valid data PASS later without reopening MT5.
    with tempfile.TemporaryDirectory() as td:
        old=dq._broker_proof_dir
        try:
            dq._broker_proof_dir=lambda: Path(td)
            broker={'verified':True,'status':'VERIFIED','source_backed_missing_count':0,'dataset_only_count':0,'missing_timestamps':[],'dataset_only_timestamps':[],'server':'Demo'}
            dq._save_cached_broker_proof('abc123',broker)
            got=dq._load_cached_broker_proof('abc123')
            req(got and got.get('verified') and got.get('proof_cache')=='EXACT_DATASET_SHA256','exact-SHA broker proof cache failed')
            req(dq._load_cached_broker_proof('different') is None,'broker proof must never cross dataset SHA')
        finally:
            dq._broker_proof_dir=old

    # Reproduce the reported FF FE MT5 preset defect directly.
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'Max.set'
        p.write_text('InpSL_ATR=3.2\n',encoding='utf-16')
        req(p.read_bytes().startswith(b'\xff\xfe'),'UTF-16 fixture invalid')
        text,enc=gr._read_mt5_text(p)
        req(enc=='utf-16' and 'InpSL_ATR=3.2' in text,'MT5 UTF-16 preset decoder failed')
        q=Path(td)/'Max_GapRepair.set'
        gr._write_mt5_text(q,text+'InpWriteTrainingData=true\n',enc)
        req(q.read_bytes().startswith(b'\xff\xfe'),'MT5 repair preset encoding was not preserved')

    req('run_gap_repair_cycle' in GAP and 'REPAIRED_AND_VERIFIED' in GAP,
        'repair cycle does not require post-repair broker verification')
    print('V0.11.1 DATA QUALITY STAGED REPAIR PASS')


if __name__=='__main__':
    main()
