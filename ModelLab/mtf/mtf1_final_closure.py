from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import acceptance.runners.run_acceptance as run_acceptance
import acceptance.runners.owner_mtf1_runtime_acceptance as owner_runtime
import acceptance.runners.owner_mtf1_metaeditor_acceptance as metaeditor
import mtf.mtf1_python_env_authority as python_env
from mtf.mtf1_closure_authority import (
    EXTERNAL_REGISTRY,
    LOCAL_ACCEPTANCE,
    MTF1ClosureError,
    assert_base_binding_equal,
    current_base_candidate_binding,
    read_json,
    sha256_file,
)

ROOT = MODELLAB_ROOT
PKG = ROOT.parent
OWNER_RUNTIME_EVIDENCE = PKG / 'owner_acceptance/evidence/mtf1/OWNER_MTF1_RUNTIME_ACCEPTANCE.json'
METAEDITOR_EVIDENCE = PKG / 'owner_acceptance/evidence/mtf1/OWNER_MTF1_METAEDITOR_ACCEPTANCE.json'
FINAL_EVIDENCE = PKG / 'owner_acceptance/evidence/mtf1/OWNER_MTF1_FINAL_CLOSURE.json'
PYTHON_ENV_EVIDENCE = python_env.EVIDENCE
SCHEMA = 'MAX_MTF1_FINAL_CLOSURE_V2_EXECUTION_PROOF'
PHASE = 'MTF_1_FINAL_CLOSURE'

FinalClosureError = MTF1ClosureError


def _closure_requirements() -> dict[str, str]:
    gates = run_acceptance._external_gates()
    by_gate = {str(x.get('gate')): str(x.get('requirement') or '') for x in gates}
    expected = dict(run_acceptance.MTF1_EXTERNAL_REQUIREMENT_LOCK)
    for gate, requirement in expected.items():
        if by_gate.get(gate) != requirement:
            raise FinalClosureError(f'FINAL_CLOSURE_EXTERNAL_REQUIREMENT_MISMATCH: {gate}')
    return expected


def build_final_closure_payload(
    *,
    acceptance_path: Path = LOCAL_ACCEPTANCE,
    owner_evidence_path: Path = OWNER_RUNTIME_EVIDENCE,
    metaeditor_evidence_path: Path = METAEDITOR_EVIDENCE,
    registry_path: Path = EXTERNAL_REGISTRY,
    owner_config_path: Path = owner_runtime.CONFIG,
    metaeditor_config_path: Path = metaeditor.CONFIG,
    python_env_path: Path = PYTHON_ENV_EVIDENCE,
    require_current_python: bool = True,
) -> dict[str, Any]:
    local = run_acceptance.validate_local_acceptance_report(
        acceptance_path,
        require_current_tree=True,
        require_current_suite=True,
        require_fresh_full=True,
        require_closure_run_id=True,
    )
    base = current_base_candidate_binding(
        acceptance_path=acceptance_path,
        registry_path=registry_path,
        require_fresh_full=True,
        require_closure_run_id=True,
    )
    run_id = str(base.get('closure_run_id') or '')
    if not run_id:
        raise FinalClosureError('FINAL_CLOSURE_RUN_ID_REQUIRED')
    python_binding = python_env.final_closure_binding(
        closure_run_id=run_id, path=python_env_path, require_current_process=require_current_python,
    )
    owner_payload = read_json(owner_evidence_path)
    owner_binding = owner_runtime.verify_owner_evidence_payload(
        owner_payload,
        acceptance_path=acceptance_path,
        config_path=owner_config_path,
        registry_path=registry_path,
        require_fresh_full=True,
    )
    meta_payload = read_json(metaeditor_evidence_path)
    meta_binding = metaeditor.verify_metaeditor_evidence_payload(
        meta_payload,
        acceptance_path=acceptance_path,
        registry_path=registry_path,
        config_path=metaeditor_config_path,
        require_fresh_full=True,
    )
    owner_base = dict(owner_binding)
    owner_base['schema'] = owner_binding.get('base_binding_schema')
    assert_base_binding_equal(owner_base, base)
    assert_base_binding_equal(meta_binding, base)
    if str((owner_payload.get('candidate_binding') or {}).get('closure_run_id') or '') != run_id:
        raise FinalClosureError('FINAL_CLOSURE_OWNER_RUN_ID_MISMATCH')
    if str((meta_payload.get('candidate_binding') or {}).get('closure_run_id') or '') != run_id:
        raise FinalClosureError('FINAL_CLOSURE_METAEDITOR_RUN_ID_MISMATCH')

    requirements = _closure_requirements()
    return {
        'schema': SCHEMA,
        'project': 'Max MTF',
        'version': '2.0.1',
        'phase': PHASE,
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'overall_status': 'PASS',
        'decision': 'MTF_1_CLOSED',
        'closure_run_id': run_id,
        'candidate_binding': base,
        'python_environment': python_binding,
        'local_acceptance': {
            'path': str(Path(acceptance_path).resolve()),
            'sha256': sha256_file(acceptance_path),
            'gate_count': len(run_acceptance.TESTS),
            'source_tree_signature': local['source_tree_signature'],
            'suite_signature': local['suite_signature'],
            'execution_mode': local.get('execution_mode'),
            'closure_run_id': local.get('closure_run_id'),
        },
        'owner_runtime_evidence': {
            'path': str(Path(owner_evidence_path).resolve()),
            'sha256': sha256_file(owner_evidence_path),
            'execution_artifact_set_sha256': ((owner_payload.get('execution_artifacts') or {}).get('artifact_set_sha256')),
            'bundle_identity_preview_sha256': owner_payload.get('bundle_identity_preview_sha256'),
            'closure_run_id': ((owner_payload.get('candidate_binding') or {}).get('closure_run_id')),
        },
        'metaeditor_evidence': {
            'path': str(Path(metaeditor_evidence_path).resolve()),
            'sha256': sha256_file(metaeditor_evidence_path),
            'ex5_sha256': ((meta_payload.get('compile') or {}).get('ex5_sha256')),
            'process_record_sha256': ((meta_payload.get('compile') or {}).get('process_record_sha256')),
            'closure_run_id': ((meta_payload.get('candidate_binding') or {}).get('closure_run_id')),
        },
        'external_requirements': requirements,
        'closure_results': [
            {'gate': f'LOCAL_ACCEPTANCE_{len(run_acceptance.TESTS)}_OF_{len(run_acceptance.TESTS)}', 'status': 'PASS'},
            {'gate': 'OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION', 'status': 'PASS'},
            {'gate': 'OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY', 'status': 'PASS'},
            {'gate': 'METAEDITOR_MAX_MTF_V2_COMPILE', 'status': 'PASS'},
            {'gate': 'MTF_STRATEGY_RUNTIME', 'status': 'NOT_APPLICABLE_MTF1'},
        ],
        'rule': 'MTF-1 closes only when one shared closure_run_id binds fresh complete local acceptance, archived+replayed+live-revalidated Owner MT5 inputs, archived-log/tool-verified MetaEditor compile proof, and this final readback authority.',
    }


def verify_final_closure_payload(
    payload: Mapping[str, Any],
    *,
    acceptance_path: Path = LOCAL_ACCEPTANCE,
    owner_evidence_path: Path = OWNER_RUNTIME_EVIDENCE,
    metaeditor_evidence_path: Path = METAEDITOR_EVIDENCE,
    registry_path: Path = EXTERNAL_REGISTRY,
    owner_config_path: Path = owner_runtime.CONFIG,
    metaeditor_config_path: Path = metaeditor.CONFIG,
    python_env_path: Path = PYTHON_ENV_EVIDENCE,
    require_current_python: bool = True,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get('schema') != SCHEMA:
        raise FinalClosureError('FINAL_CLOSURE_SCHEMA_MISMATCH')
    if payload.get('project') != 'Max MTF' or payload.get('version') != '2.0.1' or payload.get('phase') != PHASE:
        raise FinalClosureError('FINAL_CLOSURE_IDENTITY_MISMATCH')
    if payload.get('overall_status') != 'PASS' or payload.get('decision') != 'MTF_1_CLOSED':
        raise FinalClosureError('FINAL_CLOSURE_NOT_PASS')
    expected = build_final_closure_payload(
        acceptance_path=acceptance_path,
        owner_evidence_path=owner_evidence_path,
        metaeditor_evidence_path=metaeditor_evidence_path,
        registry_path=registry_path,
        owner_config_path=owner_config_path,
        metaeditor_config_path=metaeditor_config_path,
        python_env_path=python_env_path,
        require_current_python=require_current_python,
    )
    if payload.get('closure_run_id') != expected['closure_run_id']:
        raise FinalClosureError('FINAL_CLOSURE_RUN_ID_MISMATCH')
    actual_binding = payload.get('candidate_binding')
    if not isinstance(actual_binding, Mapping):
        raise FinalClosureError('FINAL_CLOSURE_BINDING_MISSING')
    assert_base_binding_equal(actual_binding, expected['candidate_binding'])
    if payload.get('python_environment') != expected['python_environment']:
        raise FinalClosureError('FINAL_CLOSURE_PYTHON_ENVIRONMENT_MISMATCH')
    for section in ('local_acceptance', 'owner_runtime_evidence', 'metaeditor_evidence'):
        actual = payload.get(section)
        if not isinstance(actual, Mapping):
            raise FinalClosureError(f'FINAL_CLOSURE_SECTION_MISSING: {section}')
        for key, value in expected[section].items():
            if key == 'path':
                continue
            if actual.get(key) != value:
                raise FinalClosureError(f'FINAL_CLOSURE_SECTION_MISMATCH: {section}.{key}')
    if payload.get('external_requirements') != expected['external_requirements']:
        raise FinalClosureError('FINAL_CLOSURE_EXTERNAL_REQUIREMENTS_MISMATCH')
    if payload.get('closure_results') != expected['closure_results']:
        raise FinalClosureError('FINAL_CLOSURE_RESULTS_MISMATCH')
    return expected


def write_and_verify_final_closure(path: Path = FINAL_EVIDENCE) -> dict[str, Any]:
    payload = build_final_closure_payload()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    verify_final_closure_payload(read_json(path))
    return payload


def verify_existing_final_closure(path: Path = FINAL_EVIDENCE) -> dict[str, Any]:
    before = sha256_file(path)
    payload = read_json(path)
    verified = verify_final_closure_payload(payload)
    after = sha256_file(path)
    if before != after:
        raise FinalClosureError('FINAL_VERIFY_MUTATED_EVIDENCE')
    return {'status': 'PASS', 'decision': 'MTF_1_CLOSED', 'evidence': str(path), 'closure_run_id': verified['closure_run_id'], 'candidate_binding': verified['candidate_binding']}


def main() -> int:
    python_env.assert_current_process_if_required('final_closure_verify' if '--verify-existing' in sys.argv else 'final_closure_write')
    ap = argparse.ArgumentParser(); ap.add_argument('--verify-existing', action='store_true'); args = ap.parse_args()
    try:
        if args.verify_existing:
            out = verify_existing_final_closure(FINAL_EVIDENCE)
        else:
            payload = write_and_verify_final_closure(FINAL_EVIDENCE)
            out = {'status': 'PASS', 'decision': payload['decision'], 'evidence': str(FINAL_EVIDENCE), 'closure_run_id': payload['closure_run_id'], 'candidate_binding': payload['candidate_binding']}
        print(json.dumps(out, indent=2)); return 0
    except Exception as exc:
        print(json.dumps({'status': 'FAIL', 'decision': 'MTF_1_NOT_CLOSED', 'reason': str(exc)}, indent=2), file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
