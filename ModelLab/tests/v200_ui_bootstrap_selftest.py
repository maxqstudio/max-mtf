from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def req(x,msg):
    if not x: raise AssertionError(msg)
app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
req('page_title="Max MTF · v2.0.1"' in app,'UI page title Max MTF')
req('MTF Research<span class="cp-side-build">v2.0.1</span>' in app,'sidebar identity Max MTF v2.0.1')
req('Strategy Champion: 0 · Baseline Active is not a Champion.' in app,'UI explicit zero Strategy Champion bootstrap')
req('EA_v2_00/baseline/Max_MTF.mq5' in app,'UI active EA identity')
req('MT5/Experts/MaxMTF' in app,'UI isolated MT5 expert target')
req('Max_MTF.set' in app,'UI isolated Tester preset')
print('V200_UI_BOOTSTRAP PASS')
