from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from core.project_paths import MODELLAB_ROOT
from typing import Any

from factory.challenger_registry import load_challenger_registry, register_eligible_challenger
from factory.champion_factory import verify_champion_terminal_authority

SCHEMA = "MAX_FACTORY_MODEL_CHALLENGER_BRIDGE_V1"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=2, default=str)
            f.write("\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _copy_immutable(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if _sha(dst) != _sha(src):
            raise RuntimeError(f"Factory Challenger destination conflicts with sealed source bytes: {dst}")
        return
    shutil.copy2(src, dst)
    if _sha(dst) != _sha(src):
        raise RuntimeError(f"Factory Challenger copy parity failed: {src.name} -> {dst.name}")


def _runtime_sources(factory_dir: Path, champion: dict, runtime: dict) -> dict[str, Path]:
    rel = str(champion.get("runtime_manifest") or "")
    if not rel:
        raise RuntimeError("Factory winner has no runtime_manifest")
    runtime_path = factory_dir / rel
    if not runtime_path.is_file():
        raise FileNotFoundError(runtime_path)
    runtime_dir = runtime_path.parent
    artifacts = dict(runtime.get("artifacts") or {})
    out: dict[str, Path] = {}
    if artifacts.get("onnx"):
        out["standalone"] = runtime_dir / str(artifacts["onnx"])
    else:
        if artifacts.get("temporal_onnx"):
            out["temporal"] = runtime_dir / str(artifacts["temporal_onnx"])
        if artifacts.get("policy_model_onnx"):
            out["policy_model"] = runtime_dir / str(artifacts["policy_model_onnx"])
    if artifacts.get("decision_policy"):
        out["decision_policy"] = runtime_dir / str(artifacts["decision_policy"])
    if "standalone" not in out and not ({"temporal", "policy_model"} <= set(out)):
        raise RuntimeError("Factory winner runtime artifacts are not a complete standalone/hybrid Challenger bundle")
    for p in out.values():
        if not p.is_file():
            raise FileNotFoundError(p)
    return out


def register_factory_winner_as_model_challenger(factory_dir: str | Path, app_dir: str | Path | None = None) -> dict:
    """Convert one sealed Factory winner into a persistent Model Challenger.

    This is an append/retain bridge only. It has no Champion promotion authority.
    Replays are idempotent: the same Factory winner maps to the same run/bundle and
    the registry preserves PROMOTED/RETIRED status if already set by Owner actions.
    """
    fd = Path(factory_dir).resolve()
    app = Path(app_dir).resolve() if app_dir is not None else MODELLAB_ROOT
    verified = verify_champion_terminal_authority(fd)
    fm = dict(verified.get("manifest") or {})
    champion = dict(verified.get("champion") or {})
    seal = dict(verified.get("seal") or {})

    runtime_rel = str(champion.get("runtime_manifest") or "")
    runtime_path = fd / runtime_rel
    runtime = _read(runtime_path, {})
    if not runtime:
        raise RuntimeError("Factory winner runtime manifest unreadable")
    sources = _runtime_sources(fd, champion, runtime)

    family = str(champion.get("family") or runtime.get("family") or "").strip()
    name = str(champion.get("name") or champion.get("pool_id") or "FactoryWinner").strip()
    if not family:
        raise RuntimeError("Factory winner model family missing")

    # Stable, human-auditable run identity. One Factory winner always maps to one
    # persistent Model run regardless of graph retry/resume count.
    run_id = f"MODEL_CHALLENGER_{fd.name}"
    run = app / "runs" / run_id
    run.mkdir(parents=True, exist_ok=True)

    if "standalone" in sources:
        _copy_immutable(sources["standalone"], run / "challenger.onnx")
    else:
        _copy_immutable(sources["temporal"], run / "challenger_temporal.onnx")
        _copy_immutable(sources["policy_model"], run / "challenger_policy_model.onnx")
    if "decision_policy" in sources:
        _copy_immutable(sources["decision_policy"], run / "challenger_policy.csv")

    metrics = dict(champion.get("metrics") or {})
    manifest = {
        "schema": "MAX_MODEL_MANIFEST_FACTORY_BRIDGE_V1",
        "run_id": run_id,
        "status": "ELIGIBLE_CHALLENGER",
        "model_family": family,
        "model_name": name,
        "hyperparameters": dict(champion.get("params") or {}),
        "take_threshold": champion.get("take_threshold"),
        "decision_policy": champion.get("decision_policy"),
        "locked_test_trading": metrics,
        "kpi_report": {"locked_test": metrics, "trading": metrics},
        "onnx_parity": champion.get("onnx_parity"),
        "generated_utc": champion.get("selected_utc") or _utc(),
        "factory_source": {
            "factory_id": fd.name,
            "factory_dir": str(fd),
            "factory_status": str(fm.get("status") or ""),
            "pool_id": champion.get("pool_id"),
            "champion_terminal_seal_hash": str(seal.get("seal_hash") or ""),
            "runtime_manifest": runtime_rel,
            "runtime_manifest_sha256": _sha(runtime_path),
        },
    }
    manifest = register_eligible_challenger(run, manifest, app)
    _atomic_json(run / "model_manifest.json", manifest)

    art = dict(manifest.get("challenger_artifact") or {})
    challenger_id = str(art.get("challenger_id") or "")
    if not challenger_id:
        raise RuntimeError("Model Challenger registration produced no challenger_id")
    registry = load_challenger_registry(app)
    entries = [r for r in (registry.get("entries") or []) if str((r or {}).get("challenger_id") or "") == challenger_id]
    if len(entries) != 1:
        raise RuntimeError(f"Model Challenger registry parity failed for {challenger_id}: matches={len(entries)}")
    entry = dict(entries[0])
    if str(entry.get("run_id") or "") != run_id:
        raise RuntimeError("Model Challenger registry run identity drift")

    copied = {}
    for p in run.iterdir():
        if p.is_file() and (p.suffix.lower() == ".onnx" or p.name.endswith("_DecisionPolicy.csv") or p.name == "challenger_policy.csv"):
            copied[p.name] = _sha(p)
    evidence = {
        "schema": SCHEMA,
        "status": "REGISTERED",
        "factory_id": fd.name,
        "factory_winner_status": str(fm.get("status") or ""),
        "champion_terminal_seal_hash": str(seal.get("seal_hash") or ""),
        "challenger_id": challenger_id,
        "challenger_run_id": run_id,
        "challenger_run_dir": str(run),
        "registry_status": str(entry.get("status") or ""),
        "registry_entry_count": len(registry.get("entries") or []),
        "copied_artifact_sha256": copied,
        "promotion_performed": False,
        "registered_utc": _utc(),
    }
    _atomic_json(fd / "model_challenger_registration.json", evidence)
    return {"manifest": manifest, "entry": entry, "evidence": evidence, "run_dir": str(run)}
