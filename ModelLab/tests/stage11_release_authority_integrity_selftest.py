from __future__ import annotations
import json
from pathlib import Path
import tempfile
import core.checkpoint_integrity as ci
ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def main():
    pm=load(PKG/'governance/PACKAGE_MANIFEST.json')
    ca=load(PKG/'governance/CURRENT_AUTHORITY.json')
    r5=load(PKG/'governance/checkpoints/CHECKPOINT_PRE_STAGE11_STATUS.json')
    run=(ROOT/'acceptance/runners/run_acceptance.py').read_text(encoding='utf-8')
    sk=(ROOT/'scientist/knowledge/scientist_knowledge.py').read_text(encoding='utf-8')
    rel=(ROOT/'tests'/'release_sync_selftest.py').read_text(encoding='utf-8')
    pm_txt=(PKG/'governance/PACKAGE_MANIFEST.json').read_text(encoding='utf-8')

    req(r5.get('checkpoint')=='R5' and r5.get('authority')=='STAGE_1_10_CLOSED_PRE_STAGE11','R5 baseline remains immutable historical authority')
    req((r5.get('cumulative_acceptance') or {}).get('passed')==96 and (r5.get('cumulative_acceptance') or {}).get('total')==96,'R5 historical acceptance remains 96/96')
    req('93_OF_93' not in pm_txt and 'STAGE8_E2E_WORKFLOW_AUDIT' not in pm_txt,'package manifest has no stale Stage1-7/Stage8 authority')
    req(pm.get('scientific_authority')=='v1.4.5','package current scientific authority advanced to v1.4.5 while historical checkpoints remain immutable')
    req((pm.get('backend_e2e_audit') or {}).get('stage_1_10_status')=='CLOSED_EXACT_TREE','package manifest preserves Stage1-10 R5 closure')
    req((pm.get('backend_e2e_audit') or {}).get('stage_11_status') in {'AUDIT_ACTIVE','CLOSED_EXACT_TREE'},'package manifest declares Stage11 release-authority state')
    req(ca.get('backend_stage_1_10_status')=='CLOSED_EXACT_TREE','current authority preserves Stage1-10 closure')
    req(ca.get('backend_stage_11_status') in {'AUDIT_ACTIVE','CLOSED_EXACT_TREE'},'current authority declares Stage11 state')
    local=ca.get('local_cumulative_acceptance') or {}
    pm_acc=pm.get('local_acceptance') or {}
    req(int(local.get('passed',-1))==136 and int(local.get('total',-1))==136 and local.get('first_failed_gate') is None,'current authority local cumulative target matches v1.4.5 136/136 source/contract closure')
    req(int(pm_acc.get('passed',-1))==int(local.get('passed',-2)) and int(pm_acc.get('total',-1))==int(local.get('total',-2)),'package/current cumulative acceptance counts agree')
    req("('STAGE11_RELEASE_AUTHORITY_INTEGRITY','tests/stage11_release_authority_integrity_selftest.py')" in run,'Stage11 gate registered in cumulative acceptance')
    req("BACKEND_E2E_AUDIT_R1_STAGE1_11" in run and "MAX_BUILD_ACCEPTANCE_V23_BACKEND_E2E_R1" in run,'acceptance revision/schema advanced for Stage11')
    req('governance/PACKAGE_MANIFEST.json' in run,'package manifest participates in acceptance tree signature')
    req('governance/PACKAGE_MANIFEST.json' in sk and 'README_FIRST.md' in sk,'Scientist Knowledge watches release authority docs')
    req('governance/PACKAGE_MANIFEST.json' in rel and 'governance/CURRENT_AUTHORITY.json' in rel and 'governance/checkpoints/CHECKPOINT_PRE_STAGE11_STATUS.json' in rel,'RELEASE_SYNC validates cross-authority release metadata')
    req((PKG/'governance'/'PACKAGE_LAYOUT.json').exists() and (PKG/'governance'/'PACKAGE_LAYOUT.md').exists(),'organized package layout authority exists')
    req(not list(PKG.glob('*.json')) and not list(PKG.glob('*.ps1')) and [p.name for p in PKG.glob('*.md')]==['README_FIRST.md'],'package root contains only README_FIRST.md as loose file')
    req(not list(ROOT.glob('*selftest.py')) and not list(ROOT.glob('*.md')),'ModelLab keeps tests/docs in dedicated folders')
    req(set(p.name for p in ROOT.glob('*.json')) <= {'config.json','cpu_calibration.json','model_registry.json','promotion_evidence_template.json','SCIENTIST_KNOWLEDGE_BASE.json'},'ModelLab loose JSON is limited to runtime/config knowledge state')
    req((ROOT/'evidence'/'current').is_dir() and (ROOT/'evidence'/'history').is_dir() and (ROOT/'evidence'/'ui').is_dir() and (ROOT/'evidence'/'research').is_dir(),'ModelLab evidence is grouped by purpose')
    req((ROOT/'tests').is_dir() and (ROOT/'docs').is_dir(),'ModelLab tests/docs folders exist')
    statuses={str(x.get('status')) for x in (pm.get('external_gates') or []) if isinstance(x,dict)}
    req(not any(s=='PASS' for s in statuses),'package manifest does not promote external NOT_RUN gates to PASS')

    # Prove the sealing primitive itself detects post-manifest tampering.
    with tempfile.TemporaryDirectory() as td:
        d=Path(td); (d/'a.txt').write_text('A',encoding='utf-8'); (d/'sub').mkdir(); (d/'sub'/'b.txt').write_text('B',encoding='utf-8')
        ci.generate(d)
        req(ci.verify(d).get('status')=='PASS','checkpoint integrity manifest verifies unchanged tree')
        (d/'a.txt').write_text('TAMPER',encoding='utf-8')
        vr=ci.verify(d)
        req(vr.get('status')=='FAIL' and any(x.get('kind')=='HASH_MISMATCH' for x in vr.get('mismatches',[])),'checkpoint integrity detects post-manifest tamper')
        (d/'new.txt').write_text('NEW',encoding='utf-8')
        vr=ci.verify(d)
        req(any(x.get('kind')=='UNMANIFESTED_FILE' for x in vr.get('mismatches',[])),'checkpoint integrity detects files added after seal')
    print('STAGE11_RELEASE_AUTHORITY_INTEGRITY PASS')

if __name__=='__main__': main()
