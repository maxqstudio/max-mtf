from pathlib import Path
import json, sys
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent; sys.path.insert(0,str(ROOT))
from core.project_paths import PROJECT_VERSION, MTF_NATIVE_DIR, MTF_BUNDLES_DIR
from mtf.mtf_data import ROLE_TO_TIMEFRAME

def req(x,msg):
    if not x: raise AssertionError(msg)
cfg=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))['mtf_data']
req(PROJECT_VERSION=='2.0.1','project version')
req(cfg['phase']=='MTF-1_DATA_FOUNDATION','MTF-1 config phase')
req(cfg['source_timeframe']=='M5' and cfg['primary_timeframe']=='M15','M5 source/M15 primary')
req(cfg['role_to_timeframe']==ROLE_TO_TIMEFRAME,'role ladder exact')
req(cfg['canonical_timezone']=='UTC','canonical UTC')
req(cfg['native_higher_tf_usage']=='BOUNDARY_AND_PARITY_ONLY','higher TF cannot become value authority')
req(cfg['closed_bar_only'] is True and cfg['forward_fill_market_bars'] is False,'closed-only/no-forward-fill')
req(cfg['future_m5_directional_use']=='FORBIDDEN','future M5 forbidden')
req(cfg['enabled_for_research'] is False,'MTF data cannot silently activate pre-MTF research engine')
req(MTF_NATIVE_DIR.is_dir() and MTF_BUNDLES_DIR.is_dir(),'MTF data layout')
print('V201_MTF_DATA_CONFIG PASS')
