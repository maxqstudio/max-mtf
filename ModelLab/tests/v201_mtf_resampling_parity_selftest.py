from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
frames=synthetic_native_frames()
views,proof=build_canonical_views(frames,price_atol=1e-9)
req(proof['status']=='PASS','parity set pass')
for tf in ('M15','H1','H4'):
    p=proof['parity'][tf]
    req(p['status']=='PASS' and p['failed_bars']==0,tf+' native parity')
    req(p['authority'].startswith('OHLCV_DERIVED_FROM_M5'),tf+' M5 value authority')
    req(len(views[tf])>0,tf+' derived rows')
    req((views[tf]['source_m5_rows']>0).all(),tf+' source row lineage')
print('V201_MTF_RESAMPLING_PARITY PASS')
