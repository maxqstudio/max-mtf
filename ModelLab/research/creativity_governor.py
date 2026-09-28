from __future__ import annotations

from collections import Counter
from copy import deepcopy

SCHEMA = "CP_ADAPTIVE_CREATIVITY_GOVERNOR_V1"


def _clamp(v, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return max(lo, min(hi, 0.5))


def owner_creativity(cfg: dict) -> float:
    search = ((cfg.get("agent") or {}).get("search") or {})
    # R5 authority. Legacy configs fall back to a neutral 0.50 rather than an LLM
    # decoding temperature, because scientific creativity is a research-allocation knob.
    return _clamp(search.get("scientific_creativity", 0.50))


def llm_research_influence(cfg: dict) -> float:
    search = ((cfg.get("agent") or {}).get("search") or {})
    if "llm_research_influence" in search:
        return _clamp(search.get("llm_research_influence"))
    # Backward-compatible read of the R4 key. R5 UI writes the new name.
    return _clamp(search.get("llm_strategy_weight", 0.45))


def _seed_instability(topology: dict | None) -> bool:
    topo = topology or {}
    gates = Counter({str(k): int(v or 0) for k, v in (topo.get("first_failed_gate_counts") or {}).items()})
    gates.update({str(k): int(v or 0) for k, v in (topo.get("all_failed_gate_counts") or {}).items()})
    if any("SEED_STABILITY" in k.upper() and v > 0 for k, v in gates.items()):
        return True
    for row in topo.get("candidate_rows") or []:
        if not isinstance(row, dict):
            continue
        sc = row.get("seed_confirmation") if isinstance(row.get("seed_confirmation"), dict) else {}
        if sc and (str(sc.get("status") or "").upper() in {"FAIL", "FAILED", "SEED_UNSTABLE"} or sc.get("passed") is False):
            return True
        for sr in sc.get("seed_results") or []:
            if isinstance(sr, dict) and sr.get("passed") is False:
                return True
    return False


def _dominant_failure_share(topology: dict | None) -> float:
    counts = (topology or {}).get("first_failed_gate_counts") or {}
    vals = [max(0, int(v or 0)) for v in counts.values()]
    total = sum(vals)
    return (max(vals) / total) if total and vals else 0.0


def _near_miss(board: list[dict] | None) -> bool:
    margins=[]
    for row in board or []:
        if not isinstance(row, dict) or bool(row.get("cv_gate_pass")):
            continue
        m=((row.get("failure_margins") or {}).get("closest_failed_gate") or {}).get("relative_margin")
        try:
            margins.append(float(m))
        except Exception:
            pass
    if not margins:
        return False
    # Relative margin is negative on failure. Within 10% is a bounded local-repair case.
    return max(margins) >= -0.10


def adaptive_creativity_profile(cfg: dict, *, board: list[dict] | None = None,
                                failure_topology: dict | None = None,
                                stale_rounds: int = 0) -> dict:
    """Translate Owner creativity into *what to test next*, never into weaker gates.

    The profile changes allocation breadth, mutation radius and hypothesis temperature.
    KPI thresholds, chronology, seed sets, locked data and PASS/FAIL authority are not
    included in the output and therefore cannot be relaxed by this governor.
    """
    owner = owner_creativity(cfg)
    stale = max(0, int(stale_rounds or 0))
    seed_unstable = _seed_instability(failure_topology)
    dominant_share = _dominant_failure_share(failure_topology)
    near = _near_miss(board)

    mode = "BALANCED"
    structural_pressure = 0.0
    local_pressure = 0.0
    if seed_unstable:
        mode = "STABILITY_REPAIR"
        local_pressure = 0.70
    elif stale >= 2 and dominant_share >= 0.60:
        mode = "STRUCTURAL_ESCAPE"
        structural_pressure = min(1.0, 0.45 + 0.15 * stale)
    elif near:
        mode = "LOCAL_REFINEMENT"
        local_pressure = 0.60
    elif stale >= 2:
        mode = "BROADEN_SEARCH"
        structural_pressure = min(0.75, 0.25 + 0.12 * stale)

    # Base creativity controls breadth; evidence state can move it, but never above 0.90.
    adaptive = owner
    if structural_pressure:
        adaptive = min(0.90, owner + (1.0-owner) * 0.55 * structural_pressure)
    if local_pressure:
        adaptive = max(0.15, owner * (1.0 - 0.45 * local_pressure))

    exploration = _clamp(0.25 + 0.55 * adaptive, 0.15, 0.85)
    architecture = _clamp(0.10 + 0.60 * adaptive + 0.20 * structural_pressure)
    family = _clamp(0.10 + 0.50 * adaptive + 0.25 * structural_pressure)
    ablation = _clamp(0.15 + 0.55 * adaptive)
    backlog = _clamp(0.02 + 0.18 * adaptive)
    local = _clamp(0.65 - 0.45 * adaptive + 0.30 * local_pressure, 0.10, 0.85)
    mutation_mult = max(0.55, min(1.80, 0.70 + 0.80 * adaptive - 0.25 * local_pressure + 0.25 * structural_pressure))

    # Phase-aware temperatures. Forensic interpretation stays conservative regardless
    # of Owner creativity; hypothesis generation gets the bounded creative headroom.
    phase_temps = {
        "CONNECTION_TEST": 0.0,
        "DIRECTOR_PREFLIGHT": round(min(0.55, 0.10 + 0.40 * adaptive), 3),
        "DIRECTOR_GENERATION_REVIEW": round(min(0.45, 0.08 + 0.32 * adaptive), 3),
        "DISCOVERY_HYPOTHESIS": round(min(0.60, 0.12 + 0.45 * adaptive), 3),
        "STAGE_FORENSIC": 0.05,
        "FAILURE_LEARNING": round(min(0.35, 0.08 + 0.22 * adaptive), 3),
        "POLICY_REVIEW": 0.08,
    }

    return {
        "schema": SCHEMA,
        "owner_creativity": round(owner, 4),
        "adaptive_creativity": round(adaptive, 4),
        "mode": mode,
        "seed_instability_detected": bool(seed_unstable),
        "stale_rounds": stale,
        "dominant_failure_share": round(dominant_share, 4),
        "near_miss_detected": bool(near),
        "target_exploration_ratio": round(exploration, 4),
        "local_refinement_share": round(local, 4),
        "architecture_breadth": round(architecture, 4),
        "family_exploration": round(family, 4),
        "ablation_breadth": round(ablation, 4),
        "backlog_idea_share": round(backlog, 4),
        "mutation_scale_multiplier": round(mutation_mult, 4),
        "phase_temperatures": phase_temps,
        "immutable_authority": [
            "KPI_GATES", "CHRONOLOGY", "OWNER_TOPOLOGY_PRIORITY", "CAPACITY_HARD_CEILING",
            "CPCV_SEED_SET", "LOCKED_FORWARD", "PASS_FAIL", "RISK_EXECUTION"
        ],
    }


def phase_temperature(cfg: dict, phase: str, profile: dict | None = None) -> float:
    p = profile if isinstance(profile, dict) else adaptive_creativity_profile(cfg)
    temps = p.get("phase_temperatures") if isinstance(p.get("phase_temperatures"), dict) else {}
    if str(phase) in temps:
        return float(temps[str(phase)])
    # Legacy fallback only; R5 no longer exposes this as the Owner creativity control.
    llm = ((cfg.get("agent") or {}).get("llm") or {})
    return max(0.0, min(1.0, float(llm.get("temperature", 0.15) or 0.15)))


def apply_llm_priority_influence(prior: float, influence: float) -> float:
    """Blend a Scientist family weight toward neutral 1.0 using the same influence
    authority used for exploration. influence=0 => no effect; 1 => full prior.
    """
    p = max(0.35, min(3.0, float(prior)))
    w = _clamp(influence)
    return 1.0 + w * (p - 1.0)
