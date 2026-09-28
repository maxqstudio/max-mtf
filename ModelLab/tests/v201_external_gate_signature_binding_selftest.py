from __future__ import annotations
import json
from pathlib import Path
import acceptance.runners.run_acceptance as run_acceptance
ROOT=Path(__file__).resolve().parents[1]
REG=ROOT.parent/'governance/EXTERNAL_RUNTIME_GATES.json'

def req(x,msg):
    if not x: raise AssertionError(msg)
    print('PASS ',msg)

before=REG.read_bytes()
sig_before=run_acceptance._tree_sig()
try:
    payload=json.loads(before.decode('utf-8'))
    payload['rule']=str(payload.get('rule') or '')+' [ADVERSARIAL_SIGNATURE_PROBE]'
    REG.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    sig_after=run_acceptance._tree_sig()
    req(sig_after!=sig_before,'external runtime registry mutation changes source-tree signature')
finally:
    REG.write_bytes(before)
req(run_acceptance._tree_sig()==sig_before,'external registry restored byte-exact after signature probe')
print('V201_EXTERNAL_GATE_SIGNATURE_BINDING PASS')
