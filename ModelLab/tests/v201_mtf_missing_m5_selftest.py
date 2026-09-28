from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import audit_m5_against_native_reference,build_canonical_views,MTFDataError
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
frames=synthetic_native_frames()
missing=frames['M5'].drop(index=100).reset_index(drop=True)
a=audit_m5_against_native_reference(missing,frames['M5'],price_atol=1e-9)
req(a['status']=='FAIL' and a['missing_count']==1,'one missing native M5 must fail exact reference audit')
mut=dict(frames); mut['M5']=missing
failed=False
try: build_canonical_views(mut,price_atol=1e-9)
except MTFDataError: failed=True
req(failed,'missing M5 must not silently survive derived native parity')
print('V201_MTF_MISSING_M5 PASS')
