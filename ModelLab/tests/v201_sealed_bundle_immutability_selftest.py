from pathlib import Path
import hashlib,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index,build_lineage_manifest,write_bundle,MTFDataError
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
views,parity=build_canonical_views(synthetic_native_frames(),price_atol=1e-9); alignment,am=build_alignment_index(views)
manifest=build_lineage_manifest(views,alignment,symbol='XAUUSD',broker_identity={'server':'TEST'},source_identity={'kind':'SYNTHETIC_TEST'},resampling_parity=parity,alignment_meta=am)
with tempfile.TemporaryDirectory() as td:
    dest=Path(td)/'sealed'; r=write_bundle(dest,views,alignment,manifest)
    req(r['sealed'] is True and r['atomic_commit'] is True,'bundle reports sealed atomic commit')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file()}
    try:
        write_bundle(dest,views,alignment,manifest)
        raise AssertionError('sealed destination overwrite must fail')
    except MTFDataError:
        pass
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file()}
    req(before==after,'failed overwrite cannot mutate sealed evidence')
print('V201_SEALED_BUNDLE_IMMUTABILITY PASS')
