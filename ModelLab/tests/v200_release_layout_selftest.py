from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]; PKG=ROOT.parent; sys.path.insert(0,str(ROOT))
from core.project_paths import *
from core.release_authority import load_active_release

def req(x,msg):
    if not x: raise AssertionError(msg)
for p in (EA_BASELINE_DIR,EA_CHALLENGERS_DIR,EA_ARCHIVE_DIR,MODEL_BASELINE_DIR,MODEL_CHALLENGERS_DIR,MODEL_ARCHIVE_DIR,RELEASE_ACTIVE_DIR,RELEASE_CHALLENGERS_DIR,RELEASE_ARCHIVE_DIR):
    req(p.is_dir(),'missing lifecycle dir '+str(p))
a=load_active_release(); req(a['release_id']=='BASELINE-MTF-V2' and a['model'] is None,'baseline release no model')
req(a['strategy_champion_id'] is None and a['model_champion_id'] is None,'release bootstrap zero Champions')
foundation=(ROOT/'docs/mtf/MAX_MTF_V2_FOUNDATION.md').read_text(encoding='utf-8')
for token in ('archive','rollback','verified MT5 terminal','Baseline is **not** a Champion'):
    req(token.lower() in foundation.lower(),'foundation docs missing '+token)
print('V200_RELEASE_LAYOUT PASS')
