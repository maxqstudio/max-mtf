from __future__ import annotations

import tempfile
from pathlib import Path

import acceptance.runners.owner_mtf1_runtime_acceptance as owner
import acceptance.runners.owner_mtf1_metaeditor_acceptance as meta
from mtf1_closure_test_utils import build_valid_metaeditor_fixture, valid_owner_runtime_payload, write_valid_local_acceptance

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
REG = PKG / 'governance/EXTERNAL_RUNTIME_GATES.json'
BASE = PKG / 'owner_acceptance/evidence/mtf1'
BASE.mkdir(parents=True, exist_ok=True)
RUN_A = 'a' * 32
RUN_B = 'b' * 32


def req(x, msg):
    if not x:
        raise AssertionError(msg)
    print('PASS ', msg)

with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory(dir=BASE) as ed:
    td = Path(td); ed = Path(ed)
    cfg = td / 'owner_cfg.json'; cfg.write_bytes((PKG / 'owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json').read_bytes())
    acc_a = td / 'a.json'; acc_b = td / 'b.json'
    write_valid_local_acceptance(acc_a, closure_run_id=RUN_A)
    write_valid_local_acceptance(acc_b, closure_run_id=RUN_B)
    payload = valid_owner_runtime_payload(owner, acceptance_path=acc_a, config_path=cfg, registry_path=REG, artifact_dir=ed / 'owner')
    owner.verify_owner_evidence_payload(payload, acceptance_path=acc_a, config_path=cfg, registry_path=REG, require_live_mt5=False, require_closure_run_id=False)
    try:
        owner.verify_owner_evidence_payload(payload, acceptance_path=acc_b, config_path=cfg, registry_path=REG, require_live_mt5=False, require_closure_run_id=False)
        accepted = True
    except owner.OwnerMTF1AcceptanceError:
        accepted = False
    req(not accepted, 'Owner runtime evidence from closure run A cannot be combined with local acceptance run B')

with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory(dir=BASE) as ed:
    td = Path(td); ed = Path(ed)
    acc_a = td / 'a.json'; acc_b = td / 'b.json'; cfg = td / 'meta_cfg.json'
    write_valid_local_acceptance(acc_a, closure_run_id=RUN_A)
    write_valid_local_acceptance(acc_b, closure_run_id=RUN_B)
    payload = build_valid_metaeditor_fixture(meta, acceptance_path=acc_a, config_path=cfg, registry_path=REG, sandbox=td / 'sandbox', artifact_dir=ed / 'meta')
    meta.verify_metaeditor_evidence_payload(payload, acceptance_path=acc_a, registry_path=REG, config_path=cfg, allow_test_fixture=True, require_closure_run_id=False)
    try:
        meta.verify_metaeditor_evidence_payload(payload, acceptance_path=acc_b, registry_path=REG, config_path=cfg, allow_test_fixture=True, require_closure_run_id=False)
        accepted = True
    except meta.MetaEditorAcceptanceError:
        accepted = False
    req(not accepted, 'MetaEditor evidence from closure run A cannot be combined with local acceptance run B')

final_source = (ROOT / 'mtf/mtf1_final_closure.py').read_text(encoding='utf-8')
req("require_closure_run_id=True" in final_source and "closure_run_id" in final_source, 'final closure explicitly requires shared run ID binding')

print('V201_CLOSURE_RUN_ID_BINDING PASS')
