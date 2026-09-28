from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT.parent
sys.path.insert(0, str(ROOT))

import strategy.strategy_challenger_registry as registry
from strategy.mtf4_strategy import MTF4_PARAM_BOUNDS
from strategy.strategy_optimizer import (
    ABSOLUTE_BOUNDS,
    _bounds_for_params,
    apply_champion_to_canonical_ea,
    assert_champion_ea_set_parity,
    optimizer_default_space,
    read_ea_optimizer_defaults,
    validate_champion_tester_preset_text,
    validate_scientist_ranges,
    write_champion_tester_preset,
)


def req(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


canonical = PKG / "EA_v2_00" / "baseline" / "Max_MTF.mq5"
req(canonical.is_file(), "canonical EA exists")

legacy = read_ea_optimizer_defaults(canonical, mtf_strategy_enabled=False)
mtf = read_ea_optimizer_defaults(canonical, mtf_strategy_enabled=True)
req(len(legacy) == len(ABSOLUTE_BOUNDS) == 16, "legacy profile remains 16")
req(len(mtf) == 23 and set(MTF4_PARAM_BOUNDS).issubset(mtf), "MTF profile is exact 16+7")
req(len(_bounds_for_params(legacy)) == 16, "legacy parameter identity")
req(len(_bounds_for_params(mtf)) == 23, "MTF parameter identity")

changed = dict(mtf)
changed["InpMtfH4MinADX"] = 17.5
req(not registry._same_params(mtf, changed), "registry identity includes MTF parameters")
req(not registry._same_params(legacy, mtf), "legacy and MTF profiles cannot alias")
req(registry._same_params(mtf, dict(mtf)), "identical MTF vectors compare equal")

partial = dict(legacy)
partial["InpMtfH4MinADX"] = mtf["InpMtfH4MinADX"]
failed = False
try:
    _bounds_for_params(partial)
except ValueError:
    failed = True
req(failed, "partial MTF vector fails closed")

proposal = {
    "ranges": {
        "InpMtfH4MinADX": {"start": 15.0, "step": 2.5, "stop": 20.0}
    }
}
compiled = validate_scientist_ranges(
    optimizer_default_space(True),
    proposal,
    optimize_params=["InpMtfH4MinADX"],
)
req(len(compiled) == 23, "Scientist deterministic validation preserves MTF profile")
req(compiled["InpMtfH4MinADX"]["start"] == 15.0, "Scientist selected range accepted in hard bounds")

with tempfile.TemporaryDirectory() as td_raw:
    td = Path(td_raw)
    legacy_ea = td / "Legacy.mq5"
    mtf_ea = td / "Mtf.mq5"
    shutil.copy2(canonical, legacy_ea)
    shutil.copy2(canonical, mtf_ea)

    legacy_apply = apply_champion_to_canonical_ea(legacy, source=legacy_ea)
    req(legacy_apply["parameter_count"] == 16, "legacy apply preserves 16 inputs")
    req(legacy_apply["mtf_strategy_enabled"] is False, "legacy apply remains non-MTF")

    mtf_apply = apply_champion_to_canonical_ea(changed, source=mtf_ea)
    req(mtf_apply["parameter_count"] == 23, "MTF apply mutates exact 23 inputs")
    req(mtf_apply["mtf_strategy_enabled"] is True, "MTF apply profile marker")
    reread = read_ea_optimizer_defaults(mtf_ea, mtf_strategy_enabled=True)
    req(abs(reread["InpMtfH4MinADX"] - 17.5) < 1e-12, "MTF EA default mutation persisted")

    fake_req = {
        "installation": {"data_dir": str(td)},
        "symbol": "XAUUSD",
        "confirm_symbol": "XAGUSD",
        "period": "M15",
        "from_date": "2024.01.01",
        "to_date": "2024.06.30",
        "deposit": 10000.0,
        "leverage": 100,
        "model": 0,
        "optimization": 2,
        "mtf_strategy_enabled": True,
        "search_space": optimizer_default_space(True),
        "optimize_params": list(optimizer_default_space(True)),
        "fixed_param_values": dict(mtf),
        "search_space_cardinality": {"optimized_inputs": 23},
        "optimizer_kpi": {"test": True},
        "optimizer_trade_sample": {"test": True},
    }

    set_path = td / "Max_MTF.set"
    preset = write_champion_tester_preset(fake_req, changed, path=set_path)
    req(preset["optimizer_owned_parameter_count"] == 23, "MTF preset contains 23 optimizer rows")
    parsed = validate_champion_tester_preset_text(set_path.read_text(encoding="utf-8"), changed)
    req(parsed["mtf_strategy_enabled"] is True, "MTF preset identity")
    parity = assert_champion_ea_set_parity(changed, set_path, ea_source=mtf_ea)
    req(parity["parameter_count"] == 23, "EA/set parity covers exact 23 inputs")

    old_ea_source = registry.EA_SOURCE
    old_artifact_root = registry.ARTIFACT_ROOT
    try:
        registry.EA_SOURCE = canonical
        registry.ARTIFACT_ROOT = td / "challengers"
        mq5 = registry.ARTIFACT_ROOT / "Max_Challenger_TEST.mq5"
        mq5.parent.mkdir(parents=True, exist_ok=True)
        entry = registry._write_challenger_bundle(
            req=fake_req,
            params=changed,
            code="TEST",
            mq5=mq5,
            kpi={"profit_factor": 1.5},
            provenance={"source_job_id": "fixture-job", "source_round": 1, "source_pass": 2},
            hard_gates={"fixture": True},
            role_origin="MTF4_LINEAGE_SELFTEST",
        )
    finally:
        registry.EA_SOURCE = old_ea_source
        registry.ARTIFACT_ROOT = old_artifact_root

    req(len(entry["params"]) == 23, "Challenger artifact preserves 23-param vector")
    req(entry["apply"]["parameter_count"] == 23, "Challenger EA apply records 23-param profile")
    req(entry["parity"]["parameter_count"] == 23, "Challenger bundle parity records 23-param profile")
    source_request = entry["source_request"]
    req(source_request["mtf_strategy_enabled"] is True, "Challenger request preserves explicit MTF flag")
    req(len(source_request["search_space"]) == 23, "Challenger request preserves search space")
    req(len(source_request["optimize_params"]) == 23, "Challenger request preserves selected optimizer vector")
    req(len(source_request["fixed_param_values"]) == 23, "Challenger request preserves frozen values")

print("V205_MTF4_CHALLENGER_LINEAGE PASS")
