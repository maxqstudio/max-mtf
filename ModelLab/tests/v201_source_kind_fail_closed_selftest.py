from __future__ import annotations
import os,tempfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index,build_lineage_manifest,write_bundle,MTFDataError,build_imported_m5_source_identity
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

native=synthetic_native_frames(); views,parity=build_canonical_views(native,price_atol=1e-9); a,am=build_alignment_index(views)

def manifest(kind,extra=None):
    src={'kind':kind}; src.update(extra or {})
    return build_lineage_manifest(views,a,symbol='XAUUSD',broker_identity={'server':'TEST'},source_identity=src,resampling_parity=parity,alignment_meta=am)

def rejected(kind):
    with tempfile.TemporaryDirectory() as td:
        try: write_bundle(Path(td)/'b',views,a,manifest(kind))
        except MTFDataError: return True
        return False
for kind in ('IMPORTED_CSV','CSV','UNKNOWN','',None):
    req(rejected(kind),'unknown/empty source kind rejected: '+repr(kind))
with tempfile.TemporaryDirectory() as td:
    r=write_bundle(Path(td)/'direct',views,a,manifest('DIRECT_MT5_NATIVE_RATES'))
    req(r['status']=='PASS','known direct MT5 production source accepted')
imp=build_imported_m5_source_identity(native['M5'],native['M5'],price_atol=1e-9)
with tempfile.TemporaryDirectory() as td:
    r=write_bundle(Path(td)/'imported',views,a,build_lineage_manifest(views,a,symbol='XAUUSD',broker_identity={'server':'TEST'},source_identity=imp,resampling_parity=parity,alignment_meta=am),native_m5_reference=native['M5'],price_atol=1e-9)
    req(r['status']=='PASS','known imported M5 accepted only with exact native reference')
old=os.environ.pop('MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE',None)
try:
    req(rejected('SYNTHETIC_TEST'),'synthetic test source rejected outside explicit test mode')
finally:
    if old is not None: os.environ['MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE']=old
print('V201_SOURCE_KIND_FAIL_CLOSED PASS')
