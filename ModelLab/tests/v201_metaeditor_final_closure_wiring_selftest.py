from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import mtf.mtf1_closure_authority as auth
import mtf.mtf1_final_closure as final
import mtf.mtf1_python_env_authority as pyenv
import acceptance.runners.owner_mtf1_metaeditor_acceptance as meta
import acceptance.runners.owner_mtf1_runtime_acceptance as owner
import acceptance.runners.run_acceptance as run_acceptance
from mtf1_closure_test_utils import (
    TEST_RUN_ID,
    build_valid_metaeditor_fixture,
    valid_owner_runtime_payload,
    write_valid_local_acceptance,
)

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
REG = PKG / 'governance/EXTERNAL_RUNTIME_GATES.json'
BASE_EVIDENCE = PKG / 'owner_acceptance/evidence/mtf1'
BASE_EVIDENCE.mkdir(parents=True, exist_ok=True)


def req(x, msg):
    if not x:
        raise AssertionError(msg)
    print('PASS ', msg)


for path in (
    ROOT / 'RUN_MTF1_METAEDITOR_ACCEPTANCE.cmd',
    ROOT / 'acceptance/verification/VERIFY_MTF1_METAEDITOR_ACCEPTANCE.cmd',
    ROOT / 'acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd',
    ROOT / 'RUN_MTF1_FINAL_CLOSURE.cmd',
):
    req(path.is_file(), path.relative_to(ROOT).as_posix() + ' one-click wiring present')
reg = json.loads(REG.read_text())
meta_row = next(x for x in reg['gates'] if x['gate'] == 'METAEDITOR_MAX_MTF_V2_COMPILE')
req(meta_row.get('runner') == 'ModelLab/RUN_MTF1_METAEDITOR_ACCEPTANCE.cmd', 'canonical registry wires MetaEditor runner')
req(meta_row.get('verifier') == 'ModelLab/acceptance/verification/VERIFY_MTF1_METAEDITOR_ACCEPTANCE.cmd', 'canonical registry wires MetaEditor verifier')

fake_run = {'closure_run_id': TEST_RUN_ID}
orig_ra = run_acceptance.read_closure_run
orig_auth = auth.read_closure_run
run_acceptance.read_closure_run = lambda required=True: fake_run
auth.read_closure_run = lambda required=True: fake_run
try:
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory(dir=BASE_EVIDENCE) as ed:
        td = Path(td); ed = Path(ed)
        acc = td / 'acceptance.json'; owner_cfg = td / 'owner_cfg.json'; meta_cfg = td / 'meta_cfg.json'
        owner_ev = td / 'owner.json'; meta_ev = td / 'meta.json'; pyenv_ev = td / 'python_env.json'
        owner_cfg.write_bytes((PKG / 'owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json').read_bytes())
        write_valid_local_acceptance(acc, closure_run_id=TEST_RUN_ID)

        owner_payload = valid_owner_runtime_payload(owner, acceptance_path=acc, config_path=owner_cfg, registry_path=REG, artifact_dir=ed / 'owner_artifacts')
        owner_ev.write_text(json.dumps(owner_payload, indent=2) + '\n')
        owner.verify_owner_evidence_payload(owner_payload, acceptance_path=acc, config_path=owner_cfg, registry_path=REG, require_live_mt5=False, require_closure_run_id=False)

        meta_payload = build_valid_metaeditor_fixture(meta, acceptance_path=acc, config_path=meta_cfg, registry_path=REG, sandbox=td / 'meta_sandbox', artifact_dir=ed / 'meta_artifacts')
        meta_ev.write_text(json.dumps(meta_payload, indent=2) + '\n')
        meta.verify_metaeditor_evidence_payload(meta_payload, acceptance_path=acc, registry_path=REG, config_path=meta_cfg, allow_test_fixture=True, require_closure_run_id=False)
        req(True, 'candidate-bound MetaEditor proof accepted only from archived log/tool/artifacts')

        fake_py = td / 'canonical_venv' / 'Scripts' / 'python.exe'
        fake_venv = fake_py.parents[1]
        pyenv_payload = {
            'schema': pyenv.SCHEMA, 'project': 'Max MTF', 'version': '2.0.1', 'phase': 'MTF_1_FINAL_CLOSURE',
            'generated_utc': '2026-09-19T00:00:00+00:00',
            'authority': 'ONE_CANONICAL_MAX_VENV_INTERPRETER_FOR_FULL_CLOSURE_CHAIN',
            'closure_run_id': TEST_RUN_ID, 'canonical_python': str(fake_py.resolve()), 'canonical_venv': str(fake_venv.resolve()),
            'requirements_digest': 'a' * 64,
            'accelerator_bootstrap': {'schema': 'MAX_ACCELERATOR_BOOTSTRAP_V1', 'status': 'READY', 'target': 'CPU'},
            'interpreter_identity': {
                'sys_executable': str(fake_py.resolve()), 'python_version': '3.12.9', 'python_major_minor': [3, 12],
                'sys_prefix': str(fake_venv.resolve()), 'sys_base_prefix': str((td / 'base312').resolve()), 'in_venv': True,
                'torch_installed': True, 'torch_version': '2.6.0+cpu', 'torch_cuda_version': None,
                'cuda_available': False, 'cpu_tensor_test': True, 'cuda_tensor_test': False,
            },
            'stage_plan': pyenv.build_stage_plan(fake_py),
            'rule': 'Every final-closure child stage must be launched with canonical_python; no arbitrary system Python stage execution is allowed.',
        }
        pyenv_ev.write_text(json.dumps(pyenv_payload, indent=2) + '\n')

        # Final closure production path is intentionally strict (live MT5 + real MetaEditor).
        # In this isolated selftest only, explicitly wrap those authorities with their test-fixture modes.
        orig_owner_verify = final.owner_runtime.verify_owner_evidence_payload
        orig_meta_verify = final.metaeditor.verify_metaeditor_evidence_payload
        final.owner_runtime.verify_owner_evidence_payload = lambda payload, **kw: orig_owner_verify(
            payload, **kw, require_live_mt5=False, require_closure_run_id=False
        )
        final.metaeditor.verify_metaeditor_evidence_payload = lambda payload, **kw: orig_meta_verify(
            payload, **kw, allow_test_fixture=True, require_closure_run_id=False
        )
        try:
            closure = final.build_final_closure_payload(
                acceptance_path=acc, owner_evidence_path=owner_ev, metaeditor_evidence_path=meta_ev, registry_path=REG,
                owner_config_path=owner_cfg, metaeditor_config_path=meta_cfg,
                python_env_path=pyenv_ev, require_current_python=False,
            )
            final.verify_final_closure_payload(
                closure, acceptance_path=acc, owner_evidence_path=owner_ev, metaeditor_evidence_path=meta_ev, registry_path=REG,
                owner_config_path=owner_cfg, metaeditor_config_path=meta_cfg,
                python_env_path=pyenv_ev, require_current_python=False,
            )
        finally:
            final.owner_runtime.verify_owner_evidence_payload = orig_owner_verify
            final.metaeditor.verify_metaeditor_evidence_payload = orig_meta_verify
        req(closure['decision'] == 'MTF_1_CLOSED' and closure['closure_run_id'] == TEST_RUN_ID, 'final closure binds one shared run ID')

        bad = copy.deepcopy(meta_payload); bad['compile']['compile_summary']['errors'] = 1
        try:
            meta.verify_metaeditor_evidence_payload(bad, acceptance_path=acc, registry_path=REG, config_path=meta_cfg, allow_test_fixture=True, require_closure_run_id=False)
            accepted = True
        except meta.MetaEditorAcceptanceError:
            accepted = False
        req(not accepted, 'caller-supplied compiler error summary cannot pass')
finally:
    run_acceptance.read_closure_run = orig_ra
    auth.read_closure_run = orig_auth

print('V201_METAEDITOR_FINAL_CLOSURE_WIRING PASS')
