from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from host.mt5_installation import validate_mt5_data_root
from mtf.mtf1_closure_authority import (
    EXTERNAL_REGISTRY,
    LOCAL_ACCEPTANCE,
    MTF1ClosureError,
    assert_base_binding_equal,
    current_base_candidate_binding,
    is_sha256,
    path_label,
    read_json,
    sha256_file,
)
from strategy.strategy_optimizer import discover_mt5_installations
from strategy.strategy_optimizer_worker import _compile_summary, _read_compile_log, re_search_error

ROOT = MODELLAB_ROOT
PKG = ROOT.parent
CONFIG = PKG / 'owner_acceptance/runtime/OWNER_MTF1_METAEDITOR_ACCEPTANCE_CONFIG.json'
EVIDENCE_ROOT = PKG / 'owner_acceptance/evidence/mtf1/metaeditor'
EVIDENCE = PKG / 'owner_acceptance/evidence/mtf1/OWNER_MTF1_METAEDITOR_ACCEPTANCE.json'
SCHEMA = 'MAX_MTF1_METAEDITOR_ACCEPTANCE_V2_EXECUTION_PROOF'
PHASE = 'MTF_1_METAEDITOR_EXECUTION_PROOF'
PROCESS_SCHEMA = 'MAX_MTF1_METAEDITOR_PROCESS_RECORD_V1'
RETURNCODE_AUTHORITY = 'DIAGNOSTIC_ONLY'

MetaEditorAcceptanceError = MTF1ClosureError


def _parse_process_returncode(value: Any, field: str) -> int:
    # subprocess return codes are exact signed integers. Booleans/floats/strings are not
    # accepted as evidence because coercion could turn malformed values into zero.
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetaEditorAcceptanceError(f'METAEDITOR_PROCESS_RETURNCODE_INVALID: {field}={value!r}')
    return value


def _test_mode() -> bool:
    return os.environ.get('MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE') == '1'


def _parse_utc(value: Any, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception as exc:
        raise MetaEditorAcceptanceError(f'METAEDITOR_EVIDENCE_INVALID_UTC: {field}') from exc
    if dt.tzinfo is None:
        raise MetaEditorAcceptanceError(f'METAEDITOR_EVIDENCE_NAIVE_UTC: {field}')
    return dt.astimezone(timezone.utc)


def _read_config(path: Path = CONFIG) -> dict[str, Any]:
    raw = read_json(path)
    return {
        'terminal_exe': str(raw.get('terminal_exe') or '').strip() or None,
        'metaeditor_exe': str(raw.get('metaeditor_exe') or '').strip() or None,
        'mt5_data_root': str(raw.get('mt5_data_root') or '').strip() or None,
        'timeout_seconds': max(30, min(600, int(raw.get('timeout_seconds') or 180))),
    }


def _resolve_installation(cfg: Mapping[str, Any]) -> dict[str, str]:
    meta = cfg.get('metaeditor_exe'); data = cfg.get('mt5_data_root'); terminal = cfg.get('terminal_exe')
    if meta or data:
        if not meta or not data:
            raise MetaEditorAcceptanceError('METAEDITOR_CONFIG_EXPLICIT_META_AND_DATA_ROOT_REQUIRED_TOGETHER')
        meta_p = Path(str(meta)).expanduser()
        if not meta_p.is_file():
            raise MetaEditorAcceptanceError(f'METAEDITOR_EXE_NOT_FOUND: {meta_p}')
        verified = validate_mt5_data_root(str(data))
        terminal_p = Path(str(terminal)).expanduser() if terminal else None
        if terminal_p is not None and not terminal_p.is_file():
            raise MetaEditorAcceptanceError(f'MT5_TERMINAL_EXE_NOT_FOUND: {terminal_p}')
        return {'terminal': str(terminal_p) if terminal_p else '', 'metaeditor': str(meta_p), 'data_dir': verified.data_root, 'terminal_id': verified.terminal_id, 'resolution': 'EXPLICIT_CONFIG'}
    installs = discover_mt5_installations()
    if terminal:
        wanted = str(Path(str(terminal)).resolve()).lower()
        installs = [x for x in installs if str(Path(x.terminal).resolve()).lower() == wanted]
    if len(installs) != 1:
        raise MetaEditorAcceptanceError(f'METAEDITOR_INSTALLATION_NOT_UNIQUE: found={len(installs)}; set metaeditor_exe + mt5_data_root explicitly in {CONFIG}')
    inst = installs[0]; verified = validate_mt5_data_root(inst.data_dir)
    return {'terminal': inst.terminal, 'metaeditor': inst.metaeditor, 'data_dir': verified.data_root, 'terminal_id': verified.terminal_id, 'resolution': 'AUTO_DETECT_UNIQUE_INSTALLATION'}


def _artifact_from_project_relative(value: Any) -> Path:
    raw = str(value or '').strip()
    if not raw:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_ARTIFACT_PATH_MISSING')
    p = Path(raw)
    if p.is_absolute():
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_ARTIFACT_PATH_NOT_PORTABLE')
    resolved = (PKG / p).resolve()
    try:
        resolved.relative_to(PKG.resolve())
    except Exception as exc:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_ARTIFACT_PATH_ESCAPES_PROJECT') from exc
    return resolved


def _norm_path(value: Any) -> str:
    return str(value or '').replace('\\', '/').rstrip('/').lower()


def _validate_metaeditor_binary(path: Path, *, allow_test_fixture: bool = False) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise MetaEditorAcceptanceError(f'METAEDITOR_EXE_NOT_FOUND: {p}')
    name = p.name.lower()
    if name not in {'metaeditor.exe', 'metaeditor64.exe'}:
        raise MetaEditorAcceptanceError(f'METAEDITOR_TOOL_BASENAME_INVALID: {p.name}')
    size = p.stat().st_size
    head = p.read_bytes()[:4096]
    if not allow_test_fixture:
        if size < 500_000 or not head.startswith(b'MZ'):
            raise MetaEditorAcceptanceError('METAEDITOR_TOOL_BINARY_IDENTITY_IMPLAUSIBLE')
    else:
        if size < 4096 or not head.startswith(b'MZ'):
            raise MetaEditorAcceptanceError('METAEDITOR_TEST_TOOL_BINARY_IDENTITY_IMPLAUSIBLE')
    return {'path': str(p), 'sha256': sha256_file(p), 'size_bytes': size, 'pe_magic': head[:2].hex()}


def _validate_ex5_binary(path: Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise MetaEditorAcceptanceError(f'METAEDITOR_EX5_MISSING: {p}')
    data = p.read_bytes()
    if len(data) < 1024:
        raise MetaEditorAcceptanceError('METAEDITOR_EX5_TOO_SMALL_OR_FAKE')
    sample = data[:4096]
    nonprint = sum(1 for b in sample if b == 0 or b < 9 or (13 < b < 32) or b > 126)
    if nonprint / max(1, len(sample)) < 0.08:
        raise MetaEditorAcceptanceError('METAEDITOR_EX5_NOT_BINARY_LIKE')
    return {'sha256': sha256_file(p), 'size_bytes': len(data), 'binary_nonprint_ratio': nonprint / max(1, len(sample))}


def _assert_compile_semantic_authority(log_text: str, ex5_path: Path, expected_source_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Authoritative MetaEditor compile semantics. OS return code is intentionally absent."""
    parsed = _compile_summary(log_text)
    if not parsed.get('found') or parsed.get('errors') is None:
        raise MetaEditorAcceptanceError('METAEDITOR_COMPILE_SUMMARY_MISSING_OR_UNPARSEABLE')
    if int(parsed['errors']) != 0 or re_search_error(log_text):
        raise MetaEditorAcceptanceError(f'METAEDITOR_COMPILE_LOG_HAS_ERRORS: summary={parsed}')
    if str(expected_source_name or '').lower() not in str(log_text or '').lower():
        raise MetaEditorAcceptanceError('METAEDITOR_COMPILE_LOG_SOURCE_IDENTITY_MISSING')
    ex5_info = _validate_ex5_binary(ex5_path)
    return parsed, ex5_info


def _expected_binding(*, acceptance_path: Path, registry_path: Path, require_fresh_full: bool, require_closure_run_id: bool) -> dict[str, Any]:
    return current_base_candidate_binding(
        acceptance_path=acceptance_path,
        registry_path=registry_path,
        require_fresh_full=require_fresh_full,
        require_closure_run_id=require_closure_run_id,
    )


def verify_metaeditor_evidence_payload(
    payload: Mapping[str, Any],
    *,
    acceptance_path: Path = LOCAL_ACCEPTANCE,
    registry_path: Path = EXTERNAL_REGISTRY,
    config_path: Path = CONFIG,
    require_fresh_full: bool = True,
    allow_test_fixture: bool = False,
    require_closure_run_id: bool = True,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get('schema') != SCHEMA:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_SCHEMA_MISMATCH')
    if payload.get('project') != 'Max MTF' or payload.get('version') != '2.0.1' or payload.get('phase') != PHASE:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_IDENTITY_MISMATCH')
    started = _parse_utc(payload.get('started_utc'), 'started_utc'); completed = _parse_utc(payload.get('completed_utc'), 'completed_utc')
    if completed < started or str(payload.get('overall_status') or '').upper() != 'PASS':
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_TIME_OR_STATUS_INVALID')
    actual_binding = payload.get('candidate_binding')
    if not isinstance(actual_binding, Mapping):
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_CANDIDATE_BINDING_MISSING')
    expected_binding = _expected_binding(acceptance_path=acceptance_path, registry_path=registry_path, require_fresh_full=require_fresh_full, require_closure_run_id=require_closure_run_id)
    assert_base_binding_equal(actual_binding, expected_binding)
    run_id = str(expected_binding.get('closure_run_id') or '')
    if not run_id:
        raise MetaEditorAcceptanceError('METAEDITOR_CLOSURE_RUN_ID_REQUIRED')
    if str(payload.get('metaeditor_config_sha256') or '') != sha256_file(config_path):
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_CONFIG_SHA_MISMATCH')
    gates = payload.get('gates')
    if not isinstance(gates, list) or len(gates) != 1 or not isinstance(gates[0], Mapping) or gates[0].get('gate') != 'METAEDITOR_MAX_MTF_V2_COMPILE' or str(gates[0].get('status') or '').upper() != 'PASS':
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_GATE_SET_INVALID')
    comp = payload.get('compile')
    if not isinstance(comp, Mapping) or str(comp.get('closure_run_id') or '') != run_id:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_COMPILE_PROOF_OR_RUN_ID_INVALID')
    compile_process_returncode = _parse_process_returncode(comp.get('process_returncode'), 'compile.process_returncode')
    if comp.get('returncode_authority') != RETURNCODE_AUTHORITY:
        raise MetaEditorAcceptanceError('METAEDITOR_RETURNCODE_AUTHORITY_INVALID')
    if comp.get('source_relative_path') != expected_binding['active_ea_relative_path'] or str(comp.get('source_sha256') or '').lower() != expected_binding['active_ea_sha256'] or str(comp.get('source_version') or '') != expected_binding['active_ea_version']:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_SOURCE_IDENTITY_MISMATCH')
    if str(comp.get('deployed_mq5_sha256') or '').lower() != expected_binding['active_ea_sha256']:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_DEPLOYED_SOURCE_SHA_MISMATCH')

    cfg = _read_config(config_path)
    installation = _resolve_installation(cfg)
    expected_meta = Path(installation['metaeditor']).resolve()
    if _norm_path(comp.get('metaeditor_exe')) != _norm_path(expected_meta):
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_TOOL_PATH_NOT_CURRENT_INSTALLATION')
    tool = _validate_metaeditor_binary(expected_meta, allow_test_fixture=allow_test_fixture)
    if str(comp.get('metaeditor_exe_sha256') or '').lower() != tool['sha256']:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_TOOL_SHA_MISMATCH')
    if int(comp.get('metaeditor_exe_size_bytes') or -1) != int(tool['size_bytes']):
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_TOOL_SIZE_MISMATCH')
    verified_root = validate_mt5_data_root(installation['data_dir'])
    if _norm_path(comp.get('terminal_data_root')) != _norm_path(verified_root.data_root) or str(comp.get('terminal_id') or '') != str(verified_root.terminal_id):
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_TERMINAL_IDENTITY_MISMATCH')

    deployed = Path(str(comp.get('deployed_mq5') or ''))
    if not deployed.is_file() or sha256_file(deployed) != expected_binding['active_ea_sha256']:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_DEPLOYED_SOURCE_NOT_PRESENT_OR_CHANGED')
    expected_cmd = [str(expected_meta), f'/compile:{deployed}', '/log']
    if comp.get('command_argv') != expected_cmd:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_COMMAND_ARGV_MISMATCH')

    archived_ex5 = _artifact_from_project_relative(comp.get('archived_ex5'))
    archived_log = _artifact_from_project_relative(comp.get('archived_log'))
    archived_process = _artifact_from_project_relative(comp.get('archived_process_record'))
    if not archived_ex5.is_file() or not archived_log.is_file() or not archived_process.is_file():
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_ARCHIVED_ARTIFACT_MISSING')
    if sha256_file(archived_ex5) != str(comp.get('ex5_sha256') or '').lower() or sha256_file(archived_log) != str(comp.get('compile_log_sha256') or '').lower() or sha256_file(archived_process) != str(comp.get('process_record_sha256') or '').lower():
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_ARCHIVED_ARTIFACT_SHA_MISMATCH')
    ex5_info = _validate_ex5_binary(archived_ex5)
    if int(comp.get('ex5_size_bytes') or -1) != ex5_info['size_bytes']:
        raise MetaEditorAcceptanceError('METAEDITOR_EVIDENCE_EX5_SIZE_MISMATCH')

    log_text = archived_log.read_text(encoding='utf-8', errors='replace')
    parsed, semantic_ex5_info = _assert_compile_semantic_authority(
        log_text, archived_ex5, Path(expected_binding['active_ea_relative_path']).name
    )
    if semantic_ex5_info['sha256'] != ex5_info['sha256'] or semantic_ex5_info['size_bytes'] != ex5_info['size_bytes']:
        raise MetaEditorAcceptanceError('METAEDITOR_EX5_SEMANTIC_REVALIDATION_MISMATCH')
    claimed = comp.get('compile_summary')
    if not isinstance(claimed, Mapping) or dict(claimed) != dict(parsed):
        raise MetaEditorAcceptanceError('METAEDITOR_COMPILE_SUMMARY_NOT_DERIVED_FROM_ARCHIVED_LOG')
    if int(gates[0].get('errors') if gates[0].get('errors') is not None else -1) != 0 or int(gates[0].get('warnings') or 0) != int(parsed.get('warnings') or 0):
        raise MetaEditorAcceptanceError('METAEDITOR_GATE_SUMMARY_NOT_DERIVED_FROM_LOG')

    process = read_json(archived_process)
    if process.get('schema') != PROCESS_SCHEMA or process.get('closure_run_id') != run_id:
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_IDENTITY_MISMATCH')
    archived_process_returncode = _parse_process_returncode(process.get('process_returncode'), 'process_record.process_returncode')
    if compile_process_returncode != archived_process_returncode:
        raise MetaEditorAcceptanceError(
            'METAEDITOR_PROCESS_RETURNCODE_MISMATCH: '
            f'compile={compile_process_returncode} process_record={archived_process_returncode}'
        )
    if process.get('returncode_authority') != RETURNCODE_AUTHORITY:
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_RETURNCODE_AUTHORITY_INVALID')
    if not isinstance(process.get('compile_summary'), Mapping) or dict(process['compile_summary']) != dict(parsed):
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_COMPILE_SUMMARY_MISMATCH')
    if process.get('command_argv') != expected_cmd or _norm_path(process.get('metaeditor_exe')) != _norm_path(expected_meta) or str(process.get('metaeditor_exe_sha256') or '').lower() != tool['sha256'] or int(process.get('metaeditor_exe_size_bytes') or -1) != int(tool['size_bytes']) or str(process.get('source_sha256') or '').lower() != expected_binding['active_ea_sha256']:
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_COMMAND_OR_IDENTITY_MISMATCH')
    if _norm_path(process.get('deployed_mq5')) != _norm_path(deployed) or str(process.get('deployed_mq5_sha256') or '').lower() != expected_binding['active_ea_sha256']:
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_DEPLOYED_SOURCE_MISMATCH')
    if _norm_path(process.get('output_ex5')) != _norm_path(deployed.with_suffix('.ex5')) or str(process.get('output_ex5_sha256') or '').lower() != ex5_info['sha256']:
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_OUTPUT_EX5_MISMATCH')
    if str(process.get('archived_log_sha256') or '').lower() != sha256_file(archived_log) or str(process.get('archived_ex5_sha256') or '').lower() != sha256_file(archived_ex5):
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_ARTIFACT_MISMATCH')
    if comp.get('precompile_ex5_absent') is not True or comp.get('ex5_exists_after_compile') is not True:
        raise MetaEditorAcceptanceError('METAEDITOR_COMPILE_FRESH_OUTPUT_FLAGS_INVALID')
    if process.get('precompile_ex5_absent') is not True or process.get('postcompile_ex5_exists') is not True:
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_FRESH_OUTPUT_INVALID')
    pstart = _parse_utc(process.get('started_utc'), 'process.started_utc'); pend = _parse_utc(process.get('completed_utc'), 'process.completed_utc')
    if pstart != started or pend != completed or pend < pstart:
        raise MetaEditorAcceptanceError('METAEDITOR_PROCESS_RECORD_TIME_MISMATCH')
    mtime_ns = int(process.get('postcompile_ex5_mtime_ns') or 0)
    archived_mtime_ns = int(archived_ex5.stat().st_mtime_ns)
    if archived_mtime_ns != mtime_ns:
        raise MetaEditorAcceptanceError('METAEDITOR_EX5_MTIME_EVIDENCE_MISMATCH')
    log_mtime_ns = int(process.get('compile_log_mtime_ns') or 0)
    if int(archived_log.stat().st_mtime_ns) != log_mtime_ns:
        raise MetaEditorAcceptanceError('METAEDITOR_COMPILE_LOG_MTIME_EVIDENCE_MISMATCH')
    lower_ns = int(started.timestamp() * 1_000_000_000) - 5_000_000_000
    upper_ns = int(completed.timestamp() * 1_000_000_000) + 5_000_000_000
    if mtime_ns < lower_ns or mtime_ns > upper_ns:
        raise MetaEditorAcceptanceError('METAEDITOR_EX5_MTIME_OUTSIDE_COMPILE_WINDOW')
    if log_mtime_ns < lower_ns or log_mtime_ns > upper_ns:
        raise MetaEditorAcceptanceError('METAEDITOR_COMPILE_LOG_MTIME_OUTSIDE_COMPILE_WINDOW')
    fresh_ex5 = comp.get('fresh_ex5')
    if not isinstance(fresh_ex5, Mapping) or fresh_ex5.get('exists') is not True:
        raise MetaEditorAcceptanceError('METAEDITOR_FRESH_EX5_EVIDENCE_MISSING')
    if str(fresh_ex5.get('sha256') or '').lower() != ex5_info['sha256'] or int(fresh_ex5.get('size_bytes') or -1) != ex5_info['size_bytes'] or int(fresh_ex5.get('mtime_ns') or 0) != mtime_ns:
        raise MetaEditorAcceptanceError('METAEDITOR_FRESH_EX5_EVIDENCE_MISMATCH')
    return expected_binding


def verify_existing_evidence(path: Path = EVIDENCE) -> dict[str, Any]:
    payload = read_json(path)
    binding = verify_metaeditor_evidence_payload(payload)
    return {'status': 'PASS', 'evidence': str(path), 'candidate_binding': binding}


def _write(payload: Mapping[str, Any]) -> None:
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(dict(payload), indent=2, default=str) + '\n', encoding='utf-8')


def _run_compile() -> int:
    started = datetime.now(timezone.utc)
    payload: dict[str, Any] = {'schema': SCHEMA, 'project': 'Max MTF', 'version': '2.0.1', 'phase': PHASE, 'started_utc': started.isoformat(), 'completed_utc': started.isoformat(), 'overall_status': 'FAIL', 'gates': []}
    try:
        binding = current_base_candidate_binding(require_fresh_full=True, require_closure_run_id=True)
        run_id = str(binding.get('closure_run_id') or '')
        if not run_id:
            raise MetaEditorAcceptanceError('METAEDITOR_CLOSURE_RUN_ID_REQUIRED')
        payload['candidate_binding'] = binding
        cfg = _read_config(); payload['metaeditor_config_sha256'] = sha256_file(CONFIG)
        installation = _resolve_installation(cfg)
        meta = Path(installation['metaeditor']).resolve()
        tool = _validate_metaeditor_binary(meta, allow_test_fixture=False)
        src = (PKG / binding['active_ea_relative_path']).resolve()
        if sha256_file(src) != binding['active_ea_sha256']:
            raise MetaEditorAcceptanceError('METAEDITOR_SOURCE_SHA_CHANGED_AFTER_BINDING')
        verified = validate_mt5_data_root(installation['data_dir'], create_subdirs=True)
        expert_dir = Path(verified.experts_dir); expert_dir.mkdir(parents=True, exist_ok=True)
        deployed = expert_dir / src.name; shutil.copy2(src, deployed)
        if sha256_file(deployed) != binding['active_ea_sha256']:
            raise MetaEditorAcceptanceError('METAEDITOR_DEPLOYED_MQ5_NOT_BYTE_IDENTICAL')
        ex5 = deployed.with_suffix('.ex5'); log = deployed.with_suffix('.log')
        if ex5.exists(): ex5.unlink()
        precompile_absent = not ex5.exists()
        if log.exists(): log.unlink()
        cmd = [str(meta), f'/compile:{deployed}', '/log']
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=int(cfg['timeout_seconds']))
        completed = datetime.now(timezone.utc)
        if not log.is_file():
            raise MetaEditorAcceptanceError(f'METAEDITOR_COMPILE_LOG_MISSING: returncode={cp.returncode}')
        log_text = _read_compile_log(log)
        parsed, ex5_info = _assert_compile_semantic_authority(log_text, ex5, src.name)
        run_dir = EVIDENCE_ROOT / run_id
        if run_dir.exists():
            raise MetaEditorAcceptanceError(f'METAEDITOR_RUN_ARTIFACT_DIR_ALREADY_EXISTS: {run_dir}')
        run_dir.mkdir(parents=True, exist_ok=False)
        archived_ex5 = run_dir / 'Max_MTF.ex5'; archived_log = run_dir / 'metaeditor_compile.log'; process_path = run_dir / 'compile_process.json'
        shutil.copy2(ex5, archived_ex5); archived_log.write_text(log_text, encoding='utf-8')
        process = {
            'schema': PROCESS_SCHEMA, 'closure_run_id': run_id, 'started_utc': started.isoformat(), 'completed_utc': completed.isoformat(),
            'metaeditor_exe': str(meta), 'metaeditor_exe_sha256': tool['sha256'], 'metaeditor_exe_size_bytes': tool['size_bytes'],
            'source_path': str(src), 'source_sha256': binding['active_ea_sha256'], 'deployed_mq5': str(deployed), 'deployed_mq5_sha256': sha256_file(deployed),
            'output_ex5': str(ex5), 'output_ex5_sha256': sha256_file(ex5),
            'command_argv': cmd, 'process_returncode': cp.returncode, 'returncode_authority': RETURNCODE_AUTHORITY, 'compile_summary': parsed,
            'precompile_ex5_absent': precompile_absent, 'postcompile_ex5_exists': ex5.is_file(),
            'postcompile_ex5_mtime_ns': ex5.stat().st_mtime_ns, 'compile_log_mtime_ns': archived_log.stat().st_mtime_ns,
            'archived_log_sha256': sha256_file(archived_log), 'archived_ex5_sha256': sha256_file(archived_ex5),
        }
        process_path.write_text(json.dumps(process, indent=2) + '\n', encoding='utf-8')
        payload.update({
            'completed_utc': completed.isoformat(), 'overall_status': 'PASS',
            'compile': {
                'closure_run_id': run_id, 'source_relative_path': binding['active_ea_relative_path'], 'source_sha256': binding['active_ea_sha256'], 'source_version': binding['active_ea_version'],
                'deployed_mq5': str(deployed), 'deployed_mq5_sha256': sha256_file(deployed), 'terminal_data_root': verified.data_root, 'terminal_id': verified.terminal_id,
                'metaeditor_exe': str(meta), 'metaeditor_exe_sha256': tool['sha256'], 'metaeditor_exe_size_bytes': tool['size_bytes'], 'installation_resolution': installation['resolution'],
                'command_argv': cmd, 'process_returncode': cp.returncode, 'returncode_authority': RETURNCODE_AUTHORITY, 'compile_summary': parsed,
                'precompile_ex5_absent': precompile_absent, 'ex5_exists_after_compile': ex5.is_file(),
                'ex5_sha256': sha256_file(archived_ex5), 'ex5_size_bytes': ex5_info['size_bytes'], 'compile_log_sha256': sha256_file(archived_log),
                'fresh_ex5': {'exists': True, 'sha256': sha256_file(archived_ex5), 'size_bytes': ex5_info['size_bytes'], 'mtime_ns': archived_ex5.stat().st_mtime_ns},
                'archived_ex5': path_label(archived_ex5), 'archived_log': path_label(archived_log), 'archived_process_record': path_label(process_path), 'process_record_sha256': sha256_file(process_path),
            },
            'gates': [{'gate': 'METAEDITOR_MAX_MTF_V2_COMPILE', 'status': 'PASS', 'errors': int(parsed['errors']), 'warnings': int(parsed.get('warnings') or 0), 'ex5_sha256': sha256_file(archived_ex5)}],
        })
        _write(payload); verify_existing_evidence(EVIDENCE)
        print(json.dumps({'status': 'PASS', 'evidence': str(EVIDENCE), 'closure_run_id': run_id, 'source_tree_signature': binding['source_tree_signature'], 'ea_sha256': binding['active_ea_sha256'], 'ex5_sha256': sha256_file(archived_ex5), 'metaeditor': str(meta)}, indent=2))
        return 0
    except Exception as exc:
        payload['completed_utc'] = datetime.now(timezone.utc).isoformat(); payload['overall_status'] = 'FAIL'; payload['failure_type'] = type(exc).__name__; payload['failure_reason'] = str(exc)
        _write(payload); print(json.dumps({'status': 'FAIL', 'evidence': str(EVIDENCE), 'reason': str(exc)}, indent=2), file=sys.stderr); return 1


def main() -> int:
    from mtf.mtf1_python_env_authority import assert_current_process_if_required
    assert_current_process_if_required('owner_metaeditor_acceptance')
    ap = argparse.ArgumentParser(); ap.add_argument('--verify-existing', action='store_true'); args = ap.parse_args()
    if args.verify_existing:
        try:
            print(json.dumps(verify_existing_evidence(EVIDENCE), indent=2)); return 0
        except Exception as exc:
            print(json.dumps({'status': 'FAIL', 'evidence': str(EVIDENCE), 'reason': str(exc)}, indent=2), file=sys.stderr); return 1
    return _run_compile()


if __name__ == '__main__':
    raise SystemExit(main())
