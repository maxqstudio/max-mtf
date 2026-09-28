from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.project_paths import (
    PACKAGE_ROOT,
    EA_SOURCE,
    RELEASE_ACTIVE_DIR,
    RELEASE_ARCHIVE_DIR,
    RELEASE_CHALLENGERS_DIR,
    MODEL_BASELINE_DIR,
)
from host.mt5_installation import validate_mt5_data_root

ACTIVE_RELEASE_FILE = PACKAGE_ROOT / "ModelLab" / "runtime" / "active_release.json"
PACKAGE_ACTIVE_RELEASE_FILE = RELEASE_ACTIVE_DIR / "release.json"
ACTIVE_RELEASE_SCHEMA = "MAX_MTF_ACTIVE_RELEASE_V1"


class ReleaseAuthorityError(RuntimeError):
    pass


def _sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def _atomic(path: Path, obj: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dict(obj), f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass


def _portable_rel(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(PACKAGE_ROOT.resolve())
    except Exception as exc:
        raise ReleaseAuthorityError(f"release artifact must be inside project root: {path}") from exc
    return rel.as_posix()


def _resolve_portable(path_value: str) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        raise ReleaseAuthorityError("active release EA path is empty")
    p = Path(raw)
    if p.is_absolute():
        raise ReleaseAuthorityError(f"active release path must be project-relative, not absolute: {raw}")
    resolved = (PACKAGE_ROOT / p).resolve()
    try:
        resolved.relative_to(PACKAGE_ROOT.resolve())
    except Exception as exc:
        raise ReleaseAuthorityError(f"active release path escapes project root: {raw}") from exc
    return resolved



def _project_ea_version() -> str:
    path = PACKAGE_ROOT / "governance" / "PROJECT_IDENTITY.json"
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReleaseAuthorityError(f"project EA version authority unreadable: {path}: {exc}") from exc
    version = str(obj.get("ea_version") or "").strip()
    if not version:
        raise ReleaseAuthorityError("project EA version authority is empty")
    return version


def _ea_property_version(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except Exception as exc:
        raise ReleaseAuthorityError(f"EA source unreadable for version parity: {path}: {exc}") from exc
    matches = re.findall(r'^\s*#property\s+version\s+"([^"]+)"', text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise ReleaseAuthorityError(f"EA must contain exactly one #property version: {path}")
    return str(matches[0]).strip()


def _assert_ea_version_parity(recorded_version: Any, path: Path) -> str:
    stored = str(recorded_version or "").strip()
    source_version = _ea_property_version(path)
    project_version = _project_ea_version()
    if not stored:
        raise ReleaseAuthorityError("active release EA version is empty")
    if stored != source_version or source_version != project_version:
        raise ReleaseAuthorityError(
            f"active release EA version mismatch: stored={stored} source={source_version} project={project_version}"
        )
    return source_version


def baseline_release() -> dict:
    return {
        "schema": ACTIVE_RELEASE_SCHEMA,
        "release_id": "BASELINE-MTF-V2",
        "status": "BASELINE_NOT_CHAMPION",
        "ea": {
            "path": _portable_rel(EA_SOURCE),
            "sha256": _sha(EA_SOURCE),
            "version": _assert_ea_version_parity(_project_ea_version(), EA_SOURCE),
        },
        "model": None,
        "strategy_champion_id": None,
        "model_champion_id": None,
        "deployed_mt5": None,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }


def validate_active_release_record(obj: Mapping[str, Any], *, require_current_baseline: bool = True) -> dict:
    if not isinstance(obj, Mapping) or obj.get("schema") != ACTIVE_RELEASE_SCHEMA:
        raise ReleaseAuthorityError("active release schema mismatch")
    ea = obj.get("ea")
    if not isinstance(ea, Mapping):
        raise ReleaseAuthorityError("active release EA identity missing")
    resolved = _resolve_portable(str(ea.get("path") or ""))
    if not resolved.is_file():
        raise ReleaseAuthorityError(f"active release EA artifact missing: {ea.get('path')}")
    actual_sha = _sha(resolved)
    _assert_ea_version_parity(ea.get("version"), resolved)
    stored_sha = str(ea.get("sha256") or "")
    if not stored_sha or stored_sha != actual_sha:
        raise ReleaseAuthorityError(
            f"active release EA SHA mismatch: stored={stored_sha or 'EMPTY'} actual={actual_sha}"
        )
    if require_current_baseline:
        if resolved != EA_SOURCE.resolve():
            raise ReleaseAuthorityError(
                f"active release EA must resolve to canonical current EA: {resolved} != {EA_SOURCE.resolve()}"
            )
        canonical_sha = _sha(EA_SOURCE)
        if canonical_sha != actual_sha:
            raise ReleaseAuthorityError("active release EA SHA does not match canonical current EA")
    normalized = dict(obj)
    normalized["ea"] = dict(ea)
    normalized["ea"]["path"] = _portable_rel(resolved)
    normalized["ea"]["sha256"] = actual_sha
    normalized["ea"]["version"] = _ea_property_version(resolved)
    return normalized


def _load_json(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReleaseAuthorityError(f"active release record unreadable: {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise ReleaseAuthorityError(f"active release record is not an object: {path}")
    return obj


def load_active_release() -> dict:
    if not ACTIVE_RELEASE_FILE.exists() and not PACKAGE_ACTIVE_RELEASE_FILE.exists():
        return initialize_zero_champion_release()
    if not ACTIVE_RELEASE_FILE.exists() or not PACKAGE_ACTIVE_RELEASE_FILE.exists():
        raise ReleaseAuthorityError("active release mirror is incomplete")
    runtime_obj = validate_active_release_record(_load_json(ACTIVE_RELEASE_FILE))
    package_obj = validate_active_release_record(_load_json(PACKAGE_ACTIVE_RELEASE_FILE))
    # generated_utc is part of the committed record and the two mirrors must be exact.
    if runtime_obj != package_obj:
        raise ReleaseAuthorityError("active release runtime/package records diverge")
    return runtime_obj


def initialize_zero_champion_release() -> dict:
    RELEASE_ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_CHALLENGERS_DIR.mkdir(parents=True, exist_ok=True)
    obj = validate_active_release_record(baseline_release())
    _atomic(ACTIVE_RELEASE_FILE, obj)
    _atomic(PACKAGE_ACTIVE_RELEASE_FILE, obj)
    return obj


def verified_mt5_targets(data_root: str | Path) -> dict:
    r = validate_mt5_data_root(data_root, create_subdirs=True)
    return {
        "terminal_id": r.terminal_id,
        "data_root": r.data_root,
        "ea_dir": r.experts_dir,
        "model_dir": r.models_dir,
        "tester_profiles_dir": r.tester_profiles_dir,
    }
