from __future__ import annotations

from copy import deepcopy
from typing import Any

ALLOWED_TOOLS={
    "TOP_CANDIDATES",
    "FAILURE_TOPOLOGY",
    "FOLD_FORENSICS",
    "FAMILY_STATS",
    "FIDELITY_ATTRIBUTION",
    "PARENT_CHILD",
    "HYPOTHESIS_MEMORY",
    "LEARNING_POLICY",
    "SCIENTIST_SKILLS",
}


def _rows(context: dict, key: str) -> list[dict]:
    value=context.get(key)
    return [deepcopy(x) for x in value] if isinstance(value,list) else []


def inspect_request(context: dict, request: dict, hypothesis_memory: list[dict] | None=None) -> dict:
    tool=str((request or {}).get("tool") or "").strip().upper()
    if tool not in ALLOWED_TOOLS:
        return {"tool":tool or "UNKNOWN","status":"REJECTED","reason":"TOOL_NOT_ALLOWED"}
    candidate=str((request or {}).get("candidate") or "").strip()
    if tool=="TOP_CANDIDATES":
        return {"tool":tool,"status":"PASS","evidence":_rows(context,"top_results")[:8]}
    if tool=="FAILURE_TOPOLOGY":
        return {"tool":tool,"status":"PASS","evidence":deepcopy(context.get("failure_topology") or {})}
    if tool=="FOLD_FORENSICS":
        rows=_rows(context,"fold_forensics")
        if candidate: rows=[r for r in rows if str(r.get("name") or "")==candidate]
        return {"tool":tool,"status":"PASS","candidate":candidate or None,"evidence":rows[:12]}
    if tool=="FAMILY_STATS":
        return {"tool":tool,"status":"PASS","evidence":deepcopy(context.get("family_stats") or {})}
    if tool=="FIDELITY_ATTRIBUTION":
        return {"tool":tool,"status":"PASS","evidence":deepcopy({
            "fidelity_ladder":context.get("fidelity_ladder") or {},
            "screen_failure_topology":context.get("screen_failure_topology") or {},
            "wfa_pass_count":context.get("wfa_pass_count"),
            "wfa_total_count":context.get("wfa_total_count"),
        })}
    if tool=="PARENT_CHILD":
        rows=_rows(context,"top_results")
        if candidate: rows=[r for r in rows if str(r.get("name") or "")==candidate]
        return {"tool":tool,"status":"PASS","candidate":candidate or None,"evidence":rows[:4]}
    if tool=="HYPOTHESIS_MEMORY":
        return {"tool":tool,"status":"PASS","evidence":deepcopy(hypothesis_memory or [])[-16:]}
    if tool=="LEARNING_POLICY":
        return {"tool":tool,"status":"PASS","evidence":deepcopy(context.get("learning_policy") or {})}
    if tool=="SCIENTIST_SKILLS":
        return {"tool":tool,"status":"PASS","evidence":deepcopy(context.get("scientist_skills") or {})}
    return {"tool":tool,"status":"REJECTED","reason":"UNHANDLED_TOOL"}


def attribute_previous_proposals(context: dict, lineage: list[dict]) -> list[dict]:
    """Attach deterministic observed fate to prior Scientist proposals.

    This is credit assignment only. It never upgrades a candidate to PASS and never
    changes deterministic gate outcomes.
    """
    top=_rows(context,"top_results")
    by_name={str(r.get("name") or ""):r for r in top if str(r.get("name") or "")}
    out=[]
    for row in lineage or []:
        if not isinstance(row,dict): continue
        rr=deepcopy(row); name=str(rr.get("candidate_name") or "")
        observed=by_name.get(name)
        if observed is not None:
            rr["fate"]="FULL_WFA_OBSERVED"
            rr["observed"]={k:deepcopy(observed.get(k)) for k in (
                "cv_gate_pass","cv_first_failed_gate","overall_expectancy_r","median_expectancy_r",
                "worst_expectancy_r","median_profit_factor","median_max_drawdown_r","total_validation_trades",
                "selection_score","failure_margins"
            ) if k in observed}
        out.append(rr)
    return out
