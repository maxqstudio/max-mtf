from pathlib import Path
import sys, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index,audit_alignment
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)
views,_=build_canonical_views(synthetic_native_frames(),price_atol=1e-9)
a,meta=build_alignment_index(views)
req(meta['status']=='PASS' and len(a)>0,'alignment ready')
req(audit_alignment(a)['status']=='PASS','causal audit')
t=pd.to_datetime(a['decision_time_utc'],utc=True)
for p in ('h4','h1','m15','m5'):
    c=pd.to_datetime(a[p+'_close_time_utc'],utc=True)
    req(bool((c<=t).all()),p+' fully closed')
req(bool((pd.to_datetime(a['m15_close_time_utc'],utc=True)==t).all()),'primary decision clock exact')
# At a shared H1/H4 boundary, exact close is legal and should be selected.
shared=a[(pd.to_datetime(a['decision_time_utc'],utc=True).dt.minute==0) & (pd.to_datetime(a['decision_time_utc'],utc=True).dt.hour%4==0)]
req(len(shared)>0,'shared boundary exists')
r=shared.iloc[0]
req(pd.Timestamp(r['h4_close_time_utc'])==pd.Timestamp(r['decision_time_utc']),'just-closed H4 admitted at exact boundary')
req(pd.Timestamp(r['h1_close_time_utc'])==pd.Timestamp(r['decision_time_utc']),'just-closed H1 admitted at exact boundary')
print('V201_MTF_ALIGNMENT PASS')
