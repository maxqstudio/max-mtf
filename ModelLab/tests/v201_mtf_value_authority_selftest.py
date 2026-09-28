from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,MTFDataError
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
frames=synthetic_native_frames()
# Corrupt only native H1 close. If code copied higher-TF values instead of rebuilding
# from M5, this could leak through. Correct behavior is parity failure.
bad={k:v.copy() for k,v in frames.items()}; bad['H1'].loc[5,'close'] += 1.0
failed=False
try: build_canonical_views(bad,price_atol=1e-9)
except MTFDataError: failed=True
req(failed,'higher-TF native value mismatch must fail rather than become canonical value')
print('V201_MTF_VALUE_AUTHORITY PASS')
