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
    payload = build_valid_metaeditor_fixture(meta, acceptance_path=acc, config_path=cfg, registry_path=REG, sandbox=td / 'sandbox', artifact_dir=ed / 'art')

    # Keep caller summary at 0 errors but replace the archived compiler log with a real parsed error.
    log = meta._artifact_from_project_relative(payload['compile']['archived_log'])
    log.write_text('Max_MTF.mq5 : error\nResult: 1 errors, 0 warnings\n', encoding='utf-8')
    payload['compile']['compile_log_sha256'] = meta.sha256_file(log)
    proc = meta._artifact_from_project_relative(payload['compile']['archived_process_record'])
    pobj = json.loads(proc.read_text()); pobj['archived_log_sha256'] = meta.sha256_file(log)
    proc.write_text(json.dumps(pobj, indent=2) + '\n')
    payload['compile']['process_record_sha256'] = meta.sha256_file(proc)
    req(rejected(payload, acc, cfg), 'fabricated zero-error summary cannot override archived compiler log with errors')

with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory(dir=BASE) as ed:
    td = Path(td); ed = Path(ed)
    acc = td / 'acceptance.json'; cfg = td / 'meta_cfg.json'
    write_valid_local_acceptance(acc)
    payload = build_valid_metaeditor_fixture(meta, acceptance_path=acc, config_path=cfg, registry_path=REG, sandbox=td / 'sandbox', artifact_dir=ed / 'art')
    payload['compile']['compile_summary'] = {'found': True, 'errors': 0, 'warnings': 99, 'line': 'FABRICATED'}
    req(rejected(payload, acc, cfg), 'caller compile_summary must exactly equal verifier reparse of archived log')

print('V201_METAEDITOR_LOG_REPARSE_AUTHORITY PASS')
