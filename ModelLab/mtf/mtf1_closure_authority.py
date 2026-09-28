from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

import acceptance.runners.run_acceptance as run_acceptance
from mtf.mtf1_closure_run import read_run as read_closure_run
from core.release_authority import load_active_release

ROOT = MODELLAB_ROOT
PKG = ROOT.parent
LOCAL_ACCEPTANCE = ROOT / 'evidence/current/BUILD_ACCEPTANCE_v2_0_1.json'
EXTERNAL_REGISTRY = PKG / 'governance/EXTERNAL_RUNTIME_GATES.json'
BASE_BINDING_SCHEMA = 'MAX_MTF1_BASE_CANDIDATE_BINDING_V3'
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


class MTF1ClosureError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    p = Path(path)
    if not p.is_file():
        raise MTF1ClosureError(f'required binding file missing: {p}')
    return hashlib.sha256(p.read_bytes()).hexdigest()


def is_sha256(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or '').lower()))


def read_json(path: Path) -> dict[str, Any]:
    p = Path(path)
    try:
        obj = json.loads(p.read_text(encoding='utf-8'))
    except Exception as exc:
        raise MTF1ClosureError(f'JSON authority unreadable: {p}: {exc}') from exc
    if not isinstance(obj, dict):
        raise MTF1ClosureError(f'JSON authority must be object: {p}')
    return obj


def path_label(path: Path) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(PKG.resolve())).replace('\\', '/')
    except Exception:
        return str(p.resolve()).replace('\\', '/')


def current_base_candidate_binding(
    *,
    acceptance_path: Path = LOCAL_ACCEPTANCE,
    registry_path: Path = EXTERNAL_REGISTRY,
    require_fresh_full: bool = True,
    require_closure_run_id: bool = False,
) -> dict[str, Any]:
    try:
        acceptance = run_acceptance.validate_local_acceptance_report(
            acceptance_path,
            require_current_tree=True,
            require_current_suite=True,
            require_fresh_full=require_fresh_full,
            require_closure_run_id=require_closure_run_id,
        )
    except Exception as exc:
        raise MTF1ClosureError(str(exc)) from exc

    # This call validates the single canonical external registry and its immutable
    # MTF-1 requirement lock before any external Owner closure is allowed.
    try:
        run_acceptance._external_gates()
    except Exception as exc:
        raise MTF1ClosureError(str(exc)) from exc

    active = load_active_release()
    ea = active.get('ea') if isinstance(active.get('ea'), Mapping) else None
    if not isinstance(ea, Mapping):
        raise MTF1ClosureError('ACTIVE_RELEASE_EA_IDENTITY_MISSING')
    ea_path = str(ea.get('path') or '')
    ea_sha = str(ea.get('sha256') or '').lower()
    ea_version = str(ea.get('version') or '')
    if not ea_path or not is_sha256(ea_sha) or not ea_version:
        raise MTF1ClosureError('ACTIVE_RELEASE_EA_IDENTITY_INCOMPLETE')

    closure_run_id = acceptance.get('closure_run_id')
    if require_closure_run_id:
        run = read_closure_run(required=True)
        if not closure_run_id or str(closure_run_id) != str(run.get('closure_run_id')):
            raise MTF1ClosureError('CLOSURE_RUN_ID_BINDING_MISMATCH')

    return {
        'schema': BASE_BINDING_SCHEMA,
        'closure_run_id': closure_run_id,
        'source_tree_signature': str(acceptance['source_tree_signature']),
        'suite_signature': str(acceptance['suite_signature']),
        'local_acceptance_sha256': sha256_file(acceptance_path),
        'external_registry_sha256': sha256_file(registry_path),
        'active_ea_relative_path': ea_path,
        'active_ea_sha256': ea_sha,
        'active_ea_version': ea_version,
        'local_acceptance_report': path_label(acceptance_path),
        'external_registry': path_label(registry_path),
    }


def assert_base_binding_equal(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    keys = (
        'schema',
        'source_tree_signature',
        'suite_signature',
        'local_acceptance_sha256',
        'external_registry_sha256',
        'active_ea_relative_path',
        'active_ea_sha256',
        'active_ea_version',
        'closure_run_id',
    )
    for key in keys:
        if actual.get(key) != expected.get(key):
            raise MTF1ClosureError(
                f'CANDIDATE_BINDING_MISMATCH: {key}: evidence={actual.get(key)!r} current={expected.get(key)!r}'
            )
