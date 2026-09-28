from __future__ import annotations
import json,re
from pathlib import Path
import acceptance.runners.run_acceptance as run_acceptance
ROOT=Path(__file__).resolve().parents[1];PKG=ROOT.parent

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

readme=(PKG/'README_FIRST.md').read_text(encoding='utf-8')
manifest=json.loads((PKG/'governance/PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
current=json.loads((PKG/'governance/CURRENT_AUTHORITY.json').read_text(encoding='utf-8'))
handoff=(PKG/'governance/PROJECT_HANDOFF_CURRENT.md').read_text(encoding='utf-8')
room=(PKG/'governance/handoffs/MAX_MTF_V2_HANDOFF.md').read_text(encoding='utf-8')
layout=(PKG/'governance/PACKAGE_LAYOUT.md').read_text(encoding='utf-8')
ext=json.loads((PKG/'governance/EXTERNAL_RUNTIME_GATES.json').read_text(encoding='utf-8'))
run_src=(ROOT/'acceptance/runners/run_acceptance.py').read_text(encoding='utf-8')
closure_src=(ROOT/'mtf/mtf1_closure_run.py').read_text(encoding='utf-8')
owner_src=(ROOT/'acceptance/runners/owner_mtf1_runtime_acceptance.py').read_text(encoding='utf-8')
meta_src=(ROOT/'acceptance/runners/owner_mtf1_metaeditor_acceptance.py').read_text(encoding='utf-8')
final_src=(ROOT/'mtf/mtf1_final_closure.py').read_text(encoding='utf-8')
expected=len(run_acceptance.TESTS); target=f'{expected}/{expected} PASS'; status_prefix=f'MTF1_EXTERNAL_EXECUTION_PROOF_{expected}_OF_{expected}'
req('Max MTF v2.0.1' in readme and 'MTF-1 External Execution Proof' in readme,'README identifies canonical v2.0.1 current phase without revision label')
req(target in readme,f'README identifies current {target} local target')
req(current.get('current_phase')=='MTF_1_EXTERNAL_EXECUTION_PROOF','CURRENT_AUTHORITY uses neutral current phase')
req((current.get('local_acceptance') or {}).get('target')==target,'CURRENT_AUTHORITY acceptance target synchronized')
req(str(manifest.get('status') or '').startswith(status_prefix),'PACKAGE_MANIFEST neutral status synchronized')
req(int((manifest.get('local_acceptance') or {}).get('gates',0))==expected,'PACKAGE_MANIFEST local gate count synchronized')
req(f'exact ordered **{expected} `(gate, script)` pairs**' in readme,'README ordered gate-count text synchronized to canonical suite')
req(f'exact ordered {expected} gate/script rows' in handoff and f'exact ordered {expected} gate/script results' in room,'current handoffs ordered gate-count text synchronized to canonical suite')
req(re.search(r'GATES\s*:\s*'+str(expected)+r'\s*/\s*'+str(expected),readme) is not None,'README machine-report example uses canonical gate count')
req(f'EXACT_ORDERED_{expected}_RESULTS' in str(current.get('local_acceptance_integrity') or ''),'CURRENT_AUTHORITY exact ordered result count synchronized')
req(f'EXACT_ORDERED_{expected}_GATE_SCRIPT' in str(manifest.get('local_acceptance_proof') or ''),'PACKAGE_MANIFEST exact ordered result count synchronized')
req(ext.get('phase')=='MTF_1_EXTERNAL_EXECUTION_PROOF','external-gate registry uses neutral active phase')
req('MTF-1 External Execution Proof' in handoff and target in handoff,'current project handoff synchronized')
req('MTF-1 External Execution Proof' in room and target in room,'room handoff synchronized')
for name,text in [('README',readme),('CURRENT_AUTHORITY',json.dumps(current)),('PACKAGE_MANIFEST',json.dumps(manifest)),('PROJECT_HANDOFF_CURRENT',handoff),('MAX_MTF_V2_HANDOFF',room),('PACKAGE_LAYOUT',layout),('EXTERNAL_RUNTIME_GATES',json.dumps(ext)),('run_acceptance',run_src),('closure_run',closure_src),('owner_runtime',owner_src),('metaeditor',meta_src),('final_closure',final_src)]:
    req(re.search(r'(?<![A-Za-z0-9])(?:MTF[-_ ]?1[-_ ]?)?R[1-9][0-9]*(?![A-Za-z0-9])|Repair[0-9]+',text,re.I) is None,f'{name} has no active revision/repair label identity')
req("MAX_MTF_BUILD_ACCEPTANCE_V8_MTF1_EXTERNAL_EXECUTION_PROOF" in run_src and "MTF_1_EXTERNAL_EXECUTION_PROOF" in run_src,'active build acceptance schema/phase are neutral')
req("MAX_MTF1_CLOSURE_RUN_V1" in closure_src and "MTF_1_EXTERNAL_EXECUTION_PROOF" in closure_src,'closure-run schema/phase are neutral')
req("MAX_MTF1_OWNER_RUNTIME_ACCEPTANCE_V5_BROKER_SYMBOL_RESOLUTION" in owner_src and "MTF_1_OWNER_RUNTIME_EXECUTION_PROOF" in owner_src,'Owner runtime acceptance schema/phase are neutral')
req("MAX_MTF1_METAEDITOR_ACCEPTANCE_V2_EXECUTION_PROOF" in meta_src and "MTF_1_METAEDITOR_EXECUTION_PROOF" in meta_src,'MetaEditor acceptance schema/phase are neutral')
req("MAX_MTF1_FINAL_CLOSURE_V2_EXECUTION_PROOF" in final_src and "MTF_1_FINAL_CLOSURE" in final_src,'final closure schema/phase are neutral')
req((PKG/'ModelLab/docs/mtf/MTF1_R6_EXTERNAL_EXECUTION_PROOF.md').is_file(),'historical revision contract remains available for traceability')
print('V201_README_AUTHORITY_SYNC PASS')
