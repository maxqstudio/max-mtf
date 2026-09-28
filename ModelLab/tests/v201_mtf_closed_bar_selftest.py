from pathlib import Path
import sys,pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
frames=synthetic_native_frames(periods=720)
# 2026-01-07 00:00 UTC is an H4/H1/M15 boundary in the synthetic stream.
asof=pd.Timestamp('2026-01-07T00:00:00Z')
views,proof=build_canonical_views(frames,price_atol=1e-9,asof_utc=asof)
req(proof['status']=='PASS','sealed asof parity')
req((pd.to_datetime(views['M5']['close_time_utc'],utc=True)<=asof).all(),'M5 view contains closed bars only')
for tf in ('M15','H1','H4'):
    req((pd.to_datetime(views[tf]['close_time_utc'],utc=True)<=asof).all(),tf+' view contains closed bars only')
a,_=build_alignment_index(views)
req((pd.to_datetime(a['decision_time_utc'],utc=True)<=asof).all(),'decision index cannot exceed sealed asof')
print('V201_MTF_CLOSED_BAR PASS')
