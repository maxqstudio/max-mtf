from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import pandas as pd

SCHEMA = "CP_TRADE_SAMPLE_AUTO_V2"

_PERIOD_TO_MINUTES = {
    1:1,2:2,3:3,4:4,5:5,6:6,10:10,12:12,15:15,20:20,30:30,
    60:60,120:120,180:180,240:240,360:360,480:480,720:720,1440:1440,10080:10080,43200:43200,
    16385:60,16386:120,16387:180,16388:240,16390:360,16392:480,16396:720,16408:1440,32769:10080,49153:43200,
}
_LABEL_TO_MINUTES = {
    "M1":1,"M2":2,"M3":3,"M4":4,"M5":5,"M6":6,"M10":10,"M12":12,"M15":15,"M20":20,"M30":30,
    "H1":60,"H2":120,"H3":180,"H4":240,"H6":360,"H8":480,"H12":720,"D1":1440,"W1":10080,"MN1":43200,
}


def timeframe_minutes(period: int | float | str) -> int:
    if isinstance(period, str):
        s=period.strip().upper()
        if s in _LABEL_TO_MINUTES:
            return int(_LABEL_TO_MINUTES[s])
    try:
        p = int(float(period))
    except Exception as exc:
        raise ValueError(f"Unsupported timeframe period: {period!r}") from exc
    if p not in _PERIOD_TO_MINUTES:
        raise ValueError(f"Unsupported timeframe period code: {p}")
    return int(_PERIOD_TO_MINUTES[p])


def effective_months(start: Any, end: Any) -> float:
    s = pd.Timestamp(start); e = pd.Timestamp(end)
    if pd.isna(s) or pd.isna(e) or e < s:
        raise ValueError(f"Invalid sample window: {start} -> {end}")
    days = max(1.0, float((e - s).total_seconds()) / 86400.0)
    return days / 30.436875


def scaled_trade_requirement(period: int | float | str, start: Any, end: Any, *, base_h1_trades_per_month: int,
                             observed_fraction: float = 1.0, timeframe_scaling: str = "SQRT",
                             min_timeframe_factor: float = 0.20, max_timeframe_factor: float = 4.00,
                             absolute_floor: int = 0) -> dict:
    """Resolve an integer monthly rate and integer final requirement.

    v0.7.6 Owner contract: H1 is the baseline. The timeframe-scaled monthly rate is
    CEILed first so the UI/evidence never carries fractional required trades/month.
    Exact evaluated duration (and OOF/CV observed_fraction where applicable) is then
    prorated and the final required closed-trade count is CEILed again.
    """
    base=int(base_h1_trades_per_month)
    if base < 1: raise ValueError("base_h1_trades_per_month must be >= 1")
    tf_min=timeframe_minutes(period)
    months=effective_months(start,end)
    frac=max(0.01,min(1.0,float(observed_fraction)))
    months_effective=months*frac
    ratio=60.0/float(tf_min)
    scaling=str(timeframe_scaling or "SQRT").upper()
    if scaling=="LINEAR": factor=ratio
    elif scaling=="NONE": factor=1.0
    else: factor=math.sqrt(ratio)
    factor=max(float(min_timeframe_factor),min(float(max_timeframe_factor),factor))
    monthly_rate=int(math.ceil(float(base)*factor-1e-12))
    prorated=float(months_effective)*monthly_rate
    minimum=max(int(absolute_floor or 0),int(math.ceil(prorated-1e-12)))
    return {
        "timeframe_minutes":int(tf_min),"calendar_months":float(months),"observed_fraction":float(frac),
        "effective_months":float(months_effective),"base_h1_trades_per_month":int(base),
        "timeframe_scaling":scaling,"timeframe_factor":float(factor),
        "scaled_trades_per_month":int(monthly_rate),"prorated_required_before_roundup":float(prorated),
        "minimum_trades":int(minimum),"absolute_floor":int(absolute_floor or 0),
        "rounding":"CEIL_MONTHLY_RATE_AND_FINAL_REQUIREMENT",
    }


def _stage_floor(stage: str, policy: dict) -> int:
    key={"DISCOVERY":"absolute_floor_discovery","TOURNAMENT":"absolute_floor_tournament","FRESH":"absolute_floor_fresh","LOCKED":"absolute_floor_tournament","CV":"absolute_floor_discovery","CPCV":"absolute_floor_discovery"}.get(str(stage).upper(),"absolute_floor_discovery")
    return int(policy.get(key,0) or 0)


def auto_trade_sample(period: int | float | str, start: Any, end: Any, cfg: dict, stage: str = "DISCOVERY", observed_fraction: float = 1.0) -> dict:
    policy=(cfg.get("trade_sample_policy") or {}); mode=str(policy.get("mode","AUTO")).upper()
    if mode!="AUTO":
        return {"schema":SCHEMA,"mode":mode,"stage":str(stage).upper(),"minimum_trades":None,"reason":"MANUAL_MODE"}
    result=scaled_trade_requirement(
        period,start,end,base_h1_trades_per_month=int(policy.get("base_h1_trades_per_month",8) or 8),
        observed_fraction=observed_fraction,timeframe_scaling=str(policy.get("timeframe_scaling","SQRT")),
        min_timeframe_factor=float(policy.get("min_timeframe_factor",0.20)),max_timeframe_factor=float(policy.get("max_timeframe_factor",4.00)),
        absolute_floor=_stage_floor(stage,policy),
    )
    result.update({"schema":SCHEMA,"mode":"AUTO","stage":str(stage).upper(),"period":period,
                   "window_start":str(pd.Timestamp(start)),"window_end":str(pd.Timestamp(end)),
                   "sufficiency_ratio":1.0,"reason":"PREDECLARED_DYNAMIC_SAMPLE_GATE_V076"})
    return result


def apply_auto_trade_thresholds(cfg: dict, period: int | float | str, start: Any, end: Any, stage: str, observed_fraction: float = 1.0) -> tuple[dict, dict]:
    out=deepcopy(cfg); meta=auto_trade_sample(period,start,end,out,stage=stage,observed_fraction=observed_fraction)
    if meta.get("minimum_trades") is None: return out,meta
    n=int(meta["minimum_trades"]); stage_u=str(stage).upper()
    if stage_u in {"DISCOVERY","CV"}: out.setdefault("acceptance",{})["cv_min_validation_trades"]=n
    elif stage_u in {"TOURNAMENT","LOCKED"}: out.setdefault("acceptance",{})["min_test_trades"]=n
    elif stage_u=="FRESH": out.setdefault("agent",{}).setdefault("promotion",{})["min_shadow_trades"]=n
    out["resolved_trade_sample"]=meta
    return out,meta
