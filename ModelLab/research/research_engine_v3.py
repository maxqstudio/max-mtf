from __future__ import annotations

"""Scientific Research Engine V3 diagnostics and fidelity utilities.

R2 scope is deliberately narrow:
- cheap-screen -> full-WFA fidelity ladder,
- hard-gate failure margins (diagnostic only),
- failure topology summaries,
- append-only all-trial ledger helpers.

Nothing in this module can grant acceptance. Full WFA remains governed by
``kpi.walk_forward_acceptance`` and CPCV remains a later finalist stage.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Iterable

from models.models import CandidateSpec
from models.model_registry import get_bounds, effective_bounds, is_hybrid_family
from models.topology_allocation import configured_hybrid_priority, allocation_counts

SCHEMA = "CP_RESEARCH_ENGINE_V3_R2"
LEDGER_SCHEMA = "CP_ALL_TRIAL_LEDGER_V1"
TOPOLOGY_SCHEMA = "CP_FAILURE_TOPOLOGY_V1"
MARGIN_SCHEMA = "CP_FAILURE_MARGIN_V1"

# Explicit direction is safer than guessing from PASS/FAIL. These are the current
# lower-is-better WFA gates; unknown gates default to higher-is-better.
LOWER_IS_BETTER = {
    "CV_MEDIAN_MAX_DD",
    "CV_WORST_FOLD_MAX_DD",
    "CV_REGIME_CONCENTRATION",
    "CV_TOP10_WIN_CONCENTRATION",
}


def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def gate_failure_margins(acceptance: dict) -> dict:
    """Describe each hard gate's margin without changing its authority.

    ``relative_margin >= 0`` means the gate is met. Negative means shortfall.
    The value is diagnostic only and MUST NOT be summed into an acceptance score.
    """
    rows = []
    for g in acceptance.get("gates") or []:
        name = str(g.get("name") or g.get("gate") or "UNKNOWN")
        actual = _num(g.get("actual")); threshold = _num(g.get("threshold"))
        direction = str(g.get("direction") or ("LOWER" if name in LOWER_IS_BETTER else "HIGHER"))
        raw = None; rel = None
        if actual is not None and threshold is not None:
            raw = (threshold - actual) if direction == "LOWER" else (actual - threshold)
            denom = max(abs(threshold), 1.0 if abs(threshold) < 1e-12 else abs(threshold), 1e-9)
            rel = raw / denom
        rows.append({
            "schema": MARGIN_SCHEMA,
            "gate": name,
            "group": str(g.get("group") or "unknown"),
            "severity": str(g.get("severity") or "QUALITY"),
            "passed": bool(g.get("passed")),
            "direction": direction,
            "actual": g.get("actual"),
            "threshold": g.get("threshold"),
            "raw_margin": raw,
            "relative_margin": rel,
        })
    failed = [x for x in rows if not x["passed"]]
    # Closest-to-pass = least-negative relative margin; deepest failure = most negative.
    finite_failed = [x for x in failed if x.get("relative_margin") is not None]
    closest = max(finite_failed, key=lambda x: x["relative_margin"]) if finite_failed else (failed[0] if failed else None)
    deepest = min(finite_failed, key=lambda x: x["relative_margin"]) if finite_failed else (failed[0] if failed else None)
    return {
        "schema": MARGIN_SCHEMA,
        "passed": bool(acceptance.get("passed")),
        "first_failed_gate": acceptance.get("first_failed_gate"),
        "failed_gate_count": len(failed),
        "closest_failed_gate": deepcopy(closest),
        "deepest_failed_gate": deepcopy(deepest),
        "gates": rows,
    }


def failure_topology(rows: Iterable[dict], *, authority: str = "FULL_WFA") -> dict:
    """Aggregate where candidate research fails; never grants qualification."""
    rows = [r for r in rows if isinstance(r, dict)]
    first = {}; allg = {}; groups = {}; families = {}; passed = 0
    near = []
    for r in rows:
        fam = str(r.get("family") or "UNKNOWN")
        fr = families.setdefault(fam, {"total": 0, "passed": 0, "first_failed": {}})
        fr["total"] += 1
        if bool(r.get("cv_gate_pass")):
            passed += 1; fr["passed"] += 1
            continue
        fg = str(r.get("cv_first_failed_gate") or "UNKNOWN")
        first[fg] = first.get(fg, 0) + 1
        fr["first_failed"][fg] = fr["first_failed"].get(fg, 0) + 1
        reasons = [str(x) for x in (r.get("cv_gate_reasons") or [])] or [fg]
        for g in reasons:
            allg[g] = allg.get(g, 0) + 1
        margins = r.get("failure_margins") or {}
        gm = margins.get("gates") or []
        for g in gm:
            if not bool(g.get("passed")):
                grp = str(g.get("group") or "unknown")
                groups[grp] = groups.get(grp, 0) + 1
        near.append({
            "name": r.get("name"), "family": fam,
            "failed_gate_count": int(margins.get("failed_gate_count", len(reasons)) or len(reasons)),
            "first_failed_gate": fg,
            "closest_failed_gate": (margins.get("closest_failed_gate") or {}).get("gate"),
            "closest_relative_margin": (margins.get("closest_failed_gate") or {}).get("relative_margin"),
            "selection_score": r.get("selection_score"),
        })
    near.sort(key=lambda x: (x["failed_gate_count"], -(float(x["closest_relative_margin"]) if x["closest_relative_margin"] is not None else -999.0), -(float(x["selection_score"]) if x["selection_score"] is not None else -1e99)))
    return {
        "schema": TOPOLOGY_SCHEMA,
        "authority": authority,
        "candidate_count": len(rows),
        "passed_count": passed,
        "failed_count": len(rows) - passed,
        "first_failed_gate_counts": dict(sorted(first.items(), key=lambda kv: (-kv[1], kv[0]))),
        "all_failed_gate_counts": dict(sorted(allg.items(), key=lambda kv: (-kv[1], kv[0]))),
        "failed_group_counts": dict(sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))),
        "family_breakdown": families,
        "dominant_first_failed_gate": max(first, key=first.get) if first else None,
        "dominant_failure_group": max(groups, key=groups.get) if groups else None,
        "near_miss_candidates": near[:12],
    }


def cheap_screen_spec(spec: CandidateSpec, cfg: dict) -> CandidateSpec:
    """Return same scientific architecture with only training-resource knobs reduced.

    Search dimensions are NOT changed. Only estimator/epoch budget is capped for the
    disposable screen. Full WFA always re-runs the original CandidateSpec.
    """
    fc = ((cfg.get("agent") or {}).get("fidelity_ladder") or {})
    scale = max(0.10, min(1.0, float(fc.get("cheap_resource_scale", 0.50))))
    p = dict(spec.params)
    bounds = effective_bounds(cfg,spec.family)
    for key in ("n_estimators", "policy_n_estimators", "epochs", "gru_epochs"):
        if key not in p or key not in bounds:
            continue
        lo, hi, typ = bounds[key]
        value = max(float(lo), min(float(hi), float(p[key]) * scale))
        p[key] = int(round(value)) if typ is int else float(value)
    return CandidateSpec(spec.family, spec.name + "__screen", p)


def cheap_screen_cfg(cfg: dict) -> dict:
    out = deepcopy(cfg)
    fc = ((cfg.get("agent") or {}).get("fidelity_ladder") or {})
    full = int((cfg.get("split") or {}).get("walk_forward_folds", 3))
    cheap = int(fc.get("cheap_folds", max(2, full - 1)))
    # candidate_cv requires a meaningful expanding-WF structure; never exceed full.
    cheap = max(2, min(full, cheap))
    out.setdefault("split", {})["walk_forward_folds"] = cheap
    # Cheap fidelity allocates compute only. Small-sample Sharpe/Sortino/PSR/DSR/
    # Calmar/Ulcer/CVaR must not decide who receives Full-WFA opportunity. They remain
    # observable diagnostics; hard risk authority begins at Full-WFA and later gates.
    discovery=((out.get("gate_kpis") or {}).get("discovery") or {})
    for spec in (discovery.get("risk_kpis") or {}).values():
        if isinstance(spec,dict):
            spec["enabled"]=False
    out.setdefault("scientific_runtime",{})["cheap_screen_risk_kpi_authority"]="DIAGNOSTIC_ONLY"
    return out


def _diverse_rank(rows: list[dict], limit: int) -> list[dict]:
    """Take the best row per family first, then fill remaining slots by rank."""
    ranked=sorted(rows,key=lambda r:(bool(r.get("cv_gate_pass")),float(r.get("selection_score",-1e99))),reverse=True)
    out=[]; used=set()
    for r in ranked:
        fam=str(r.get("family") or "")
        if fam in used:
            continue
        out.append(r); used.add(fam)
        if len(out)>=limit:
            return out
    for r in ranked:
        if r in out:
            continue
        out.append(r)
        if len(out)>=limit:
            break
    return out


def select_full_wfa_promotions(screen_rows: list[dict], cfg: dict) -> list[str]:
    """Allocate full-WFA opportunity without erasing Owner topology/family coverage.

    Cheap screen remains resource-only.  The Owner Single↔Hybrid slider is preserved
    through the fidelity ladder, and within each topology we promote family-diverse
    evidence before taking second candidates from the same family.
    """
    if not screen_rows:
        return []
    fc = ((cfg.get("agent") or {}).get("fidelity_ladder") or {})
    frac = max(0.05, min(1.0, float(fc.get("promote_fraction", 0.34))))
    min_n = max(1, int(fc.get("min_promote_per_round", 2)))
    max_n = max(min_n, int(fc.get("max_promote_per_round", 3)))
    target = max(min_n, int(math.ceil(len(screen_rows) * frac)))
    target = min(len(screen_rows), max_n, target)

    priority=configured_hybrid_priority(cfg,legacy_none=True)
    if priority is None:
        chosen=_diverse_rank(screen_rows,target)
        return [str(r.get("original_name") or r.get("name")) for r in chosen]

    singles=[r for r in screen_rows if not is_hybrid_family(str(r.get("family") or ""))]
    hybrids=[r for r in screen_rows if is_hybrid_family(str(r.get("family") or ""))]
    alloc=allocation_counts(target,priority,single_available=bool(singles),hybrid_available=bool(hybrids))
    chosen=[]
    chosen.extend(_diverse_rank(singles,int(alloc.get("single",0))))
    chosen.extend(_diverse_rank(hybrids,int(alloc.get("hybrid",0))))
    # Defensive fill only if one topology cannot satisfy its allocation.
    if len(chosen)<target:
        remaining=[r for r in sorted(screen_rows,key=lambda r:(bool(r.get("cv_gate_pass")),float(r.get("selection_score",-1e99))),reverse=True) if r not in chosen]
        chosen.extend(remaining[:target-len(chosen)])
    return [str(r.get("original_name") or r.get("name")) for r in chosen[:target]]


def trial_record(*, run_id: str, round_no: int, stage: str, spec: CandidateSpec,
                 metrics: dict, acceptance: dict, promoted: bool | None = None,
                 full_spec: CandidateSpec | None = None) -> dict:
    margins = gate_failure_margins(acceptance)
    return {
        "schema": LEDGER_SCHEMA,
        "run_id": str(run_id),
        "trial_stage": str(stage),
        "round": int(round_no),
        "name": str(spec.name),
        "original_name": str(full_spec.name if full_spec is not None else spec.name),
        "family": str(spec.family),
        "params": deepcopy(spec.params),
        "full_params": deepcopy(full_spec.params) if full_spec is not None else deepcopy(spec.params),
        "promoted_to_full_wfa": promoted,
        "cv_gate_pass": bool(acceptance.get("passed")),
        "cv_first_failed_gate": acceptance.get("first_failed_gate"),
        "cv_gate_reasons": list(acceptance.get("reasons") or []),
        "selection_score": metrics.get("selection_score"),
        "metrics": {k: metrics.get(k) for k in (
            "total_validation_trades", "median_profit_factor", "overall_expectancy_r", "median_expectancy_r", "worst_expectancy_r",
            "median_max_drawdown_r", "worst_fold_max_drawdown_r", "median_recovery_factor",
            "worst_fold_recovery_factor", "positive_fold_ratio", "median_stress_x1_50_expectancy_r",
            "median_threshold_plateau", "total_fit_seconds", "training_memory_months", "take_threshold")},
        "failure_margins": margins,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
    }


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, default=str, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            x = json.loads(line)
            if isinstance(x, dict): out.append(x)
        except Exception:
            continue
    return out
