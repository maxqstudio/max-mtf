from pathlib import Path
import sys, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
views,_=build_canonical_views(synthetic_native_frames(),price_atol=1e-9)
a,_=build_alignment_index(views)
idx=max(1,len(a)//3); t=pd.Timestamp(a.iloc[idx]['decision_time_utc'])
before=a.loc[a['decision_time_utc']==t,'m5_open_time_utc'].iloc[0]
# Add a distinctive M5 bar strictly after t. Directional as-of selection at t must not change.
f=views['M5'].iloc[-1:].copy()
f['open_time_utc']=t+pd.Timedelta(minutes=5)
f['close_time_utc']=t+pd.Timedelta(minutes=10)
f['source_first_m5_open_utc']=f['open_time_utc']; f['source_last_m5_open_utc']=f['open_time_utc']
views2=dict(views); views2['M5']=pd.concat([views['M5'],f],ignore_index=True).sort_values('open_time_utc',kind='stable').drop_duplicates('open_time_utc',keep='first')
a2,_=build_alignment_index(views2)
after=a2.loc[a2['decision_time_utc']==t,'m5_open_time_utc'].iloc[0]
req(pd.Timestamp(before)==pd.Timestamp(after),'future M5 must not alter directional alignment')
req(pd.Timestamp(a2.loc[a2['decision_time_utc']==t,'m5_close_time_utc'].iloc[0])<=t,'future M5 close cannot be selected')
print('V201_MTF_FUTURE_LEAKAGE PASS')
