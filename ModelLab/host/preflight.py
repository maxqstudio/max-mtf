from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

import pandas as pd

from core.contract import FEATURES, CONTRACT_ID
from models.model_lab import load_training_csv
from data.labels import build_labels
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry
from mtf.mtf_names import TRAINING_CSV


def default_mt5_training_csv() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    root = Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"
    canonical = root / TRAINING_CSV
    return canonical if canonical.exists() else None


def detect_terminal_files_dirs() -> list[Path]:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    root = Path(appdata) / "MetaQuotes" / "Terminal"
    if not root.exists():
        return []
    out = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        p = child / "MQL5" / "Files"
        if p.exists() and p.is_dir():
            out.append(p)
    return sorted(out, key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def period_label(period) -> str:
    try: p=int(float(period))
    except Exception: return str(period or "?")
    mapping={1:"M1",2:"M2",3:"M3",4:"M4",5:"M5",6:"M6",10:"M10",12:"M12",15:"M15",20:"M20",30:"M30",16385:"H1",16386:"H2",16387:"H3",16388:"H4",16390:"H6",16392:"H8",16396:"H12",16408:"D1",32769:"W1",49153:"MN1",60:"H1",120:"H2",180:"H3",240:"H4",360:"H6",480:"H8",720:"H12",1440:"D1",10080:"W1",43200:"MN1"}
    return mapping.get(p,f"P{p}")


def quick_summary(path: str | Path) -> dict:
    path = Path(path)
    df = load_training_csv(path)
    one = df[["symbol", "period"]].iloc[0]
    return {
        "path": str(path),
        "size_mb": path.stat().st_size / (1024 * 1024),
        "rows": int(len(df)),
        "symbol": str(one["symbol"]),
        "period": int(one["period"]),
        "timeframe": period_label(one["period"]),
        "start": df["signal_time"].min(),
        "end": df["signal_time"].max(),
        "contract": CONTRACT_ID,
        "feature_count": len(FEATURES),
        "duplicates_removed": 0,
        "nan_features": int(df[FEATURES].isna().sum().sum()),
        "sha256": sha256_file(path),
    }


def label_summary(path: str | Path, cfg: dict) -> dict:
    raw = load_training_csv(path)
    cfg, _geometry = synchronize_cfg_with_dataset_geometry(cfg, raw)
    labeled = build_labels(raw, cfg)
    counts = labeled["label"].value_counts().to_dict()
    names = {0: "SELL", 1: "SKIP", 2: "BUY"}
    class_counts = {names[k]: int(counts.get(k, 0)) for k in (0, 1, 2)}
    return {
        "raw_rows": int(len(raw)),
        "labeled_rows": int(len(labeled)),
        "dropped_rows": int(len(raw) - len(labeled)),
        "class_counts": class_counts,
        "class_pct": {k: (v / max(1, len(labeled))) for k, v in class_counts.items()},
        "ambiguous_dropped": int(raw.shape[0] - labeled.shape[0]),
    }


def load_manifest(run_dir: str | Path) -> dict:
    p = Path(run_dir) / "model_manifest.json"
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def list_runs(runs_dir: str | Path) -> list[Path]:
    """Manifest-driven run discovery. Never hide POLICY_/FRESH_ descendants."""
    root=Path(runs_dir)
    if not root.exists(): return []
    rows=[p for p in root.iterdir() if p.is_dir() and (p/"model_manifest.json").exists()]
    return sorted(rows,key=lambda p:p.name,reverse=True)
