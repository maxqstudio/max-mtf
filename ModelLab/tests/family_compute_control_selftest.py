from __future__ import annotations
import json
from pathlib import Path
from research.research_architect import capability_catalog, compile_research_plan
from host.compute_backend import compact_compute_status

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'config/config.json').read_text(encoding='utf-8'))

def req(x,m):
    if not x: raise AssertionError(m)
    print('PASS ',m)

def fake_profile(cuda=True,vram=8.0):
    return {
        'profile_hash':'R2_GPU' if cuda else 'R2_CPU',
        'cpu':{'name':'test','physical_cores':8,'logical_threads':16},
        'memory':{'total_gib':32.0,'available_gib':24.0},
        'nvidia':{'detected':cuda,'devices':[{'name':'RTX 2060 SUPER','memory_total_gib':vram,'memory_free_gib':vram-1}] if cuda else []},
        'torch':{'installed':True,'cuda_available':cuda},
    }

def main():
    cfg=json.loads(json.dumps(BASE))
    ra=cfg.setdefault('research_architecture',{})
    ra['family_selection_mode']='AUTO'
    auto=capability_catalog(fake_profile(True),cfg)
    req(auto['selection']['mode']=='AUTO','AUTO family selection mode recorded')
    req({'lightgbm','xgboost','gru','lstm','tcn','transformer'}.issubset(set(auto['selection']['allowed_families'])),'AUTO exposes registered family universe')

    ra['family_selection_mode']='MANUAL'
    ra['allowed_families']=['tcn','lightgbm']
    manual=capability_catalog(fake_profile(True),cfg)
    req(set(manual['selection']['allowed_families'])=={'tcn','lightgbm'},'MANUAL checklist becomes allowed universe')
    req(manual['families']['tcn']['permitted'] and not manual['families']['gru']['permitted'],'MANUAL permissions are family-specific')
    strategy={'active_families':['gru','tcn','lightgbm'], 'hybrid_compositions':[{'temporal':'tcn','policy':'lightgbm'},{'temporal':'gru','policy':'lightgbm'}]}
    plan=compile_research_plan(strategy,fake_profile(True),cfg)
    active=set(plan['active_families'])
    req('tcn' in active and 'lightgbm' in active,'allowed manual families compile')
    req('gru' not in active,'disallowed manual family rejected')
    req('hybrid::tcn::lightgbm' in active,'Scientist may compose hybrid from manually allowed components')
    req('hybrid::gru::lightgbm' not in active,'hybrid cannot escape manual component universe')

    ra['allowed_families']=['transformer']
    plan2=compile_research_plan({},fake_profile(True),cfg)
    req(plan2['active_families']==['transformer'],'manual single-family selection is respected without forced baseline')

    ra['allowed_families']=[]
    try:
        compile_research_plan({},fake_profile(True),cfg)
    except RuntimeError as exc:
        req('MANUAL_FAMILY_SELECTION_EMPTY' in str(exc),'empty manual checklist fails closed')
    else:
        raise AssertionError('empty manual checklist must fail')

    fake_compute={
        'temporal_dl':{'backend':'CUDA'},'xgboost':{'backend':'CUDA'},'lightgbm':{'backend':'CPU'},
        'vulkan':{'state':'DETECTED_SCAN_ONLY'},'notes':[]
    }
    ra['allowed_families']=['tcn','lightgbm']
    rows=compact_compute_status(fake_compute,cfg)
    names={r['Family'] for r in rows}
    req({'gru','lstm','tcn','transformer','lightgbm','xgboost'}.issubset(names),'compute table is registry-driven for all families')
    row={r['Family']:r for r in rows}
    req(row['tcn']['Backend']=='CUDA' and row['transformer']['Backend']=='CUDA','all temporal DL families inherit resolved temporal backend')
    req(row['lightgbm']['Allowed']=='YES' and row['xgboost']['Allowed']=='NO','compute table reflects manual allowed universe')
    print('FAMILY_COMPUTE_CONTROL_SELFTEST PASS')

if __name__=='__main__':
    main()
