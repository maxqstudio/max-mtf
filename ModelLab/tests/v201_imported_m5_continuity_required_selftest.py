from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index,build_lineage_manifest,build_imported_m5_source_identity,write_bundle,MTFDataError
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)

native=synthetic_native_frames()
views,parity=build_canonical_views(native,price_atol=1e-9)
alignment,am=build_alignment_index(views)
manifest=build_lineage_manifest(
    views,alignment,symbol='XAUUSD',broker_identity={'server':'TEST'},
    source_identity={'kind':'IMPORTED_M5','native_reference_audit':'NOT_RUN'},
    resampling_parity=parity,alignment_meta=am,
)
with tempfile.TemporaryDirectory() as td:
    out=Path(td)/'bundle'
    try:
        write_bundle(out,views,alignment,manifest)
        raise AssertionError('IMPORTED_M5 without native reference must be rejected')
    except MTFDataError:
        pass
    req(not out.exists(),'rejected imported source must not create bundle')

# A valid imported source must still be sealable when the exact native-M5
# reference is supplied and its recomputed proof is identity-bound.
source_identity=build_imported_m5_source_identity(native['M5'],native['M5'],price_atol=1e-9)
valid_manifest=build_lineage_manifest(
    views,alignment,symbol='XAUUSD',broker_identity={'server':'TEST'},
    source_identity=source_identity,resampling_parity=parity,alignment_meta=am,
)
with tempfile.TemporaryDirectory() as td:
    out=Path(td)/'valid_bundle'
    result=write_bundle(out,views,alignment,valid_manifest,native_m5_reference=native['M5'],price_atol=1e-9)
    req(result['status']=='PASS' and out.is_dir(),'valid imported M5 with exact reference must seal')

print('V201_IMPORTED_M5_CONTINUITY_REQUIRED PASS')
