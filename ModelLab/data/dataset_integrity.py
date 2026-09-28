from __future__ import annotations

import contextlib
import csv
import hashlib
import os
import shutil
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from strategy.strategy_geometry import extract_dataset_strategy_geometry

KEY_COLUMNS = ["contract", "symbol", "period", "signal_time"]
LOCK_SUFFIX = ".lock"


def _coerce_calendar_date(value, field_name: str) -> date:
    """Normalize UI/config/manifest date values at the dataset boundary.

    Streamlit date_input returns datetime.date, while persisted JSON/config and
    lineage manifests carry ISO strings. Dataset slicing must accept both without
    allowing Python object comparisons between date and str.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        ts = pd.Timestamp(value)
    except Exception as exc:
        raise ValueError(f"{field_name} bukan tanggal valid: {value!r}") from exc
    if pd.isna(ts):
        raise ValueError(f"{field_name} bukan tanggal valid: {value!r}")
    return ts.date()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv_auto(path: str | Path, *, usecols=None, nrows=None) -> pd.DataFrame:
    """Read CPMF CSV authorities using their actual delimiter.

    MT5 master/snapshot files use semicolons, while several internal evidence
    CSVs use commas. Detect from the header so every consumer sees the same
    columns instead of relying on pandas' comma default.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        header = f.readline()
    if not header:
        raise ValueError(f"CSV kosong/tidak memiliki header: {path}")
    semi = header.count(";")
    comma = header.count(",")
    if semi == 0 and comma == 0:
        raise ValueError(f"Delimiter CSV tidak dikenali (; atau ,): {path}")
    sep = ";" if semi >= comma else ","
    return pd.read_csv(path, sep=sep, usecols=usecols, nrows=nrows)


def _read_csv(path: str | Path, *, usecols=None) -> pd.DataFrame:
    return read_csv_auto(path, usecols=usecols)


def _normalized_key_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in KEY_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("CSV tidak memiliki identity key: " + ", ".join(missing))
    out = df[KEY_COLUMNS].copy()
    out["contract"] = out["contract"].astype(str)
    out["symbol"] = out["symbol"].astype(str)
    out["period"] = pd.to_numeric(out["period"], errors="raise").astype("int64")
    out["signal_time"] = pd.to_datetime(out["signal_time"], errors="raise")
    return out


def integrity_summary(path: str | Path, *, _lock_held: bool = False) -> dict:
    """Return one physical identity from one writer-serialized source revision."""
    path = Path(path)
    if not _lock_held:
        with writer_lock(path):
            return integrity_summary(path, _lock_held=True)
    df = _read_csv(path)
    if df.empty:
        raise ValueError("Training CSV kosong")
    keys = _normalized_key_frame(df)
    dup_mask = keys.duplicated(KEY_COLUMNS, keep=False)
    duplicate_rows = int(dup_mask.sum())
    duplicate_extra_rows = int(keys.duplicated(KEY_COLUMNS, keep="first").sum())
    unique_identity = keys[["contract", "symbol", "period"]].drop_duplicates()
    ts = keys["signal_time"]
    dates = sorted(ts.dt.date.unique().tolist())
    return {
        "path": str(path),
        "physical_rows": int(len(df)),
        "unique_key_rows": int(len(df) - duplicate_extra_rows),
        "duplicate_rows": duplicate_rows,
        "duplicate_extra_rows": duplicate_extra_rows,
        "identity_count": int(len(unique_identity)),
        "start": ts.min(),
        "end": ts.max(),
        "available_dates": dates,
        "sha256": sha256_file(path),
        "size_mb": path.stat().st_size / (1024 * 1024),
    }


@contextlib.contextmanager
def writer_lock(csv_path: str | Path, timeout_sec: float = 10.0):
    """Coordinate with EA v1.06 through the same exclusive `.lock` file.

    Windows uses CreateFileW with share-mode 0, matching MQL FileOpen without
    FILE_SHARE_* flags. POSIX uses flock for local acceptance tests.
    """
    csv_path = Path(csv_path)
    lock_path = Path(str(csv_path) + LOCK_SUFFIX)
    deadline = time.monotonic() + timeout_sec
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        CreateFileW = kernel32.CreateFileW
        CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        CreateFileW.restype = wintypes.HANDLE
        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_ALWAYS = 4
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
        handle = None
        while time.monotonic() < deadline:
            h = CreateFileW(str(lock_path), GENERIC_READ | GENERIC_WRITE, 0, None,
                            OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, None)
            if h != INVALID_HANDLE_VALUE:
                handle = h
                break
            time.sleep(0.05)
        if handle is None:
            raise TimeoutError(f"Training writer lock sibuk: {lock_path}")
        try:
            yield lock_path
        finally:
            CloseHandle(handle)
    else:
        import fcntl
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(lock_path, "a+b")
        acquired = False
        while time.monotonic() < deadline:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                time.sleep(0.05)
        if not acquired:
            f.close()
            raise TimeoutError(f"Training writer lock sibuk: {lock_path}")
        try:
            yield lock_path
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            f.close()


def repair_legacy_duplicates(path: str | Path) -> dict:
    """Backup then remove exact identity duplicates using first-write-wins.

    Operation is serialized against EA v1.06. The original column order and
    semicolon delimiter are preserved. Rows are sorted chronologically after
    dedup so historical gap-fill does not leave the physical CSV out of order.
    """
    path = Path(path)
    with writer_lock(path):
        before_hash = sha256_file(path)
        df = _read_csv(path)
        keys = _normalized_key_frame(df)
        extra_mask = keys.duplicated(KEY_COLUMNS, keep="first")
        removed = int(extra_mask.sum())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
        backup = path.with_name(f"{path.stem}.legacy_backup_{stamp}{path.suffix}")
        shutil.copy2(path, backup)
        if removed == 0:
            return {
                "status": "CLEAN_ALREADY",
                "removed": 0,
                "backup": str(backup),
                "before_sha256": before_hash,
                "after_sha256": before_hash,
                "rows": int(len(df)),
            }
        clean = df.loc[~extra_mask].copy()
        clean["signal_time"] = pd.to_datetime(clean["signal_time"], errors="raise")
        clean = clean.sort_values(["signal_time"], kind="stable").reset_index(drop=True)
        # Restore the exact textual datetime format the EA uses.
        clean["signal_time"] = clean["signal_time"].dt.strftime("%Y.%m.%d %H:%M")
        tmp = path.with_name(path.name + ".repair.tmp")
        clean.to_csv(tmp, sep=";", index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        if sha256_file(path) != before_hash:
            tmp.unlink(missing_ok=True)
            raise RuntimeError("CSV berubah selama cleanup; source tidak disentuh. Ulangi setelah writer stabil.")
        os.replace(tmp, path)
        after = integrity_summary(path, _lock_held=True)
        if after["duplicate_extra_rows"] != 0:
            raise RuntimeError("Cleanup verification gagal: duplicate masih ada")
        return {
            "status": "REPAIRED",
            "removed": removed,
            "backup": str(backup),
            "before_sha256": before_hash,
            "after_sha256": after["sha256"],
            "rows": after["physical_rows"],
        }


def available_date_range(path: str | Path) -> dict:
    info = integrity_summary(path)
    if info["duplicate_extra_rows"]:
        raise ValueError(
            f"CSV memiliki {info['duplicate_extra_rows']} duplicate identity rows. "
            "Jalankan cleanup legacy sebelum research."
        )
    dates = info["available_dates"]
    if not dates:
        raise ValueError("CSV tidak memiliki signal_time")
    return {**info, "first_date": dates[0], "last_date": dates[-1]}


def research_window_preview(path: str | Path, start_date: date | str, end_date: date | str, horizon_bars: int | None = None) -> dict:
    start_date = _coerce_calendar_date(start_date, "Research From")
    end_date = _coerce_calendar_date(end_date, "Research To")
    if start_date > end_date:
        raise ValueError("Research From harus <= Research To")
    path = Path(path)
    with writer_lock(path):
        info = integrity_summary(path, _lock_held=True)
        if info["duplicate_extra_rows"]:
            raise ValueError(f"CSV memiliki {info['duplicate_extra_rows']} duplicate identity rows. Jalankan cleanup legacy sebelum research.")
        dates = info["available_dates"]
        if not dates:
            raise ValueError("CSV tidak memiliki signal_time")
        info = {**info, "first_date": dates[0], "last_date": dates[-1]}
        df = _read_csv(path, usecols=KEY_COLUMNS + ["sl_atr","tp_atr","max_hold_bars"])
    keys = _normalized_key_frame(df)
    ts = keys["signal_time"]
    d = ts.dt.date
    mask = (d >= start_date) & (d <= end_date)
    if not mask.any():
        raise ValueError("Range yang dipilih tidak memiliki row")
    selected = keys.loc[mask].sort_values("signal_time", kind="stable")
    cutoff = selected["signal_time"].max()
    after = keys.loc[ts > cutoff].sort_values("signal_time", kind="stable")
    geometry=extract_dataset_strategy_geometry(df)
    h=max(1,int(geometry["max_hold_bars"]))
    # A fresh raw row is mature when at least h later source rows exist.
    full = keys.sort_values("signal_time", kind="stable").reset_index(drop=True)
    mature_boundary_index = max(-1, len(full) - h - 1)
    mature_boundary = full.iloc[mature_boundary_index]["signal_time"] if mature_boundary_index >= 0 else pd.NaT
    mature_after = after[after["signal_time"] <= mature_boundary] if pd.notna(mature_boundary) else after.iloc[0:0]
    return {
        "master_rows": int(len(keys)),
        "selected_rows": int(len(selected)),
        "selected_start": selected["signal_time"].min(),
        "cutoff": cutoff,
        "reserve_raw_rows": int(len(after)),
        "reserve_mature_raw_rows": int(len(mature_after)),
        "pending_horizon_rows": int(len(after) - len(mature_after)),
        "horizon_bars": h,
        "master_end": keys["signal_time"].max(),
        "master_sha256": info["sha256"],
    }


def build_research_window_snapshot(path: str | Path, start_date: date | str, end_date: date | str, out_path: str | Path) -> dict:
    start_date = _coerce_calendar_date(start_date, "Research From")
    end_date = _coerce_calendar_date(end_date, "Research To")
    if start_date > end_date:
        raise ValueError("Research From harus <= Research To")
    path = Path(path)
    out_path = Path(out_path)
    with writer_lock(path):
        info = integrity_summary(path, _lock_held=True)
        if info["duplicate_extra_rows"]:
            raise ValueError(
                f"CSV memiliki {info['duplicate_extra_rows']} duplicate identity rows. "
                "Jalankan cleanup legacy sebelum research."
            )
        master_hash = info["sha256"]
        df = _read_csv(path)
    ts = pd.to_datetime(df["signal_time"], errors="raise")
    d = ts.dt.date
    mask = (d >= start_date) & (d <= end_date)
    if not mask.any():
        raise ValueError("Research window kosong")
    window = df.loc[mask].copy()
    window["signal_time"] = pd.to_datetime(window["signal_time"], errors="raise")
    window = window.sort_values("signal_time", kind="stable").reset_index(drop=True)
    # Preserve MQL datetime format for a stable, human-readable authority snapshot.
    window["signal_time"] = window["signal_time"].dt.strftime("%Y.%m.%d %H:%M")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    window.to_csv(tmp, sep=";", index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    os.replace(tmp, out_path)
    snapshot_hash = sha256_file(out_path)
    cutoff = pd.to_datetime(window["signal_time"], errors="raise").max()
    return {
        "schema": "CP_RESEARCH_WINDOW_V1",
        "master_csv": str(path),
        "master_csv_sha256_at_start": master_hash,
        "research_from": str(start_date),
        "research_to": str(end_date),
        "source_raw_end": str(cutoff),
        "snapshot_csv": str(out_path),
        "snapshot_csv_sha256": snapshot_hash,
        "snapshot_rows": int(len(window)),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }


def fresh_readiness(path: str | Path, cutoff, cfg: dict) -> dict:
    """Explain why a fresh holdout is or is not usable without opening it for scoring."""
    # Local imports avoid circular import during model_lab module initialization.
    from data.labels import build_labels
    from models.model_lab import load_training_csv

    raw = load_training_csv(path)
    from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry
    cfg, geometry = synchronize_cfg_with_dataset_geometry(cfg, raw)
    cutoff = pd.Timestamp(str(cutoff))
    ts = pd.to_datetime(raw["signal_time"], errors="raise")
    newer = raw.loc[ts > cutoff].copy()
    horizon = int(geometry["max_hold_bars"])
    if newer.empty:
        return {
            "status": "NO_FRESH_ROWS", "cutoff": str(cutoff), "raw_new_rows": 0,
            "mature_raw_rows": 0, "labeled_fresh_rows": 0, "pending_horizon_rows": 0,
            "horizon_bars": horizon, "newest": str(ts.max()),
        }
    # Maturity is structural: any source row among the final h positions lacks full future horizon.
    ordered = raw.sort_values("signal_time", kind="stable").reset_index(drop=True)
    mature = ordered.iloc[:max(0, len(ordered)-horizon)]
    mts = pd.to_datetime(mature["signal_time"], errors="raise") if not mature.empty else pd.Series([], dtype="datetime64[ns]")
    mature_new = mature.loc[mts > cutoff].copy() if not mature.empty else mature
    labeled = build_labels(raw, cfg)
    lts = pd.to_datetime(labeled["signal_time"], errors="raise") if not labeled.empty else pd.Series([], dtype="datetime64[ns]")
    # v1.3.2: build_labels intentionally preserves immature/context-only rows so
    # temporal chronology is not compressed. Fresh readiness must therefore count
    # only rows whose future-horizon label is actually mature/valid; otherwise a
    # zero-weight SKIP placeholder in the horizon tail can falsely report READY.
    if not labeled.empty and "label_valid" in labeled.columns:
        label_ready = labeled["label_valid"].astype(bool).to_numpy()
        fresh = labeled.loc[(lts > cutoff).to_numpy() & label_ready].copy()
    else:
        fresh = labeled.loc[lts > cutoff].copy() if not labeled.empty else labeled
    if fresh.empty and mature_new.empty:
        status = "WAITING_LABEL_HORIZON"
    elif fresh.empty:
        status = "NO_VALID_LABELS"
    else:
        status = "READY"
    return {
        "status": status,
        "cutoff": str(cutoff),
        "raw_new_rows": int(len(newer)),
        "mature_raw_rows": int(len(mature_new)),
        "labeled_fresh_rows": int(len(fresh)),
        "pending_horizon_rows": int(max(0, len(newer)-len(mature_new))),
        "horizon_bars": horizon,
        "newest": str(ts.max()),
    }
