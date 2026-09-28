from __future__ import annotations

import json
import math
import os
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from core.project_paths import MODELLAB_ROOT
from typing import Any

DATASET_FIELDS = ("sl_atr", "tp_atr", "max_hold_bars")
RUNTIME_AUTHORITY = MODELLAB_ROOT / "runtime" / "strategy_authority.json"

# v1.3.2: Model Research must replay the promoted EA execution policy, not a
# research-local approximation. max_spread/onnx_blend are static EA runtime knobs
# (not Strategy Optimizer search dimensions) and are preserved across promotions.
STATIC_EXECUTION_DEFAULTS = {
    "max_spread_points": 45.0,
    "onnx_blend": 0.65,
}


def _same(a: float, b: float, tol: float = 1e-9) -> bool:
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)), abs(float(b)))


def extract_dataset_strategy_geometry(df) -> dict:
    missing = [c for c in DATASET_FIELDS if c not in df.columns]
    if missing:
        raise ValueError("STRATEGY_GEOMETRY_MISSING: " + ", ".join(missing))
    rows = []
    for c in DATASET_FIELDS:
        vals = df[c].astype(float)
        if vals.isna().any() or (~vals.map(math.isfinite)).any():
            raise ValueError(f"STRATEGY_GEOMETRY_NON_FINITE: {c}")
        rows.append(vals)
    norm = []
    for sl, tp, hold in zip(rows[0], rows[1], rows[2]):
        hi = int(round(float(hold)))
        if not _same(float(hold), hi) or float(sl) <= 0 or float(tp) <= 0 or hi <= 0:
            raise ValueError("STRATEGY_GEOMETRY_INVALID")
        norm.append((round(float(sl), 10), round(float(tp), 10), hi))
    unique = sorted(set(norm))
    if len(unique) != 1:
        preview = unique[:8]
        raise ValueError(f"STRATEGY_GEOMETRY_MIXED_DATASET: found {len(unique)} geometries; regenerate a clean training CSV after Strategy Optimizer Champion. sample={preview}")
    sl, tp, hold = unique[0]
    return {
        "schema": "MAX_STRATEGY_GEOMETRY_V1",
        "source": "CP32_DATASET",
        "sl_atr": float(sl),
        "tp_atr": float(tp),
        "max_hold_bars": int(hold),
        "label_geometry": {"sl_atr": float(sl), "tp_atr": float(tp), "horizon_bars": int(hold)},
    }


def config_strategy_geometry(cfg: dict) -> dict | None:
    sg = cfg.get("strategy_geometry") if isinstance(cfg.get("strategy_geometry"), dict) else {}
    source = sg.get("label_geometry") if isinstance(sg.get("label_geometry"), dict) else sg
    try:
        sl = float(source.get("sl_atr")); tp = float(source.get("tp_atr"))
        hold = int(source.get("max_hold_bars", source.get("horizon_bars")))
        if sl > 0 and tp > 0 and hold > 0:
            return {"sl_atr": sl, "tp_atr": tp, "max_hold_bars": hold, "horizon_bars": hold}
    except Exception:
        pass
    label = cfg.get("label") if isinstance(cfg.get("label"), dict) else {}
    try:
        sl = float(label.get("sl_atr")); tp = float(label.get("tp_atr")); hold = int(label.get("horizon_bars"))
        if sl > 0 and tp > 0 and hold > 0:
            return {"sl_atr": sl, "tp_atr": tp, "max_hold_bars": hold, "horizon_bars": hold}
    except Exception:
        pass
    return None


def resolved_strategy_horizon_bars(cfg: dict) -> int:
    g = config_strategy_geometry(cfg)
    return int(g["max_hold_bars"]) if g else 0


def resolved_strategy_sl_atr(cfg: dict) -> float:
    g = config_strategy_geometry(cfg)
    return float(g["sl_atr"]) if g else 0.0


def assert_strategy_geometry_matches_dataset(df, cfg: dict) -> dict:
    g = extract_dataset_strategy_geometry(df); c = config_strategy_geometry(cfg)
    if c is None:
        return g
    mismatches = []
    if not _same(c["sl_atr"], g["sl_atr"]): mismatches.append(f"sl_atr: cfg={c['sl_atr']} dataset={g['sl_atr']}")
    if not _same(c["tp_atr"], g["tp_atr"]): mismatches.append(f"tp_atr: cfg={c['tp_atr']} dataset={g['tp_atr']}")
    if int(c["max_hold_bars"]) != int(g["max_hold_bars"]): mismatches.append(f"max_hold_bars: cfg={c['max_hold_bars']} dataset={g['max_hold_bars']}")
    if mismatches:
        raise ValueError("STRATEGY_GEOMETRY_RUNTIME_MISMATCH: " + "; ".join(mismatches))
    return g


def assert_label_geometry_matches_dataset(df, cfg: dict) -> dict:
    return assert_strategy_geometry_matches_dataset(df, cfg)


def load_runtime_strategy_authority(path: str | Path | None = None) -> dict | None:
    p = Path(path) if path is not None else RUNTIME_AUTHORITY
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _authority_geometry(authority: dict | None) -> dict | None:
    if not isinstance(authority, dict): return None
    g = authority.get("geometry") if isinstance(authority.get("geometry"), dict) else authority
    try:
        out={"sl_atr": float(g["sl_atr"]), "tp_atr": float(g["tp_atr"]), "max_hold_bars": int(g["max_hold_bars"])}
        if out["sl_atr"]<=0 or out["tp_atr"]<=0 or out["max_hold_bars"]<=0: return None
        return out
    except Exception:
        return None


def authority_execution_policy(authority: dict | None) -> dict | None:
    """Resolve the exact promoted Strategy execution-policy subset Model Research needs."""
    if not isinstance(authority, dict): return None
    ep = authority.get("execution_policy") if isinstance(authority.get("execution_policy"), dict) else {}
    params = authority.get("optimizer_params") if isinstance(authority.get("optimizer_params"), dict) else {}
    def pick(name, param, default=None):
        if name in ep: return ep[name]
        if param in params: return params[param]
        return default
    try:
        out={
            "entry_threshold": float(pick("entry_threshold","InpEntryThreshold")),
            "exit_reverse_threshold": float(pick("exit_reverse_threshold","InpExitReverseThreshold")),
            "min_consensus": float(pick("min_consensus","InpMinConsensus")),
            "shock_halt_range_atr": float(pick("shock_halt_range_atr","InpShockHaltATR")),
            "max_spread_points": float(pick("max_spread_points","InpMaxSpreadPoints",STATIC_EXECUTION_DEFAULTS["max_spread_points"])),
            "onnx_blend": float(pick("onnx_blend","InpOnnxBlend",STATIC_EXECUTION_DEFAULTS["onnx_blend"])),
        }
    except Exception:
        return None
    if not (0.0 <= out["entry_threshold"] <= 1.0 and 0.0 <= out["exit_reverse_threshold"] <= 1.0 and
            0.0 <= out["min_consensus"] <= 1.0 and out["shock_halt_range_atr"] > 0.0 and
            out["max_spread_points"] >= 0.0 and 0.0 <= out["onnx_blend"] <= 1.0):
        return None
    return out


def require_runtime_strategy_authority(path: str | Path | None = None) -> dict:
    p = Path(path) if path is not None else RUNTIME_AUTHORITY
    if not p.exists(): raise ValueError(f"STRATEGY_AUTHORITY_MISSING: {p}")
    authority = load_runtime_strategy_authority(p)
    if not isinstance(authority, dict): raise ValueError(f"STRATEGY_AUTHORITY_UNREADABLE: {p}")
    if _authority_geometry(authority) is None: raise ValueError(f"STRATEGY_AUTHORITY_INVALID_GEOMETRY: {p}")
    if authority_execution_policy(authority) is None: raise ValueError(f"STRATEGY_AUTHORITY_INVALID_EXECUTION_POLICY: {p}")
    return authority


def synchronize_cfg_with_dataset_geometry(cfg: dict, df, *, require_runtime_authority_match: bool = True) -> tuple[dict, dict]:
    g = extract_dataset_strategy_geometry(df)
    authority = require_runtime_strategy_authority() if require_runtime_authority_match else load_runtime_strategy_authority()
    ag = _authority_geometry(authority); ep = authority_execution_policy(authority)
    if require_runtime_authority_match:
        mismatch = (not _same(ag["sl_atr"], g["sl_atr"]) or not _same(ag["tp_atr"], g["tp_atr"]) or int(ag["max_hold_bars"]) != int(g["max_hold_bars"]))
        if mismatch:
            raise ValueError(
                "STRATEGY_AUTHORITY_DATASET_MISMATCH: current Optimizer/EA authority "
                f"SL={ag['sl_atr']}, TP={ag['tp_atr']}, Hold={ag['max_hold_bars']} but dataset "
                f"SL={g['sl_atr']}, TP={g['tp_atr']}, Hold={g['max_hold_bars']}. Regenerate training data with current Max EA."
            )
    out = deepcopy(cfg)
    label = out.setdefault("label", {})
    for key in ("sl_atr", "tp_atr", "horizon_bars"): label.pop(key, None)
    hold = int(g["max_hold_bars"])
    split = out.setdefault("split", {})
    requested_purge = int(split.get("purge_bars", 0) or 0); requested_embargo = int(split.get("embargo_bars", requested_purge) or 0)
    # Inherited v1.4.7 geometry handoff: MaxHold is the MINIMUM temporal
    # leakage guard. Stale weaker research values are lifted, while an
    # intentionally stricter upstream purge/embargo must never be reduced.
    split["purge_bars"] = max(requested_purge, hold)
    split["embargo_bars"] = max(requested_embargo, hold)

    # v1.3.2 SCI-01: promoted Strategy Champion execution policy overrides stale
    # research-local deployment copies. Research no longer owns these values.
    if ep is not None:
        dep=out.setdefault("deployment", {})
        before={k:dep.get(k) for k in ep}
        dep.update(ep)
        out["strategy_execution_policy"]={
            "schema":"MAX_STRATEGY_EXECUTION_POLICY_V1",
            **ep,
            "source":"PROMOTED_STRATEGY_AUTHORITY",
            "overrode_research_values":{k:{"before":before.get(k),"authority":v} for k,v in ep.items() if before.get(k) is not None and not _same(float(before.get(k)),float(v))},
        }

    out["strategy_geometry"] = {
        **g,
        "authority": authority or {"source": "DATASET_ONLY_DIAGNOSTIC_ONLY"},
        "sync_mode": "DATASET_EXECUTION_GEOMETRY_AND_POLICY_LOCKED" if ep is not None else "DATASET_EXECUTION_GEOMETRY_LOCKED",
        "temporal_guard": {
            "requested_purge_bars": requested_purge,
            "requested_embargo_bars": requested_embargo,
            "effective_purge_bars": int(split["purge_bars"]),
            "effective_embargo_bars": int(split["embargo_bars"]),
            "minimum_from_max_hold_bars": hold,
        },
    }
    return out, g


def _atomic_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, default=str) + "\n"
    for attempt in range(8):
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)); tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(payload); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path); return
        except PermissionError:
            try: tmp.unlink(missing_ok=True)
            except Exception: pass
            if attempt == 7: raise
            time.sleep(0.03 * (attempt + 1))
        finally:
            try: tmp.unlink(missing_ok=True)
            except Exception: pass


def persist_optimizer_champion_authority(*, params: dict[str, Any], ea_sha256: str, job_id: str, champion_pass: int, path: str | Path | None = None) -> dict:
    p = Path(path) if path is not None else RUNTIME_AUTHORITY
    geometry = {"sl_atr": float(params["InpSL_ATR"]), "tp_atr": float(params["InpTP_ATR"]), "max_hold_bars": int(round(float(params["InpMaxHoldBars"])))}
    previous=load_runtime_strategy_authority(p)
    prior_ep=authority_execution_policy(previous) or dict(STATIC_EXECUTION_DEFAULTS)
    execution_policy={
        "entry_threshold":float(params.get("InpEntryThreshold",prior_ep.get("entry_threshold",0.18))),
        "exit_reverse_threshold":float(params.get("InpExitReverseThreshold",prior_ep.get("exit_reverse_threshold",0.25))),
        "min_consensus":float(params.get("InpMinConsensus",prior_ep.get("min_consensus",0.70))),
        "shock_halt_range_atr":float(params.get("InpShockHaltATR",prior_ep.get("shock_halt_range_atr",3.5))),
        "max_spread_points":float(prior_ep.get("max_spread_points",STATIC_EXECUTION_DEFAULTS["max_spread_points"])),
        "onnx_blend":float(prior_ep.get("onnx_blend",STATIC_EXECUTION_DEFAULTS["onnx_blend"])),
    }
    obj = {
        "schema": "MAX_STRATEGY_EXECUTION_AUTHORITY_V3",
        "scientific_contract": "STRATEGY_OPTIMIZER_CHAMPION_TO_MODEL_EXECUTION_PARITY",
        "source": "STRATEGY_OPTIMIZER_CHAMPION", "job_id": str(job_id), "champion_pass": int(champion_pass),
        "geometry": geometry, "execution_policy":execution_policy, "optimizer_params":deepcopy(params),
        "ea_sha256": str(ea_sha256), "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_json(p, obj); return obj
