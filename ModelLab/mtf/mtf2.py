from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from mtf.mtf_data import NATIVE_FRAME_ORDER, audit_alignment

CONTRACT_ID = "MAX_MTF2_ROLE_FEATURE_LABEL_V3"
SCHEMA = "MAX_MTF2_DATASET_V1"
LABEL_SCHEMA = "MTF2_DIRECTIONAL_LABEL_V1"

ROLE_TO_TIMEFRAME = {
    "TF+2": "H4",
    "TF+1": "H1",
    "TF": "M15",
    "TF-1": "M5",
}

FEATURE_PRIMITIVES = (
    {"id": "ret_1_atr", "source_columns": ["close", "high", "low"], "lookback_bars": 15, "formula": "clip((close_t-close_t-1)/atr14_sma_t,-5,5)"},
    {"id": "ret_3_atr", "source_columns": ["close", "high", "low"], "lookback_bars": 15, "formula": "clip((close_t-close_t-3)/atr14_sma_t,-8,8)"},
    {"id": "ret_6_atr", "source_columns": ["close", "high", "low"], "lookback_bars": 15, "formula": "clip((close_t-close_t-6)/atr14_sma_t,-12,12)"},
    {"id": "ret_20_atr", "source_columns": ["close", "high", "low"], "lookback_bars": 21, "formula": "clip((close_t-close_t-20)/atr14_sma_t,-20,20)"},
    {"id": "atr_ratio_14_50", "source_columns": ["high", "low", "close"], "lookback_bars": 51, "formula": "clip(atr14_sma_t/atr50_sma_t,0,4)"},
    {"id": "efficiency_10", "source_columns": ["close"], "lookback_bars": 11, "formula": "abs(close_t-close_t-10)/sum(abs(close_i-close_i-1),i=t-9..t); zero path => 0"},
    {"id": "range_position_20", "source_columns": ["high", "low", "close"], "lookback_bars": 20, "formula": "clip(2*(close_t-min(low_t-19..t))/(max(high_t-19..t)-min(low_t-19..t))-1,-1,1); zero span => 0"},
    {"id": "distance_high_20_atr", "source_columns": ["high", "low", "close"], "lookback_bars": 21, "formula": "clip((close_t-max(high_t-20..t-1))/atr14_sma_t,-10,10)"},
    {"id": "distance_low_20_atr", "source_columns": ["high", "low", "close"], "lookback_bars": 21, "formula": "clip((close_t-min(low_t-20..t-1))/atr14_sma_t,-10,10)"},
    {"id": "range_atr", "source_columns": ["high", "low", "close"], "lookback_bars": 15, "formula": "clip((high_t-low_t)/atr14_sma_t,0,8)"},
    {"id": "signed_body_atr", "source_columns": ["open", "close", "high", "low"], "lookback_bars": 15, "formula": "clip((close_t-open_t)/atr14_sma_t,-5,5)"},
    {"id": "upper_wick_atr", "source_columns": ["open", "high", "close", "low"], "lookback_bars": 15, "formula": "clip((high_t-max(open_t,close_t))/atr14_sma_t,0,5)"},
    {"id": "lower_wick_atr", "source_columns": ["open", "high", "close", "low"], "lookback_bars": 15, "formula": "clip((min(open_t,close_t)-low_t)/atr14_sma_t,0,5)"},
    {"id": "tick_volume_z_30", "source_columns": ["tick_volume"], "lookback_bars": 30, "formula": "clip(zscore_current_over_last_30,-5,5); zero variance => 0"},
    {"id": "spread_z_30", "source_columns": ["spread"], "lookback_bars": 30, "formula": "clip(zscore_current_over_last_30,-5,5); zero variance => 0"},
    {"id": "hour_sin", "source_columns": ["close_time_utc"], "lookback_bars": 1, "formula": "sin(2*pi*UTC_hour/24)"},
    {"id": "hour_cos", "source_columns": ["close_time_utc"], "lookback_bars": 1, "formula": "cos(2*pi*UTC_hour/24)"},
)

ROLE_FEATURES = {
    "TF+2": {"timeframe": "H4", "role": "context_regime", "features": ["ret_6_atr", "ret_20_atr", "atr_ratio_14_50", "efficiency_10", "range_position_20", "range_atr"]},
    "TF+1": {"timeframe": "H1", "role": "setup", "features": ["ret_1_atr", "ret_3_atr", "ret_6_atr", "distance_high_20_atr", "distance_low_20_atr", "efficiency_10", "range_position_20", "range_atr", "tick_volume_z_30"]},
    "TF": {"timeframe": "M15", "role": "primary_direction", "features": ["ret_1_atr", "ret_3_atr", "ret_6_atr", "distance_high_20_atr", "distance_low_20_atr", "efficiency_10", "range_position_20", "atr_ratio_14_50", "range_atr", "upper_wick_atr", "lower_wick_atr", "tick_volume_z_30", "hour_sin", "hour_cos"]},
    "TF-1": {"timeframe": "M5", "role": "closed_execution_context_only", "features": ["ret_1_atr", "ret_3_atr", "range_position_20", "range_atr", "upper_wick_atr", "lower_wick_atr", "tick_volume_z_30", "spread_z_30"]},
}

ABLATION_ROLES = {
    "A": ("TF",),
    "B": ("TF+1", "TF"),
    "C": ("TF+2", "TF+1", "TF"),
    "D": ("TF+2", "TF+1", "TF", "TF-1"),
}

_PRIMITIVE_BY_ID = {row["id"]: row for row in FEATURE_PRIMITIVES}
_ROLE_PREFIX = {"H4": "h4", "H1": "h1", "M15": "m15", "M5": "m5"}


class MTF2Error(ValueError):
    pass


def feature_schema_payload() -> dict[str, Any]:
    return {
        "contract_id": CONTRACT_ID,
        "schema_version": 3,
        "primitive_registry": [dict(row) for row in FEATURE_PRIMITIVES],
        "role_features": {role: dict(spec) for role, spec in ROLE_FEATURES.items()},
    }


def feature_schema_sha256() -> str:
    raw = json.dumps(feature_schema_payload(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require_columns(frame: pd.DataFrame, timeframe: str) -> None:
    required = {"open_time_utc", "close_time_utc", "open", "high", "low", "close", "tick_volume", "spread"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise MTF2Error(f"{timeframe} missing columns: {missing}")
    if frame.empty:
        raise MTF2Error(f"{timeframe} frame is empty")


def _numeric(frame: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(frame[name], errors="raise").astype(float)


def _zscore_last(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std(ddof=0)
    z = (series - mean) / std.replace(0.0, np.nan)
    zero_var = std.eq(0.0) & mean.notna()
    return z.where(~zero_var, 0.0)


def _primitive_frame(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    _require_columns(frame, timeframe)
    src = frame.copy().sort_values("close_time_utc", kind="stable").reset_index(drop=True)
    opens = pd.to_datetime(src["open_time_utc"], utc=True, errors="raise")
    closes = pd.to_datetime(src["close_time_utc"], utc=True, errors="raise")
    if bool(opens.duplicated().any()) or bool(closes.duplicated().any()) or not bool(closes.is_monotonic_increasing):
        raise MTF2Error(f"{timeframe} timestamps are not unique monotonic authority")

    o, h, l, c = (_numeric(src, x) for x in ("open", "high", "low", "close"))
    tv = _numeric(src, "tick_volume")
    spread = _numeric(src, "spread")
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1, skipna=False)
    atr14 = tr.rolling(14, min_periods=14).mean()
    atr50 = tr.rolling(50, min_periods=50).mean()
    safe_atr = atr14.replace(0.0, np.nan)

    out = pd.DataFrame({"open_time_utc": opens, "close_time_utc": closes})
    out["_atr14_sma"] = atr14
    out["ret_1_atr"] = ((c - c.shift(1)) / safe_atr).clip(-5.0, 5.0)
    out["ret_3_atr"] = ((c - c.shift(3)) / safe_atr).clip(-8.0, 8.0)
    out["ret_6_atr"] = ((c - c.shift(6)) / safe_atr).clip(-12.0, 12.0)
    out["ret_20_atr"] = ((c - c.shift(20)) / safe_atr).clip(-20.0, 20.0)
    out["atr_ratio_14_50"] = (atr14 / atr50.replace(0.0, np.nan)).clip(0.0, 4.0)

    step = c.diff().abs()
    path10 = step.rolling(10, min_periods=10).sum()
    eff = (c - c.shift(10)).abs() / path10.replace(0.0, np.nan)
    out["efficiency_10"] = eff.where(~path10.eq(0.0), 0.0)

    hi20 = h.rolling(20, min_periods=20).max()
    lo20 = l.rolling(20, min_periods=20).min()
    span20 = hi20 - lo20
    rp = 2.0 * (c - lo20) / span20.replace(0.0, np.nan) - 1.0
    out["range_position_20"] = rp.where(~span20.eq(0.0), 0.0).clip(-1.0, 1.0)

    prior_hi20 = h.shift(1).rolling(20, min_periods=20).max()
    prior_lo20 = l.shift(1).rolling(20, min_periods=20).min()
    out["distance_high_20_atr"] = ((c - prior_hi20) / safe_atr).clip(-10.0, 10.0)
    out["distance_low_20_atr"] = ((c - prior_lo20) / safe_atr).clip(-10.0, 10.0)
    out["range_atr"] = ((h - l) / safe_atr).clip(0.0, 8.0)
    out["signed_body_atr"] = ((c - o) / safe_atr).clip(-5.0, 5.0)
    out["upper_wick_atr"] = ((h - pd.concat([o, c], axis=1).max(axis=1)) / safe_atr).clip(0.0, 5.0)
    out["lower_wick_atr"] = ((pd.concat([o, c], axis=1).min(axis=1) - l) / safe_atr).clip(0.0, 5.0)
    out["tick_volume_z_30"] = _zscore_last(tv, 30).clip(-5.0, 5.0)
    out["spread_z_30"] = _zscore_last(spread, 30).clip(-5.0, 5.0)

    utc_hour = closes.dt.hour.astype(float)
    out["hour_sin"] = np.sin(2.0 * math.pi * utc_hour / 24.0)
    out["hour_cos"] = np.cos(2.0 * math.pi * utc_hour / 24.0)
    return out


def _role_columns(role: str) -> list[str]:
    tf = ROLE_FEATURES[role]["timeframe"].lower()
    return [f"{tf}__{name}" for name in ROLE_FEATURES[role]["features"]]


def build_role_feature_matrix(
    views: Mapping[str, pd.DataFrame],
    alignment: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    missing = [tf for tf in NATIVE_FRAME_ORDER if tf not in views]
    if missing:
        raise MTF2Error("canonical views missing: " + ", ".join(missing))
    if audit_alignment(alignment).get("status") != "PASS":
        raise MTF2Error("alignment must pass MTF-1 causal audit")

    base = alignment.copy().sort_values("decision_time_utc", kind="stable").reset_index(drop=True)
    base["decision_time_utc"] = pd.to_datetime(base["decision_time_utc"], utc=True, errors="raise")
    if bool(base["decision_time_utc"].duplicated().any()):
        raise MTF2Error("duplicate M15 decision_time_utc")
    base["decision_id"] = base["decision_time_utc"].map(lambda x: f"M15@{x.isoformat()}")

    role_meta: dict[str, Any] = {}
    for role, spec in ROLE_FEATURES.items():
        tf = spec["timeframe"]
        prefix = _ROLE_PREFIX[tf]
        primitives = _primitive_frame(views[tf], tf)
        names = list(spec["features"])
        max_lookback = max(int(_PRIMITIVE_BY_ID[name]["lookback_bars"]) for name in names)
        role_table = pd.DataFrame({
            f"{prefix}__source_close_time_utc": primitives["close_time_utc"],
            f"{prefix}__dependency_start_time_utc": primitives["open_time_utc"].shift(max_lookback - 1),
        })
        for name in names:
            role_table[f"{prefix}__{name}"] = primitives[name]
        base = base.merge(
            role_table,
            left_on=f"{prefix}_close_time_utc",
            right_on=f"{prefix}__source_close_time_utc",
            how="left",
            validate="many_to_one",
            sort=False,
        )
        role_meta[role] = {
            "timeframe": tf,
            "feature_columns": _role_columns(role),
            "max_lookback_bars": max_lookback,
        }

    all_features = [col for role in ABLATION_ROLES["D"] for col in _role_columns(role)]
    finite = np.isfinite(base[all_features].to_numpy(dtype=float)).all(axis=1)
    base["feature_ready_d"] = finite

    audited = base.loc[finite, all_features].astype(float)
    constant_features: list[str] = []
    exact_duplicate_pairs: list[list[str]] = []
    high_abs_corr_pairs: list[dict[str, Any]] = []
    if len(audited):
        constant_features = [
            col for col in all_features
            if int(audited[col].nunique(dropna=False)) <= 1
        ]
        variable = [col for col in all_features if col not in constant_features]
        for index, left in enumerate(variable):
            left_values = audited[left].to_numpy(dtype=float)
            for right in variable[index + 1:]:
                right_values = audited[right].to_numpy(dtype=float)
                if np.array_equal(left_values, right_values):
                    exact_duplicate_pairs.append([left, right])
                    continue
                corr = float(np.corrcoef(left_values, right_values)[0, 1])
                if math.isfinite(corr) and abs(corr) >= 0.995:
                    high_abs_corr_pairs.append({
                        "left": left,
                        "right": right,
                        "abs_pearson": abs(corr),
                    })

    redundancy_status = "PASS" if not exact_duplicate_pairs else "FAIL"
    meta = {
        "schema": "MAX_MTF2_FEATURE_MATRIX_V2",
        "status": redundancy_status,
        "rows": int(len(base)),
        "d_feature_ready_rows": int(finite.sum()),
        "feature_schema_sha256": feature_schema_sha256(),
        "role_meta": role_meta,
        "all_feature_columns": all_features,
        "redundancy_audit": {
            "status": redundancy_status,
            "audited_rows": int(finite.sum()),
            "constant_features": constant_features,
            "exact_duplicate_pairs": exact_duplicate_pairs,
            "high_abs_corr_threshold": 0.995,
            "high_abs_corr_pairs": high_abs_corr_pairs,
            "automatic_drop_authority": False,
        },
    }
    return base, meta


def audit_feature_causality(feature_matrix: pd.DataFrame) -> dict[str, Any]:
    if feature_matrix.empty:
        return {"schema": "MAX_MTF2_FEATURE_CAUSALITY_V1", "status": "FAIL", "reason": "EMPTY"}
    decision = pd.to_datetime(feature_matrix["decision_time_utc"], utc=True, errors="raise")
    future_close: dict[str, int] = {}
    bad_dependency: dict[str, int] = {}
    missing_source: dict[str, int] = {}
    ready_without_dependency: dict[str, int] = {}

    for role, spec in ROLE_FEATURES.items():
        prefix = _ROLE_PREFIX[spec["timeframe"]]
        source_col = f"{prefix}__source_close_time_utc"
        dep_col = f"{prefix}__dependency_start_time_utc"
        source = pd.to_datetime(feature_matrix[source_col], utc=True, errors="coerce")
        dep = pd.to_datetime(feature_matrix[dep_col], utc=True, errors="coerce")
        future_close[role] = int((source > decision).fillna(False).sum())
        bad_dependency[role] = int((dep > source).fillna(False).sum())
        missing_source[role] = int(source.isna().sum())
        role_cols = _role_columns(role)
        role_ready = np.isfinite(feature_matrix[role_cols].to_numpy(dtype=float)).all(axis=1)
        ready_without_dependency[role] = int((role_ready & dep.isna().to_numpy()).sum())

    duplicate_decisions = int(feature_matrix["decision_id"].duplicated().sum())
    non_monotonic = not bool(decision.is_monotonic_increasing)
    failures = (
        sum(future_close.values())
        + sum(bad_dependency.values())
        + sum(missing_source.values())
        + sum(ready_without_dependency.values())
        + duplicate_decisions
        + int(non_monotonic)
    )
    return {
        "schema": "MAX_MTF2_FEATURE_CAUSALITY_V1",
        "status": "PASS" if failures == 0 else "FAIL",
        "rows": int(len(feature_matrix)),
        "future_role_close_violations": future_close,
        "bad_dependency_intervals": bad_dependency,
        "missing_role_source_rows": missing_source,
        "ready_rows_missing_dependency_start": ready_without_dependency,
        "duplicate_decisions": duplicate_decisions,
        "non_monotonic_decisions": bool(non_monotonic),
    }


def _validate_geometry(geometry: Mapping[str, Any]) -> dict[str, Any]:
    required = ("geometry_id", "sl_atr", "tp_atr", "horizon_minutes", "min_edge_r", "min_margin_r")
    missing = [key for key in required if key not in geometry]
    if missing:
        if "max_hold_bars" in geometry and "horizon_minutes" not in geometry:
            raise MTF2Error("untyped max_hold_bars is not MTF-2 horizon authority")
        raise MTF2Error("directional geometry missing: " + ", ".join(missing))
    out = {
        "geometry_id": str(geometry["geometry_id"]).strip(),
        "sl_atr": float(geometry["sl_atr"]),
        "tp_atr": float(geometry["tp_atr"]),
        "horizon_minutes": int(geometry["horizon_minutes"]),
        "min_edge_r": float(geometry["min_edge_r"]),
        "min_margin_r": float(geometry["min_margin_r"]),
    }
    if not out["geometry_id"]:
        raise MTF2Error("geometry_id is empty")
    if not math.isfinite(out["sl_atr"]) or out["sl_atr"] <= 0:
        raise MTF2Error("sl_atr must be finite > 0")
    if not math.isfinite(out["tp_atr"]) or out["tp_atr"] <= 0:
        raise MTF2Error("tp_atr must be finite > 0")
    if out["horizon_minutes"] <= 0 or out["horizon_minutes"] % 5 != 0:
        raise MTF2Error("horizon_minutes must be positive and divisible by 5")
    if not math.isfinite(out["min_edge_r"]) or out["min_edge_r"] < 0:
        raise MTF2Error("min_edge_r must be finite >= 0")
    if not math.isfinite(out["min_margin_r"]) or out["min_margin_r"] < 0:
        raise MTF2Error("min_margin_r must be finite >= 0")
    return out


def _first_touch(
    highs: np.ndarray,
    lows: np.ndarray,
    tp: float,
    sl: float,
    *,
    long_side: bool,
) -> tuple[int | None, bool]:
    for high, low in zip(highs, lows):
        if long_side:
            hit_tp, hit_sl = high >= tp, low <= sl
        else:
            hit_tp, hit_sl = low <= tp, high >= sl
        if hit_tp and hit_sl:
            return None, True
        if hit_tp:
            return 1, False
        if hit_sl:
            return -1, False
    return None, False


def build_directional_labels(
    views: Mapping[str, pd.DataFrame],
    feature_matrix: pd.DataFrame,
    geometry: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    g = _validate_geometry(geometry)
    if "M5" not in views or "M15" not in views:
        raise MTF2Error("M5 and M15 canonical views are required for labels")

    m5 = views["M5"].copy().sort_values("open_time_utc", kind="stable").reset_index(drop=True)
    _require_columns(m5, "M5")
    m5_open = pd.to_datetime(m5["open_time_utc"], utc=True, errors="raise")
    m5_close = pd.to_datetime(m5["close_time_utc"], utc=True, errors="raise")
    if bool(m5_open.duplicated().any()) or not bool(m5_open.is_monotonic_increasing):
        raise MTF2Error("M5 label path timestamps are not unique monotonic")
    open_index = {int(ts.value): idx for idx, ts in enumerate(m5_open)}
    close_ns = m5_close.astype("int64").to_numpy()
    max_close = m5_close.iloc[-1]
    highs = _numeric(m5, "high").to_numpy()
    lows = _numeric(m5, "low").to_numpy()
    closes = _numeric(m5, "close").to_numpy()
    opens = _numeric(m5, "open").to_numpy()

    m15_support = _primitive_frame(views["M15"], "M15")[["close_time_utc", "_atr14_sma"]].rename(
        columns={"close_time_utc": "m15__source_close_time_utc", "_atr14_sma": "label_risk_scale_internal"}
    )
    work = feature_matrix[["decision_id", "decision_time_utc", "m15__source_close_time_utc"]].merge(
        m15_support,
        on="m15__source_close_time_utc",
        how="left",
        validate="many_to_one",
        sort=False,
    )

    rr = g["tp_atr"] / g["sl_atr"]
    rows: list[dict[str, Any]] = []
    for row in work.itertuples(index=False):
        decision = pd.Timestamp(row.decision_time_utc)
        if decision.tzinfo is None:
            decision = decision.tz_localize("UTC")
        else:
            decision = decision.tz_convert("UTC")
        label_end = decision + pd.Timedelta(minutes=g["horizon_minutes"])
        risk_scale = float(row.label_risk_scale_internal) if pd.notna(row.label_risk_scale_internal) else math.nan
        result = {
            "decision_id": row.decision_id,
            "decision_time_utc": decision,
            "label_start_time_utc": decision,
            "label_end_time_utc": label_end,
            "geometry_id": g["geometry_id"],
            "risk_scale": risk_scale,
            "long_r": math.nan,
            "short_r": math.nan,
            "label": 1,
            "label_valid": False,
            "ambiguous_barrier": False,
            "label_reason": "UNRESOLVED",
        }
        if not math.isfinite(risk_scale) or risk_scale <= 0:
            result["label_reason"] = "INVALID_RISK_SCALE"
            rows.append(result)
            continue
        if max_close < label_end:
            result["label_reason"] = "INCOMPLETE_HORIZON"
            rows.append(result)
            continue
        entry_idx = open_index.get(int(decision.value))
        if entry_idx is None:
            result["label_reason"] = "MISSING_EXACT_M5_ENTRY"
            rows.append(result)
            continue
        end_idx = int(np.searchsorted(close_ns, int(label_end.value), side="right") - 1)
        if end_idx < entry_idx:
            result["label_reason"] = "NO_FULLY_CLOSED_M5_IN_HORIZON"
            rows.append(result)
            continue

        entry = float(opens[entry_idx])
        stop_dist = g["sl_atr"] * risk_scale
        take_dist = g["tp_atr"] * risk_scale
        path_high = highs[entry_idx : end_idx + 1]
        path_low = lows[entry_idx : end_idx + 1]

        long_mark, long_amb = _first_touch(
            path_high, path_low, entry + take_dist, entry - stop_dist, long_side=True
        )
        short_mark, short_amb = _first_touch(
            path_high, path_low, entry - take_dist, entry + stop_dist, long_side=False
        )
        if long_amb or short_amb:
            result["ambiguous_barrier"] = True
            result["label_reason"] = "AMBIGUOUS_BARRIER"
            rows.append(result)
            continue

        timeout_close = float(closes[end_idx])
        long_r = rr if long_mark == 1 else (-1.0 if long_mark == -1 else float(np.clip((timeout_close - entry) / stop_dist, -1.0, rr)))
        short_r = rr if short_mark == 1 else (-1.0 if short_mark == -1 else float(np.clip((entry - timeout_close) / stop_dist, -1.0, rr)))
        best = max(long_r, short_r)
        margin = abs(long_r - short_r)
        label = 1 if best < g["min_edge_r"] or margin < g["min_margin_r"] else (2 if long_r > short_r else 0)

        result.update({
            "long_r": float(long_r),
            "short_r": float(short_r),
            "label": int(label),
            "label_valid": True,
            "label_reason": "VALID",
        })
        rows.append(result)

    labels = pd.DataFrame(rows)
    valid = int(labels["label_valid"].sum()) if len(labels) else 0
    meta = {
        "schema": LABEL_SCHEMA,
        "status": "PASS",
        "rows": int(len(labels)),
        "valid_rows": valid,
        "invalid_rows": int(len(labels) - valid),
        "geometry": g,
        "future_path_authority": "POST_DECISION_CANONICAL_M5_LABEL_ONLY",
        "execution_label": "NOT_ACTIVE_IN_MTF2",
    }
    return labels, meta


def build_ablation_views(
    feature_matrix: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    merged = feature_matrix.merge(
        labels.drop(columns=["decision_time_utc"], errors="ignore"),
        on="decision_id",
        how="left",
        validate="one_to_one",
        sort=False,
    )
    all_d_features = [col for role in ABLATION_ROLES["D"] for col in _role_columns(role)]
    d_ready = np.isfinite(merged[all_d_features].to_numpy(dtype=float)).all(axis=1)
    label_ready = merged["label_valid"].fillna(False).to_numpy(dtype=bool)
    common = merged.loc[d_ready & label_ready].copy().reset_index(drop=True)

    views: dict[str, pd.DataFrame] = {}
    feature_counts: dict[str, int] = {}
    common_ids = common["decision_id"].astype(str).tolist()
    sample_hash = hashlib.sha256(("\n".join(common_ids) + "\n").encode("utf-8")).hexdigest()
    for name, roles in ABLATION_ROLES.items():
        feature_cols = [col for role in roles for col in _role_columns(role)]
        dep_cols = [f"{_ROLE_PREFIX[ROLE_FEATURES[role]['timeframe']]}__dependency_start_time_utc" for role in roles]
        dep = pd.concat([pd.to_datetime(common[col], utc=True, errors="raise") for col in dep_cols], axis=1).min(axis=1)
        out = pd.DataFrame({
            "decision_id": common["decision_id"],
            "decision_time_utc": pd.to_datetime(common["decision_time_utc"], utc=True),
            "dependency_start_time_utc": dep,
            "label_start_time_utc": pd.to_datetime(common["label_start_time_utc"], utc=True),
            "label_end_time_utc": pd.to_datetime(common["label_end_time_utc"], utc=True),
            "geometry_id": common["geometry_id"],
            "label": common["label"].astype(np.int64),
            "long_r": common["long_r"].astype(float),
            "short_r": common["short_r"].astype(float),
        })
        for col in feature_cols:
            out[col] = common[col].astype(float)
        views[name] = out
        feature_counts[name] = len(feature_cols)

    meta = {
        "schema": "MAX_MTF2_ABLATION_SET_V1",
        "status": "PASS" if len(common) else "FAIL",
        "common_rows": int(len(common)),
        "common_decision_ids_sha256": sample_hash,
        "feature_counts": feature_counts,
        "roles": {name: list(roles) for name, roles in ABLATION_ROLES.items()},
        "same_sample_authority": True,
    }
    return views, meta


def build_mtf2_dataset(
    views: Mapping[str, pd.DataFrame],
    alignment: pd.DataFrame,
    geometry: Mapping[str, Any],
) -> dict[str, Any]:
    feature_matrix, feature_meta = build_role_feature_matrix(views, alignment)
    if feature_meta.get("status") != "PASS":
        raise MTF2Error(f"feature redundancy audit failed: {feature_meta.get('redundancy_audit')}")
    causal = audit_feature_causality(feature_matrix)
    if causal.get("status") != "PASS":
        raise MTF2Error(f"feature causality failed: {causal}")
    labels, label_meta = build_directional_labels(views, feature_matrix, geometry)
    ablations, ablation_meta = build_ablation_views(feature_matrix, labels)
    if ablation_meta.get("status") != "PASS":
        raise MTF2Error("no common D-complete feature/label-ready rows")
    return {
        "schema": SCHEMA,
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "feature_matrix": feature_matrix,
        "labels": labels,
        "ablations": ablations,
        "meta": {
            "feature": feature_meta,
            "causality": causal,
            "labels": label_meta,
            "ablations": ablation_meta,
        },
    }
