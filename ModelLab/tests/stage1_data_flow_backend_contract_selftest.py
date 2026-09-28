from __future__ import annotations
import json, tempfile
from copy import deepcopy
from pathlib import Path
import factory.champion_factory as cf
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))
def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)
def main():
    src=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    ml=(ROOT/'models/model_lab.py').read_text(encoding='utf-8')
    fw=(ROOT/'factory/factory_worker.py').read_text(encoding='utf-8')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    req('_assert_data_quality_authority(master,cfg)' in src,'Discovery boundary requires exact Data Quality authority')
    req('read_csv_auto(path)' in ml and 'np.isfinite(vals).all()' in ml,'CP32 loader is delimiter-consistent and rejects non-finite features')
    req('elif action=="DISCOVERY"' in fw and '_prepare_auto_data_quality' in fw[fw.index('elif action=="DISCOVERY"'):fw.index('elif action=="CPCV"')],'Direct Discovery worker performs DQ preflight')
    req('with writer_lock(p)' in app and 'os.replace(tmp, p)' in app,'Uploaded training CSV replacement is locked and atomic')
    # v0.8.7: purge/embargo are automatically lifted to the Strategy Optimizer MaxHold horizon.
    geom=pd.DataFrame({'sl_atr':np.full(8,2.6),'tp_atr':np.full(8,4.2),'max_hold_bars':np.full(8,54)})
    bad=deepcopy(CFG); bad['split']['purge_bars']=24; bad['split']['embargo_bars']=24
    synced,_=synchronize_cfg_with_dataset_geometry(bad,geom,require_runtime_authority_match=False)
    t=cf._assert_temporal_leakage_guard(synced,require_embargo=True)
    req(t['label_horizon_bars']==54 and t['purge_bars']>=54 and t['embargo_bars']>=54,'purge/embargo auto-follow Strategy Optimizer MaxHold horizon')
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'master.csv'; p.write_text('x\n1\n',encoding='utf-8')
        cfg=deepcopy(CFG); h=cf._sha(p); cfg.setdefault('agent',{})['data_quality_source_sha256']=h; cfg['agent']['data_quality_context']={'quality_status':'VALID','continuity':{'broker_verified':True,'source_backed_missing':0,'dataset_only':0}}
        req(cf._assert_data_quality_authority(p,cfg)['source_sha256']==h,'DQ authority is bound to exact source hash')
        p.write_text('x\n2\n',encoding='utf-8')
        try: cf._assert_data_quality_authority(p,cfg); raise AssertionError('stale DQ hash accepted')
        except RuntimeError as e: req('DQ_SOURCE_SHA_DRIFT' in str(e),'Source mutation after DQ is rejected')
    print('STAGE1_DATA_FLOW_BACKEND_CONTRACT PASS')
if __name__=='__main__': main()
