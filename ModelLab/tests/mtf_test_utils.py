from __future__ import annotations
import numpy as np
import pandas as pd


def synthetic_native_frames(periods: int = 576):
    t = pd.date_range('2026-01-05T00:00:00Z', periods=periods, freq='5min')
    x = np.arange(periods, dtype=float)
    base = 2600.0 + 0.05*x + 0.8*np.sin(x/13.0)
    close = base + 0.03*np.cos(x/7.0)
    open_ = np.r_[base[0], close[:-1]]
    high = np.maximum(open_, close) + 0.15 + 0.01*np.sin(x/5.0)**2
    low = np.minimum(open_, close) - 0.15 - 0.01*np.cos(x/5.0)**2
    vol = (100 + (x.astype(int)%17)).astype(int)
    m5 = pd.DataFrame({
        'time': (t.view('int64')//10**9).astype('int64'),
        'open':open_, 'high':high, 'low':low, 'close':close,
        'tick_volume':vol, 'spread':20, 'real_volume':0,
    })
    indexed = m5.copy()
    indexed['time'] = pd.to_datetime(indexed['time'], unit='s', utc=True)
    indexed = indexed.set_index('time')
    refs={'M5':m5}
    for tf,rule in [('M15','15min'),('H1','1h'),('H4','4h')]:
        g=indexed.resample(rule, origin='start_day', closed='left', label='left')
        r=pd.DataFrame({
            'open':g['open'].first(), 'high':g['high'].max(), 'low':g['low'].min(), 'close':g['close'].last(),
            'tick_volume':g['tick_volume'].sum(), 'spread':g['spread'].last(), 'real_volume':g['real_volume'].sum(),
        }).dropna().reset_index()
        r['time']=(pd.to_datetime(r['time'],utc=True).astype('int64')//10**9).astype('int64')
        refs[tf]=r
    return refs
