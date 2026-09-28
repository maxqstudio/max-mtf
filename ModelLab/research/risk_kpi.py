from __future__ import annotations

from copy import deepcopy
from typing import Any

# R6 Owner-approved defaults. The UI does not own these numbers; config does.
DEFAULT_RISK_KPIS: dict[str, dict[str, Any]] = {
    "sharpe": {
        "label": "Sharpe Ratio",
        "enabled": True,
        "threshold": 0.30,
        "direction": "higher",
        "unit": "ratio",
        "basis": "PER_TRADE_R_NON_ANNUALIZED",
        "wfa_metric": "median_sharpe_ratio",
        "point_metric": "sharpe_ratio",
        "canonical_aggregate": "median",
        "ui_min": -5.0, "ui_max": 10.0, "ui_step": 0.05,
        "min_trades": 30,
    },
    "sortino": {
        "label": "Sortino Ratio",
        "enabled": True,
        "threshold": 0.40,
        "direction": "higher",
        "unit": "ratio",
        "basis": "PER_TRADE_R; MAR=0.00R",
        "wfa_metric": "median_sortino_ratio",
        "point_metric": "sortino_ratio",
        "canonical_aggregate": "median",
        "ui_min": -5.0, "ui_max": 20.0, "ui_step": 0.05,
        "min_trades": 30,
    },
    "calmar": {
        "label": "Calmar / MAR",
        "enabled": True,
        "threshold": 1.00,
        "direction": "higher",
        "unit": "ratio",
        "basis": "LINEAR_ANNUALIZED_R_OVER_MAX_DD_R",
        "wfa_metric": "median_calmar_mar_ratio",
        "point_metric": "calmar_mar_ratio",
        "canonical_aggregate": "median",
        "ui_min": -10.0, "ui_max": 50.0, "ui_step": 0.10,
        "min_trades": 30, "min_sample_years": 0.25,
    },
    "psr": {
        "label": "PSR",
        "enabled": True,
        "threshold": 0.95,
        "direction": "higher",
        "unit": "probability",
        "basis": "PROBABILISTIC_SHARPE",
        "benchmark_sharpe": 0.20,
        "wfa_metric": "median_probabilistic_sharpe_ratio",
        "point_metric": "probabilistic_sharpe_ratio",
        "canonical_aggregate": "median",
        "ui_min": 0.0, "ui_max": 1.0, "ui_step": 0.01,
        "min_trades": 50,
    },
    "dsr": {
        "label": "DSR",
        "enabled": True,
        "threshold": 0.95,
        "direction": "higher",
        "unit": "probability",
        "basis": "DEFLATED_SHARPE; PREDECLARED_CYCLE_BUDGET",
        "wfa_metric": "median_deflated_sharpe_ratio",
        "point_metric": "deflated_sharpe_ratio",
        "canonical_aggregate": "median",
        "ui_min": 0.0, "ui_max": 1.0, "ui_step": 0.01,
        "min_trades": 100,
    },
    "ulcer": {
        "label": "Ulcer Index",
        "enabled": True,
        "threshold": 5.00,
        "direction": "lower",
        "unit": "R",
        "basis": "CHRONOLOGICAL_EQUITY_DRAWDOWN_R",
        "wfa_metric": "median_ulcer_index_r",
        "point_metric": "ulcer_index_r",
        "canonical_aggregate": "worst",
        "ui_min": 0.0, "ui_max": 100.0, "ui_step": 0.10,
        "min_trades": 20,
    },
    "cvar": {
        "label": "CVaR / Expected Shortfall 95%",
        "enabled": True,
        "threshold": -2.00,
        "direction": "higher",
        "unit": "R/day",
        "basis": "DAILY_AGGREGATED_R; WORST_5_PERCENT_DAYS",
        "wfa_metric": "median_daily_cvar95_r",
        "point_metric": "daily_cvar95_r",
        "canonical_aggregate": "worst",
        "ui_min": -20.0, "ui_max": 0.0, "ui_step": 0.10,
        "min_trades": 30, "min_active_days": 40, "min_tail_days": 2,
        "allow_positive_tail_floor": False,
    },
}


def ensure_risk_kpi_config(cfg: dict) -> dict[str, dict[str, Any]]:
    acceptance = cfg.setdefault("acceptance", {})
    current = acceptance.setdefault("risk_kpis", {})
    for key, default in DEFAULT_RISK_KPIS.items():
        if not isinstance(current.get(key), dict):
            current[key] = deepcopy(default)
            continue
        merged = deepcopy(default)
        merged.update(current[key])
        current[key] = merged
    # KPI-01 v1.3.2: daily CVaR is a signed lower-tail return floor. A positive
    # threshold means even the worst 5% trading days must be profitable, which is
    # occasionally intentional but was previously easy to configure by sign error.
    # Fail closed unless that unusually strict semantic is explicitly acknowledged.
    cvar=current.get("cvar") if isinstance(current.get("cvar"),dict) else None
    if cvar and bool(cvar.get("enabled",True)):
        threshold=float(cvar.get("threshold",-2.0))
        if threshold > 0.0 and not bool(cvar.get("allow_positive_tail_floor",False)):
            raise ValueError(
                "CVAR_SIGN_SEMANTICS: CVaR is average R of the worst 5% active trading days; "
                f"threshold {threshold:+.4f}R/day requires those worst days to remain profitable. "
                "Use a negative loss floor (for example -2.0) or set allow_positive_tail_floor=true explicitly."
            )
    # Unknown future KPI entries are retained; the registry is data-driven.
    return current


def psr_benchmark(cfg: dict) -> float:
    kpis = ensure_risk_kpi_config(cfg)
    return float((kpis.get("psr") or {}).get("benchmark_sharpe", 0.20))


def dsr_trial_count(cfg: dict) -> int:
    """Predeclared multiple-testing count including model, threshold and policy search.

    Earlier CPMF versions counted only the candidate budget, understating selection
    pressure because each candidate also searched a take-threshold grid and bounded
    Policy Discovery could test additional policies.  This remains deterministic and
    fixed before results are observed.
    """
    diag = cfg.setdefault("diagnostics", {}).setdefault("risk_adjusted", {})
    override = int(diag.get("dsr_trials_override", 0) or 0)
    if override > 0:
        return override
    factory = cfg.get("champion_factory") or {}
    agent = cfg.get("agent") or {}
    model_trials = max(1,int(factory.get("max_total_experiments", 0) or agent.get("max_experiments", 1) or 1))
    dep=cfg.get("deployment") or {}
    threshold_trials=max(1,len(list(dep.get("take_threshold_grid") or [])))
    pd=(agent.get("policy_discovery") or {}) if isinstance(agent.get("policy_discovery"),dict) else {}
    policy_trials=max(0,int(pd.get("max_policies",0) or 0)) if bool(pd.get("enabled",False)) else 0
    declared=model_trials*threshold_trials + policy_trials
    diag["dsr_trial_budget_components"]={
        "model_candidates":model_trials,"take_thresholds_per_candidate":threshold_trials,
        "bounded_policy_trials":policy_trials,"declared_total":declared,
        "schema":"CP_DSR_TRIAL_BUDGET_V2",
    }
    return max(1,int(declared))


def metric_pass(actual: Any, threshold: float, direction: str, epsilon: float = 1e-12) -> bool:
    if actual is None:
        return False
    try:
        value = float(actual)
    except Exception:
        return False
    if direction == "lower":
        return value <= float(threshold) + abs(float(epsilon))
    return value + abs(float(epsilon)) >= float(threshold)


def _evidence_snapshot(metrics: dict, mode: str) -> dict[str, float]:
    if mode == "wfa":
        folds=max(1,int(metrics.get("folds",1) or 1))
        trades=float(metrics.get("median_fold_trades", float(metrics.get("total_validation_trades",0) or 0)/folds) or 0)
        days=float(metrics.get("median_active_trade_days",0) or 0)
        tail=float(metrics.get("median_daily_tail_sample_count",0) or 0)
        years=float(metrics.get("median_sample_years",0) or 0)
    else:
        trades=float(metrics.get("trades",0) or 0)
        days=float(metrics.get("active_trade_days",metrics.get("daily_tail_observations",0)) or 0)
        tail=float(metrics.get("daily_tail_sample_count",0) or 0)
        years=float(metrics.get("sample_years",0) or 0)
    return {"trades":trades,"active_days":days,"tail_days":tail,"sample_years":years}


def _evidence_requirements(spec: dict) -> dict[str, float]:
    return {
        "trades":float(spec.get("min_trades",0) or 0),
        "active_days":float(spec.get("min_active_days",0) or 0),
        "tail_days":float(spec.get("min_tail_days",0) or 0),
        "sample_years":float(spec.get("min_sample_years",0) or 0),
    }


def _evidence_failure(actual: dict, required: dict) -> tuple[str,float,float] | None:
    for key in ("trades","active_days","tail_days","sample_years"):
        if float(actual.get(key,0.0)) + 1e-12 < float(required.get(key,0.0)):
            return key,float(actual.get(key,0.0)),float(required.get(key,0.0))
    return None


def gate_rows(metrics: dict, cfg: dict, *, mode: str, prefix: str, group: str = "risk_adjusted") -> list[dict]:
    """Build fail-closed but sample-aware risk KPI rows.

    Insufficient evidence is reported as an explicit ``*_EVIDENCE`` failure instead of
    falsely diagnosing model quality (for example CVaR from one tail day or DSR from a
    handful of trades). The candidate still fails the stage, but Scientist receives the
    correct causal reason: sample sufficiency, not poor risk-adjusted performance.
    """
    kpis = ensure_risk_kpi_config(cfg); rows: list[dict] = []
    evidence=_evidence_snapshot(metrics,mode)
    for key, spec in kpis.items():
        if not bool(spec.get("enabled", True)):
            continue
        metric_key = spec.get("wfa_metric") if mode == "wfa" else spec.get("point_metric")
        if not metric_key:
            continue
        required=_evidence_requirements(spec); missing=_evidence_failure(evidence,required)
        if missing is not None:
            dim,actual_e,required_e=missing
            rows.append({
                "name":f"{prefix}_{key.upper()}_EVIDENCE","passed":False,"actual":actual_e,"threshold":required_e,
                "severity":"MANDATORY","group":"sample_sufficiency","detail":f"{spec.get('label',key)} insufficient {dim}; metric is not authoritative",
                "kpi_key":key,"direction":"higher","evidence_status":"INSUFFICIENT_EVIDENCE",
                "evidence":dict(evidence),"evidence_required":required,
            })
            continue
        actual = metrics.get(str(metric_key)); threshold = float(spec.get("threshold", 0.0)); direction = str(spec.get("direction", "higher"))
        rows.append({
            "name": f"{prefix}_{key.upper()}", "passed": metric_pass(actual, threshold, direction),
            "actual": actual, "threshold": threshold, "severity": "MANDATORY", "group": group,
            "detail": f"{spec.get('label', key)} · {spec.get('basis', '')}", "kpi_key": key, "direction": direction,
            "evidence_status":"SUFFICIENT","evidence":dict(evidence),"evidence_required":required,
        })
    return rows

def canonical_summary(paths: list[dict], cfg: dict) -> dict:
    """Aggregate canonical CPCV paths according to each KPI's declared policy."""
    import numpy as np

    kpis = ensure_risk_kpi_config(cfg)
    out: dict[str, Any] = {}
    for key, spec in kpis.items():
        if not bool(spec.get("enabled", True)):
            continue
        field = str(spec.get("point_metric") or "")
        vals = []
        for path in paths:
            value = path.get(field)
            if value is not None:
                try:
                    vals.append(float(value))
                except Exception:
                    pass
        if not vals:
            out[key] = None
            continue
        agg = str(spec.get("canonical_aggregate", "median"))
        if agg == "worst":
            out[key] = float(max(vals) if str(spec.get("direction")) == "lower" else min(vals))
        else:
            out[key] = float(np.median(np.asarray(vals, dtype=float)))
    return out


def canonical_gate_rows(paths: list[dict], cfg: dict, *, prefix: str = "CPCV_CANONICAL") -> tuple[list[dict], dict]:
    summary = canonical_summary(paths, cfg); kpis = ensure_risk_kpi_config(cfg); rows=[]
    # Canonical reconstructed paths each represent a chronological evaluation path.
    # Evidence authority uses medians across those paths so one sparse path cannot make
    # a statistically fragile metric look fully authoritative.
    if paths:
        import numpy as np
        def med(field, default=0.0):
            vals=[]
            for p in paths:
                v=p.get(field)
                if v is None: continue
                try: vals.append(float(v))
                except Exception: pass
            return float(np.median(vals)) if vals else float(default)
        evidence={"trades":med("trades"),"active_days":med("active_trade_days"),"tail_days":med("daily_tail_sample_count"),"sample_years":med("sample_years")}
    else:
        evidence={"trades":0.0,"active_days":0.0,"tail_days":0.0,"sample_years":0.0}
    for key,spec in kpis.items():
        if not bool(spec.get("enabled",True)): continue
        required=_evidence_requirements(spec); missing=_evidence_failure(evidence,required)
        if missing is not None:
            dim,actual_e,required_e=missing
            rows.append({"name":f"{prefix}_{key.upper()}_EVIDENCE","passed":False,"actual":actual_e,"threshold":required_e,"severity":"MANDATORY","group":"sample_sufficiency",
                         "detail":f"Canonical CPCV · {spec.get('label',key)} insufficient {dim}; metric is not authoritative","kpi_key":key,"direction":"higher",
                         "evidence_status":"INSUFFICIENT_EVIDENCE","evidence":dict(evidence),"evidence_required":required})
            continue
        actual=summary.get(key); threshold=float(spec.get("threshold",0.0)); direction=str(spec.get("direction","higher"))
        rows.append({"name":f"{prefix}_{key.upper()}","passed":metric_pass(actual,threshold,direction),"actual":actual,"threshold":threshold,"severity":"MANDATORY","group":"risk_adjusted",
                     "detail":f"Canonical CPCV · {spec.get('label',key)} · {spec.get('basis','')}","kpi_key":key,"direction":direction,
                     "evidence_status":"SUFFICIENT","evidence":dict(evidence),"evidence_required":required})
    summary["evidence"]=evidence
    return rows, summary

