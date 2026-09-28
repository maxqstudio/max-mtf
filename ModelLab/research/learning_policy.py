from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

SCHEMA="MAX_DETERMINISTIC_LEARNING_POLICY_V1"
ACTIONS=(
    "SELECTIVITY_POLICY","FEATURE_ABLATION","TRAINING_MEMORY","MODEL_ARCHITECTURE",
    "HYBRID_ABLATION","SEED_STABILITY","LABEL_GEOMETRY","REGIME_POLICY",
)

# These priors are scientific navigation hints, never PASS/FAIL authority.
_GATE_PRIORS={
    "MIN_TRADES": {"SELECTIVITY_POLICY":1.0,"TRAINING_MEMORY":0.70,"FEATURE_ABLATION":0.60,"MODEL_ARCHITECTURE":0.45},
    "COVERAGE": {"SELECTIVITY_POLICY":1.0,"FEATURE_ABLATION":0.65,"TRAINING_MEMORY":0.60},
    "WORST": {"MODEL_ARCHITECTURE":0.85,"FEATURE_ABLATION":0.80,"TRAINING_MEMORY":0.75,"SEED_STABILITY":0.60},
    "SEED": {"SEED_STABILITY":1.0,"MODEL_ARCHITECTURE":0.75,"TRAINING_MEMORY":0.45},
    "EXPECTANCY": {"FEATURE_ABLATION":0.80,"MODEL_ARCHITECTURE":0.75,"LABEL_GEOMETRY":0.55,"SELECTIVITY_POLICY":0.50},
    "PROFIT_FACTOR": {"FEATURE_ABLATION":0.80,"MODEL_ARCHITECTURE":0.75,"REGIME_POLICY":0.55},
    "DRAWDOWN": {"FEATURE_ABLATION":0.80,"MODEL_ARCHITECTURE":0.75,"REGIME_POLICY":0.70,"SELECTIVITY_POLICY":0.55},
    "CVAR": {"REGIME_POLICY":0.85,"FEATURE_ABLATION":0.75,"MODEL_ARCHITECTURE":0.70},
    "SHARPE": {"FEATURE_ABLATION":0.75,"MODEL_ARCHITECTURE":0.70,"REGIME_POLICY":0.65},
    "SORTINO": {"FEATURE_ABLATION":0.75,"MODEL_ARCHITECTURE":0.70,"REGIME_POLICY":0.65},
    "PBO": {"FEATURE_ABLATION":0.70,"MODEL_ARCHITECTURE":0.65,"TRAINING_MEMORY":0.60,"SEED_STABILITY":0.55},
}


def _gate(topology: dict) -> str:
    t=topology if isinstance(topology,dict) else {}
    return str(t.get("dominant_first_failed_gate") or t.get("dominant_failure_group") or "UNKNOWN").upper()


def _prior(gate: str, action: str) -> float:
    score=0.35
    for key,weights in _GATE_PRIORS.items():
        if key in gate:
            score=max(score,float(weights.get(action,0.25)))
    return score


def recommend_learning_actions(memory: dict, failure_topology: dict, *, limit: int=5) -> dict:
    stats=(memory or {}).get("learning_policy_stats") if isinstance((memory or {}).get("learning_policy_stats"),dict) else {}
    by_kind=stats.get("by_action_kind") if isinstance(stats.get("by_action_kind"),dict) else {}
    by_gate=stats.get("by_failure_gate") if isinstance(stats.get("by_failure_gate"),dict) else {}
    gate=_gate(failure_topology)
    exact=by_gate.get(gate) if isinstance(by_gate.get(gate),dict) else {}
    rows=[]
    total_experience=int(stats.get("experience_count",0) or 0)
    for action in ACTIONS:
        global_row=by_kind.get(action) if isinstance(by_kind.get(action),dict) else {}
        exact_row=exact.get(action) if isinstance(exact.get(action),dict) else {}
        n_global=int(global_row.get("attempts",0) or 0); n_exact=int(exact_row.get("attempts",0) or 0)
        empirical=float(global_row.get("posterior_utility",0.5) or 0.5)
        if n_exact:
            empirical=0.35*empirical+0.65*float(exact_row.get("posterior_utility",0.5) or 0.5)
        contextual=_prior(gate,action)
        # Small deterministic exploration bonus prevents permanent lock-in when evidence is scarce.
        exploration=min(0.18, 0.18/math.sqrt(1.0+n_global))
        score=0.55*empirical+0.35*contextual+0.10*(exploration/0.18 if exploration else 0.0)
        rows.append({
            "action_kind":action,"score":round(score,6),"context_prior":round(contextual,4),
            "historical_utility":round(empirical,4),"global_attempts":n_global,"matching_gate_attempts":n_exact,
            "authority":"ADVISORY_NEXT_EXPERIMENT_RANKING_ONLY",
        })
    rows.sort(key=lambda r:(float(r["score"]),-int(r["global_attempts"]),r["action_kind"]),reverse=True)
    return {
        "schema":SCHEMA,"dominant_failure_gate":gate,"experience_count":total_experience,
        "recommendations":deepcopy(rows[:max(1,int(limit))]),
        "may_emit_pass_fail":False,"may_promote":False,"may_read_protected_oos":False,
        "policy_mode":"DETERMINISTIC_STRUCTURED_MEMORY_RANKING",
    }
