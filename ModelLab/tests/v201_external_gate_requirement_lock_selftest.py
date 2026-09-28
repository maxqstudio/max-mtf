from __future__ import annotations
import json
from pathlib import Path
import acceptance.runners.run_acceptance as run_acceptance
ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT.parent
REG=PKG/'governance/EXTERNAL_RUNTIME_GATES.json'
MAN=PKG/'governance/PACKAGE_MANIFEST.json'


def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)


def must_reject():
    try:
        run_acceptance._external_gates()
    except RuntimeError:
        return True
    return False

reg_before=REG.read_bytes(); man_before=MAN.read_bytes()
try:
    base=json.loads(reg_before.decode('utf-8'))
    rows={str(r.get('gate')):r for r in base.get('gates') or []}
    req(run_acceptance.MTF1_EXTERNAL_REQUIREMENT_LOCK=={
        'OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY':'REQUIRED_ON_OWNER_MACHINE',
        'OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION':'REQUIRED_ON_OWNER_MACHINE',
        'METAEDITOR_MAX_MTF_V2_COMPILE':'REQUIRED_ON_OWNER_MACHINE',
        'MTF_STRATEGY_RUNTIME':'NOT_APPLICABLE_MTF1',
    },'MTF-1 external requirement lock exact')
    for gate,expected in run_acceptance.MTF1_EXTERNAL_REQUIREMENT_LOCK.items():
        req(str(rows[gate].get('requirement'))==expected,'registry requirement locked: '+gate)
        req(str(rows[gate].get('status'))==expected,'compatibility status mirrors locked requirement: '+gate)

    # Adversarial downgrade of the new requirement field, with Package Manifest synced,
    # must still fail because the phase invariant is compiled into acceptance validation.
    for gate in ('OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY','OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION','METAEDITOR_MAX_MTF_V2_COMPILE'):
        bad=json.loads(reg_before.decode('utf-8'))
        for row in bad['gates']:
            if row.get('gate')==gate:
                row['requirement']='NOT_APPLICABLE_MTF1'; row['status']='NOT_APPLICABLE_MTF1'
        REG.write_text(json.dumps(bad,indent=2)+'\n',encoding='utf-8')
        man=json.loads(man_before.decode('utf-8'));man['external_gates']=bad['gates']
        MAN.write_text(json.dumps(man,indent=2)+'\n',encoding='utf-8')
        req(must_reject(),'downgraded required gate rejected even when manifest mirror is synced: '+gate)
        REG.write_bytes(reg_before);MAN.write_bytes(man_before)

    # Changing only legacy status cannot bypass the new requirement lock either.
    bad=json.loads(reg_before.decode('utf-8'))
    for row in bad['gates']:
        if row.get('gate')=='OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY':
            row['status']='NOT_APPLICABLE_MTF1'
    REG.write_text(json.dumps(bad,indent=2)+'\n',encoding='utf-8')
    req(must_reject(),'status-only downgrade cannot bypass requirement lock')
finally:
    REG.write_bytes(reg_before);MAN.write_bytes(man_before)

req(run_acceptance._external_gates() is not None,'canonical external registry restored and valid')
print('V201_EXTERNAL_GATE_REQUIREMENT_LOCK PASS')
