from pathlib import Path
import sys,pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from mtf.mtf_data import normalize_native_frame,MTFDataError

def frame(times):
    n=len(times)
    return pd.DataFrame({'time':times,'open':[1.0]*n,'high':[1.1]*n,'low':[0.9]*n,'close':[1.0]*n,'tick_volume':[10]*n})
def req(x,msg):
    if not x: raise AssertionError(msg)
failed=False
try: normalize_native_frame(frame(['2026-01-01 00:00','2026-01-01 00:05']),'M5')
except MTFDataError: failed=True
req(failed,'naive timestamps without source_timezone fail closed')
x=normalize_native_frame(frame(['2026-01-01 00:00','2026-01-01 00:05']),'M5',source_timezone='UTC')
req(str(x['open_time_utc'].dt.tz)=='UTC','explicit UTC normalization')
# Europe/Berlin 2026-10-25 02:30 is DST-ambiguous; do not guess fold.
failed=False
try: normalize_native_frame(frame(['2026-10-25 02:30','2026-10-25 02:35']),'M5',source_timezone='Europe/Berlin')
except MTFDataError: failed=True
req(failed,'DST-ambiguous broker-local timestamps fail closed')
print('V201_MTF_TIMEZONE PASS')
