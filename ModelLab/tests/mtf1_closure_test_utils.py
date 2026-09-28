from __future__ import annotations

import json
import tempfile
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import acceptance.runners.run_acceptance as run_acceptance
from mtf.mtf_data import build_alignment_index, build_canonical_views, build_lineage_manifest
from mtf.mtf_data_quality import audit_canonical_bundle
from mtf_test_utils import synthetic_native_frames

TEST_RUN_ID = '1' * 32


def valid_local_acceptance_payload(*, execution_mode: str = 'FRESH_FULL', closure_run_id: str = TEST_RUN_ID) -> dict[str, Any]:
    return {
        'schema': run_acceptance.ACCEPTANCE_SCHEMA,
        'project': 'Max MTF',
        'version': '2.0.1',
        'phase': run_acceptance.ACCEPTANCE_PHASE,
        'overall_status': 'PASS',
        'first_failed_gate': None,
        'gate_count': len(run_acceptance.TESTS),
        'results': [
            {'gate': gate, 'script': script, 'status': 'PASS', 'exit_code': 0, 'elapsed_seconds': 0.001}
            for gate, script in run_acceptance.TESTS
        ],
        'source_tree_signature': run_acceptance._tree_sig(),
        'suite_signature': run_acceptance._suite_sig(),
        'execution_mode': execution_mode,
        'closure_run_id': closure_run_id,
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'checkpointed_after_each_gate': True,
        'external_gates': run_acceptance._external_gates(),
    }


def write_valid_local_acceptance(path: Path, *, execution_mode: str = 'FRESH_FULL', closure_run_id: str = TEST_RUN_ID) -> dict[str, Any]:
    obj = valid_local_acceptance_payload(execution_mode=execution_mode, closure_run_id=closure_run_id)
    path.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
    return obj


def valid_owner_runtime_payload(owner, *, acceptance_path: Path, config_path: Path, registry_path: Path, artifact_dir: Path | None = None, frames=None, sealed_asof=None) -> dict[str, Any]:
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    logical_symbol = str(cfg.get('symbol') or 'XAUUSD')
    symbol = str(cfg.get('broker_symbol_override') or logical_symbol)
    frames = synthetic_native_frames() if frames is None else frames
    m5_times = pd.to_datetime(frames['M5']['time'], unit='s', utc=True)
    sealed_asof = (m5_times.max() + pd.Timedelta(minutes=5)).to_pydatetime() if sealed_asof is None else pd.Timestamp(sealed_asof).to_pydatetime()
    views, parity = build_canonical_views(frames, price_atol=1e-9, asof_utc=sealed_asof)
    alignment, alignment_meta = build_alignment_index(views)
    dq = audit_canonical_bundle(views, alignment, parity)
    align_audit = dq['alignment']
    native_rows = {tf: int(len(frames[tf])) for tf in ('M5', 'M15', 'H1', 'H4')}
    window = {
        'from_utc': m5_times.min().isoformat(),
        'to_utc': sealed_asof.isoformat(),
    }
    method = 'EXPLICIT_OVERRIDE' if cfg.get('broker_symbol_override') else 'EXACT'
    candidates = [symbol]
    terminal_path = r'C:\\Program Files\\MetaTrader 5\\terminal64.exe'
    terminal_data_path = r'C:\\Users\\pc\\AppData\\Roaming\\MetaQuotes\\Terminal\\TEST123'
    broker = {
        'symbol': symbol,
        'logical_symbol': logical_symbol,
        'resolved_broker_symbol': symbol,
        'symbol_resolution_method': method,
        'symbol_resolution_candidates': candidates,
        'broker_symbol_override': cfg.get('broker_symbol_override'),
        'server': 'TEST-SERVER',
        'terminal_path': terminal_path,
        'terminal_data_path': terminal_data_path,
        'terminal_identity': {'path': terminal_path, 'data_path': terminal_data_path, 'build': 5000, 'name': 'MetaTrader 5'},
        'broker_identity': {'server': 'TEST-SERVER', 'company': 'TEST-BROKER'},
        'start_utc': window['from_utc'],
        'end_utc': window['to_utc'],
    }
    source_identity = {
        'kind': 'DIRECT_MT5_NATIVE_RATES', 'native_rows': native_rows, 'window': window,
        'logical_symbol': logical_symbol, 'resolved_broker_symbol': symbol,
        'sealed_asof_utc': sealed_asof.isoformat(),
    }
    manifest = build_lineage_manifest(
        views,
        alignment,
        symbol=symbol,
        broker_identity=broker,
        source_identity=source_identity,
        resampling_parity=parity,
        alignment_meta=alignment_meta,
        data_quality=dq,
    )
    binding = owner._current_candidate_binding(
        acceptance_path=acceptance_path,
        config_path=config_path,
        registry_path=registry_path,
        require_fresh_full=True,
        require_closure_run_id=False,
    )
    run_id = str(binding.get('closure_run_id') or TEST_RUN_ID)
    if artifact_dir is None:
        base = owner.PKG / 'owner_acceptance/evidence/mtf1'
        base.mkdir(parents=True, exist_ok=True)
        artifact_dir = Path(tempfile.mkdtemp(prefix='test_owner_', dir=base))
        # archive helper requires destination to not exist, so use a child.
        artifact_dir = artifact_dir / 'artifacts'
    artifacts = owner.archive_native_execution_inputs(
        frames,
        broker,
        symbol=symbol,
        window=window,
        closure_run_id=run_id,
        sealed_asof_utc=sealed_asof,
        artifact_dir=artifact_dir,
    )
    return {
        'schema': owner.SCHEMA,
        'project': 'Max MTF',
        'version': '2.0.1',
        'phase': owner.PHASE,
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'overall_status': 'PASS',
        'candidate_binding': binding,
        'symbol': symbol,
        'logical_symbol': logical_symbol,
        'resolved_broker_symbol': symbol,
        'symbol_resolution_method': method,
        'symbol_resolution_candidates': candidates,
        'window': window,
        'sealed_asof_utc': sealed_asof.isoformat(),
        'broker_provenance': broker,
        'native_rows': native_rows,
        'parity': parity,
        'alignment': {'meta': alignment_meta, 'audit': align_audit},
        'data_quality': dq,
        'lineage_manifest_preview': manifest,
        'bundle_identity_preview_sha256': manifest['bundle_identity_sha256'],
        'execution_artifacts': artifacts,
        'immutable_live_revalidation': owner._compare_immutable_native_revalidation(frames, frames, sealed_asof_utc=sealed_asof),
        'gates': [
            {
                'gate': 'OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION',
                'status': 'PASS',
                'verified': True,
                'terminal_id': 'TEST123',
                'terminal_data_root': broker['terminal_data_path'],
                'broker_terminal_data_path': broker['terminal_data_path'],
            },
            {
                'gate': 'OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY',
                'status': 'PASS',
                'parity_status': 'PASS',
                'alignment_status': 'PASS',
                'data_quality_status': 'PASS',
                'native_rows': native_rows,
            },
        ],
    }


def build_valid_metaeditor_fixture(meta, *, acceptance_path: Path, config_path: Path, registry_path: Path, sandbox: Path, artifact_dir: Path) -> dict[str, Any]:
    import os
    import shutil
    from datetime import timedelta

    sandbox = Path(sandbox)
    artifact_dir = Path(artifact_dir)
    tool_dir = sandbox / 'tool'; tool_dir.mkdir(parents=True, exist_ok=True)
    meta_exe = tool_dir / 'MetaEditor64.exe'
    # Test-only PE-like binary; production verifier uses stronger minimum size.
    meta_exe.write_bytes(b'MZ' + bytes(range(256)) * 20)
    data_root = sandbox / 'TEST123'; (data_root / 'MQL5').mkdir(parents=True, exist_ok=True)
    expert_dir = data_root / 'MQL5' / 'Experts' / 'MaxMTF'; expert_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({
        'terminal_exe': None,
        'metaeditor_exe': str(meta_exe),
        'mt5_data_root': str(data_root),
        'timeout_seconds': 180,
    }, indent=2) + '\n', encoding='utf-8')

    binding = meta.current_base_candidate_binding(
        acceptance_path=acceptance_path,
        registry_path=registry_path,
        require_fresh_full=True,
        require_closure_run_id=False,
    )
    deployed = expert_dir / 'Max_MTF.mq5'
    shutil.copy2(meta.PKG / binding['active_ea_relative_path'], deployed)
    artifact_dir.mkdir(parents=True, exist_ok=False)
    output_ex5 = deployed.with_suffix('.ex5')
    ex5 = artifact_dir / 'Max_MTF.ex5'
    # Binary-like deterministic compile output plus immutable archived copy.
    output_ex5.write_bytes((b'\x00\x9fEX5R6' + bytes(range(256))) * 16)
    log = artifact_dir / 'metaeditor_compile.log'
    log_text = f'{deployed.name} : info\nResult: 0 errors, 0 warnings\n'
    log.write_text(log_text, encoding='utf-8')
    started = datetime.now(timezone.utc) - timedelta(seconds=1)
    completed = datetime.now(timezone.utc) + timedelta(seconds=1)
    mid_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
    os.utime(output_ex5, ns=(mid_ns, mid_ns))
    shutil.copy2(output_ex5, ex5)
    cmd = [str(meta_exe.resolve()), f'/compile:{deployed}', '/log']
    process = {
        'schema': meta.PROCESS_SCHEMA,
        'closure_run_id': str(binding.get('closure_run_id') or TEST_RUN_ID),
        'started_utc': started.isoformat(),
        'completed_utc': completed.isoformat(),
        'metaeditor_exe': str(meta_exe.resolve()),
        'metaeditor_exe_sha256': meta.sha256_file(meta_exe),
        'metaeditor_exe_size_bytes': meta_exe.stat().st_size,
        'source_path': str((meta.PKG / binding['active_ea_relative_path']).resolve()),
        'source_sha256': binding['active_ea_sha256'],
        'deployed_mq5': str(deployed),
        'deployed_mq5_sha256': meta.sha256_file(deployed),
        'output_ex5': str(output_ex5),
        'output_ex5_sha256': meta.sha256_file(ex5),
        'command_argv': cmd,
        'process_returncode': 0,
        'returncode_authority': meta.RETURNCODE_AUTHORITY,
        'compile_summary': meta._compile_summary(log_text),
        'precompile_ex5_absent': True,
        'postcompile_ex5_exists': True,
        'postcompile_ex5_mtime_ns': ex5.stat().st_mtime_ns,
        'compile_log_mtime_ns': log.stat().st_mtime_ns,
        'archived_log_sha256': meta.sha256_file(log),
        'archived_ex5_sha256': meta.sha256_file(ex5),
    }
    proc = artifact_dir / 'compile_process.json'
    proc.write_text(json.dumps(process, indent=2) + '\n', encoding='utf-8')
    parsed = meta._compile_summary(log_text)
    return {
        'schema': meta.SCHEMA,
        'project': 'Max MTF',
        'version': '2.0.1',
        'phase': meta.PHASE,
        'started_utc': started.isoformat(),
        'completed_utc': completed.isoformat(),
        'overall_status': 'PASS',
        'candidate_binding': binding,
        'metaeditor_config_sha256': meta.sha256_file(config_path),
        'compile': {
            'closure_run_id': str(binding.get('closure_run_id') or TEST_RUN_ID),
            'source_relative_path': binding['active_ea_relative_path'],
            'source_sha256': binding['active_ea_sha256'],
            'source_version': binding['active_ea_version'],
            'deployed_mq5': str(deployed),
            'deployed_mq5_sha256': meta.sha256_file(deployed),
            'terminal_data_root': str(data_root),
            'terminal_id': data_root.name,
            'metaeditor_exe': str(meta_exe.resolve()),
            'metaeditor_exe_sha256': meta.sha256_file(meta_exe),
            'metaeditor_exe_size_bytes': meta_exe.stat().st_size,
            'installation_resolution': 'EXPLICIT_CONFIG',
            'command_argv': cmd,
            'process_returncode': 0,
            'returncode_authority': meta.RETURNCODE_AUTHORITY,
            'compile_summary': parsed,
            'precompile_ex5_absent': True,
            'ex5_exists_after_compile': True,
            'ex5_sha256': meta.sha256_file(ex5),
            'ex5_size_bytes': ex5.stat().st_size,
            'compile_log_sha256': meta.sha256_file(log),
            'fresh_ex5': {'exists': True, 'sha256': meta.sha256_file(ex5), 'size_bytes': ex5.stat().st_size, 'mtime_ns': ex5.stat().st_mtime_ns},
            'archived_ex5': meta.path_label(ex5),
            'archived_log': meta.path_label(log),
            'archived_process_record': meta.path_label(proc),
            'process_record_sha256': meta.sha256_file(proc),
        },
        'gates': [{
            'gate': 'METAEDITOR_MAX_MTF_V2_COMPILE',
            'status': 'PASS',
            'errors': 0,
            'warnings': 0,
            'ex5_sha256': meta.sha256_file(ex5),
        }],
    }
