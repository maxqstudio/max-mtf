from __future__ import annotations
import json, tempfile
from pathlib import Path
import numpy as np, pandas as pd
import strategy.strategy_geometry as sg
ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def frame(sl=3.2,tp=4.8,hold=54,n=12):
    x=np.arange(n,dtype=float)
    return pd.DataFrame({'sl_atr':np.full(n,sl),'tp_atr':np.full(n,tp),'max_hold_bars':np.full(n,hold)})

def authority_payload(sl=3.2,tp=4.8,hold=54):
    return {
        'geometry':{'sl_atr':sl,'tp_atr':tp,'max_hold_bars':hold},
        'execution_policy':{
            'entry_threshold':0.18,
            'exit_reverse_threshold':0.25,
            'min_consensus':0.70,
            'shock_halt_range_atr':3.5,
            'max_spread_points':45.0,
            'onnx_blend':0.65,
        },
    }

def main():
    cfg={'label':{},'split':{}}
    original=sg.RUNTIME_AUTHORITY
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'authority.json'; sg.RUNTIME_AUTHORITY=p
        try:
            for payload, expected in ((None,'STRATEGY_AUTHORITY_MISSING'),('{bad json','STRATEGY_AUTHORITY_UNREADABLE'),(json.dumps({'geometry':{'sl_atr':'x'}}),'STRATEGY_AUTHORITY_INVALID_GEOMETRY')):
                if payload is None: p.unlink(missing_ok=True)
                else: p.write_text(payload,encoding='utf-8')
                try: sg.synchronize_cfg_with_dataset_geometry(cfg,frame())
                except ValueError as e: req(expected in str(e),f'fail closed: {expected}')
                else: raise AssertionError(f'{expected} silently accepted')
            p.write_text(json.dumps(authority_payload(sl=2.6)),encoding='utf-8')
            try: sg.synchronize_cfg_with_dataset_geometry(cfg,frame())
            except ValueError as e: req('STRATEGY_AUTHORITY_DATASET_MISMATCH' in str(e),'mismatched authority fails closed')
            else: raise AssertionError('mismatched authority silently accepted')
            p.write_text(json.dumps(authority_payload()),encoding='utf-8')
            out,_=sg.synchronize_cfg_with_dataset_geometry(cfg,frame())
            req((out.get('strategy_geometry') or {}).get('authority',{}).get('geometry',{}).get('sl_atr')==3.2,'matching authority accepted')
        finally: sg.RUNTIME_AUTHORITY=original

    opt=(ROOT/'strategy/strategy_optimizer_jobs.py').read_text(encoding='utf-8')
    app=(ROOT/'ui/app.py').read_text(encoding='utf-8')
    cf=(ROOT/'factory/champion_factory.py').read_text(encoding='utf-8')
    orch=(ROOT/'factory/factory_orchestrator.py').read_text(encoding='utf-8')
    acc=(ROOT/'acceptance/runners/run_acceptance.py').read_text(encoding='utf-8')
    req('"STOPPED"' in opt and 'st["status"]="STOPPED"' in opt and 'st["status"]="CANCELLED"' not in opt,'Strategy Optimizer canonical stop state is STOPPED')
    req('NO_CHAMPION_MAX_ROUNDS","FAILED","STOPPED"' in app,'Optimizer UI recognizes STOPPED terminal state')
    req('status="FACTORY_WINNER"' in cf and 'status="FACTORY_WINNER_RUNTIME_BLOCKED"' in cf,'new Model Factory writes unambiguous winner lifecycle statuses')
    req("state.update({'status':'FACTORY_WINNER'" in orch and "'status':'FACTORY_WINNER_RUNTIME_BLOCKED'" in orch,'orchestrator canonicalizes winner lifecycle status')
    req('"runtime/strategy_authority.json"' in acc,'Strategy runtime authority participates in source-tree acceptance signature')

    ca=json.loads((PKG/'governance/CURRENT_AUTHORITY.json').read_text(encoding='utf-8'))
    pm=json.loads((PKG/'governance/PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    hand=(PKG/'governance/PROJECT_HANDOFF_CURRENT.md').read_text(encoding='utf-8')
    idx=(PKG/'governance/CONTRACT_AUDIT_INDEX.md').read_text(encoding='utf-8')
    req(ca.get('scientific_authority')=='v1.4.5' and pm.get('scientific_authority')=='v1.4.5','v1.2.6 repairs remain preserved under current v1.4.5 authority')
    req('v1.4.5' in hand and 'v1.2.6' in hand and 'v0.11.2**' not in hand,'PROJECT_HANDOFF_CURRENT points to v1.4.5 and names frozen v1.2.6 control')
    req('Current authority: **v1.4.5**' in idx and 'v1.2.6 authority/lifecycle repair' in idx,'CONTRACT_AUDIT_INDEX current authority advanced without deleting v1.2.6 repair lineage')
    print('V126_AUTHORITY_LIFECYCLE_GOVERNANCE_REPAIR_PASS')
if __name__=='__main__': main()
