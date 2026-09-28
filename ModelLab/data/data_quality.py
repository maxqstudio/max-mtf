from __future__ import annotations

import math
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.contract import CONTRACT_ID, FEATURES, REQUIRED_COLUMNS
from data.dataset_integrity import integrity_summary, read_csv_auto, sha256_file, writer_lock

SCHEMA = "MAX_DATA_QUALITY_V3"


BROKER_PROOF_SCHEMA = "MAX_BROKER_PROOF_V1"
def _broker_proof_dir() -> Path:
    base=os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)/"MaxMTF"/"data_quality_proofs"
    return Path.home()/".max_research_agent"/"onnx_factory"/"data_quality_proofs"


def _broker_proof_path(dataset_sha256: str) -> Path:
    token=str(dataset_sha256 or "").strip().lower()
    if not token:
        raise ValueError("dataset SHA256 required for broker proof")
    return _broker_proof_dir() / f"broker_{token}.json"


def _load_cached_broker_proof(dataset_sha256: str) -> dict[str, Any] | None:
    """Load only an exact-byte broker proof. Never launches MT5."""
    try:
        q=_broker_proof_path(dataset_sha256)
        if not q.is_file():
            return None
        obj=json.loads(q.read_text(encoding="utf-8"))
        if str(obj.get("schema") or "") != BROKER_PROOF_SCHEMA:
            return None
        if str(obj.get("dataset_sha256") or "").lower() != str(dataset_sha256 or "").lower():
            return None
        broker=dict(obj.get("broker_reconciliation") or {})
        if not broker.get("verified"):
            return None
        broker["proof_cache"]="EXACT_DATASET_SHA256"
        broker["proof_cached_utc"]=obj.get("generated_utc")
        return broker
    except Exception:
        return None


def _save_cached_broker_proof(dataset_sha256: str, broker: dict[str, Any]) -> None:
    """Persist verified broker evidence for the exact immutable CSV bytes."""
    if not broker.get("verified") or not dataset_sha256:
        return
    _broker_proof_dir().mkdir(parents=True, exist_ok=True)
    q=_broker_proof_path(dataset_sha256)
    payload={
        "schema":BROKER_PROOF_SCHEMA,
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "dataset_sha256":str(dataset_sha256),
        "broker_reconciliation":dict(broker),
    }
    tmp=q.with_suffix(q.suffix+".tmp")
    tmp.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    tmp.replace(q)


def _period_seconds(period: Any) -> int | None:
    try:
        p = int(float(period))
    except Exception:
        return None
    mapping = {
        1:60,2:120,3:180,4:240,5:300,6:360,10:600,12:720,15:900,20:1200,30:1800,
        60:3600,120:7200,180:10800,240:14400,360:21600,480:28800,720:43200,1440:86400,
        10080:604800,43200:2592000,
        16385:3600,16386:7200,16387:10800,16388:14400,16390:21600,16392:28800,
        16396:43200,16408:86400,32769:604800,49153:2592000,
    }
    return mapping.get(p)


def _period_label(period: Any) -> str:
    sec = _period_seconds(period)
    if sec is None:
        return str(period)
    if sec < 3600:
        return f"M{sec//60}"
    if sec < 86400:
        return f"H{sec//3600}"
    if sec == 86400:
        return "D1"
    if sec == 604800:
        return "W1"
    return "MN1"


def _mt5_timeframe(mt5, period: Any):
    label = _period_label(period)
    attr = "TIMEFRAME_" + label
    return getattr(mt5, attr, None)


def _finite_series(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)


def _feature_health(df: pd.DataFrame) -> dict[str, Any]:
    rows = []
    hard_fail = 0
    warnings = 0
    for name in FEATURES:
        arr = _finite_series(df[name])
        finite = np.isfinite(arr)
        finite_count = int(finite.sum())
        nonfinite = int(len(arr) - finite_count)
        if finite_count:
            x = arr[finite]
            std = float(np.std(x))
            mn = float(np.min(x)); mx = float(np.max(x)); med = float(np.median(x))
            zero_ratio = float(np.mean(np.isclose(x, 0.0, rtol=0.0, atol=1e-15)))
            constant = bool(std <= 1e-14 or math.isclose(mn, mx, rel_tol=0.0, abs_tol=1e-14))
        else:
            std = mn = mx = med = float("nan"); zero_ratio = 1.0; constant = True
        status = "PASS"
        if nonfinite:
            status = "FAIL_NONFINITE"; hard_fail += 1
        elif constant:
            status = "WARN_CONSTANT"; warnings += 1
        elif zero_ratio >= 0.995:
            status = "WARN_ALMOST_ZERO"; warnings += 1
        rows.append({
            "feature": name,
            "status": status,
            "finite_rows": finite_count,
            "nonfinite_rows": nonfinite,
            "min": mn,
            "median": med,
            "max": mx,
            "std": std,
            "zero_ratio": zero_ratio,
        })
    return {"rows": rows, "hard_failures": hard_fail, "warnings": warnings}


def _market_sanity(df: pd.DataFrame) -> dict[str, int]:
    o = _finite_series(df["open"]); h = _finite_series(df["high"]); l = _finite_series(df["low"]); c = _finite_series(df["close"])
    atr = _finite_series(df["atr"]); bid = _finite_series(df["decision_bid"]); ask = _finite_series(df["decision_ask"])
    finite_ohlc = np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c)
    invalid_ohlc = (~finite_ohlc) | (h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l) | (o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)
    invalid_atr = (~np.isfinite(atr)) | (atr <= 0)

    # Quote authority distinguishes a legitimate/sourced zero-spread observation
    # from a structurally impossible quote.  ask == bid is not corrupt data by
    # itself and must not block an entire research dataset; it remains visible as
    # a warning because zero transaction cost can be optimistic.  Hard failure is
    # reserved for non-finite/non-positive quotes or an inverted ask < bid.
    quote_nonfinite = (~np.isfinite(bid)) | (~np.isfinite(ask))
    quote_nonpositive = np.isfinite(bid) & np.isfinite(ask) & ((bid <= 0) | (ask <= 0))
    quote_inverted = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > 0) & (ask < bid)
    quote_zero_spread = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > 0) & np.isclose(ask, bid, rtol=0.0, atol=1e-15)
    invalid_quote = quote_nonfinite | quote_nonpositive | quote_inverted
    return {
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "invalid_atr_rows": int(invalid_atr.sum()),
        "invalid_decision_quote_rows": int(invalid_quote.sum()),
        "zero_spread_decision_quote_rows": int(quote_zero_spread.sum()),
        "quote_nonfinite_rows": int(quote_nonfinite.sum()),
        "quote_nonpositive_rows": int(quote_nonpositive.sum()),
        "quote_inverted_rows": int(quote_inverted.sum()),
    }


def _observed_discontinuities(ts: pd.Series, period: Any) -> dict[str, Any]:
    seconds = _period_seconds(period)
    if not seconds or len(ts) < 2:
        return {"nominal_seconds": seconds, "count": 0, "largest_missing_slots": 0, "examples": []}
    vals = pd.Series(pd.to_datetime(ts, errors="coerce")).dropna().sort_values().drop_duplicates().reset_index(drop=True)
    delta = vals.diff().dt.total_seconds()
    rows = []
    for i in np.where((delta.to_numpy(dtype=float) > seconds * 1.5) & np.isfinite(delta.to_numpy(dtype=float)))[0]:
        slots = max(0, int(round(float(delta.iloc[i]) / seconds)) - 1)
        rows.append({"from": vals.iloc[i-1].isoformat(), "to": vals.iloc[i].isoformat(), "nominal_missing_slots": slots})
    rows.sort(key=lambda r: r["nominal_missing_slots"], reverse=True)
    return {
        "nominal_seconds": int(seconds),
        "count": len(rows),
        "largest_missing_slots": int(rows[0]["nominal_missing_slots"] if rows else 0),
        "examples": rows[:25],
        "authority": "OBSERVED_ONLY_NOT_MISSING_AUTHORITY",
    }


def _best_time_shift(dataset_times: set[pd.Timestamp], reference_times: list[pd.Timestamp]) -> tuple[int, int, float]:
    if not dataset_times or not reference_times:
        return 0, 0, 0.0
    # Broker chart/server time can differ from Python UTC conversion. Infer the
    # stable offset by maximizing exact overlap. 30-minute increments cover the
    # common full/half-hour broker offsets without guessing a timezone name.
    best = (0, -1, 0.0)
    denom = max(1, min(len(dataset_times), len(reference_times)))
    ref = pd.DatetimeIndex(reference_times)
    for minutes in range(-14*60, 14*60 + 1, 30):
        shifted = set((ref + pd.Timedelta(minutes=minutes)).to_pydatetime())
        score = sum(1 for x in dataset_times if x.to_pydatetime() in shifted)
        ratio = score / denom
        if score > best[1] or (score == best[1] and ratio > best[2]):
            best = (minutes, score, ratio)
    return best


def _broker_reconcile(df: pd.DataFrame, terminal_exe: str | Path | None = None) -> dict[str, Any]:
    base = {
        "status": "UNAVAILABLE",
        "verified": False,
        "reason": None,
        "source_backed_missing_count": 0,
        "dataset_only_count": 0,
        "missing_timestamps": [],
        "dataset_only_timestamps": [],
        "server": None,
        "terminal_path": None,
        "terminal_data_path": None,
        "time_shift_minutes": None,
        "match_ratio": 0.0,
        "ohlc_match_ratio": 0.0,
        "ohlc_tolerance": None,
        "ohlc_p99_abs_error": None,
    }
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:
        base["reason"] = f"METATRADER5_PYTHON_NOT_INSTALLED: {exc}"
        return base
    tf = _mt5_timeframe(mt5, df["period"].iloc[0])
    if tf is None:
        base["reason"] = f"UNSUPPORTED_TIMEFRAME: {df['period'].iloc[0]}"
        return base
    initialized = False
    try:
        init_ok = mt5.initialize(path=str(terminal_exe)) if terminal_exe else mt5.initialize()
        if not init_ok:
            base["reason"] = f"MT5_INITIALIZE_FAILED: {mt5.last_error()}"
            return base
        initialized = True
        symbol = str(df["symbol"].iloc[0])
        if not mt5.symbol_select(symbol, True):
            base["reason"] = f"MT5_SYMBOL_SELECT_FAILED: {symbol} {mt5.last_error()}"
            return base
        start = pd.Timestamp(df["signal_time"].min()) - pd.Timedelta(days=7)
        end = pd.Timestamp(df["signal_time"].max()) + pd.Timedelta(days=1)
        # MT5 Python API expects UTC datetimes. A server/chart offset is inferred
        # below from the exact overlap with the already authoritative CSV rows.
        s_utc = start.to_pydatetime().replace(tzinfo=timezone.utc)
        e_utc = end.to_pydatetime().replace(tzinfo=timezone.utc)
        rates = mt5.copy_rates_range(symbol, tf, s_utc, e_utc)
        if rates is None or len(rates) == 0:
            base["reason"] = f"MT5_COPY_RATES_EMPTY: {mt5.last_error()}"
            return base
        ref = [pd.Timestamp(datetime.fromtimestamp(int(x), tz=timezone.utc).replace(tzinfo=None)) for x in rates["time"]]
        dset = set(pd.to_datetime(df["signal_time"], errors="coerce").dropna().dt.floor("s"))
        minutes, matches, ratio = _best_time_shift(dset, ref)
        base["time_shift_minutes"] = int(minutes); base["match_ratio"] = float(ratio)
        # Fail closed: timestamps alone are not enough to prove this is the same
        # broker/feed.  First establish high timestamp overlap, then reconcile
        # OHLC values against the broker bars with the symbol point as tolerance.
        if ratio < 0.90:
            base["status"] = "UNVERIFIED"
            base["reason"] = f"BROKER_TIMESTAMP_ALIGNMENT_LOW: {matches} matches ratio={ratio:.4f}"
            return base

        ref_df = pd.DataFrame({
            "signal_time": (pd.DatetimeIndex(ref) + pd.Timedelta(minutes=minutes)).floor("s"),
            "ref_open": np.asarray(rates["open"], dtype=float),
            "ref_high": np.asarray(rates["high"], dtype=float),
            "ref_low": np.asarray(rates["low"], dtype=float),
            "ref_close": np.asarray(rates["close"], dtype=float),
        }).drop_duplicates("signal_time", keep="first")
        cmp_df = df[["signal_time","open","high","low","close"]].copy()
        cmp_df["signal_time"] = pd.to_datetime(cmp_df["signal_time"], errors="coerce").dt.floor("s")
        cmp_df = cmp_df.merge(ref_df, on="signal_time", how="inner")
        info = mt5.symbol_info(symbol)
        point = float(getattr(info, "point", 0.0) or 0.0) if info is not None else 0.0
        tol = max(point * 0.51, 1e-9)
        base["ohlc_tolerance"] = tol
        if cmp_df.empty:
            base["status"] = "UNVERIFIED"
            base["reason"] = "BROKER_OHLC_RECONCILIATION_EMPTY"
            return base
        errs=[]
        row_ok=np.ones(len(cmp_df), dtype=bool)
        for col in ("open","high","low","close"):
            e=np.abs(pd.to_numeric(cmp_df[col],errors="coerce").to_numpy(dtype=float)-pd.to_numeric(cmp_df[f"ref_{col}"],errors="coerce").to_numpy(dtype=float))
            errs.append(e)
            row_ok &= np.isfinite(e) & (e <= tol)
        err_all=np.concatenate(errs) if errs else np.asarray([],dtype=float)
        ohlc_ratio=float(np.mean(row_ok)) if len(row_ok) else 0.0
        base["ohlc_match_ratio"] = ohlc_ratio
        base["ohlc_p99_abs_error"] = float(np.nanpercentile(err_all,99)) if len(err_all) else None
        if ohlc_ratio < 0.98:
            base["status"] = "UNVERIFIED"
            base["reason"] = f"BROKER_OHLC_MATCH_LOW: ratio={ohlc_ratio:.4f} tolerance={tol:.10g}"
            return base

        shifted = set(ref_df["signal_time"])
        lo = pd.Timestamp(df["signal_time"].min()).floor("s"); hi = pd.Timestamp(df["signal_time"].max()).floor("s")
        shifted = {x for x in shifted if lo <= x <= hi}
        missing = sorted(shifted - dset)
        extra = sorted(dset - shifted)
        ai = mt5.account_info()
        ti = mt5.terminal_info()
        base.update({
            "status": "VERIFIED",
            "verified": True,
            "source_backed_missing_count": len(missing),
            "dataset_only_count": len(extra),
            "missing_timestamps": [x.isoformat() for x in missing[:5000]],
            "dataset_only_timestamps": [x.isoformat() for x in extra[:5000]],
            "reference_rows": len(shifted),
            "matched_rows": len(dset & shifted),
            "server": getattr(ai, "server", None) if ai else None,
            "terminal_path": getattr(ti, "path", None) if ti else None,
            "terminal_data_path": getattr(ti, "data_path", None) if ti else None,
        })
        return base
    except Exception as exc:
        base["reason"] = f"BROKER_RECONCILE_ERROR: {exc}"
        return base
    finally:
        if initialized:
            try:
                mt5.shutdown()
            except Exception:
                pass


def audit_dataset(path: str | Path, *, broker_reconcile: bool = True, use_cached_broker_proof: bool = True, broker_terminal_exe: str | Path | None = None) -> dict[str, Any]:
    p = Path(path)
    # Bind bytes, parsed rows and SHA to one writer-serialized source revision.
    with writer_lock(p):
        physical = integrity_summary(p, _lock_held=True)
        df = read_csv_auto(p)
    hard_reasons: list[str] = []
    warnings: list[str] = []

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        hard_reasons.append("MISSING_REQUIRED_COLUMNS:" + ",".join(missing_cols))
        return {
            "schema": SCHEMA, "status": "INVALID", "path": str(p), "sha256": physical.get("sha256"),
            "hard_reasons": hard_reasons, "warnings": warnings, "physical": physical,
        }
    if physical.get("duplicate_extra_rows", 0):
        hard_reasons.append(f"DUPLICATE_IDENTITY_ROWS:{physical['duplicate_extra_rows']}")
    if df[["symbol", "period"]].drop_duplicates().shape[0] != 1:
        hard_reasons.append("MIXED_SYMBOL_OR_TIMEFRAME")
    if not (df["contract"].astype(str) == CONTRACT_ID).all():
        hard_reasons.append("UNEXPECTED_FEATURE_CONTRACT")

    df = df.copy()
    df["signal_time"] = pd.to_datetime(df["signal_time"], errors="coerce")
    if df["signal_time"].isna().any():
        hard_reasons.append(f"INVALID_SIGNAL_TIME:{int(df['signal_time'].isna().sum())}")
    df = df.dropna(subset=["signal_time"]).sort_values("signal_time", kind="stable").reset_index(drop=True)
    if len(df) == 0:
        hard_reasons.append("NO_VALID_ROWS")

    market = _market_sanity(df) if len(df) else {"invalid_ohlc_rows":0,"invalid_atr_rows":0,"invalid_decision_quote_rows":0,"zero_spread_decision_quote_rows":0,"quote_nonfinite_rows":0,"quote_nonpositive_rows":0,"quote_inverted_rows":0}
    if market["invalid_ohlc_rows"]:
        hard_reasons.append(f"INVALID_OHLC_ROWS:{market['invalid_ohlc_rows']}")
    if market["invalid_atr_rows"]:
        hard_reasons.append(f"INVALID_ATR_ROWS:{market['invalid_atr_rows']}")
    if market["invalid_decision_quote_rows"]:
        hard_reasons.append(f"INVALID_DECISION_QUOTE_ROWS:{market['invalid_decision_quote_rows']}")
    if market.get("zero_spread_decision_quote_rows", 0):
        warnings.append(f"ZERO_SPREAD_DECISION_QUOTE_ROWS:{market['zero_spread_decision_quote_rows']}")

    features = _feature_health(df) if len(df) else {"rows":[],"hard_failures":0,"warnings":0}
    if features["hard_failures"]:
        hard_reasons.append(f"FEATURE_NONFINITE:{features['hard_failures']}")
    if features["warnings"]:
        warnings.append(f"FEATURE_HEALTH_WARNINGS:{features['warnings']}")

    period = None
    if len(df):
        try:
            period = int(float(df["period"].iloc[0]))
        except Exception:
            hard_reasons.append("INVALID_PERIOD")
        symbol = str(df["symbol"].iloc[0]).strip()
        if not symbol:
            hard_reasons.append("INVALID_SYMBOL")
        if period is not None and _period_seconds(period) is None:
            hard_reasons.append(f"UNSUPPORTED_TIMEFRAME:{period}")
    observed = _observed_discontinuities(df["signal_time"], period) if len(df) and period is not None else {}
    if broker_reconcile and len(df):
        broker = _broker_reconcile(df, terminal_exe=broker_terminal_exe) if broker_terminal_exe else _broker_reconcile(df)
    elif use_cached_broker_proof and len(df):
        broker = _load_cached_broker_proof(str(physical.get("sha256") or "")) or {"status":"SKIPPED","verified":False,"source_backed_missing_count":0,"reason":"BROKER_PROOF_CACHE_MISS"}
    else:
        broker = {"status":"SKIPPED","verified":False,"source_backed_missing_count":0,"reason":"BROKER_RECONCILE_DISABLED"}
    if not broker.get("verified"):
        warnings.append("BROKER_RECONCILIATION_NOT_VERIFIED")
    elif int(broker.get("dataset_only_count", 0) or 0) > 0:
        warnings.append(f"DATASET_ONLY_TIMESTAMPS:{int(broker.get('dataset_only_count',0))}")

    if hard_reasons:
        status = "INVALID"
    elif broker.get("verified") and int(broker.get("source_backed_missing_count", 0) or 0) > 0:
        status = "INCOMPLETE"
    elif warnings:
        status = "VALID_WITH_WARNINGS"
    else:
        status = "VALID"

    if broker_reconcile and broker.get("verified"):
        _save_cached_broker_proof(str(physical.get("sha256") or ""), broker)

    return {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "path": str(p),
        "sha256": str(physical.get("sha256") or ""),
        "identity": {
            "symbol": str(df["symbol"].iloc[0]) if len(df) else None,
            "period": period,
            "timeframe": _period_label(period) if period is not None else None,
            "rows": int(len(df)),
            "start": df["signal_time"].min().isoformat() if len(df) else None,
            "end": df["signal_time"].max().isoformat() if len(df) else None,
        },
        "physical": physical,
        "market_sanity": market,
        "feature_health": features,
        "observed_discontinuities": observed,
        "broker_reconciliation": broker,
        "hard_reasons": hard_reasons,
        "warnings": warnings,
    }


def llm_data_quality_context(report: dict[str, Any]) -> dict[str, Any]:
    """Bounded, row-free context for LLM Data Review."""
    b = dict(report.get("broker_reconciliation") or {})
    f = dict(report.get("feature_health") or {})
    return {
        "schema": "MAX_LLM_DATA_QUALITY_CONTEXT_V1",
        "quality_status": report.get("status"),
        "dataset": dict(report.get("identity") or {}),
        "duplicates": int((report.get("physical") or {}).get("duplicate_extra_rows", 0) or 0),
        "market_sanity": dict(report.get("market_sanity") or {}),
        "feature_health": {
            "hard_failures": int(f.get("hard_failures", 0) or 0),
            "warnings": int(f.get("warnings", 0) or 0),
            "warning_features": [r.get("feature") for r in (f.get("rows") or []) if str(r.get("status")) != "PASS"][:32],
        },
        "continuity": {
            "broker_verified": bool(b.get("verified")),
            "broker_server": b.get("server"),
            "timestamp_match_ratio": float(b.get("match_ratio",0.0) or 0.0),
            "ohlc_match_ratio": float(b.get("ohlc_match_ratio",0.0) or 0.0),
            "source_backed_missing": int(b.get("source_backed_missing_count", 0) or 0),
            "dataset_only": int(b.get("dataset_only_count", 0) or 0),
            "observed_discontinuities": int((report.get("observed_discontinuities") or {}).get("count", 0) or 0),
            "largest_nominal_gap_slots": int((report.get("observed_discontinuities") or {}).get("largest_missing_slots", 0) or 0),
        },
        "hard_reasons": list(report.get("hard_reasons") or []),
        "warnings": list(report.get("warnings") or []),
    }


def research_readiness(report: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons=[]
    if str(report.get("status")) == "INVALID":
        reasons.extend(str(x) for x in (report.get("hard_reasons") or []))
    b=dict(report.get("broker_reconciliation") or {})
    if not b.get("verified"):
        reasons.append("BROKER_RECONCILIATION_REQUIRED")
    if int(b.get("source_backed_missing_count",0) or 0)>0:
        reasons.append(f"SOURCE_BACKED_MISSING_BARS:{int(b.get('source_backed_missing_count',0) or 0)}")
    if int(b.get("dataset_only_count",0) or 0)>0:
        reasons.append(f"DATASET_ONLY_TIMESTAMPS:{int(b.get('dataset_only_count',0) or 0)}")
    return (len(reasons)==0), reasons
