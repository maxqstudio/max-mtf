from __future__ import annotations

import math
from typing import Iterable

from models.model_registry import is_hybrid_family

SCHEMA = "CP_TOPOLOGY_PRIORITY_V1"


def clamp_hybrid_priority(value, default: float = 0.50) -> float:
    try:
        value = float(value)
    except Exception:
        value = float(default)
    return max(0.0, min(1.0, value))


def configured_hybrid_priority(cfg: dict, *, legacy_none: bool = False) -> float | None:
    """Return Owner hybrid-candidate priority.

    A persisted research plan wins over mutable UI config so a running Factory cannot
    silently change allocation semantics. Older evidence without either field may ask
    for ``legacy_none=True`` to preserve its historical planner behaviour.
    """
    plan = (((cfg or {}).get("agent") or {}).get("research_plan") or {})
    topo = plan.get("topology_priority") if isinstance(plan, dict) else None
    if isinstance(topo, dict) and "hybrid" in topo:
        return clamp_hybrid_priority(topo.get("hybrid"))
    ra = ((cfg or {}).get("research_architecture") or {})
    if "hybrid_priority" in ra:
        return clamp_hybrid_priority(ra.get("hybrid_priority"))
    return None if legacy_none else 0.50


def effective_hybrid_priority(cfg: dict, llm_strategy: dict | None = None, *, legacy_none: bool = False) -> float | None:
    """Return current candidate topology allocation authority.

    In SCIENTIST_DIRECTED mode the Owner freezes the allowed topology universe while
    the Scientist may move the single/hybrid allocation inside [0,1] as evidence
    changes. Deterministic clamps remain final authority.
    """
    plan = (((cfg or {}).get("agent") or {}).get("research_plan") or {})
    topo = plan.get("topology_priority") if isinstance(plan, dict) else {}
    mode=str((topo or {}).get("mode") or ((cfg or {}).get("research_architecture") or {}).get("topology_selection_mode") or "OWNER_FIXED").upper()
    allowed=set(str(x).upper() for x in ((topo or {}).get("allowed_topologies") or ["SINGLE","HYBRID"]))
    if mode=="SCIENTIST_DIRECTED":
        if allowed=={"SINGLE"}: return 0.0
        if allowed=={"HYBRID"}: return 1.0
        if isinstance(llm_strategy,dict) and "hybrid_priority" in llm_strategy:
            return clamp_hybrid_priority(llm_strategy.get("hybrid_priority"))
    return configured_hybrid_priority(cfg,legacy_none=legacy_none)


def topology_name(family: str) -> str:
    return "HYBRID" if is_hybrid_family(family) else "SINGLE"


def allocation_counts(total: int, hybrid_priority: float, *, single_available: bool = True, hybrid_available: bool = True) -> dict:
    total = max(0, int(total))
    p = clamp_hybrid_priority(hybrid_priority)
    if total == 0:
        return {"single": 0, "hybrid": 0, "configured_hybrid_priority": p, "constraint": None}
    if hybrid_available and not single_available:
        return {"single": 0, "hybrid": total, "configured_hybrid_priority": p, "constraint": "SINGLE_UNAVAILABLE"}
    if single_available and not hybrid_available:
        return {"single": total, "hybrid": 0, "configured_hybrid_priority": p, "constraint": "HYBRID_UNAVAILABLE"}
    if not single_available and not hybrid_available:
        return {"single": 0, "hybrid": 0, "configured_hybrid_priority": p, "constraint": "NO_ELIGIBLE_TOPOLOGY"}
    # Round-half-up gives intuitive allocations: 12@0.25 -> 3, 12@0.50 -> 6.
    hybrid = int(math.floor(total * p + 0.5))
    hybrid = max(0, min(total, hybrid))
    return {"single": total - hybrid, "hybrid": hybrid, "configured_hybrid_priority": p, "constraint": None}


def split_families(families: Iterable[str]) -> tuple[list[str], list[str]]:
    singles, hybrids = [], []
    for f in families:
        (hybrids if is_hybrid_family(f) else singles).append(str(f))
    return singles, hybrids


def allocation_summary(total: int, hybrid_priority: float, families: Iterable[str]) -> dict:
    singles, hybrids = split_families(families)
    counts = allocation_counts(total, hybrid_priority, single_available=bool(singles), hybrid_available=bool(hybrids))
    p = counts["configured_hybrid_priority"]
    return {
        "schema": SCHEMA,
        "configured_hybrid_priority": p,
        "configured_single_priority": 1.0 - p,
        "target_single_candidates": counts["single"],
        "target_hybrid_candidates": counts["hybrid"],
        "single_family_count": len(singles),
        "hybrid_family_count": len(hybrids),
        "constraint": counts.get("constraint"),
        "authority": "OWNER_SLIDER_0_TO_1",
    }


def enforce_item_allocation(items, hybrid_priority: float, *, family_getter=None, target_total: int | None = None, available_families=None):
    """Deterministically enforce Owner topology allocation on an arbitrary item batch.

    ``available_families`` should be the compiled research universe.  This prevents a
    malformed LLM batch containing only hybrids from redefining 50/50 as 100% hybrid.
    Missing requested topology slots remain unfilled and deterministic Discovery can
    fill them later. Order is preserved inside each topology.
    """
    rows=list(items or [])
    total=len(rows) if target_total is None else max(0,min(len(rows),int(target_total)))
    if total<=0:
        return [],{"single":0,"hybrid":0,"rejected":len(rows)}
    getter=family_getter or (lambda x:getattr(x,"family",None) if not isinstance(x,dict) else x.get("family"))
    singles=[x for x in rows if not is_hybrid_family(str(getter(x) or ""))]
    hybrids=[x for x in rows if is_hybrid_family(str(getter(x) or ""))]
    if available_families is None:
        single_available=bool(singles); hybrid_available=bool(hybrids)
    else:
        af=list(available_families or [])
        single_available=any(not is_hybrid_family(str(f)) for f in af)
        hybrid_available=any(is_hybrid_family(str(f)) for f in af)
    alloc=allocation_counts(total,hybrid_priority,single_available=single_available,hybrid_available=hybrid_available)
    out=singles[:int(alloc.get("single",0))]+hybrids[:int(alloc.get("hybrid",0))]
    selected_ids={id(x) for x in out}
    admitted=[x for x in rows if id(x) in selected_ids]
    meta=dict(alloc); meta.update({"admitted":len(admitted),"rejected":len(rows)-len(admitted),"missing_slots":max(0,total-len(admitted))})
    return admitted,meta

