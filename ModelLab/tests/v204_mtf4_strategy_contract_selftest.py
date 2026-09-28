from __future__ import annotations

import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
sys.path.insert(0, str(ROOT))

from strategy.mtf4_strategy import (
    CONTRACT_ID,
    MTF4_PARAM_BOUNDS,
    MTF4_PARAM_DEFAULTS,
    MTF4StrategyError,
    evaluate_mtf4_strategy,
    validate_mtf4_params,
)
from strategy.strategy_optimizer import (
    ABSOLUTE_BOUNDS,
    _parameter_signature,
    _parse_frame_inputs_blob,
    build_set_text,
    validate_request,
)


def req(value, message):
    if not value:
        raise AssertionError(message)


contracts = json.loads((PKG / ".workflow" / "contracts.json").read_text(encoding="utf-8"))
contract = next(row for row in contracts["data_contracts"] if row.get("contract_id") == CONTRACT_ID)
expected_mtf_params = {
    "InpMtfH4MinADX",
    "InpMtfH4MinATRRatio",
    "InpMtfH4MaxATRRatio",
    "InpMtfH1MinADX",
    "InpMtfH1MaxAbsBBZ",
    "InpMtfM5MinBodyATR",
    "InpMtfM5MaxOppWickATR",
}
req(set(MTF4_PARAM_BOUNDS) == expected_mtf_params, "exact seven MTF-4 parameters")
req(set(MTF4_PARAM_DEFAULTS) == expected_mtf_params, "MTF-4 defaults bind exact parameter set")
req(set(contract["optimizer_integration"]["mtf_parameter_names"]) == expected_mtf_params, "contract/profile parameter parity")
req(contract["primary_decision_timeframe"] == "M15", "M15 remains primary decision timeframe")
req(any("M15 is the only directional owner" in x for x in contract["invariants"]), "M15 sole-direction invariant")
req(any("no ENTER/WAIT/CANCEL" in x or "no ENTER/WAIT/CANCEL" in x.upper() for x in contract["invariants"]), "MTF-7 timing state remains deferred")

decision = "2026-09-01T12:00:00+00:00"
h4_buy = {
    "close_time_utc": decision,
    "adx": 22.0,
    "atr_ratio": 1.0,
    "ma_fast": 2.0,
    "ma_slow": 1.0,
}
h1_buy = {
    "close_time_utc": decision,
    "adx": 20.0,
    "bb_z": 0.3,
    "ma_fast": 2.0,
    "ma_slow": 1.0,
}
m5_buy = {
    "close_time_utc": decision,
    "open": 100.0,
    "close": 101.0,
    "body_atr": 0.20,
    "upper_wick_atr": 0.10,
    "lower_wick_atr": 0.05,
}

buy = evaluate_mtf4_strategy(
    m15_direction=1,
    decision_time_utc=decision,
    h4=h4_buy,
    h1=h1_buy,
    m5=m5_buy,
)
req(buy["take"] and buy["status"] == "TAKE_BUY", "all-pass BUY")
req(buy["m15_direction"] == 1 and buy["decision_direction"] == 1, "BUY direction unchanged")

h4_sell = {**h4_buy, "ma_fast": 1.0, "ma_slow": 2.0}
h1_sell = {**h1_buy, "ma_fast": 1.0, "ma_slow": 2.0}
m5_sell = {**m5_buy, "open": 101.0, "close": 100.0}
sell = evaluate_mtf4_strategy(
    m15_direction=-1,
    decision_time_utc=decision,
    h4=h4_sell,
    h1=h1_sell,
    m5=m5_sell,
)
req(sell["take"] and sell["status"] == "TAKE_SELL", "all-pass SELL")
req(sell["m15_direction"] == -1 and sell["decision_direction"] == -1, "SELL direction unchanged")

for label, kwargs, expected_reason in (
    ("H4", {"h4": h4_sell, "h1": h1_buy, "m5": m5_buy}, "MTF_H4_ALIGNMENT"),
    ("H1", {"h4": h4_buy, "h1": h1_sell, "m5": m5_buy}, "MTF_H1_ALIGNMENT"),
    ("M5", {"h4": h4_buy, "h1": h1_buy, "m5": m5_sell}, "MTF_M5_DIRECTION"),
):
    result = evaluate_mtf4_strategy(
        m15_direction=1,
        decision_time_utc=decision,
        **kwargs,
    )
    req(not result["take"], label + " veto")
    req(result["m15_direction"] == 1 and result["decision_direction"] == 0, label + " cannot reverse M15")
    req(result["reason"] == expected_reason, label + " deterministic reason")

for label in ("h4", "h1", "m5"):
    roles = {"h4": h4_buy, "h1": h1_buy, "m5": m5_buy}
    roles[label] = None
    result = evaluate_mtf4_strategy(m15_direction=1, decision_time_utc=decision, **roles)
    req(not result["take"] and result["reason"] == "MTF_" + label.upper() + "_UNAVAILABLE", label + " missing fails closed")

future_h4 = {**h4_buy, "close_time_utc": "2026-09-01T12:00:01+00:00"}
future = evaluate_mtf4_strategy(
    m15_direction=1, decision_time_utc=decision, h4=future_h4, h1=h1_buy, m5=m5_buy
)
req(not future["take"] and future["reason"] == "MTF_H4_FUTURE_BAR", "future role bar fails closed")

failed = False
try:
    evaluate_mtf4_strategy(
        m15_direction=1,
        decision_time_utc="2026-09-01 12:00:00",
        h4=h4_buy, h1=h1_buy, m5=m5_buy,
    )
except MTF4StrategyError:
    failed = True
req(failed, "timezone-naive decision fails closed")

failed = False
try:
    validate_mtf4_params({"InpMtfH4MinADX": 99.0})
except MTF4StrategyError:
    failed = True
req(failed, "MTF hard bound violation fails closed")

base_request = {
    "symbol": "XAUUSD",
    "confirm_symbol": "XAGUSD",
    "from_date": "2021.01.01",
    "to_date": "2024.12.31",
    "installation": {"terminal": "T", "metaeditor": "M", "data_dir": "D"},
}
legacy = validate_request(base_request)
req(legacy["mtf_strategy_enabled"] is False, "legacy profile remains default")
req(len(ABSOLUTE_BOUNDS) == 16 and len(legacy["search_space"]) == 16, "legacy universe remains exact 16")
legacy_set = build_set_text(
    legacy["search_space"],
    confirm_symbol=legacy["confirm_symbol"],
    optimize_params=legacy["optimize_params"],
    fixed_param_values=legacy["fixed_param_values"],
)
req("InpUseMtfStrategy=false" in legacy_set, "legacy set explicitly disables MTF")
req(not any((name + "=") in legacy_set for name in MTF4_PARAM_BOUNDS), "legacy set has no MTF optimizer rows")

mtf = validate_request({**base_request, "mtf_strategy_enabled": True, "period": "M15"})
req(len(mtf["search_space"]) == 23 and len(mtf["optimize_params"]) == 23, "MTF profile is 16+7")
mtf_set = build_set_text(
    mtf["search_space"],
    confirm_symbol=mtf["confirm_symbol"],
    optimize_params=mtf["optimize_params"],
    fixed_param_values=mtf["fixed_param_values"],
)
req("InpUseMtfStrategy=true" in mtf_set, "MTF set explicitly enables MTF")
req(all((name + "=") in mtf_set for name in MTF4_PARAM_BOUNDS), "MTF set contains all seven role parameters")
req(len(_parameter_signature(legacy["fixed_param_values"])) == 16, "legacy signature exact 16")
req(len(_parameter_signature(mtf["fixed_param_values"])) == 23, "MTF signature exact 23")

legacy_blob = "|".join(f"{k}={v}" for k, v in legacy["fixed_param_values"].items())
mtf_blob = "|".join(f"{k}={v}" for k, v in mtf["fixed_param_values"].items())
req(len(_parse_frame_inputs_blob(legacy_blob)) == 16, "legacy frame vector parses")
req(len(_parse_frame_inputs_blob(mtf_blob)) == 23, "MTF frame vector parses")
failed = False
try:
    _parse_frame_inputs_blob(legacy_blob + "|InpMtfH4MinADX=15")
except ValueError:
    failed = True
req(failed, "partial MTF frame vector fails closed")

failed = False
try:
    validate_request({**base_request, "mtf_strategy_enabled": True, "period": "H1"})
except ValueError:
    failed = True
req(failed, "MTF optimizer refuses non-M15 primary period")

ea = (PKG / "EA_v2_00" / "baseline" / "Max_MTF.mq5").read_text(encoding="utf-8")
for token in (
    "input bool   InpUseMtfStrategy        = false;",
    "bool Mtf4EvaluateStrategy(",
    "bool Mtf4BuildRoleSnapshot(",
    "bool Mtf4H4ContextGate(",
    "bool Mtf4H1SetupGate(",
    "bool Mtf4M5TimingGate(",
    "if(_Period!=PERIOD_M15)",
    "if(InpUseOnnxChampion || InpUseOnnxChallenger)",
    "if(r.close_time>decision_time) return false;",
):
    req(token in ea, "EA MTF-4 source contract: " + token)

eval_start = ea.index("bool Mtf4EvaluateStrategy(")
eval_end = ea.index("\nint AcquireTrainingWriterLock()", eval_start)
eval_body = ea[eval_start:eval_end]
for token in (
    "RuleMetaScore(families,consensus)",
    "Mtf4BuildRoleSnapshot(PERIOD_H4",
    "Mtf4BuildRoleSnapshot(PERIOD_H1",
    "Mtf4BuildRoleSnapshot(PERIOD_M5",
    "Mtf4H4ContextGate(h4,direction,reason)",
    "Mtf4H1SetupGate(h1,direction,reason)",
    "Mtf4M5TimingGate(m5,direction,reason)",
    "OpenTrade(direction,s,rule_score)",
):
    req(token in eval_body, "EA MTF evaluator source path: " + token)
req("int direction=(rule_score>0.0 ? 1 : -1);" in eval_body, "M15 rule score owns direction")
req("direction=" not in eval_body.split("int direction=(rule_score>0.0 ? 1 : -1);", 1)[1], "role gates cannot reassign direction")

on_tick = ea[ea.index("void OnTick()"):]
mtf_branch = on_tick.index("if(InpUseMtfStrategy)")
legacy_rule = on_tick.index("double rule_score=RuleMetaScore(families,consensus);")
req(mtf_branch < legacy_rule, "explicit MTF branch precedes untouched legacy decision branch")
req("return;" in on_tick[mtf_branch:legacy_rule], "MTF path cannot fall through into legacy path")

m5_start = ea.index("bool Mtf4M5TimingGate(")
m5_end = ea.index("bool Mtf4EvaluateStrategy(", m5_start)
m5_body = ea[m5_start:m5_end]
req(re.search(r"(?m)^\\s*direction\\s*=", m5_body) is None, "M5 gate never mutates direction")
req("WAIT" not in m5_body and "CANCEL" not in m5_body, "MTF-7 timing state not introduced")

worker = (ROOT / "strategy" / "strategy_optimizer_worker.py").read_text(encoding="utf-8")
req("register_optimizer_challenger" in worker, "optimizer winner registers Strategy Challenger")
req("STRATEGY_CHALLENGER_FOUND" in worker, "worker terminates at Strategy Challenger status")

print("V204_MTF4_STRATEGY_CONTRACT PASS")
