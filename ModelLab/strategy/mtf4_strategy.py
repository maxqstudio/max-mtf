from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping

CONTRACT_ID = "MAX_MTF4_DETERMINISTIC_STRATEGY_CHALLENGER_V1"

MTF4_PARAM_BOUNDS: dict[str, tuple[float, float, float, str]] = {
    "InpMtfH4MinADX": (10.0, 35.0, 2.5, "float"),
    "InpMtfH4MinATRRatio": (0.50, 1.00, 0.05, "float"),
    "InpMtfH4MaxATRRatio": (1.20, 2.50, 0.10, "float"),
    "InpMtfH1MinADX": (10.0, 30.0, 2.0, "float"),
    "InpMtfH1MaxAbsBBZ": (0.75, 3.00, 0.25, "float"),
    "InpMtfM5MinBodyATR": (0.00, 0.40, 0.025, "float"),
    "InpMtfM5MaxOppWickATR": (0.20, 2.00, 0.10, "float"),
}

MTF4_PARAM_DEFAULTS: dict[str, float] = {
    "InpMtfH4MinADX": 15.0,
    "InpMtfH4MinATRRatio": 0.65,
    "InpMtfH4MaxATRRatio": 2.00,
    "InpMtfH1MinADX": 12.0,
    "InpMtfH1MaxAbsBBZ": 2.50,
    "InpMtfM5MinBodyATR": 0.05,
    "InpMtfM5MaxOppWickATR": 1.50,
}


class MTF4StrategyError(ValueError):
    pass


def validate_mtf4_params(params: Mapping[str, Any] | None = None) -> dict[str, float]:
    source = dict(MTF4_PARAM_DEFAULTS)
    if params:
        source.update(dict(params))
    out: dict[str, float] = {}
    for name, (lo, hi, _step, _typ) in MTF4_PARAM_BOUNDS.items():
        if name not in source:
            raise MTF4StrategyError(f"missing MTF-4 parameter: {name}")
        value = float(source[name])
        if not isfinite(value) or value < lo or value > hi:
            raise MTF4StrategyError(f"{name} outside frozen hard bounds")
        out[name] = value
    if out["InpMtfH4MaxATRRatio"] < out["InpMtfH4MinATRRatio"]:
        raise MTF4StrategyError("H4 ATR-ratio maximum is below minimum")
    return out


def _utc(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        stamp = value
    else:
        try:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception as exc:
            raise MTF4StrategyError(f"{field} is not an ISO timestamp") from exc
    if stamp.tzinfo is None:
        raise MTF4StrategyError(f"{field} must be timezone-aware")
    return stamp.astimezone(timezone.utc)


def _finite(role: Mapping[str, Any], *names: str) -> list[float]:
    values: list[float] = []
    for name in names:
        try:
            value = float(role[name])
        except Exception as exc:
            raise MTF4StrategyError(f"role field missing/non-numeric: {name}") from exc
        if not isfinite(value):
            raise MTF4StrategyError(f"role field non-finite: {name}")
        values.append(value)
    return values


def _causal_role(role: Mapping[str, Any] | None, decision_time_utc: datetime, name: str) -> tuple[bool, str]:
    if not isinstance(role, Mapping):
        return False, f"MTF_{name}_UNAVAILABLE"
    try:
        close_time = _utc(role.get("close_time_utc"), f"{name}.close_time_utc")
    except MTF4StrategyError:
        return False, f"MTF_{name}_TIME_INVALID"
    if close_time > decision_time_utc:
        return False, f"MTF_{name}_FUTURE_BAR"
    return True, ""


def h4_context_gate(role: Mapping[str, Any], m15_direction: int, params: Mapping[str, float]) -> tuple[bool, str]:
    adx, atr_ratio, ma_fast, ma_slow = _finite(role, "adx", "atr_ratio", "ma_fast", "ma_slow")
    if adx < params["InpMtfH4MinADX"]:
        return False, "MTF_H4_ADX"
    if not (params["InpMtfH4MinATRRatio"] <= atr_ratio <= params["InpMtfH4MaxATRRatio"]):
        return False, "MTF_H4_ATR_REGIME"
    trend = 1 if ma_fast > ma_slow else (-1 if ma_fast < ma_slow else 0)
    if trend != m15_direction:
        return False, "MTF_H4_ALIGNMENT"
    return True, ""


def h1_setup_gate(role: Mapping[str, Any], m15_direction: int, params: Mapping[str, float]) -> tuple[bool, str]:
    adx, bb_z, ma_fast, ma_slow = _finite(role, "adx", "bb_z", "ma_fast", "ma_slow")
    if adx < params["InpMtfH1MinADX"]:
        return False, "MTF_H1_ADX"
    if abs(bb_z) > params["InpMtfH1MaxAbsBBZ"]:
        return False, "MTF_H1_BB_EXTENSION"
    trend = 1 if ma_fast > ma_slow else (-1 if ma_fast < ma_slow else 0)
    if trend != m15_direction:
        return False, "MTF_H1_ALIGNMENT"
    return True, ""


def m5_timing_gate(role: Mapping[str, Any], m15_direction: int, params: Mapping[str, float]) -> tuple[bool, str]:
    open_, close, body_atr, upper_wick_atr, lower_wick_atr = _finite(
        role, "open", "close", "body_atr", "upper_wick_atr", "lower_wick_atr"
    )
    candle_direction = 1 if close > open_ else (-1 if close < open_ else 0)
    if candle_direction != m15_direction:
        return False, "MTF_M5_DIRECTION"
    if body_atr < params["InpMtfM5MinBodyATR"]:
        return False, "MTF_M5_BODY"
    opposite_wick = upper_wick_atr if m15_direction > 0 else lower_wick_atr
    if opposite_wick > params["InpMtfM5MaxOppWickATR"]:
        return False, "MTF_M5_OPPOSITE_WICK"
    return True, ""


def evaluate_mtf4_strategy(
    *,
    m15_direction: int,
    decision_time_utc: Any,
    h4: Mapping[str, Any] | None,
    h1: Mapping[str, Any] | None,
    m5: Mapping[str, Any] | None,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if int(m15_direction) not in (-1, 1):
        raise MTF4StrategyError("M15 direction must be -1 or +1")
    direction = int(m15_direction)
    decision_time = _utc(decision_time_utc, "decision_time_utc")
    frozen = validate_mtf4_params(params)

    gate_results: dict[str, dict[str, Any]] = {}
    for name, role in (("H4", h4), ("H1", h1), ("M5", m5)):
        causal, reason = _causal_role(role, decision_time, name)
        gate_results[name] = {"causal": causal, "passed": False, "reason": reason}
        if not causal:
            return {
                "status": "SKIP", "take": False, "m15_direction": direction,
                "decision_direction": 0, "reason": reason, "gates": gate_results,
            }

    for name, gate, role in (
        ("H4", h4_context_gate, h4),
        ("H1", h1_setup_gate, h1),
        ("M5", m5_timing_gate, m5),
    ):
        assert isinstance(role, Mapping)
        passed, reason = gate(role, direction, frozen)
        gate_results[name] = {"causal": True, "passed": bool(passed), "reason": reason}
        if not passed:
            return {
                "status": "SKIP", "take": False, "m15_direction": direction,
                "decision_direction": 0, "reason": reason, "gates": gate_results,
            }

    return {
        "status": "TAKE_BUY" if direction > 0 else "TAKE_SELL",
        "take": True,
        "m15_direction": direction,
        "decision_direction": direction,
        "reason": "",
        "gates": gate_results,
    }
