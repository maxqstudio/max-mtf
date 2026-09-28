from pathlib import Path
import sys, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
# Simulate a broker-defined market closure by deleting a contiguous M5 segment,
# then reconstruct native higher-TF references from that exact broker session stream.
base=synthetic_native_frames(periods=720)['M5'].copy()
t=pd.to_datetime(base['time'],unit='s',utc=True)
mask=~((t>=pd.Timestamp('2026-01-06T06:00:00Z')) & (t<pd.Timestamp('2026-01-06T12:00:00Z')))
m5=base.loc[mask].reset_index(drop=True)
idx=m5.copy(); idx['time']=pd.to_datetime(idx['time'],unit='s',utc=True); idx=idx.set_index('time')
frames={'M5':m5}
for tf,rule in [('M15','15min'),('H1','1h'),('H4','4h')]:
    g=idx.resample(rule,origin='start_day',closed='left',label='left')
    r=pd.DataFrame({'open':g['open'].first(),'high':g['high'].max(),'low':g['low'].min(),'close':g['close'].last(),'tick_volume':g['tick_volume'].sum(),'spread':g['spread'].last(),'real_volume':g['real_volume'].sum()}).dropna().reset_index()
    r['time']=(pd.to_datetime(r['time'],utc=True).astype('int64')//10**9).astype('int64')
    frames[tf]=r
views,proof=build_canonical_views(frames,price_atol=1e-9)
req(proof['status']=='PASS','broker-defined session gap must not be treated as synthetic missing bars')
req(all(proof['parity'][tf]['status']=='PASS' for tf in ('M15','H1','H4')),'all parity survives explicit session closure')
print('V201_MTF_SESSION_GAP PASS')
