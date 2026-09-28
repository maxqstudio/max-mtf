from __future__ import annotations

from copy import deepcopy
from typing import Any

from models.model_registry import all_families, family_spec, get_bounds, effective_bounds
from models.models import validate_candidate, CandidateSpec, candidate_capacity_contract
from core.training_method_contract import training_method_context
from models.capacity_governor import recommended_capacity_envelopes
from host.resource_preflight import compile_resource_capacity

SCHEMA = "MAX_RESEARCH_CONTROL_R1"
MODES = ("AUTO", "MANUAL")


def research_mode(cfg: dict | None) -> str:
    fc = ((cfg or {}).get("champion_factory") or {})
    raw_value = fc.get("research_mode")
    if raw_value is None or not str(raw_value).strip():
        return "AUTO"
    raw = str(raw_value).upper().strip()
    if raw not in MODES:
        raise ValueError(f"Unknown research_mode {raw_value!r}; expected one of {MODES}")
    return raw


def manual_cfg(cfg: dict | None) -> dict:
    fc = (cfg or {}).get("champion_factory") or {}
    raw = fc.get("manual_research") if isinstance(fc.get("manual_research"), dict) else {}
    candidates = [deepcopy(x) for x in (raw.get("candidates") or []) if isinstance(x, dict)]
    return {
        "schema": "MAX_MANUAL_RESEARCH_V1",
        "enabled": bool(raw.get("enabled", False)),
        "take_threshold": float(raw.get("take_threshold", 0.65) or 0.65),
        "minimum_wfa_survivors": max(1, int(raw.get("minimum_wfa_survivors", 1) or 1)),
        "candidates": candidates,
    }


def _midpoint(lo: Any, hi: Any, typ: type) -> int | float:
    v = (float(lo) + float(hi)) / 2.0
    return int(round(v)) if typ is int else float(v)


def default_manual_candidate(family: str, serial: int = 1) -> dict:
    fam = str(family or "").strip().lower()
    if not family_spec(fam):
        raise ValueError(f"Unknown model family: {family!r}")
    bounds = get_bounds([fam]).get(fam) or {}
    params = {k: _midpoint(lo, hi, typ) for k, (lo, hi, typ) in bounds.items()}
    return {
        "family": fam,
        "name": f"manual_{fam.replace('::', '_')}_{int(serial):02d}",
        "params": params,
    }


def normalize_manual_candidates(cfg: dict) -> list[dict]:
    m = manual_cfg(cfg)
    out = []
    for i, raw in enumerate(m["candidates"], 1):
        fam = str(raw.get("family") or "").strip().lower()
        if not fam:
            continue
        row = deepcopy(raw)
        row["family"] = fam
        row["name"] = str(row.get("name") or f"manual_{fam.replace('::', '_')}_{i:02d}")[:64]
        if not isinstance(row.get("params"), dict):
            row["params"] = {}
        out.append(row)
    return out


def _neutral_family_priorities() -> dict[str, float]:
    # Manual exact candidates are not a search. Size-priority sliders must not silently
    # narrow an Owner-entered exact parameter value. Hard legal/capacity validation
    # still applies downstream.
    return {f: 0.50 for f in all_families(include_legacy=False, include_dynamic=False)}


def compile_manual_runtime(cfg: dict) -> tuple[dict, list[dict]]:
    """Compile a fail-closed MANUAL runtime without any candidate discovery authority.

    This does *not* weaken validation. It only replaces proposal/discovery authority
    with an explicit Owner candidate list. WFA/CPCV/Tournament/Monte-Carlo/Forward
    remain deterministic downstream authorities.
    """
    runtime = deepcopy(cfg)
    fc = runtime.setdefault("champion_factory", {})
    m = manual_cfg(runtime)
    candidates = normalize_manual_candidates(runtime)
    if not candidates:
        raise ValueError("MANUAL RESEARCH requires at least one exact Owner candidate")

    fc["research_mode"] = "MANUAL"
    fc["manual_research"] = {
        "schema": "MAX_MANUAL_RESEARCH_V1",
        "enabled": True,
        "take_threshold": max(0.0, min(1.0, float(m["take_threshold"]))),
        "minimum_wfa_survivors": max(1, min(len(candidates), int(m["minimum_wfa_survivors"]))),
        "candidates": deepcopy(candidates),
    }
    fc["target_pool"] = len(candidates)
    fc["max_generations"] = 1
    fc["max_total_experiments"] = len(candidates)
    fc["discovery_batch_experiments"] = len(candidates)
    fc["orchestrator_max_cycles"] = 1

    agent = runtime.setdefault("agent", {})
    llm = agent.setdefault("llm", {})
    llm["enabled"] = False
    agent["manual_research"] = {
        "schema": "MAX_MANUAL_RESEARCH_V1",
        "enabled": True,
        "proposal_authority": "OWNER",
        "deterministic_discovery_used": False,
        "llm_used": False,
        "validation_authority": "DETERMINISTIC",
        "candidates": deepcopy(candidates),
        "minimum_wfa_survivors": int(fc["manual_research"]["minimum_wfa_survivors"]),
    }
    agent["max_experiments"] = len(candidates)
    agent["round_size"] = len(candidates)
    agent["max_rounds"] = 1
    agent["patience_rounds"] = 1
    agent["min_experiments_before_stop"] = len(candidates)
    agent["memory_elite_recheck_count"] = 0
    agent.setdefault("fidelity_ladder", {})["enabled"] = False
    agent.setdefault("policy_discovery", {})["enabled"] = False

    selected_families = list(dict.fromkeys(str(c["family"]).lower() for c in candidates))
    legal = get_bounds(selected_families)
    parameter_envelopes = {
        fam: {k: [v[0], v[1]] for k, v in (legal.get(fam) or {}).items()}
        for fam in selected_families
    }
    agent["research_plan"] = {
        "schema": "MAX_MANUAL_RESEARCH_PLAN_V1",
        "selection_source": "OWNER_MANUAL_EXACT",
        "active_families": selected_families,
        "parameter_envelopes": parameter_envelopes,
        "family_size_priorities": _neutral_family_priorities(),
        "topology_priority": {"authority": "OWNER_EXACT_CANDIDATE_LIST"},
        "resource_capacity": {"authority": "HARD_CAPACITY_GOVERNOR"},
        "model_training_method_contract": training_method_context(),
        "manual_candidate_count": len(candidates),
    }

    # A manual take threshold is exact policy input, not a threshold-search dimension.
    runtime.setdefault("deployment", {})["take_threshold_grid"] = [float(fc["manual_research"]["take_threshold"])]

    # Fail closed before starting a worker if an Owner candidate is illegal or exceeds
    # the hard capacity contract. validate_candidate also verifies every required field.
    validated = []
    for i, raw in enumerate(candidates, 1):
        # Key identity is checked before the generic candidate validator so missing or
        # unknown Owner intent cannot disappear behind a generic invalid-candidate error.
        supplied = raw.get("params") or {}
        family = str(raw.get("family") or "").strip().lower()
        expected_keys = set(effective_bounds(runtime, family).keys())
        supplied_keys = set(str(k) for k in supplied.keys())
        unknown_keys = sorted(supplied_keys - expected_keys)
        missing_keys = sorted(expected_keys - supplied_keys)
        if unknown_keys:
            raise ValueError(f"MANUAL candidate #{i} unknown parameter(s): {unknown_keys}")
        if missing_keys:
            raise ValueError(f"MANUAL candidate #{i} missing required parameter(s): {missing_keys}")
        spec = validate_candidate(raw, runtime, i)
        if spec is None:
            raise ValueError(f"MANUAL candidate #{i} is outside legal/capacity authority: {raw.get('name') or raw.get('family')}")
        # MANUAL is exact Owner intent: transformed parameter values are never silent.
        executable_keys = set(spec.params.keys())
        if executable_keys != expected_keys:
            raise ValueError(
                f"MANUAL candidate #{i} executable keyset drift: "
                f"expected={sorted(expected_keys)} executable={sorted(executable_keys)}"
            )
        for key, value in spec.params.items():
            if key not in supplied:
                raise ValueError(f"MANUAL candidate #{i} missing required parameter: {key}")
            try:
                if abs(float(value) - float(supplied[key])) > 1e-12:
                    raise ValueError(f"MANUAL candidate #{i} parameter {key} would be coerced from {supplied[key]} to {value}")
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ValueError) and "would be coerced" in str(exc):
                    raise
                if value != supplied[key]:
                    raise ValueError(f"MANUAL candidate #{i} parameter {key} is invalid") from exc
        validated.append({"family": spec.family, "name": spec.name, "params": deepcopy(spec.params)})

    agent["manual_research"]["candidates"] = deepcopy(validated)
    fc["manual_research"]["candidates"] = deepcopy(validated)
    return runtime, validated



def bind_manual_capacity_authority(runtime: dict, candidates: list[dict], hardware_profile: dict, dataset_capacity: dict) -> tuple[dict,list[dict]]:
    """Bind MANUAL exact candidates to the same frozen dynamic capacity authority.

    UI compilation can validate exact legal identity before a Factory exists.  The
    immutable dataset/hardware snapshots only exist at Factory start, so final Manual
    resource/scientific admission is intentionally performed here.
    """
    out=runtime
    agent=out.setdefault("agent",{})
    plan=deepcopy(agent.get("research_plan") or {})
    ra=out.get("research_architecture") or {}
    guidance=recommended_capacity_envelopes(dataset_capacity or {},hardware_profile or {})
    budget={
        "safe_ram_fraction":float(ra.get("safe_ram_fraction",0.75)),
        "safe_vram_fraction":float(ra.get("safe_vram_fraction",0.80)),
        "max_single_experiment_minutes":int(ra.get("max_single_experiment_minutes",120)),
        "max_experiments":len(candidates or []),
    }
    plan["dataset_capacity_profile"]=deepcopy(dataset_capacity or {})
    plan["capacity_guidance"]=deepcopy(guidance)
    plan["resource_capacity"]=compile_resource_capacity(hardware_profile or {},budget,dataset_capacity or {},out)
    plan["capacity_evidence"]={"schema":"MAX_CAPACITY_EVIDENCE_SIGNAL_V1","status":"OWNER_MANUAL_NOT_SEARCH_ADAPTIVE","expansion_factor":1.0}
    plan["capacity_authority"]={
        "schema":"MAX_DYNAMIC_MODEL_CAPACITY_AUTHORITY_V1",
        "legal":"MODEL_REGISTRY_IMPLEMENTATION_BOUNDS",
        "resource":"FROZEN_HARDWARE_ARCHITECTURE_SPECIFIC_PREFLIGHT",
        "scientific":"CANDIDATE_MEMORY_SEQUENCE_EFFECTIVE_INFORMATION",
        "recommended_envelope":"STARTING_GUIDANCE_ONLY_NOT_MANUAL_REJECTION",
        "effective":"MIN_LEGAL_RESOURCE_SCIENTIFIC_ON_ACTUAL_PARAMETER_COUNT",
    }
    agent["research_plan"]=plan
    evidence=[]
    for i,row in enumerate(candidates or [],1):
        spec=CandidateSpec(str(row.get("family") or ""),str(row.get("name") or f"manual_{i:02d}"),deepcopy(row.get("params") or {}))
        cap=candidate_capacity_contract(spec,out)
        evidence.append({"name":spec.name,"family":spec.family,"capacity_contract":cap})
        if not cap.get("passed",False):
            raise ValueError(
                f"MANUAL_DYNAMIC_CAPACITY_REJECTED:{spec.name}:"
                f"{cap.get('rejecting_authority') or cap.get('first_failed_gate') or 'CAPACITY'}"
            )
    return out,evidence

def provenance(mode: str) -> dict:
    mode = str(mode or "AUTO").upper()
    if mode == "MANUAL":
        return {
            "schema": SCHEMA,
            "research_mode": "MANUAL",
            "proposal_authority": "OWNER",
            "llm_used": False,
            "deterministic_discovery_used": False,
            "validation_authority": "DETERMINISTIC",
        }
    return {
        "schema": SCHEMA,
        "research_mode": "AUTO",
        "proposal_authority": "FACTORY",
        "llm_used": "CONFIGURED_ROUTE_WITH_DETERMINISTIC_FALLBACK",
        "deterministic_discovery_used": True,
        "validation_authority": "DETERMINISTIC",
    }
