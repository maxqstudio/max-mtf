from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from host.mt5_installation import validate_mt5_data_root
from mtf.mtf_data import (
    _serialize_for_csv,
    _stable_json_hash,
    build_alignment_index,
    build_canonical_views,
    build_lineage_manifest,
    collect_native_frames_from_mt5,
    normalize_native_frame,
)
from mtf.mtf_data_quality import audit_canonical_bundle
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

ROOT = MODELLAB_ROOT
PKG = ROOT.parent
CONFIG = PKG / 'owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json'
EVIDENCE = PKG / 'owner_acceptance/evidence/mtf1/OWNER_MTF1_RUNTIME_ACCEPTANCE.json'
ARTIFACT_ROOT = PKG / 'owner_acceptance/evidence/mtf1/owner_runtime'
SCHEMA = 'MAX_MTF1_OWNER_RUNTIME_ACCEPTANCE_V5_BROKER_SYMBOL_RESOLUTION'
BINDING_SCHEMA = 'MAX_MTF1_OWNER_RUNTIME_BINDING_V3'
PHASE = 'MTF_1_OWNER_RUNTIME_EXECUTION_PROOF'
PROVENANCE_SCHEMA = 'MAX_MTF1_OWNER_NATIVE_INPUT_PROVENANCE_V1'
REQUIRED_RUNTIME_GATES = (
    'OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION',
    'OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY',
)
NATIVE_TFS = ('M5', 'M15', 'H1', 'H4')
TF_MINUTES = {'M5': 5, 'M15': 15, 'H1': 60, 'H4': 240}
IMMUTABLE_NATIVE_FIELDS = ('open_time_utc', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume', 'timeframe')

OwnerMTF1AcceptanceError = MTF1ClosureError


def _test_mode() -> bool:
    return os.environ.get('MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE') == '1'


def _read_config(path: Path = CONFIG) -> dict[str, Any]:
    raw = read_json(path)
    symbol = str(raw.get('symbol') or '').strip()
    if not symbol:
        raise OwnerMTF1AcceptanceError('OWNER_MTF1_CONFIG_SYMBOL_REQUIRED: set symbol in ' + str(path))
    days = int(raw.get('lookback_days') or 30)
    if days < 7:
        raise OwnerMTF1AcceptanceError('OWNER_MTF1_CONFIG_LOOKBACK_TOO_SHORT: minimum 7 days')
    terminal_exe = raw.get('terminal_exe')
    broker_symbol_override = str(raw.get('broker_symbol_override') or '').strip() or None
    return {
        'symbol': symbol,
        'logical_symbol': symbol,
        'broker_symbol_override': broker_symbol_override,
        'lookback_days': days,
        'terminal_exe': terminal_exe,
    }


def _current_candidate_binding(
    *,
    acceptance_path: Path = LOCAL_ACCEPTANCE,
    config_path: Path = CONFIG,
    registry_path: Path = EXTERNAL_REGISTRY,
    require_fresh_full: bool = True,
    require_closure_run_id: bool = True,
) -> dict[str, Any]:
    base = current_base_candidate_binding(
        acceptance_path=acceptance_path,
        registry_path=registry_path,
        require_fresh_full=require_fresh_full,
        require_closure_run_id=require_closure_run_id,
    )
    if require_closure_run_id and not base.get('closure_run_id'):
        raise OwnerMTF1AcceptanceError('OWNER_CLOSURE_RUN_ID_REQUIRED')
    return {
        **base,
        'schema': BINDING_SCHEMA,
        'base_binding_schema': base['schema'],
        'owner_config_sha256': sha256_file(config_path),
        'owner_config': path_label(config_path),
    }


def _assert_binding_equal(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    if actual.get('schema') != BINDING_SCHEMA:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BINDING_SCHEMA_MISMATCH')
    actual_base = dict(actual)
    expected_base = dict(expected)
    actual_base['schema'] = actual.get('base_binding_schema')
    expected_base['schema'] = expected.get('base_binding_schema')
    assert_base_binding_equal(actual_base, expected_base)
    if actual.get('owner_config_sha256') != expected.get('owner_config_sha256'):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BINDING_MISMATCH: owner_config_sha256')


def _parse_aware_utc(value: Any, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception as exc:
        raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_INVALID_UTC: {field}') from exc
    if dt.tzinfo is None:
        raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_NAIVE_UTC: {field}')
    return dt.astimezone(timezone.utc)


def _norm_path_text(value: Any) -> str:
    return str(value or '').strip().replace('\\', '/').rstrip('/').lower()


def _artifact_from_project_relative(value: Any) -> Path:
    raw = str(value or '').strip()
    if not raw:
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_ARTIFACT_PATH_MISSING')
    p = Path(raw)
    if p.is_absolute():
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_ARTIFACT_PATH_NOT_PORTABLE')
    resolved = (PKG / p).resolve()
    try:
        resolved.relative_to(PKG.resolve())
    except Exception as exc:
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_ARTIFACT_PATH_ESCAPES_PROJECT') from exc
    return resolved


def _raw_frame_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator='\n', float_format='%.17g').encode('utf-8')


def _normalized_native_hash(frame: pd.DataFrame, tf: str) -> str:
    norm = normalize_native_frame(frame, tf)
    serial = _serialize_for_csv(norm)
    return hashlib.sha256(serial.to_csv(index=False, lineterminator='\n', float_format='%.17g').encode('utf-8')).hexdigest()


def _hash_normalized_immutable_rows(norm: pd.DataFrame) -> str:
    keep = [c for c in IMMUTABLE_NATIVE_FIELDS if c in norm.columns]
    serial = _serialize_for_csv(norm.loc[:, keep].reset_index(drop=True))
    return hashlib.sha256(serial.to_csv(index=False, lineterminator='\n', float_format='%.17g').encode('utf-8')).hexdigest()


def _immutable_native_revalidation_view(frame: pd.DataFrame, tf: str, sealed_asof_utc: datetime) -> dict[str, Any]:
    tf = str(tf).upper()
    if tf not in TF_MINUTES:
        raise OwnerMTF1AcceptanceError(f'OWNER_IMMUTABLE_REVALIDATION_UNSUPPORTED_TF: {tf}')
    seal = pd.Timestamp(sealed_asof_utc)
    if seal.tzinfo is None:
        raise OwnerMTF1AcceptanceError('OWNER_IMMUTABLE_REVALIDATION_NAIVE_SEAL')
    seal = seal.tz_convert('UTC')
    norm = normalize_native_frame(frame, tf)
    opens = pd.to_datetime(norm['open_time_utc'], utc=True)
    if bool((opens > seal).any()):
        raise OwnerMTF1AcceptanceError(f'OWNER_IMMUTABLE_REVALIDATION_ROW_AFTER_SEAL: {tf}')
    duration = pd.Timedelta(minutes=TF_MINUTES[tf])
    closes = opens + duration
    closed_mask = closes <= seal
    mutable_mask = ~closed_mask
    closed = norm.loc[closed_mask].reset_index(drop=True)
    mutable = norm.loc[mutable_mask].reset_index(drop=True)
    if closed.empty:
        raise OwnerMTF1AcceptanceError(f'OWNER_IMMUTABLE_REVALIDATION_NO_CLOSED_ROWS: {tf}')
    # With a fixed-timeframe feed and a collection window ending at the seal,
    # there can be at most one row that was still forming at that seal.  More
    # than one means the tail cannot be explained by legitimate candle evolution.
    if len(mutable) > 1:
        raise OwnerMTF1AcceptanceError(f'OWNER_IMMUTABLE_REVALIDATION_MULTIPLE_MUTABLE_ROWS: {tf}')
    mutable_opens = [pd.Timestamp(x).isoformat() for x in pd.to_datetime(mutable.get('open_time_utc', pd.Series(dtype='datetime64[ns, UTC]')), utc=True)]
    first_closed = pd.Timestamp(closed['open_time_utc'].iloc[0])
    last_closed = pd.Timestamp(closed['open_time_utc'].iloc[-1])
    required_boundary = mutable_opens[0] if tf in {'M15', 'H1', 'H4'} and mutable_opens else None
    return {
        'raw_archived_rows': int(len(norm)),
        'immutable_closed_rows': int(len(closed)),
        'immutable_closed_sha256': _hash_normalized_immutable_rows(closed),
        'first_closed_open_utc': first_closed.isoformat(),
        'last_closed_open_utc': last_closed.isoformat(),
        'last_closed_close_utc': (last_closed + duration).isoformat(),
        'mutable_tail_rows': int(len(mutable)),
        'mutable_tail_open_times_utc': mutable_opens,
        'required_boundary_open_utc': required_boundary,
    }


def _compare_immutable_native_revalidation(
    archived_native: Mapping[str, pd.DataFrame],
    live_native: Mapping[str, pd.DataFrame],
    *,
    sealed_asof_utc: datetime,
) -> dict[str, Any]:
    by_tf: dict[str, Any] = {}
    for tf in NATIVE_TFS:
        if tf not in archived_native or tf not in live_native:
            raise OwnerMTF1AcceptanceError(f'OWNER_LIVE_REVALIDATION_NATIVE_TF_MISSING: {tf}')
        archived = _immutable_native_revalidation_view(archived_native[tf], tf, sealed_asof_utc)
        live = _immutable_native_revalidation_view(live_native[tf], tf, sealed_asof_utc)
        if archived['immutable_closed_rows'] != live['immutable_closed_rows']:
            raise OwnerMTF1AcceptanceError(f'OWNER_LIVE_REVALIDATION_IMMUTABLE_ROW_COUNT_MISMATCH: {tf}')
        if archived['immutable_closed_sha256'] != live['immutable_closed_sha256']:
            raise OwnerMTF1AcceptanceError(f'OWNER_LIVE_REVALIDATION_IMMUTABLE_INPUT_MISMATCH: {tf}')
        for key in ('first_closed_open_utc', 'last_closed_open_utc', 'last_closed_close_utc'):
            if archived[key] != live[key]:
                raise OwnerMTF1AcceptanceError(f'OWNER_LIVE_REVALIDATION_IMMUTABLE_BOUNDARY_MISMATCH: {tf}:{key}')
        # Mutable values may evolve after the seal, but the row identity may not.
        # This prevents arbitrary rows from being silently ignored as "tail".
        if archived['mutable_tail_open_times_utc'] != live['mutable_tail_open_times_utc']:
            raise OwnerMTF1AcceptanceError(f'OWNER_LIVE_REVALIDATION_MUTABLE_TAIL_IDENTITY_MISMATCH: {tf}')
        if archived['required_boundary_open_utc'] != live['required_boundary_open_utc']:
            raise OwnerMTF1AcceptanceError(f'OWNER_LIVE_REVALIDATION_REQUIRED_BOUNDARY_MISMATCH: {tf}')
        by_tf[tf] = {
            **archived,
            'live_immutable_sha256': live['immutable_closed_sha256'],
            'live_raw_rows': int(live['raw_archived_rows']),
            'live_mutable_tail_rows': int(live['mutable_tail_rows']),
            'immutable_revalidation_status': 'PASS',
            'mutable_tail_exclusion_reason': 'BAR_NOT_CLOSED_AT_SEALED_ASOF_UTC',
        }
    return {
        'schema': 'MAX_MTF1_IMMUTABLE_NATIVE_REVALIDATION_V1',
        'sealed_asof_utc': pd.Timestamp(sealed_asof_utc).tz_convert('UTC').isoformat(),
        'authority': 'CLOSED_NATIVE_ROWS_EXACT; MUTABLE_TAIL_VALUES_EXCLUDED_ONLY_IF_OPEN_AT_ORIGINAL_SEAL; TAIL_OPEN_TIME_IDENTITY_EXACT',
        'timeframes': by_tf,
        'status': 'PASS',
    }


def archive_native_execution_inputs(
    native: Mapping[str, pd.DataFrame],
    broker: Mapping[str, Any],
    *,
    symbol: str,
    window: Mapping[str, Any],
    closure_run_id: str,
    sealed_asof_utc: datetime | None = None,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    if not closure_run_id:
        raise OwnerMTF1AcceptanceError('OWNER_ARCHIVE_CLOSURE_RUN_ID_REQUIRED')
    seal = sealed_asof_utc or _parse_aware_utc(window.get('to_utc'), 'window.to_utc')
    seal = _parse_aware_utc(seal.isoformat() if isinstance(seal, datetime) else seal, 'sealed_asof_utc')
    target = Path(artifact_dir) if artifact_dir is not None else ARTIFACT_ROOT / closure_run_id
    if target.exists():
        raise OwnerMTF1AcceptanceError(f'OWNER_EXECUTION_ARTIFACT_DIR_ALREADY_EXISTS: {target}')
    target.mkdir(parents=True, exist_ok=False)
    descriptors: dict[str, Any] = {}
    for tf in NATIVE_TFS:
        frame = native.get(tf)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise OwnerMTF1AcceptanceError(f'OWNER_NATIVE_FRAME_EMPTY: {tf}')
        path = target / f'native_{tf}.csv'
        path.write_bytes(_raw_frame_csv_bytes(frame))
        archived_frame = pd.read_csv(path, float_precision='round_trip')
        descriptors[tf] = {
            'path': path_label(path),
            'sha256': sha256_file(path),
            'rows': int(len(archived_frame)),
            'columns': [str(x) for x in archived_frame.columns],
            'normalized_sha256': _normalized_native_hash(archived_frame, tf),
        }
    provenance = {
        'schema': PROVENANCE_SCHEMA,
        'project': 'Max MTF',
        'version': '2.0.1',
        'phase': PHASE,
        'closure_run_id': closure_run_id,
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'symbol': str(symbol),
        'logical_symbol': str(broker.get('logical_symbol') or symbol),
        'resolved_broker_symbol': str(broker.get('resolved_broker_symbol') or symbol),
        'symbol_resolution_method': str(broker.get('symbol_resolution_method') or 'EXACT'),
        'symbol_resolution_candidates': list(broker.get('symbol_resolution_candidates') or [symbol]),
        'window': dict(window),
        'sealed_asof_utc': seal.isoformat(),
        'broker_provenance': dict(broker),
        'native_artifacts': descriptors,
        'collector_authority': 'MetaTrader5.copy_rates_range via collect_native_frames_from_mt5',
    }
    prov_path = target / 'mt5_runtime_provenance.json'
    prov_path.write_text(json.dumps(provenance, indent=2, default=str) + '\n', encoding='utf-8')
    proof_core = {
        'closure_run_id': closure_run_id,
        'native_artifacts': descriptors,
        'provenance_path': path_label(prov_path),
        'provenance_sha256': sha256_file(prov_path),
    }
    return {
        **proof_core,
        'artifact_set_sha256': _stable_json_hash(proof_core),
    }


def _load_archived_native_inputs(payload: Mapping[str, Any]) -> tuple[dict[str, pd.DataFrame], dict[str, Any], Mapping[str, Any]]:
    proof = payload.get('execution_artifacts')
    if not isinstance(proof, Mapping):
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_ARTIFACT_PROOF_MISSING')
    run_id = str((payload.get('candidate_binding') or {}).get('closure_run_id') or '')
    if not run_id or str(proof.get('closure_run_id') or '') != run_id:
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_ARTIFACT_RUN_ID_MISMATCH')
    descriptors = proof.get('native_artifacts')
    if not isinstance(descriptors, Mapping) or set(descriptors) != set(NATIVE_TFS):
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_NATIVE_ARTIFACT_SET_INVALID')
    native: dict[str, pd.DataFrame] = {}
    canonical_desc: dict[str, Any] = {}
    for tf in NATIVE_TFS:
        desc = descriptors.get(tf)
        if not isinstance(desc, Mapping):
            raise OwnerMTF1AcceptanceError(f'OWNER_EXECUTION_NATIVE_ARTIFACT_INVALID: {tf}')
        path = _artifact_from_project_relative(desc.get('path'))
        if sha256_file(path) != str(desc.get('sha256') or '').lower():
            raise OwnerMTF1AcceptanceError(f'OWNER_EXECUTION_NATIVE_ARTIFACT_SHA_MISMATCH: {tf}')
        frame = pd.read_csv(path, float_precision='round_trip')
        if int(desc.get('rows') or -1) != len(frame) or list(desc.get('columns') or []) != [str(x) for x in frame.columns]:
            raise OwnerMTF1AcceptanceError(f'OWNER_EXECUTION_NATIVE_ARTIFACT_SHAPE_MISMATCH: {tf}')
        normalized_hash = _normalized_native_hash(frame, tf)
        if normalized_hash != str(desc.get('normalized_sha256') or '').lower():
            raise OwnerMTF1AcceptanceError(f'OWNER_EXECUTION_NATIVE_NORMALIZED_HASH_MISMATCH: {tf}')
        native[tf] = frame
        canonical_desc[tf] = dict(desc)
    prov_path = _artifact_from_project_relative(proof.get('provenance_path'))
    if sha256_file(prov_path) != str(proof.get('provenance_sha256') or '').lower():
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_PROVENANCE_SHA_MISMATCH')
    provenance = read_json(prov_path)
    if provenance.get('schema') != PROVENANCE_SCHEMA or provenance.get('closure_run_id') != run_id:
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_PROVENANCE_IDENTITY_MISMATCH')
    if provenance.get('native_artifacts') != canonical_desc:
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_PROVENANCE_ARTIFACT_SET_MISMATCH')
    core = {
        'closure_run_id': run_id,
        'native_artifacts': canonical_desc,
        'provenance_path': path_label(prov_path),
        'provenance_sha256': sha256_file(prov_path),
    }
    if _stable_json_hash(core) != str(proof.get('artifact_set_sha256') or ''):
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_ARTIFACT_SET_HASH_MISMATCH')
    return native, provenance, proof


def _recompute_from_archived_inputs(payload: Mapping[str, Any]) -> dict[str, Any]:
    native, provenance, _ = _load_archived_native_inputs(payload)
    symbol = str(payload.get('symbol') or '')
    window = payload.get('window') if isinstance(payload.get('window'), Mapping) else {}
    broker = payload.get('broker_provenance') if isinstance(payload.get('broker_provenance'), Mapping) else {}
    expected_resolution = {
        'logical_symbol': str(payload.get('logical_symbol') or ''),
        'resolved_broker_symbol': str(payload.get('resolved_broker_symbol') or ''),
        'symbol_resolution_method': str(payload.get('symbol_resolution_method') or ''),
        'symbol_resolution_candidates': list(payload.get('symbol_resolution_candidates') or []),
    }
    if (
        provenance.get('symbol') != symbol
        or provenance.get('window') != dict(window)
        or provenance.get('sealed_asof_utc') != str(payload.get('sealed_asof_utc') or '')
        or provenance.get('broker_provenance') != dict(broker)
        or any(provenance.get(k) != v for k, v in expected_resolution.items())
    ):
        raise OwnerMTF1AcceptanceError('OWNER_EXECUTION_PROVENANCE_SUMMARY_MISMATCH')
    sealed_asof = _parse_aware_utc(payload.get('sealed_asof_utc'), 'sealed_asof_utc')
    views, parity = build_canonical_views(native, asof_utc=sealed_asof)
    alignment, alignment_meta = build_alignment_index(views)
    dq = audit_canonical_bundle(views, alignment, parity)
    native_rows = {tf: int(len(native[tf])) for tf in NATIVE_TFS}
    source_identity = {
        'kind': 'DIRECT_MT5_NATIVE_RATES',
        'native_rows': native_rows,
        'window': dict(window),
        'logical_symbol': str(payload.get('logical_symbol') or ''),
        'resolved_broker_symbol': str(payload.get('resolved_broker_symbol') or ''),
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
    return {
        'native_rows': native_rows,
        'parity': parity,
        'alignment': {'meta': alignment_meta, 'audit': dq.get('alignment') or {}},
        'data_quality': dq,
        'lineage_manifest_preview': manifest,
        'bundle_identity_preview_sha256': manifest['bundle_identity_sha256'],
        'native': native,
    }


def _validate_owner_runtime_proof(payload: Mapping[str, Any]) -> None:
    symbol = str(payload.get('symbol') or '').strip()
    if not symbol:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_SYMBOL_MISSING')
    logical_symbol = str(payload.get('logical_symbol') or '').strip()
    resolved_symbol = str(payload.get('resolved_broker_symbol') or '').strip()
    method = str(payload.get('symbol_resolution_method') or '').strip()
    candidates = payload.get('symbol_resolution_candidates')
    if not logical_symbol:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_LOGICAL_SYMBOL_MISSING')
    if not resolved_symbol or resolved_symbol != symbol:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_RESOLVED_SYMBOL_MISMATCH')
    if method not in {'EXACT', 'UNIQUE_SUFFIX_OR_PREFIX', 'EXPLICIT_OVERRIDE'}:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_SYMBOL_RESOLUTION_METHOD_INVALID')
    if not isinstance(candidates, list) or not candidates or resolved_symbol not in [str(x) for x in candidates]:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_SYMBOL_RESOLUTION_CANDIDATES_INVALID')
    window = payload.get('window')
    if not isinstance(window, Mapping):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_WINDOW_MISSING')
    start = _parse_aware_utc(window.get('from_utc'), 'window.from_utc')
    end = _parse_aware_utc(window.get('to_utc'), 'window.to_utc')
    if end <= start:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_WINDOW_INVALID')
    sealed_asof = _parse_aware_utc(payload.get('sealed_asof_utc'), 'sealed_asof_utc')
    if sealed_asof != end:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_SEALED_ASOF_WINDOW_MISMATCH')
    broker = payload.get('broker_provenance')
    if not isinstance(broker, Mapping):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BROKER_PROVENANCE_MISSING')
    if str(broker.get('symbol') or '').strip() != symbol:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BROKER_SYMBOL_MISMATCH')
    if str(broker.get('logical_symbol') or '').strip() != logical_symbol:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BROKER_LOGICAL_SYMBOL_MISMATCH')
    if str(broker.get('resolved_broker_symbol') or '').strip() != resolved_symbol:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BROKER_RESOLVED_SYMBOL_MISMATCH')
    if str(broker.get('symbol_resolution_method') or '').strip() != method:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BROKER_RESOLUTION_METHOD_MISMATCH')
    if list(broker.get('symbol_resolution_candidates') or []) != list(candidates):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BROKER_RESOLUTION_CANDIDATES_MISMATCH')
    if not isinstance(broker.get('terminal_identity'), Mapping) or not isinstance(broker.get('broker_identity'), Mapping):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_TERMINAL_BROKER_IDENTITY_MISSING')
    for key in ('server', 'terminal_path', 'terminal_data_path', 'start_utc', 'end_utc'):
        if not str(broker.get(key) or '').strip():
            raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_BROKER_FIELD_MISSING: {key}')
    if _parse_aware_utc(broker.get('start_utc'), 'broker.start_utc') != start or _parse_aware_utc(broker.get('end_utc'), 'broker.end_utc') != end:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BROKER_WINDOW_MISMATCH')
    rows = payload.get('native_rows')
    if not isinstance(rows, Mapping) or set(rows) != set(NATIVE_TFS):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_NATIVE_ROWS_INVALID')
    for tf in NATIVE_TFS:
        if int(rows.get(tf) or 0) <= 0:
            raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_NATIVE_ROWS_NONPOSITIVE: {tf}')
    parity = payload.get('parity')
    if not isinstance(parity, Mapping) or str(parity.get('status') or '').upper() != 'PASS' or parity.get('source_authority') != 'M5':
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_PARITY_NOT_PASS')
    tf_parity = parity.get('parity')
    if not isinstance(tf_parity, Mapping):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_PARITY_DETAIL_MISSING')
    for tf in ('M15', 'H1', 'H4'):
        row = tf_parity.get(tf)
        if not isinstance(row, Mapping) or str(row.get('status') or '').upper() != 'PASS':
            raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_PARITY_TF_NOT_PASS: {tf}')
        if int(row.get('compared_closed_bars') or 0) <= 0 or row.get('failed_bars') is None or int(row['failed_bars']) != 0:
            raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_PARITY_TF_COUNTS_INVALID: {tf}')
        if str(row.get('real_volume_mode') or '') not in {'EXACT_PARITY_REQUIRED', 'UNAVAILABLE_ZERO_ONLY'}:
            raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_REAL_VOLUME_MODE_INVALID: {tf}')
        if row.get('real_volume_failed_bars') is None or int(row['real_volume_failed_bars']) != 0:
            raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_REAL_VOLUME_NOT_EXACT: {tf}')
    alignment = payload.get('alignment')
    if not isinstance(alignment, Mapping):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_ALIGNMENT_MISSING')
    align_meta = alignment.get('meta'); align_audit = alignment.get('audit')
    if not isinstance(align_meta, Mapping) or str(align_meta.get('status') or '').upper() != 'PASS' or int(align_meta.get('ready_rows') or 0) <= 0:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_ALIGNMENT_META_NOT_PASS')
    if not isinstance(align_audit, Mapping) or str(align_audit.get('status') or '').upper() != 'PASS':
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_ALIGNMENT_AUDIT_NOT_PASS')
    violations = align_audit.get('future_close_violations')
    if not isinstance(violations, Mapping) or set(violations) != {'h4', 'h1', 'm15', 'm5'}:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_ALIGNMENT_VIOLATIONS_INVALID')
    if any(int(violations[k]) != 0 for k in ('h4', 'h1', 'm15', 'm5')) or int(align_audit.get('primary_close_mismatch') or 0) != 0:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_ALIGNMENT_VIOLATION_PRESENT')
    dq = payload.get('data_quality')
    if not isinstance(dq, Mapping) or str(dq.get('status') or '').upper() != 'PASS':
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_DATA_QUALITY_NOT_PASS')
    if dq.get('closed_bar_only') is not True or dq.get('no_forward_fill') is not True or str(dq.get('resampling_parity_status') or '').upper() != 'PASS':
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_DATA_QUALITY_CAUSAL_FLAGS_INVALID')
    if dq.get('alignment') != align_audit:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_DQ_ALIGNMENT_MISMATCH')
    frames = dq.get('frames')
    if not isinstance(frames, Mapping) or set(frames) != set(NATIVE_TFS):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_DQ_FRAMES_INVALID')
    for tf in NATIVE_TFS:
        if not isinstance(frames[tf], Mapping) or str(frames[tf].get('status') or '').upper() != 'PASS':
            raise OwnerMTF1AcceptanceError(f'OWNER_EVIDENCE_DQ_FRAME_NOT_PASS: {tf}')
    manifest = payload.get('lineage_manifest_preview')
    identity = str(payload.get('bundle_identity_preview_sha256') or '').lower()
    if not isinstance(manifest, Mapping) or not is_sha256(identity):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BUNDLE_IDENTITY_MISSING')
    if str(manifest.get('bundle_identity_sha256') or '').lower() != identity:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BUNDLE_IDENTITY_FIELD_MISMATCH')
    core = dict(manifest); core.pop('bundle_identity_sha256', None)
    if _stable_json_hash(core) != identity:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_BUNDLE_IDENTITY_INVALID')
    if manifest.get('symbol') != symbol or manifest.get('broker_identity') != dict(broker):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_LINEAGE_PROVENANCE_MISMATCH')
    source_identity = manifest.get('source_identity')
    if not isinstance(source_identity, Mapping) or source_identity.get('kind') != 'DIRECT_MT5_NATIVE_RATES':
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_LINEAGE_SOURCE_KIND_INVALID')
    if source_identity.get('native_rows') != dict(rows) or source_identity.get('window') != dict(window) or source_identity.get('sealed_asof_utc') != sealed_asof.isoformat():
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_LINEAGE_SOURCE_IDENTITY_MISMATCH')
    if manifest.get('resampling_parity') != dict(parity) or manifest.get('alignment_meta') != dict(align_meta) or manifest.get('data_quality') != dict(dq):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_LINEAGE_PROOF_MISMATCH')
    gates = payload.get('gates')
    if not isinstance(gates, list) or len(gates) != len(REQUIRED_RUNTIME_GATES):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_RUNTIME_GATE_SET_INVALID')
    gate_map: dict[str, Mapping[str, Any]] = {}
    for row in gates:
        if not isinstance(row, Mapping) or not row.get('gate') or str(row['gate']) in gate_map:
            raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_RUNTIME_GATE_ROW_INVALID')
        gate_map[str(row['gate'])] = row
    if set(gate_map) != set(REQUIRED_RUNTIME_GATES):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_RUNTIME_GATE_SET_INVALID')
    root_gate = gate_map['OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION']
    if str(root_gate.get('status') or '').upper() != 'PASS' or root_gate.get('verified') is not True or not str(root_gate.get('terminal_id') or '').strip():
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_TERMINAL_ROOT_GATE_NOT_PASS')
    if _norm_path_text(root_gate.get('terminal_data_root')) != _norm_path_text(broker.get('terminal_data_path')):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_TERMINAL_ROOT_PROVENANCE_MISMATCH')
    parity_gate = gate_map['OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY']
    if str(parity_gate.get('status') or '').upper() != 'PASS' or str(parity_gate.get('parity_status') or '').upper() != 'PASS' or str(parity_gate.get('alignment_status') or '').upper() != 'PASS' or str(parity_gate.get('data_quality_status') or '').upper() != 'PASS':
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_PARITY_GATE_PROOF_INVALID')


def _assert_recomputed_summary(payload: Mapping[str, Any], recomputed: Mapping[str, Any]) -> None:
    for key in ('native_rows', 'parity', 'alignment', 'data_quality', 'lineage_manifest_preview', 'bundle_identity_preview_sha256'):
        if payload.get(key) != recomputed.get(key):
            raise OwnerMTF1AcceptanceError(f'OWNER_ARCHIVED_REPLAY_MISMATCH: {key}')


def _live_revalidate(
    payload: Mapping[str, Any],
    archived_native: Mapping[str, pd.DataFrame],
    *,
    config_path: Path,
    live_probe: Callable[..., tuple[dict[str, pd.DataFrame], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    cfg = _read_config(config_path)
    logical_symbol = str(payload.get('logical_symbol') or '')
    resolved_symbol = str(payload.get('resolved_broker_symbol') or '')
    if cfg['logical_symbol'] != logical_symbol:
        raise OwnerMTF1AcceptanceError('OWNER_LIVE_REVALIDATION_CONFIG_LOGICAL_SYMBOL_MISMATCH')
    window = payload.get('window') or {}
    start = _parse_aware_utc(window.get('from_utc'), 'window.from_utc')
    end = _parse_aware_utc(window.get('to_utc'), 'window.to_utc')
    sealed_asof = _parse_aware_utc(payload.get('sealed_asof_utc'), 'sealed_asof_utc')
    if sealed_asof != end:
        raise OwnerMTF1AcceptanceError('OWNER_LIVE_REVALIDATION_SEAL_WINDOW_MISMATCH')
    collector = live_probe or collect_native_frames_from_mt5
    live, live_broker = collector(
        symbol=logical_symbol,
        start_utc=start,
        end_utc=end,
        terminal_exe=cfg.get('terminal_exe') or None,
        broker_symbol_override=cfg.get('broker_symbol_override'),
    )
    if str(live_broker.get('resolved_broker_symbol') or '') != resolved_symbol:
        raise OwnerMTF1AcceptanceError('OWNER_LIVE_REVALIDATION_RESOLVED_SYMBOL_MISMATCH')
    archived_broker = payload.get('broker_provenance') or {}
    for key in ('symbol', 'logical_symbol', 'resolved_broker_symbol', 'symbol_resolution_method', 'server', 'start_utc', 'end_utc'):
        if str(live_broker.get(key) or '') != str(archived_broker.get(key) or ''):
            raise OwnerMTF1AcceptanceError(f'OWNER_LIVE_REVALIDATION_BROKER_MISMATCH: {key}')
    for key in ('terminal_path', 'terminal_data_path'):
        if _norm_path_text(live_broker.get(key)) != _norm_path_text(archived_broker.get(key)):
            raise OwnerMTF1AcceptanceError(f'OWNER_LIVE_REVALIDATION_BROKER_MISMATCH: {key}')
    if list(live_broker.get('symbol_resolution_candidates') or []) != list(archived_broker.get('symbol_resolution_candidates') or []):
        raise OwnerMTF1AcceptanceError('OWNER_LIVE_REVALIDATION_SYMBOL_CANDIDATES_MISMATCH')
    if not (_test_mode() and live_probe is not None):
        validate_mt5_data_root(str(live_broker.get('terminal_data_path') or ''))
    return _compare_immutable_native_revalidation(archived_native, live, sealed_asof_utc=sealed_asof)


def verify_owner_evidence_payload(
    payload: Mapping[str, Any],
    *,
    acceptance_path: Path = LOCAL_ACCEPTANCE,
    config_path: Path = CONFIG,
    registry_path: Path = EXTERNAL_REGISTRY,
    require_fresh_full: bool = True,
    require_live_mt5: bool = True,
    require_closure_run_id: bool = True,
    live_probe: Callable[..., tuple[dict[str, pd.DataFrame], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get('schema') != SCHEMA:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_SCHEMA_MISMATCH')
    if payload.get('project') != 'Max MTF' or payload.get('version') != '2.0.1' or payload.get('phase') != PHASE:
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_IDENTITY_MISMATCH')
    _parse_aware_utc(payload.get('generated_utc'), 'generated_utc')
    if str(payload.get('overall_status') or '').upper() != 'PASS':
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_NOT_PASS')
    actual = payload.get('candidate_binding')
    if not isinstance(actual, Mapping):
        raise OwnerMTF1AcceptanceError('OWNER_EVIDENCE_CANDIDATE_BINDING_MISSING')
    expected = _current_candidate_binding(
        acceptance_path=acceptance_path,
        config_path=config_path,
        registry_path=registry_path,
        require_fresh_full=require_fresh_full,
        require_closure_run_id=require_closure_run_id,
    )
    _assert_binding_equal(actual, expected)
    _validate_owner_runtime_proof(payload)
    recomputed = _recompute_from_archived_inputs(payload)
    _assert_recomputed_summary(payload, recomputed)
    recorded_revalidation = payload.get('immutable_live_revalidation')
    if not isinstance(recorded_revalidation, Mapping) or str(recorded_revalidation.get('status') or '').upper() != 'PASS':
        raise OwnerMTF1AcceptanceError('OWNER_IMMUTABLE_REVALIDATION_EVIDENCE_MISSING')
    archived_self_check = _compare_immutable_native_revalidation(
        recomputed['native'], recomputed['native'],
        sealed_asof_utc=_parse_aware_utc(payload.get('sealed_asof_utc'), 'sealed_asof_utc'),
    )
    # Immutable baseline and mutable-tail identities in the evidence must be
    # derivable from the exact raw archive, not manually asserted metadata.
    if recorded_revalidation != archived_self_check:
        raise OwnerMTF1AcceptanceError('OWNER_IMMUTABLE_REVALIDATION_EVIDENCE_ARCHIVE_MISMATCH')
    if require_live_mt5:
        current_revalidation = _live_revalidate(payload, recomputed['native'], config_path=config_path, live_probe=live_probe)
        if recorded_revalidation != current_revalidation:
            raise OwnerMTF1AcceptanceError('OWNER_IMMUTABLE_REVALIDATION_EVIDENCE_LIVE_MISMATCH')
    return expected


def verify_existing_evidence(
    path: Path = EVIDENCE,
    *,
    acceptance_path: Path = LOCAL_ACCEPTANCE,
    config_path: Path = CONFIG,
    registry_path: Path = EXTERNAL_REGISTRY,
    require_closure_run_id: bool = True,
    live_probe: Callable[..., tuple[dict[str, pd.DataFrame], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    payload = read_json(path)
    binding = verify_owner_evidence_payload(
        payload,
        acceptance_path=acceptance_path,
        config_path=config_path,
        registry_path=registry_path,
        require_closure_run_id=require_closure_run_id,
        live_probe=live_probe,
    )
    return {'status': 'PASS', 'evidence': str(path), 'candidate_binding': binding, 'execution_artifact_set_sha256': (payload.get('execution_artifacts') or {}).get('artifact_set_sha256')}


def _write(payload: dict[str, Any], path: Path = EVIDENCE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + '\n', encoding='utf-8')


def _run_owner_runtime(
    *,
    acceptance_path: Path = LOCAL_ACCEPTANCE,
    config_path: Path = CONFIG,
    registry_path: Path = EXTERNAL_REGISTRY,
    evidence_path: Path = EVIDENCE,
    artifact_root: Path = ARTIFACT_ROOT,
    collector: Callable[..., tuple[dict[str, pd.DataFrame], dict[str, Any]]] | None = None,
    data_root_validator: Callable[[str], Any] | None = None,
) -> int:
    started = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        'schema': SCHEMA,
        'project': 'Max MTF',
        'version': '2.0.1',
        'phase': PHASE,
        'generated_utc': started.isoformat(),
        'overall_status': 'FAIL',
        'gates': [],
    }
    try:
        binding = _current_candidate_binding(acceptance_path=acceptance_path, config_path=config_path, registry_path=registry_path, require_fresh_full=True)
        if not binding.get('closure_run_id'):
            raise OwnerMTF1AcceptanceError('OWNER_CLOSURE_RUN_ID_REQUIRED')
        payload['candidate_binding'] = binding
        cfg = _read_config(config_path)
        sealed_asof_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        end_utc = sealed_asof_utc
        start_utc = end_utc - timedelta(days=cfg['lookback_days'])
        runtime_collector = collector or collect_native_frames_from_mt5
        native, broker = runtime_collector(
            symbol=cfg['logical_symbol'],
            start_utc=start_utc,
            end_utc=end_utc,
            terminal_exe=cfg.get('terminal_exe') or None,
            broker_symbol_override=cfg.get('broker_symbol_override'),
        )
        resolved_symbol = str(broker.get('resolved_broker_symbol') or '').strip()
        if not resolved_symbol:
            raise OwnerMTF1AcceptanceError('OWNER_RESOLVED_BROKER_SYMBOL_MISSING')
        data_root = str(broker.get('terminal_data_path') or '').strip()
        root_validator = data_root_validator or validate_mt5_data_root
        verified = root_validator(data_root)
        payload['gates'].append({'gate': 'OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION', 'status': 'PASS', 'verified': True, 'terminal_id': verified.terminal_id, 'terminal_data_root': verified.data_root, 'broker_terminal_data_path': data_root})
        views, parity = build_canonical_views(native, asof_utc=sealed_asof_utc)
        alignment, alignment_meta = build_alignment_index(views)
        dq = audit_canonical_bundle(views, alignment, parity)
        if dq.get('status') != 'PASS' or str(parity.get('status') or '').upper() != 'PASS' or str((dq.get('alignment') or {}).get('status') or '').upper() != 'PASS':
            raise OwnerMTF1AcceptanceError('MTF1 owner runtime canonical proof failed')
        source_identity = {
            'kind': 'DIRECT_MT5_NATIVE_RATES',
            'native_rows': {tf: int(len(df)) for tf, df in native.items()},
            'window': {'from_utc': start_utc.isoformat(), 'to_utc': end_utc.isoformat()},
            'logical_symbol': cfg['logical_symbol'],
            'resolved_broker_symbol': resolved_symbol,
            'sealed_asof_utc': sealed_asof_utc.isoformat(),
        }
        manifest = build_lineage_manifest(views, alignment, symbol=resolved_symbol, broker_identity=broker, source_identity=source_identity, resampling_parity=parity, alignment_meta=alignment_meta, data_quality=dq)
        artifacts = archive_native_execution_inputs(
            native, broker, symbol=resolved_symbol, window=source_identity['window'],
            closure_run_id=str(binding['closure_run_id']),
            sealed_asof_utc=sealed_asof_utc,
            artifact_dir=Path(artifact_root) / str(binding['closure_run_id']),
        )
        align_audit = dq.get('alignment') or {}
        payload.update({
            'symbol': resolved_symbol,
            'logical_symbol': cfg['logical_symbol'],
            'resolved_broker_symbol': resolved_symbol,
            'symbol_resolution_method': broker.get('symbol_resolution_method'),
            'symbol_resolution_candidates': list(broker.get('symbol_resolution_candidates') or []),
            'window': source_identity['window'], 'sealed_asof_utc': sealed_asof_utc.isoformat(), 'broker_provenance': broker,
            'native_rows': source_identity['native_rows'], 'parity': parity,
            'alignment': {'meta': alignment_meta, 'audit': align_audit}, 'data_quality': dq,
            'lineage_manifest_preview': manifest, 'bundle_identity_preview_sha256': manifest['bundle_identity_sha256'],
            'execution_artifacts': artifacts,
        })
        payload['gates'].append({'gate': 'OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY', 'status': 'PASS', 'parity_status': parity.get('status'), 'alignment_status': align_audit.get('status'), 'data_quality_status': dq.get('status'), 'native_rows': source_identity['native_rows']})
        payload['immutable_live_revalidation'] = _live_revalidate(
            payload, native, config_path=config_path,
            live_probe=runtime_collector if collector is not None else None,
        )
        payload['overall_status'] = 'PASS'
        _write(payload, evidence_path)
        verify_existing_evidence(
            evidence_path, acceptance_path=acceptance_path, config_path=config_path, registry_path=registry_path,
            require_closure_run_id=True, live_probe=runtime_collector if collector is not None else None,
        )
        print(json.dumps({'status': 'PASS', 'evidence': str(evidence_path), 'logical_symbol': cfg['logical_symbol'], 'resolved_broker_symbol': resolved_symbol, 'symbol_resolution_method': broker.get('symbol_resolution_method'), 'terminal_id': verified.terminal_id, 'closure_run_id': binding['closure_run_id'], 'source_tree_signature': binding['source_tree_signature'], 'bundle_identity_preview_sha256': manifest['bundle_identity_sha256'], 'execution_artifact_set_sha256': artifacts['artifact_set_sha256']}, indent=2))
        return 0
    except Exception as exc:
        payload['overall_status'] = 'FAIL'; payload['failure_type'] = type(exc).__name__; payload['failure_reason'] = str(exc)
        _write(payload, evidence_path)
        print(json.dumps({'status': 'FAIL', 'evidence': str(evidence_path), 'reason': str(exc)}, indent=2), file=sys.stderr)
        return 1


def main() -> int:
    from mtf.mtf1_python_env_authority import assert_current_process_if_required
    assert_current_process_if_required('owner_runtime_acceptance')
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify-existing', action='store_true', help='Read-only verification of existing PASS evidence; production verification live-revalidates archived bars against Owner MT5.')
    args = ap.parse_args()
    if args.verify_existing:
        try:
            print(json.dumps(verify_existing_evidence(EVIDENCE), indent=2)); return 0
        except Exception as exc:
            print(json.dumps({'status': 'FAIL', 'evidence': str(EVIDENCE), 'reason': str(exc)}, indent=2), file=sys.stderr); return 1
    return _run_owner_runtime()


if __name__ == '__main__':
    raise SystemExit(main())
