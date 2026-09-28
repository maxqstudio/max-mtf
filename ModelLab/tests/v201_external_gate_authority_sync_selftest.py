from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

registry=json.loads((PKG/'governance/EXTERNAL_RUNTIME_GATES.json').read_text(encoding='utf-8'))
manifest=json.loads((PKG/'governance/PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
current=json.loads((PKG/'governance/CURRENT_AUTHORITY.json').read_text(encoding='utf-8'))
req(registry.get('schema')=='MAX_EXTERNAL_RUNTIME_GATES_V1','canonical external registry schema')
req(registry.get('authority')=='SINGLE_CANONICAL_EXTERNAL_RUNTIME_GATE_REGISTRY','single external authority declaration')
ids=[str(x.get('gate')) for x in registry.get('gates') or []]
req(len(ids)==len(set(ids)) and len(ids)>0,'external gate ids unique/nonempty')
for gate in ('OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY','OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION','METAEDITOR_MAX_MTF_V2_COMPILE','MTF_STRATEGY_RUNTIME'):
    req(gate in ids,'MTF external gate registered: '+gate)
req(manifest.get('external_gates_registry')=='governance/EXTERNAL_RUNTIME_GATES.json','package manifest points to canonical registry')
req(manifest.get('external_gates')==registry.get('gates'),'package manifest consumes exact canonical gate rows')
req(current.get('external_gates_registry')=='governance/EXTERNAL_RUNTIME_GATES.json','CURRENT_AUTHORITY points to canonical registry')
runacc=(ROOT/'acceptance/runners/run_acceptance.py').read_text(encoding='utf-8')
req("GOV/'EXTERNAL_RUNTIME_GATES.json'" in runacc and "'external_gates':_external_gates()" in runacc,'build acceptance reads canonical registry')
req("return [" not in runacc[runacc.index('def _external_gates'):runacc.index('def write')],'build acceptance external gate function is not hardcoded list')
req((ROOT/'RUN_MTF1_OWNER_ACCEPTANCE.cmd').is_file(),'one-click Owner MTF-1 runner present')
req((ROOT/'acceptance/runners/owner_mtf1_runtime_acceptance.py').is_file(),'machine-verifiable Owner MTF-1 runtime acceptance present')
runner=(ROOT/'acceptance/runners/owner_mtf1_runtime_acceptance.py').read_text(encoding='utf-8')
for token in ('collect_native_frames_from_mt5','validate_mt5_data_root','build_canonical_views','build_alignment_index','audit_canonical_bundle','OWNER_MTF1_RUNTIME_ACCEPTANCE.json'):
    req(token in runner,'Owner acceptance runtime contract wired: '+token)
req(not any(str(x.get('status') or '').upper()=='PASS' for x in registry.get('gates') or []),'source registry cannot pre-promote external gate PASS')
print('V201_EXTERNAL_GATE_AUTHORITY_SYNC PASS')
