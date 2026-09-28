from pathlib import Path
import sys,tempfile,pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/'tests'))
from mtf.mtf_data import build_canonical_views,build_alignment_index,build_lineage_manifest,write_bundle,MTFDataError,audit_m5_against_native_reference
from mtf.mtf_data_quality import audit_canonical_bundle
from mtf_test_utils import synthetic_native_frames

def req(x,msg):
    if not x: raise AssertionError(msg)

def higher_refs_from_m5(m5):
    indexed=m5.copy(); indexed['time']=pd.to_datetime(indexed['time'],unit='s',utc=True); indexed=indexed.set_index('time')
    refs={'M5':m5.copy()}
    for tf,rule in [('M15','15min'),('H1','1h'),('H4','4h')]:
        g=indexed.resample(rule,origin='start_day',closed='left',label='left')
        r=pd.DataFrame({
            'open':g['open'].first(),'high':g['high'].max(),'low':g['low'].min(),'close':g['close'].last(),
            'tick_volume':g['tick_volume'].sum(),'spread':g['spread'].last(),'real_volume':g['real_volume'].sum(),
        }).dropna().reset_index()
        r['time']=(pd.to_datetime(r['time'],utc=True).astype('int64')//10**9).astype('int64')
        refs[tf]=r
    return refs

# Make one interior M5 bar aggregate-neutral, then remove it from the imported source.
base=synthetic_native_frames()['M5'].copy()
lo=min(float(base.loc[0,'low']),float(base.loc[2,'low'])); hi=max(float(base.loc[0,'high']),float(base.loc[2,'high'])); mid=(lo+hi)/2.0
for c in ('open','high','low','close'): base.loc[1,c]=mid
base.loc[1,'tick_volume']=0; base.loc[1,'real_volume']=0
native=higher_refs_from_m5(base)
imported={k:v.copy() for k,v in native.items()}
imported['M5']=base.drop(index=1).reset_index(drop=True)

views,parity=build_canonical_views(imported,price_atol=1e-9)
req(parity['status']=='PASS' and all(x['status']=='PASS' for x in parity['parity'].values()),'higher-TF aggregate parity must remain PASS in adversarial neutral-bar case')
alignment,am=build_alignment_index(views)
dq=audit_canonical_bundle(views,alignment,parity); req(dq['status']=='PASS','ordinary DQ intentionally cannot see broker-reference missing neutral bar')
continuity=audit_m5_against_native_reference(imported['M5'],native['M5'],price_atol=1e-9)
req(continuity['status']=='FAIL' and continuity['missing_count']==1,'exact native-M5 reference must detect the missing neutral bar')

# Forge a superficially PASS proof; seal-time recomputation must still reject it.
fake=dict(continuity); fake['status']='PASS'; fake['missing_count']=0; fake['missing_timestamps']=[]
manifest=build_lineage_manifest(
    views,alignment,symbol='XAUUSD',broker_identity={'server':'TEST'},
    source_identity={'kind':'IMPORTED_M5','native_reference_audit':fake,'native_reference_m5_sha256':'0'*64},
    resampling_parity=parity,alignment_meta=am,data_quality=dq,
)
with tempfile.TemporaryDirectory() as td:
    out=Path(td)/'bundle'
    try:
        write_bundle(out,views,alignment,manifest,native_m5_reference=native['M5'],price_atol=1e-9)
        raise AssertionError('neutral missing imported M5 bar must be rejected at seal')
    except MTFDataError:
        pass
    req(not out.exists(),'failed continuity proof must not seal a bundle')
print('V201_IMPORTED_M5_NEUTRAL_BAR_MISSING PASS')
