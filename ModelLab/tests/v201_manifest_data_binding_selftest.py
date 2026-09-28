from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index,build_lineage_manifest,write_bundle,MTFDataError
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
views,parity=build_canonical_views(synthetic_native_frames(),price_atol=1e-9); alignment,am=build_alignment_index(views)
manifest=build_lineage_manifest(views,alignment,symbol='XAUUSD',broker_identity={'server':'TEST'},source_identity={'kind':'SYNTHETIC_TEST'},resampling_parity=parity,alignment_meta=am)
mut={k:v.copy() for k,v in views.items()}; mut['M5']=mut['M5'].copy(); mut['M5'].loc[0,'close']+=0.01; mut['M5'].loc[0,'high']=max(mut['M5'].loc[0,'high'],mut['M5'].loc[0,'close'])
with tempfile.TemporaryDirectory() as td:
    dest=Path(td)/'sealed'
    try:
        write_bundle(dest,mut,alignment,manifest)
        raise AssertionError('stale manifest must not bind modified data')
    except MTFDataError:
        pass
    req(not dest.exists(),'manifest mismatch leaves no final bundle')
print('V201_MANIFEST_DATA_BINDING PASS')
