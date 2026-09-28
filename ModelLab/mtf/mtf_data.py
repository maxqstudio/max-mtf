from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

SCHEMA = "MAX_MTF_DATA_BUNDLE_V1"
ALIGNMENT_SCHEMA = "MAX_MTF_ALIGNMENT_V1"
LINEAGE_SCHEMA = "MAX_MTF_DATA_LINEAGE_V1"

ROLE_TO_TIMEFRAME = {
    "TF+2": "H4",
    "TF+1": "H1",
    "TF": "M15",
    "TF-1": "M5",
}
TIMEFRAME_MINUTES = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}
TIMEFRAME_SECONDS = {k: v * 60 for k, v in TIMEFRAME_MINUTES.items()}
NATIVE_FRAME_ORDER = ("M5", "M15", "H1", "H4")
PRICE_COLUMNS = ("open", "high", "low", "close")
OPTIONAL_COLUMNS = ("tick_volume", "spread", "real_volume")


class MTFDataError(ValueError):
    pass


@dataclass(frozen=True)
class MTFAudit:
    status: str
    timeframe: str
    rows: int
    first_open_time_utc: str | None
    last_open_time_utc: str | None
    duplicate_timestamps: int
    non_monotonic: bool
    invalid_ohlc_rows: int
    nonfinite_price_rows: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timeframe": self.timeframe,
            "rows": self.rows,
            "first_open_time_utc": self.first_open_time_utc,
            "last_open_time_utc": self.last_open_time_utc,
            "duplicate_timestamps": self.duplicate_timestamps,
            "non_monotonic": self.non_monotonic,
            "invalid_ohlc_rows": self.invalid_ohlc_rows,
            "nonfinite_price_rows": self.nonfinite_price_rows,
        }


def _stable_json_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _normalize_timestamp_series(raw: pd.Series, *, source_timezone: str | None) -> pd.Series:
    """Normalize one bar-open timestamp series to timezone-aware UTC.

    Numeric values are MT5/POSIX epoch seconds and therefore UTC. String or
    datetime values that are timezone-naive require an explicit source_timezone;
    DST ambiguity/non-existent local times fail closed instead of being guessed.
    """
    if pd.api.types.is_numeric_dtype(raw):
        ts = pd.to_datetime(raw, unit="s", utc=True, errors="raise")
        return pd.Series(ts, index=raw.index, name="open_time_utc")

    ts = pd.to_datetime(raw, errors="raise")
    s = pd.Series(ts, index=raw.index)
    try:
        tz = s.dt.tz
    except AttributeError as exc:
        raise MTFDataError("timestamp column is not datetime-like") from exc
    if tz is None:
        if not source_timezone:
            raise MTFDataError("timezone-naive timestamp requires explicit source_timezone")
        try:
            s = s.dt.tz_localize(source_timezone, ambiguous="raise", nonexistent="raise")
        except Exception as exc:
            raise MTFDataError(f"timezone localization failed for {source_timezone}: {exc}") from exc
    return s.dt.tz_convert("UTC").rename("open_time_utc")


def _time_column(df: pd.DataFrame) -> str:
    found = [c for c in ("open_time_utc", "open_time", "time") if c in df.columns]
    if len(found) != 1:
        raise MTFDataError("native frame must contain exactly one of: open_time_utc, open_time, time")
    return found[0]


def normalize_native_frame(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    source_timezone: str | None = None,
) -> pd.DataFrame:
    timeframe = str(timeframe).upper()
    if timeframe not in TIMEFRAME_MINUTES:
        raise MTFDataError(f"unsupported timeframe: {timeframe}")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise MTFDataError(f"{timeframe} native frame is empty")

    tcol = _time_column(frame)
    missing = [c for c in PRICE_COLUMNS if c not in frame.columns]
    if missing:
        raise MTFDataError(f"{timeframe} missing OHLC columns: {', '.join(missing)}")

    out = pd.DataFrame(index=frame.index.copy())
    if tcol == "open_time_utc":
        raw = frame[tcol]
        parsed = pd.to_datetime(raw, errors="raise")
        parsed = pd.Series(parsed, index=raw.index)
        if parsed.dt.tz is None:
            raise MTFDataError("open_time_utc must be timezone-aware")
        out["open_time_utc"] = parsed.dt.tz_convert("UTC")
    else:
        out["open_time_utc"] = _normalize_timestamp_series(frame[tcol], source_timezone=source_timezone)

    for c in PRICE_COLUMNS:
        out[c] = pd.to_numeric(frame[c], errors="raise").astype(float)
    for c in OPTIONAL_COLUMNS:
        if c in frame.columns:
            out[c] = pd.to_numeric(frame[c], errors="raise")
        else:
            out[c] = 0

    # MT5 exposes real_volume as zero-only for instruments/brokers where real
    # exchange volume is unavailable. Preserve that availability explicitly so
    # higher-timeframe parity cannot silently ignore a populated real_volume.
    real_volume_raw_available = bool(
        "real_volume" in frame.columns
        and (pd.to_numeric(frame["real_volume"], errors="raise").fillna(0) != 0).any()
    )
    out["real_volume_available"] = real_volume_raw_available

    out["timeframe"] = timeframe
    out = out.reset_index(drop=True)
    audit = audit_native_frame(out, timeframe)
    if audit.status != "PASS":
        raise MTFDataError(f"{timeframe} native frame failed audit: {audit.as_dict()}")
    return out


def audit_native_frame(frame: pd.DataFrame, timeframe: str) -> MTFAudit:
    timeframe = str(timeframe).upper()
    if "open_time_utc" not in frame.columns:
        raise MTFDataError(f"{timeframe} frame has no open_time_utc")
    ts = pd.Series(pd.to_datetime(frame["open_time_utc"], utc=True, errors="raise"))
    dup = int(ts.duplicated(keep=False).sum())
    non_monotonic = not bool(ts.is_monotonic_increasing)
    prices = np.column_stack([pd.to_numeric(frame[c], errors="coerce").to_numpy(float) for c in PRICE_COLUMNS])
    nonfinite_mask = ~np.isfinite(prices).all(axis=1)
    o, h, l, c = (prices[:, i] for i in range(4))
    invalid = nonfinite_mask | (h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l) | (prices <= 0).any(axis=1)
    status = "PASS" if dup == 0 and not non_monotonic and int(invalid.sum()) == 0 else "FAIL"
    return MTFAudit(
        status=status,
        timeframe=timeframe,
        rows=int(len(frame)),
        first_open_time_utc=ts.min().isoformat() if len(ts) else None,
        last_open_time_utc=ts.max().isoformat() if len(ts) else None,
        duplicate_timestamps=dup,
        non_monotonic=non_monotonic,
        invalid_ohlc_rows=int(invalid.sum()),
        nonfinite_price_rows=int(nonfinite_mask.sum()),
    )


def audit_m5_against_native_reference(source_m5: pd.DataFrame, reference_m5: pd.DataFrame, *, price_atol: float = 1e-10) -> dict[str, Any]:
    """Exact broker-reference continuity/parity gate for the sealed M5 window.

    Calendar-gap inference is intentionally forbidden. Weekends/session breaks are
    broker-specific, so missing M5 authority comes from the exact native M5
    timestamp set returned by the same terminal/feed, not from naive wall-clock
    continuity assumptions.
    """
    src = normalize_native_frame(source_m5, "M5") if "timeframe" not in source_m5.columns else source_m5.copy()
    ref = normalize_native_frame(reference_m5, "M5") if "timeframe" not in reference_m5.columns else reference_m5.copy()
    sidx = pd.DatetimeIndex(pd.to_datetime(src["open_time_utc"], utc=True))
    ridx = pd.DatetimeIndex(pd.to_datetime(ref["open_time_utc"], utc=True))
    missing = ridx.difference(sidx)
    extra = sidx.difference(ridx)
    merged = src.merge(ref, on="open_time_utc", suffixes=("_src", "_ref"), how="inner", validate="one_to_one")
    price_errors: dict[str, float] = {}
    parity = True
    for c in PRICE_COLUMNS:
        err = np.abs(merged[f"{c}_src"].to_numpy(float) - merged[f"{c}_ref"].to_numpy(float))
        max_err = float(np.max(err)) if len(err) else math.inf
        price_errors[c] = max_err
        parity = parity and bool(len(err)) and max_err <= price_atol
    volume_parity = True
    if "tick_volume_src" in merged.columns and "tick_volume_ref" in merged.columns:
        volume_parity = bool(np.array_equal(merged["tick_volume_src"].to_numpy(), merged["tick_volume_ref"].to_numpy()))

    src_rv_available = bool(src.get("real_volume_available", pd.Series(False, index=src.index)).astype(bool).any()) or bool((pd.to_numeric(src.get("real_volume", pd.Series(0, index=src.index)), errors="raise") != 0).any())
    ref_rv_available = bool(ref.get("real_volume_available", pd.Series(False, index=ref.index)).astype(bool).any()) or bool((pd.to_numeric(ref.get("real_volume", pd.Series(0, index=ref.index)), errors="raise") != 0).any())
    real_volume_required = src_rv_available or ref_rv_available
    real_volume_parity = True
    if real_volume_required:
        real_volume_parity = bool(np.array_equal(
            pd.to_numeric(merged["real_volume_src"], errors="raise").to_numpy(),
            pd.to_numeric(merged["real_volume_ref"], errors="raise").to_numpy(),
        ))
    real_volume_status = "EXACT_PARITY" if real_volume_required else "UNAVAILABLE_ZERO_ONLY"

    ok = len(missing) == 0 and len(extra) == 0 and parity and volume_parity and real_volume_parity and len(src) == len(ref)
    return {
        "schema": "MAX_MTF_M5_BROKER_CONTINUITY_V1",
        "status": "PASS" if ok else "FAIL",
        "source_rows": int(len(src)),
        "reference_rows": int(len(ref)),
        "missing_count": int(len(missing)),
        "extra_count": int(len(extra)),
        "missing_timestamps": [x.isoformat() for x in missing[:50]],
        "extra_timestamps": [x.isoformat() for x in extra[:50]],
        "price_max_abs_error": price_errors,
        "tick_volume_exact": bool(volume_parity),
        "real_volume_status": real_volume_status,
        "real_volume_exact": bool(real_volume_parity),
        "authority": "EXACT_NATIVE_M5_TIMESTAMP_SET_NOT_WALL_CLOCK_GUESS; REAL_VOLUME_EXACT_WHEN_AVAILABLE",
    }



def _normalized_m5_reference_hash(frame: pd.DataFrame) -> str:
    normalized = normalize_native_frame(frame, "M5") if "timeframe" not in frame.columns else frame.copy()
    cols = ["open_time_utc", *PRICE_COLUMNS, "tick_volume", "spread", "real_volume", "real_volume_available", "timeframe"]
    keep = [c for c in cols if c in normalized.columns]
    return _canonical_frame_hash(normalized[keep].reset_index(drop=True))


def build_imported_m5_source_identity(
    source_m5: pd.DataFrame,
    native_reference_m5: pd.DataFrame,
    *,
    price_atol: float = 1e-10,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build identity-bound continuity proof for an imported M5 source.

    Imported M5 is never allowed to rely on higher-TF aggregate parity as a
    substitute for exact native-M5 timestamp continuity.  The exact reference
    audit and reference hash are bound into the bundle manifest and are
    recomputed again by ``write_bundle`` before sealing.
    """
    audit = audit_m5_against_native_reference(source_m5, native_reference_m5, price_atol=price_atol)
    if audit.get("status") != "PASS":
        raise MTFDataError(f"imported M5 native-reference audit failed: {audit}")
    payload = dict(extra or {})
    payload.update({
        "kind": "IMPORTED_M5",
        "native_reference_audit": audit,
        "native_reference_m5_sha256": _normalized_m5_reference_hash(native_reference_m5),
        "continuity_authority": "EXACT_NATIVE_M5_REFERENCE_REQUIRED_AT_SEAL",
    })
    return payload


PRODUCTION_SOURCE_KINDS = frozenset({"DIRECT_MT5_NATIVE_RATES", "IMPORTED_M5"})
TEST_SOURCE_KINDS = frozenset({"SYNTHETIC_TEST"})


def _validate_source_kind(source_identity: Mapping[str, Any]) -> str:
    if not isinstance(source_identity, Mapping):
        raise MTFDataError("bundle source_identity must be an object")
    kind = str(source_identity.get("kind") or "").strip().upper()
    if not kind:
        raise MTFDataError("bundle source_identity.kind is required")
    if kind in PRODUCTION_SOURCE_KINDS:
        return kind
    if kind in TEST_SOURCE_KINDS and os.environ.get("MAX_MTF_ALLOW_SYNTHETIC_TEST_SOURCE") == "1":
        return kind
    raise MTFDataError(f"unsupported source_identity.kind: {kind}")


def _validate_imported_m5_seal_authority(
    views: Mapping[str, pd.DataFrame],
    manifest: Mapping[str, Any],
    native_m5_reference: pd.DataFrame | None,
    *,
    price_atol: float = 1e-10,
) -> None:
    source_identity = manifest.get("source_identity") or {}
    kind = _validate_source_kind(source_identity)
    if kind != "IMPORTED_M5":
        return
    if native_m5_reference is None:
        raise MTFDataError("IMPORTED_M5 requires native M5 reference at seal time")
    supplied_audit = source_identity.get("native_reference_audit")
    if not isinstance(supplied_audit, Mapping) or supplied_audit.get("status") != "PASS":
        raise MTFDataError("IMPORTED_M5 requires PASS native_reference_audit evidence")
    recomputed = audit_m5_against_native_reference(views["M5"], native_m5_reference, price_atol=price_atol)
    if recomputed.get("status") != "PASS":
        raise MTFDataError(f"IMPORTED_M5 continuity proof failed at seal time: {recomputed}")
    if dict(supplied_audit) != recomputed:
        raise MTFDataError("IMPORTED_M5 native_reference_audit does not match seal-time recomputation")
    supplied_ref_sha = str(source_identity.get("native_reference_m5_sha256") or "")
    actual_ref_sha = _normalized_m5_reference_hash(native_m5_reference)
    if not supplied_ref_sha or supplied_ref_sha != actual_ref_sha:
        raise MTFDataError(
            f"IMPORTED_M5 native reference SHA mismatch: supplied={supplied_ref_sha or 'EMPTY'} actual={actual_ref_sha}"
        )


def _derive_one_from_m5(
    m5: pd.DataFrame,
    native_reference: pd.DataFrame,
    timeframe: str,
    *,
    price_atol: float = 1e-10,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    timeframe = str(timeframe).upper()
    if timeframe == "M5":
        raise MTFDataError("M5 is source authority, not a derived frame")
    src = normalize_native_frame(m5, "M5") if "timeframe" not in m5.columns else m5.copy()
    ref = normalize_native_frame(native_reference, timeframe) if "timeframe" not in native_reference.columns else native_reference.copy()
    if len(ref) < 2:
        raise MTFDataError(f"{timeframe} native reference needs at least 2 bar opens to prove a fully closed interval")

    src_ts = pd.DatetimeIndex(pd.to_datetime(src["open_time_utc"], utc=True))
    ref_ts = pd.DatetimeIndex(pd.to_datetime(ref["open_time_utc"], utc=True))
    rows: list[dict[str, Any]] = []
    parity_rows: list[dict[str, Any]] = []
    for i in range(len(ref) - 1):
        left = ref_ts[i]
        right = ref_ts[i + 1]
        if right <= left:
            raise MTFDataError(f"{timeframe} native reference is non-monotonic")
        mask = (src_ts >= left) & (src_ts < right)
        chunk = src.loc[mask]
        if chunk.empty:
            raise MTFDataError(f"{timeframe} interval {left.isoformat()}..{right.isoformat()} has no M5 source bars")
        # A source M5 bar must itself be fully closed by the higher-TF boundary.
        latest_m5_close = pd.Timestamp(chunk["open_time_utc"].iloc[-1]) + pd.Timedelta(minutes=5)
        if latest_m5_close > right:
            raise MTFDataError(f"{timeframe} interval includes an M5 bar that closes after the native boundary")
        derived = {
            "open_time_utc": left,
            "close_time_utc": right,
            "open": float(chunk["open"].iloc[0]),
            "high": float(chunk["high"].max()),
            "low": float(chunk["low"].min()),
            "close": float(chunk["close"].iloc[-1]),
            "tick_volume": int(pd.to_numeric(chunk["tick_volume"], errors="raise").sum()),
            "spread": float(pd.to_numeric(chunk["spread"], errors="raise").iloc[-1]),
            "real_volume": int(pd.to_numeric(chunk["real_volume"], errors="raise").sum()),
            "real_volume_available": bool(chunk.get("real_volume_available", pd.Series(False, index=chunk.index)).astype(bool).any()),
            "timeframe": timeframe,
            "source_first_m5_open_utc": pd.Timestamp(chunk["open_time_utc"].iloc[0]),
            "source_last_m5_open_utc": pd.Timestamp(chunk["open_time_utc"].iloc[-1]),
            "source_m5_rows": int(len(chunk)),
        }
        rows.append(derived)
        ref_row = ref.iloc[i]
        err = {c: abs(float(derived[c]) - float(ref_row[c])) for c in PRICE_COLUMNS}
        price_ok = all(v <= price_atol for v in err.values())
        vol_ok = int(derived["tick_volume"]) == int(ref_row.get("tick_volume", derived["tick_volume"]))
        ref_real_available = bool(ref_row.get("real_volume_available", False)) or int(ref_row.get("real_volume", 0)) != 0
        real_volume_required = bool(derived["real_volume_available"]) or ref_real_available
        real_volume_ok = (
            int(derived["real_volume"]) == int(ref_row.get("real_volume", derived["real_volume"]))
            if real_volume_required else True
        )
        parity_rows.append({
            "open_time_utc": left.isoformat(),
            "price_max_abs_error": max(err.values()),
            "price_ok": bool(price_ok),
            "tick_volume_ok": bool(vol_ok),
            "real_volume_required": bool(real_volume_required),
            "real_volume_ok": bool(real_volume_ok),
            "real_volume_status": "EXACT_PARITY" if real_volume_required else "UNAVAILABLE_ZERO_ONLY",
        })
    out = pd.DataFrame(rows)
    bad = [r for r in parity_rows if not r["price_ok"] or not r["tick_volume_ok"] or not r["real_volume_ok"]]
    parity = {
        "schema": "MAX_MTF_DERIVED_NATIVE_PARITY_V1",
        "timeframe": timeframe,
        "status": "PASS" if not bad else "FAIL",
        "compared_closed_bars": len(parity_rows),
        "failed_bars": len(bad),
        "max_price_abs_error": max((r["price_max_abs_error"] for r in parity_rows), default=math.inf),
        "real_volume_mode": (
            "EXACT_PARITY_REQUIRED" if any(r["real_volume_required"] for r in parity_rows)
            else "UNAVAILABLE_ZERO_ONLY"
        ),
        "real_volume_failed_bars": sum(1 for r in parity_rows if not r["real_volume_ok"]),
        "examples": bad[:20],
        "authority": "OHLCV_DERIVED_FROM_M5; TICK_VOLUME_EXACT; REAL_VOLUME_EXACT_WHEN_AVAILABLE; NATIVE_HIGHER_TF_BOUNDARY_AND_PARITY_ONLY",
    }
    if bad:
        raise MTFDataError(f"{timeframe} deterministic M5 resampling does not match native MT5 reference: {parity}")
    return out, parity


def _m5_view(m5: pd.DataFrame) -> pd.DataFrame:
    src = normalize_native_frame(m5, "M5") if "timeframe" not in m5.columns else m5.copy()
    out = src.copy()
    out["close_time_utc"] = pd.to_datetime(out["open_time_utc"], utc=True) + pd.Timedelta(minutes=5)
    out["source_first_m5_open_utc"] = out["open_time_utc"]
    out["source_last_m5_open_utc"] = out["open_time_utc"]
    out["source_m5_rows"] = 1
    return out


def build_canonical_views(
    native_frames: Mapping[str, pd.DataFrame],
    *,
    source_timezone: str | None = None,
    price_atol: float = 1e-10,
    asof_utc: datetime | pd.Timestamp | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    missing = [tf for tf in NATIVE_FRAME_ORDER if tf not in native_frames]
    if missing:
        raise MTFDataError("native frames missing: " + ", ".join(missing))
    normalized = {tf: normalize_native_frame(native_frames[tf], tf, source_timezone=source_timezone) for tf in NATIVE_FRAME_ORDER}
    if asof_utc is not None:
        asof = pd.Timestamp(asof_utc)
        if asof.tzinfo is None:
            raise MTFDataError("asof_utc must be timezone-aware")
        asof = asof.tz_convert("UTC")
        m5_close = pd.to_datetime(normalized["M5"]["open_time_utc"], utc=True) + pd.Timedelta(minutes=5)
        normalized["M5"] = normalized["M5"].loc[m5_close <= asof].reset_index(drop=True)
        if normalized["M5"].empty:
            raise MTFDataError("no fully closed M5 bars at asof_utc")
        # Keep a higher-TF bar open exactly at asof as the right boundary for the
        # preceding fully closed interval, but never derive/copy its still-open values.
        for tf in ("M15", "H1", "H4"):
            opens = pd.to_datetime(normalized[tf]["open_time_utc"], utc=True)
            normalized[tf] = normalized[tf].loc[opens <= asof].reset_index(drop=True)
            if len(normalized[tf]) < 2:
                raise MTFDataError(f"{tf} has insufficient native boundaries at asof_utc")
    # The exact M5 source object is the canonical market-data authority in this
    # phase. A separately fetched reference may be supplied by the caller to
    # audit_m5_against_native_reference before this build; higher-TF native bars
    # are never copied into the canonical feature views.
    views = {"M5": _m5_view(normalized["M5"])}
    parities: dict[str, Any] = {}
    for tf in ("M15", "H1", "H4"):
        views[tf], parities[tf] = _derive_one_from_m5(normalized["M5"], normalized[tf], tf, price_atol=price_atol)
    return views, {
        "schema": "MAX_MTF_RESAMPLING_PARITY_SET_V1",
        "status": "PASS",
        "parity": parities,
        "source_authority": "M5",
        "native_higher_tf_role": "BOUNDARY_AND_PARITY_ONLY",
    }


def build_alignment_index(views: Mapping[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    missing = [tf for tf in NATIVE_FRAME_ORDER if tf not in views]
    if missing:
        raise MTFDataError("canonical views missing: " + ", ".join(missing))

    primary = views["M15"].copy().sort_values("close_time_utc", kind="stable").reset_index(drop=True)
    out = pd.DataFrame({
        "decision_time_utc": pd.to_datetime(primary["close_time_utc"], utc=True),
        "m15_open_time_utc": pd.to_datetime(primary["open_time_utc"], utc=True),
        "m15_close_time_utc": pd.to_datetime(primary["close_time_utc"], utc=True),
    })
    base = out.sort_values("decision_time_utc", kind="stable")
    for tf, prefix in (("H4", "h4"), ("H1", "h1"), ("M5", "m5")):
        src = views[tf].copy().sort_values("close_time_utc", kind="stable")
        right = pd.DataFrame({
            f"{prefix}_open_time_utc": pd.to_datetime(src["open_time_utc"], utc=True),
            f"{prefix}_close_time_utc": pd.to_datetime(src["close_time_utc"], utc=True),
        }).sort_values(f"{prefix}_close_time_utc", kind="stable")
        base = pd.merge_asof(
            base,
            right,
            left_on="decision_time_utc",
            right_on=f"{prefix}_close_time_utc",
            direction="backward",
            allow_exact_matches=True,
        )
    base["alignment_ready"] = base[["h4_close_time_utc", "h1_close_time_utc", "m5_close_time_utc"]].notna().all(axis=1)
    ready = base.loc[base["alignment_ready"]].reset_index(drop=True)
    audit = audit_alignment(ready)
    if audit["status"] != "PASS":
        raise MTFDataError(f"causal alignment failed: {audit}")
    meta = {
        "schema": ALIGNMENT_SCHEMA,
        "status": "PASS",
        "primary_rows": int(len(base)),
        "ready_rows": int(len(ready)),
        "warmup_unaligned_rows": int((~base["alignment_ready"]).sum()),
        "rule": "LATEST_FULLY_CLOSED_ROLE_BAR_WITH_CLOSE_TIME_LE_DECISION_TIME",
        "future_m5_for_direction": "FORBIDDEN",
    }
    return ready, meta


def audit_alignment(alignment: pd.DataFrame) -> dict[str, Any]:
    if alignment.empty:
        return {"schema": ALIGNMENT_SCHEMA, "status": "FAIL", "reason": "EMPTY_ALIGNMENT"}
    t = pd.to_datetime(alignment["decision_time_utc"], utc=True)
    violations: dict[str, int] = {}
    for prefix in ("h4", "h1", "m15", "m5"):
        c = pd.to_datetime(alignment[f"{prefix}_close_time_utc"], utc=True)
        violations[prefix] = int((c > t).sum())
    primary_mismatch = int((pd.to_datetime(alignment["m15_close_time_utc"], utc=True) != t).sum())
    status = "PASS" if sum(violations.values()) == 0 and primary_mismatch == 0 else "FAIL"
    return {
        "schema": ALIGNMENT_SCHEMA,
        "status": status,
        "rows": int(len(alignment)),
        "future_close_violations": violations,
        "primary_close_mismatch": primary_mismatch,
    }


def _canonical_frame_hash(df: pd.DataFrame) -> str:
    x = df.copy()
    for c in x.columns:
        if c.endswith('_time_utc') or c in {'decision_time_utc','open_time_utc','close_time_utc'}:
            x[c] = pd.to_datetime(x[c], utc=True).map(lambda v: v.isoformat())
    payload = x.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_lineage_manifest(
    views: Mapping[str, pd.DataFrame],
    alignment: pd.DataFrame,
    *,
    symbol: str,
    broker_identity: Mapping[str, Any],
    source_identity: Mapping[str, Any] | None = None,
    resampling_parity: Mapping[str, Any] | None = None,
    alignment_meta: Mapping[str, Any] | None = None,
    data_quality: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    frame_hashes = {tf: _canonical_frame_hash(views[tf]) for tf in NATIVE_FRAME_ORDER}
    alignment_hash = _canonical_frame_hash(alignment)
    core = {
        "schema": LINEAGE_SCHEMA,
        "symbol": str(symbol),
        "role_to_timeframe": dict(ROLE_TO_TIMEFRAME),
        "canonical_timezone": "UTC",
        "source_authority": "M5",
        "frame_hashes": frame_hashes,
        "alignment_hash": alignment_hash,
        "broker_identity": dict(broker_identity),
        "source_identity": dict(source_identity or {}),
        "resampling_parity": dict(resampling_parity or {}),
        "alignment_meta": dict(alignment_meta or {}),
        "data_quality": dict(data_quality or {}),
        "closed_bar_only": True,
        "forward_fill": False,
        "future_m5_directional_use": False,
    }
    core["bundle_identity_sha256"] = _stable_json_hash(core)
    return core


def _serialize_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if c.endswith('_time_utc') or c in {'decision_time_utc','open_time_utc','close_time_utc'}:
            out[c] = pd.to_datetime(out[c], utc=True).map(lambda v: v.isoformat())
    return out


def _validated_manifest_binding(
    views: Mapping[str, pd.DataFrame],
    alignment: pd.DataFrame,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute data-bound identity and reject stale/forged manifests."""
    if not isinstance(manifest, Mapping) or manifest.get("schema") != LINEAGE_SCHEMA:
        raise MTFDataError("bundle manifest schema mismatch")
    supplied = dict(manifest)
    expected_frame_hashes = {tf: _canonical_frame_hash(views[tf]) for tf in NATIVE_FRAME_ORDER}
    expected_alignment_hash = _canonical_frame_hash(alignment)
    if supplied.get("frame_hashes") != expected_frame_hashes:
        raise MTFDataError(
            f"bundle manifest frame_hashes do not bind current data: supplied={supplied.get('frame_hashes')} expected={expected_frame_hashes}"
        )
    if supplied.get("alignment_hash") != expected_alignment_hash:
        raise MTFDataError(
            f"bundle manifest alignment_hash does not bind current alignment: supplied={supplied.get('alignment_hash')} expected={expected_alignment_hash}"
        )
    identity_core = dict(supplied)
    supplied_identity = str(identity_core.pop("bundle_identity_sha256", ""))
    expected_identity = _stable_json_hash(identity_core)
    if not supplied_identity or supplied_identity != expected_identity:
        raise MTFDataError(
            f"bundle_identity_sha256 mismatch: supplied={supplied_identity or 'EMPTY'} expected={expected_identity}"
        )
    supplied["bundle_identity_sha256"] = expected_identity
    return supplied


def _readback_canonical_hash(path: Path) -> str:
    frame = pd.read_csv(path)
    return _canonical_frame_hash(frame)


def write_bundle(
    out_dir: str | Path,
    views: Mapping[str, pd.DataFrame],
    alignment: pd.DataFrame,
    manifest: Mapping[str, Any],
    *,
    native_m5_reference: pd.DataFrame | None = None,
    price_atol: float = 1e-10,
) -> dict[str, Any]:
    """Commit one immutable MTF evidence bundle.

    Contract: destination must not exist; current frames/alignment must exactly bind
    the supplied manifest; data are written and verified in a sibling staging
    directory and only then atomically renamed to the final sealed directory.
    """
    out = Path(out_dir)
    parent = out.parent
    parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise MTFDataError(f"sealed bundle destination already exists: {out}")

    verified_manifest = _validated_manifest_binding(views, alignment, manifest)
    _validate_imported_m5_seal_authority(
        views, verified_manifest, native_m5_reference, price_atol=price_atol
    )
    lock_path = parent / f".{out.name}.commit.lock"
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise MTFDataError(f"bundle commit already in progress: {out}") from exc
    os.close(lock_fd)

    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}.staging-", dir=str(parent)))
    committed = False
    try:
        files: dict[str, Path] = {}
        for tf in NATIVE_FRAME_ORDER:
            path = staging / f"{tf}.csv"
            _serialize_for_csv(views[tf]).to_csv(path, index=False, lineterminator="\n", float_format="%.12g")
            files[tf] = path
        ap = staging / "alignment.csv"
        _serialize_for_csv(alignment).to_csv(ap, index=False, lineterminator="\n", float_format="%.12g")
        files["alignment"] = ap
        mp = staging / "manifest.json"
        mp.write_text(json.dumps(verified_manifest, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        files["manifest"] = mp

        # Verify bytes just written still canonicalize to the manifest identities.
        for tf in NATIVE_FRAME_ORDER:
            actual = _readback_canonical_hash(files[tf])
            expected = verified_manifest["frame_hashes"][tf]
            if actual != expected:
                raise MTFDataError(f"staged {tf} readback hash mismatch: {actual} != {expected}")
        actual_alignment = _readback_canonical_hash(ap)
        if actual_alignment != verified_manifest["alignment_hash"]:
            raise MTFDataError(
                f"staged alignment readback hash mismatch: {actual_alignment} != {verified_manifest['alignment_hash']}"
            )
        roundtrip_manifest = json.loads(mp.read_text(encoding="utf-8"))
        _validated_manifest_binding(views, alignment, roundtrip_manifest)

        if out.exists():
            raise MTFDataError(f"sealed bundle destination appeared during commit: {out}")
        os.rename(staging, out)
        committed = True
        final_files = {k: str(out / p.name) for k, p in files.items()}
        return {
            "schema": SCHEMA,
            "status": "PASS",
            "sealed": True,
            "atomic_commit": True,
            "directory": str(out),
            "bundle_identity_sha256": verified_manifest["bundle_identity_sha256"],
            "files": final_files,
        }
    finally:
        if not committed and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def _mt5_available_symbol_names(mt5: Any) -> list[str]:
    """Return a deterministic, de-duplicated broker symbol inventory."""
    rows = mt5.symbols_get()
    if rows is None:
        raise RuntimeError(f"MT5 symbols_get failed: {mt5.last_error()}")
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = str(getattr(row, "name", "") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    names.sort(key=lambda x: (x.casefold(), x))
    return names


def resolve_mt5_broker_symbol(
    mt5: Any,
    *,
    logical_symbol: str,
    broker_symbol_override: str | None = None,
) -> dict[str, Any]:
    """Resolve one executable broker symbol from a logical/base symbol.

    Resolution is intentionally conservative:
      1. explicit exact override, when supplied;
      2. exact case-insensitive logical-symbol match;
      3. exactly one prefix/suffix affix match;
      4. otherwise fail closed.

    The resolver never guesses among multiple broker-specific variants and does
    not contain a broker suffix/prefix allow-list.
    """
    logical = str(logical_symbol or "").strip()
    if not logical:
        raise MTFDataError("logical_symbol is required")
    override = str(broker_symbol_override or "").strip() or None
    names = _mt5_available_symbol_names(mt5)

    if override is not None:
        if override not in names:
            raise RuntimeError(
                "MT5 explicit broker symbol override unavailable: "
                f"requested={override!r}; logical_symbol={logical!r}"
            )
        return {
            "logical_symbol": logical,
            "resolved_broker_symbol": override,
            "symbol_resolution_method": "EXPLICIT_OVERRIDE",
            "symbol_resolution_candidates": [override],
            "broker_symbol_override": override,
        }

    logical_cf = logical.casefold()
    exact = [name for name in names if name.casefold() == logical_cf]
    if len(exact) == 1:
        return {
            "logical_symbol": logical,
            "resolved_broker_symbol": exact[0],
            "symbol_resolution_method": "EXACT",
            "symbol_resolution_candidates": list(exact),
            "broker_symbol_override": None,
        }
    if len(exact) > 1:
        raise RuntimeError(
            "MT5 logical symbol exact-match ambiguity: "
            f"logical_symbol={logical!r}; candidates={exact}"
        )

    affix = [
        name for name in names
        if name.casefold() != logical_cf
        and (name.casefold().startswith(logical_cf) or name.casefold().endswith(logical_cf))
    ]
    if len(affix) == 1:
        return {
            "logical_symbol": logical,
            "resolved_broker_symbol": affix[0],
            "symbol_resolution_method": "UNIQUE_SUFFIX_OR_PREFIX",
            "symbol_resolution_candidates": list(affix),
            "broker_symbol_override": None,
        }
    if len(affix) > 1:
        raise RuntimeError(
            "MT5 logical symbol broker-affix ambiguity; explicit broker_symbol_override required: "
            f"logical_symbol={logical!r}; candidates={affix}"
        )

    # Helpful fail-closed diagnostics without changing the resolution rule.
    token_candidates: list[str] = []
    anchors = {logical_cf}
    if len(logical_cf) >= 6:
        anchors.update({logical_cf[:3], logical_cf[-3:]})
    for name in names:
        folded = name.casefold()
        if any(anchor and anchor in folded for anchor in anchors):
            token_candidates.append(name)
        if len(token_candidates) >= 50:
            break
    raise RuntimeError(
        "MT5 logical symbol not found: "
        f"logical_symbol={logical!r}; compatible_candidates=[]; "
        f"relevant_available_symbols={token_candidates}"
    )


def collect_native_frames_from_mt5(
    *,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    terminal_exe: str | Path | None = None,
    broker_symbol_override: str | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Owner-runtime collector using one resolved broker symbol authority.

    ``symbol`` is the logical/base symbol. After terminal initialization the
    broker-specific executable symbol is resolved exactly once, selected once,
    and then used for every native timeframe fetch and downstream provenance.
    """
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise MTFDataError("start_utc/end_utc must be timezone-aware")
    if end_utc <= start_utc:
        raise MTFDataError("end_utc must be after start_utc")
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"MetaTrader5 Python package unavailable: {exc}") from exc
    initialized = False
    try:
        ok = mt5.initialize(path=str(terminal_exe)) if terminal_exe else mt5.initialize()
        if not ok:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        initialized = True
        resolution = resolve_mt5_broker_symbol(
            mt5,
            logical_symbol=symbol,
            broker_symbol_override=broker_symbol_override,
        )
        resolved_symbol = str(resolution["resolved_broker_symbol"])
        if not mt5.symbol_select(resolved_symbol, True):
            raise RuntimeError(f"MT5 symbol_select failed for {resolved_symbol}: {mt5.last_error()}")
        mapping = {
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
        }
        frames: dict[str, pd.DataFrame] = {}
        for tf, constant in mapping.items():
            rates = mt5.copy_rates_range(
                resolved_symbol,
                constant,
                start_utc.astimezone(timezone.utc),
                end_utc.astimezone(timezone.utc),
            )
            if rates is None or len(rates) == 0:
                raise RuntimeError(
                    f"MT5 copy_rates_range empty for {resolved_symbol} {tf}: {mt5.last_error()}"
                )
            frames[tf] = pd.DataFrame(rates)
        ai = mt5.account_info()
        ti = mt5.terminal_info()
        terminal_path = getattr(ti, "path", None) if ti is not None else None
        terminal_data_path = getattr(ti, "data_path", None) if ti is not None else None
        server = getattr(ai, "server", None) if ai is not None else None
        identity = {
            "symbol": resolved_symbol,
            **resolution,
            "server": server,
            "terminal_path": terminal_path,
            "terminal_data_path": terminal_data_path,
            "terminal_identity": {
                "path": terminal_path,
                "data_path": terminal_data_path,
                "build": getattr(ti, "build", None) if ti is not None else None,
                "name": getattr(ti, "name", None) if ti is not None else None,
            },
            "broker_identity": {
                "server": server,
                "company": getattr(ai, "company", None) if ai is not None else None,
            },
            "start_utc": start_utc.astimezone(timezone.utc).isoformat(),
            "end_utc": end_utc.astimezone(timezone.utc).isoformat(),
        }
        return frames, identity
    finally:
        if initialized:
            mt5.shutdown()
