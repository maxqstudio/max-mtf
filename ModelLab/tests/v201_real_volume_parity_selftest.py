from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,MTFDataError
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)

# Zero-only MT5 real volume is explicit unavailability, not silently omitted.
frames=synthetic_native_frames()
_,proof=build_canonical_views(frames,price_atol=1e-9)
for tf in ('M15','H1','H4'):
    req(proof['parity'][tf]['real_volume_mode']=='UNAVAILABLE_ZERO_ONLY',tf+' zero-only real volume recorded unavailable')

# Adversarial native higher-TF real volume must fail when it becomes populated.
bad=synthetic_native_frames(); bad['H1']=bad['H1'].copy(); bad['H1'].loc[0,'real_volume']=999999
try:
    build_canonical_views(bad,price_atol=1e-9)
    raise AssertionError('native H1 real_volume corruption must fail parity')
except MTFDataError:
    pass

# When real volume is available, exact parity is mandatory and can pass.
frames=synthetic_native_frames(); m5=frames['M5'].copy(); m5['real_volume']=1+(m5.index%5); frames['M5']=m5
idx=m5.copy(); idx['time']=pd.to_datetime(idx['time'],unit='s',utc=True); idx=idx.set_index('time')
for tf,rule in [('M15','15min'),('H1','1h'),('H4','4h')]:
    g=idx.resample(rule,origin='start_day',closed='left',label='left')
    r=pd.DataFrame({'open':g['open'].first(),'high':g['high'].max(),'low':g['low'].min(),'close':g['close'].last(),
                    'tick_volume':g['tick_volume'].sum(),'spread':g['spread'].last(),'real_volume':g['real_volume'].sum()}).dropna().reset_index()
    r['time']=(pd.to_datetime(r['time'],utc=True).astype('int64')//10**9).astype('int64'); frames[tf]=r
_,proof=build_canonical_views(frames,price_atol=1e-9)
for tf in ('M15','H1','H4'):
    req(proof['parity'][tf]['real_volume_mode']=='EXACT_PARITY_REQUIRED',tf+' available real volume exact parity active')
    req(proof['parity'][tf]['real_volume_failed_bars']==0,tf+' available real volume exact')
print('V201_REAL_VOLUME_PARITY PASS')
