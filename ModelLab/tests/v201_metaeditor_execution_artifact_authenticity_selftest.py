from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import acceptance.runners.owner_mtf1_metaeditor_acceptance as meta
from mtf1_closure_test_utils import build_valid_metaeditor_fixture, write_valid_local_acceptance

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
REG = PKG / 'governance/EXTERNAL_RUNTIME_GATES.json'
BASE = PKG / 'owner_acceptance/evidence/mtf1'
BASE.mkdir(parents=True, exist_ok=True)


def req(x, msg):
    if not x:
        raise AssertionError(msg)
    print('PASS ', msg)


def rejected(payload, acc, cfg):
    try:
        meta.verify_metaeditor_evidence_payload(payload, acceptance_path=acc, registry_path=REG, config_path=cfg, allow_test_fixture=True, require_closure_run_id=False)
    except meta.MetaEditorAcceptanceError:
        return True
    return False

with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory(dir=BASE) as ed:
    td = Path(td); ed = Path(ed)
    acc = td / 'acceptance.json'; cfg = td / 'meta_cfg.json'
    write_valid_local_acceptance(acc)
    payload = build_valid_metaeditor_fixture(meta, acceptance_path=acc, config_path=cfg, registry_path=REG, sandbox=td / 'sandbox', artifact_dir=ed / 'valid')
    meta.verify_metaeditor_evidence_payload(payload, acceptance_path=acc, registry_path=REG, config_path=cfg, allow_test_fixture=True, require_closure_run_id=False)
    req(True, 'valid archived MetaEditor execution proof accepted')

    # Internally consistent arbitrary text renamed .ex5 must fail binary execution-artifact checks.
    fake = build_valid_metaeditor_fixture(meta, acceptance_path=acc, config_path=cfg, registry_path=REG, sandbox=td / 'sandbox2', artifact_dir=ed / 'fake_ex5')
    ex5 = meta._artifact_from_project_relative(fake['compile']['archived_ex5'])
    ex5.write_bytes((b'FAKE-EX5-BYTES-NOT-COMPILED\n' * 100))
    fake['compile']['ex5_sha256'] = meta.sha256_file(ex5)
    fake['compile']['ex5_size_bytes'] = ex5.stat().st_size
    fake['gates'][0]['ex5_sha256'] = meta.sha256_file(ex5)
    proc = meta._artifact_from_project_relative(fake['compile']['archived_process_record'])
    pobj = json.loads(proc.read_text()); pobj['archived_ex5_sha256'] = meta.sha256_file(ex5)
    proc.write_text(json.dumps(pobj, indent=2) + '\n')
    fake['compile']['process_record_sha256'] = meta.sha256_file(proc)
    req(rejected(fake, acc, cfg), 'arbitrary text bytes renamed .ex5 rejected even with synchronized hashes')

    # Claimed tool identity cannot replace the actual configured MetaEditor file/hash.
    bad_tool = copy.deepcopy(payload)
    bad_tool['compile']['metaeditor_exe_sha256'] = 'a' * 64
    req(rejected(bad_tool, acc, cfg), 'fabricated MetaEditor SHA rejected against actual configured executable')

print('V201_METAEDITOR_EXECUTION_ARTIFACT_AUTHENTICITY PASS')
