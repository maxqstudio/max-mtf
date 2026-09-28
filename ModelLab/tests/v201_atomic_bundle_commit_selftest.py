from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
import mtf.mtf_data as mtf_data
from mtf.mtf_data import build_canonical_views,build_alignment_index,build_lineage_manifest,write_bundle,MTFDataError
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
views,parity=build_canonical_views(synthetic_native_frames(),price_atol=1e-9); alignment,am=build_alignment_index(views)
manifest=build_lineage_manifest(views,alignment,symbol='XAUUSD',broker_identity={'server':'TEST'},source_identity={'kind':'SYNTHETIC_TEST'},resampling_parity=parity,alignment_meta=am)
with tempfile.TemporaryDirectory() as td:
    parent=Path(td); dest=parent/'sealed'
    original=mtf_data._readback_canonical_hash
    calls={'n':0}
    def corrupt(path):
        calls['n']+=1
        if calls['n']==1: return '0'*64
        return original(path)
    mtf_data._readback_canonical_hash=corrupt
    try:
        try:
            write_bundle(dest,views,alignment,manifest)
            raise AssertionError('staging verification failure must abort commit')
        except MTFDataError:
            pass
    finally:
        mtf_data._readback_canonical_hash=original
    req(not dest.exists(),'failed staged verification exposes no final directory')
    req(not list(parent.glob('.sealed.staging-*')),'failed commit cleans staging directory')
    req(not (parent/'.sealed.commit.lock').exists(),'failed commit cleans commit lock')
    ok=write_bundle(dest,views,alignment,manifest)
    req(ok['status']=='PASS' and ok['atomic_commit'] is True and dest.is_dir(),'verified staging atomically promoted')
print('V201_ATOMIC_BUNDLE_COMMIT PASS')
