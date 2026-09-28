from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "MAX_CHALLENGER_REGISTRY_V1"

_FAMILY_NAMES = {
    "lightgbm": "LightGBM",
    "xgboost": "XGBoost",
    "random_forest": "RandomForest",
    "gru": "GRU",
    "lstm": "LSTM",
    "tcn": "TCN",
    "transformer": "TransformerEncoder",
    "patchtst": "PatchTST",
    "itransformer": "iTransformer",
    "tft": "TFT",
    "transformer_moe": "TransformerMoE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def family_display_name(family: str) -> str:
    raw = str(family or "unknown").strip().lower()
    if raw.startswith("hybrid::"):
        parts = [p for p in raw.split("::")[1:] if p]
        return "-".join(_FAMILY_NAMES.get(p, p.replace("_", "").title()) for p in parts) or "Hybrid"
    if raw.startswith("hybrid_"):
        # Legacy canonical IDs: hybrid_gru_lightgbm / hybrid_gru_xgboost / ...
        parts = [p for p in raw.split("_")[1:] if p]
        return "-".join(_FAMILY_NAMES.get(p, p.replace("_", "").title()) for p in parts) or "Hybrid"
    return _FAMILY_NAMES.get(raw, raw.replace("_", "").title() or "Unknown")


def _safe_token(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text or "").strip())
    text = re.sub(r"-+", "-", text).strip("-_.")
    return text or "Model"


def _stamp_from_run_id(run_id: str) -> str:
    m = re.search(r"(20\d{6})[_-]?(\d{6})", str(run_id or ""))
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


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


def _read_json(path: Path, default: Any) -> Any:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj
    except Exception:
        return default


def registry_path(app_dir: str | Path) -> Path:
    return Path(app_dir) / "governance" / "challenger_registry.json"


def load_challenger_registry(app_dir: str | Path) -> dict:
    p = registry_path(app_dir)
    obj = _read_json(p, {"schema": SCHEMA, "entries": [], "updated_utc": None})
    if not isinstance(obj, dict):
        obj = {"schema": SCHEMA, "entries": [], "updated_utc": None}
    if not isinstance(obj.get("entries"), list):
        obj["entries"] = []
    obj["schema"] = SCHEMA
    return obj


def _with_registry_lock(app_dir: str | Path, fn):
    p = registry_path(app_dir)
    lock = p.with_suffix(p.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    for attempt in range(80):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if attempt == 79:
                raise RuntimeError("challenger registry is busy")
            time.sleep(0.025 * min(8, attempt + 1))
    try:
        if fd is not None:
            os.write(fd, f"pid={os.getpid()} utc={utc_now()}\n".encode("utf-8"))
            os.close(fd)
            fd = None
        reg = load_challenger_registry(app_dir)
        result = fn(reg)
        reg["schema"] = SCHEMA
        reg["updated_utc"] = utc_now()
        _atomic_json(p, reg)
        return result
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass


def _same_bytes(a: Path, b: Path) -> bool:
    try:
        return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()
    except Exception:
        return False


def _bundle_suffix(index: int) -> str:
    return "" if index == 1 else f"_{index:02d}"


def _allocate_standalone_destination(run: Path, stem: str, source: Path) -> tuple[Path, str]:
    for i in range(1, 1000):
        suffix = _bundle_suffix(i)
        dest = run / f"{stem}{suffix}.onnx"
        if not dest.exists() or _same_bytes(dest, source):
            return dest, suffix
    raise RuntimeError("Could not allocate human-readable Challenger filename")


def _allocate_hybrid_bundle(run: Path, stem: str, temporal: Path, policy: Path) -> tuple[Path, Path, str]:
    # Temporal and policy files are one atomic identity. They must always share the
    # same human-readable collision suffix.
    for i in range(1, 1000):
        suffix = _bundle_suffix(i)
        td = run / f"{stem}{suffix}_Temporal.onnx"
        pd = run / f"{stem}{suffix}_Policy.onnx"
        t_ok = (not td.exists()) or _same_bytes(td, temporal)
        p_ok = (not pd.exists()) or _same_bytes(pd, policy)
        if t_ok and p_ok:
            # Do not reuse a half-existing bundle unless the existing side is byte-identical.
            return td, pd, suffix
    raise RuntimeError("Could not allocate human-readable hybrid Challenger filename pair")


def _decision_policy_destination(run: Path, stem: str, suffix: str, source: Path) -> Path:
    dest = run / f"{stem}{suffix}_DecisionPolicy.csv"
    if not dest.exists() or _same_bytes(dest, source):
        return dest
    # A policy collision means the model bundle identity is not reusable; fail closed
    # instead of silently mixing policy evidence under the same Challenger ID.
    raise RuntimeError(f"Decision-policy artifact conflicts with Challenger bundle identity: {dest.name}")


def release_human_challenger_artifacts(run_dir: str | Path, manifest: dict) -> dict:
    """Create immutable human-readable Challenger artifacts without replacing compatibility aliases.

    Filenames never contain hashes. SHA values remain manifest-only integrity evidence.
    """
    run = Path(run_dir)
    family = str(manifest.get("model_family") or "unknown")
    run_id = str(manifest.get("run_id") or run.name)
    family_name = _safe_token(family_display_name(family))
    stamp = _stamp_from_run_id(run_id)
    stem = f"Challenger_{family_name}_{stamp}"

    standalone = run / "challenger.onnx"
    temporal = run / "challenger_temporal.onnx"
    policy_model = run / "challenger_policy_model.onnx"
    decision_policy = run / "challenger_policy.csv"

    files: dict[str, str | None] = {
        "standalone": None,
        "temporal": None,
        "policy_model": None,
        "decision_policy": None,
    }
    topology = "STANDALONE"
    collision_suffix = ""

    if temporal.exists() or policy_model.exists():
        topology = "TEMPORAL_TO_TREE_HYBRID"
        if not temporal.exists() or not policy_model.exists():
            raise RuntimeError("Hybrid Challenger export is incomplete: temporal/policy model pair required")
        td, pd, collision_suffix = _allocate_hybrid_bundle(run, stem, temporal, policy_model)
        if td != temporal:
            shutil.copy2(temporal, td)
        if pd != policy_model:
            shutil.copy2(policy_model, pd)
        files["temporal"] = td.name
        files["policy_model"] = pd.name
    else:
        if not standalone.exists():
            raise FileNotFoundError(run / "challenger.onnx")
        sd, collision_suffix = _allocate_standalone_destination(run, stem, standalone)
        if sd != standalone:
            shutil.copy2(standalone, sd)
        files["standalone"] = sd.name

    if decision_policy.exists():
        dd = _decision_policy_destination(run, stem, collision_suffix, decision_policy)
        if dd != decision_policy:
            shutil.copy2(decision_policy, dd)
        files["decision_policy"] = dd.name

    id_suffix = collision_suffix.replace("_", "-")
    challenger_id = f"CHL-{family_name}-{stamp.replace('_', '-')}{id_suffix}"
    display = f"{family_display_name(family)} · {stamp[:8]} {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]} UTC"
    return {
        "schema": "MAX_CHALLENGER_ARTIFACT_V1",
        "challenger_id": challenger_id,
        "display_name": display,
        "family_label": family_display_name(family),
        "topology": topology,
        "files": files,
        "manual_ea_parameters": {
            "InpChallengerHybrid": ("true" if topology == "TEMPORAL_TO_TREE_HYBRID" else "false"),
            "InpChallengerModel": (f"models\\{files['standalone']}" if files["standalone"] else None),
            "InpChallengerTemporalModel": (f"models\\{files['temporal']}" if files["temporal"] else None),
            "InpChallengerHybridPolicyModel": (f"models\\{files['policy_model']}" if files["policy_model"] else None),
        },
        "released_utc": utc_now(),
        "naming_authority": "HUMAN_READABLE_FAMILY_PLUS_UTC_RUN_TIME_NO_HASH_IN_FILENAME",
    }


def _locked_kpi(manifest: dict) -> dict:
    src = dict(manifest.get("locked_test_trading") or {})
    if not src:
        rep = manifest.get("kpi_report") or {}
        src = dict(rep.get("locked_test") or rep.get("trading") or {})
    keys = ("trades", "profit_factor", "expectancy_r", "max_drawdown_r", "recovery_factor", "win_rate", "payoff_ratio", "cvar95_r")
    return {k: src.get(k) for k in keys}


def register_eligible_challenger(run_dir: str | Path, manifest: dict, app_dir: str | Path) -> dict:
    if str(manifest.get("status") or "") != "ELIGIBLE_CHALLENGER":
        return manifest
    run = Path(run_dir)
    art = manifest.get("challenger_artifact")
    if not isinstance(art, dict):
        art = release_human_challenger_artifacts(run, manifest)
        manifest["challenger_artifact"] = art
    entry = {
        "challenger_id": art["challenger_id"],
        "display_name": art["display_name"],
        "status": "CHALLENGER",
        "run_id": manifest.get("run_id") or run.name,
        "run_dir": str(run.resolve()),
        "model_family": manifest.get("model_family"),
        "family_label": art.get("family_label"),
        "model_name": manifest.get("model_name"),
        "topology": art.get("topology"),
        "files": art.get("files"),
        "manual_ea_parameters": art.get("manual_ea_parameters"),
        "locked_test_kpi": _locked_kpi(manifest),
        "take_threshold": manifest.get("take_threshold"),
        "policy_schema": manifest.get("policy_schema"),
        "created_utc": manifest.get("generated_utc") or utc_now(),
        "updated_utc": utc_now(),
    }

    def mutate(reg: dict):
        rows = list(reg.get("entries") or [])
        replaced = False
        for i, row in enumerate(rows):
            if str(row.get("challenger_id")) == str(entry["challenger_id"]):
                prior_status = str(row.get("status") or "CHALLENGER")
                merged = dict(row)
                merged.update(entry)
                if prior_status in {"PROMOTED", "RETIRED"}:
                    merged["status"] = prior_status
                rows[i] = merged
                replaced = True
                break
        if not replaced:
            rows.append(entry)
        reg["entries"] = rows
        return entry

    _with_registry_lock(app_dir, mutate)
    return manifest


def mark_challenger_promoted(app_dir: str | Path, challenger_id: str, champion_id: str) -> None:
    def mutate(reg: dict):
        rows = list(reg.get("entries") or [])
        for row in rows:
            if str(row.get("challenger_id")) == str(challenger_id):
                row["status"] = "PROMOTED"
                row["champion_id"] = str(champion_id)
                row["promoted_utc"] = utc_now()
                row["updated_utc"] = utc_now()
        reg["entries"] = rows
    _with_registry_lock(app_dir, mutate)


def publish_challenger_to_terminal(run_dir: str | Path, terminal_files_dir: str | Path, manifest: dict) -> dict:
    """Copy human-readable Challenger files to MT5 /Files/models without mutating EA inputs."""
    run = Path(run_dir)
    terminal = Path(terminal_files_dir)
    art = manifest.get("challenger_artifact")
    if not isinstance(art, dict):
        art = release_human_challenger_artifacts(run, manifest)
    models = terminal / "models"
    models.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for key, name in (art.get("files") or {}).items():
        if not name:
            continue
        src = run / str(name)
        if not src.exists():
            raise FileNotFoundError(src)
        dst = models / src.name
        shutil.copy2(src, dst)
        copied[key] = str(dst)
    return {
        "challenger_id": art.get("challenger_id"),
        "copied": copied,
        "manual_ea_parameters": art.get("manual_ea_parameters") or {},
        "ea_mutated": False,
        "published_utc": utc_now(),
    }
