from __future__ import annotations

from copy import deepcopy
from typing import Any

from research.risk_kpi import DEFAULT_RISK_KPIS

SCHEMA = "MAX_GATE_KPI_PROFILES_V1"
GATES = ("discovery", "cpcv", "tournament", "monte_carlo", "fresh_forward", "champion_promotion")

# v1.4.4: canonical visibility contract for every runtime hard gate that Owner may
# tune in Advanced -> KPI by Gate. This registry does not change evaluation
# formulas; it prevents a config-driven PASS/FAIL threshold from existing only in
# backend code with no operator-visible control. Methodology invariants and
# floating-point epsilons are intentionally excluded because they are not KPI.
KPI_UI_HARD_GATE_CONTRACT: dict[str, tuple[str, ...]] = {
    "discovery": (
        "max_drawdown_r", "cv_max_worst_fold_drawdown_r",
        "cv_min_median_recovery_factor", "cv_min_worst_fold_recovery_factor",
        "cv_min_median_profit_factor", "cv_min_overall_expectancy_r",
        "cv_min_median_expectancy_r", "cv_min_worst_expectancy_r",
        "cv_min_positive_fold_ratio", "min_positive_month_ratio",
        "min_positive_quarter_ratio", "max_dominant_positive_regime_share",
        "max_top10_win_profit_share",
        "stress_min_expectancy_r.spread_x1.25",
        "stress_min_expectancy_r.spread_x1.50",
        "sensitivity_min_profitable_ratio",
        "risk_kpis.*.enabled", "risk_kpis.*.threshold",
        "risk_kpis.*.min_trades", "risk_kpis.*.min_active_days",
        "risk_kpis.*.min_tail_days", "risk_kpis.*.min_sample_years",
    ),
    "cpcv": (
        "cv_min_median_profit_factor", "cv_min_median_expectancy_r",
        "cpcv_min_worst_expectancy_r", "cv_max_worst_fold_drawdown_r",
        "cv_min_median_recovery_factor", "cv_min_worst_fold_recovery_factor",
        "cv_min_positive_fold_ratio", "cpcv_min_path_sample_ratio",
        "pbo_enabled", "pbo_max", "pbo_min_candidates",
        "risk_kpis.*.enabled", "risk_kpis.*.threshold",
        "risk_kpis.*.min_trades", "risk_kpis.*.min_active_days",
        "risk_kpis.*.min_tail_days", "risk_kpis.*.min_sample_years",
    ),
    "tournament": (
        "min_profit_factor", "min_expectancy_r", "min_recovery_factor",
        "max_drawdown_r", "require_every_year_nonnegative",
        "min_positive_month_ratio", "min_positive_quarter_ratio",
        "max_dominant_positive_regime_share", "max_top10_win_profit_share",
        "stress_x1_50_min_expectancy_r",
        "risk_kpis.*.enabled", "risk_kpis.*.threshold",
        "risk_kpis.*.min_trades", "risk_kpis.*.min_active_days",
        "risk_kpis.*.min_tail_days", "risk_kpis.*.min_sample_years",
    ),
    "monte_carlo": (
        "min_p05_profit_factor", "min_p05_expectancy_r",
        "max_p95_drawdown_r", "min_p05_recovery_factor",
        "max_probability_loss", "max_probability_ruin",
        "min_survival_rate", "ruin_floor_r",
    ),
    "fresh_forward": (
        "min_profit_factor", "min_expectancy_r", "min_recovery_factor",
        "max_drawdown_r",
        "risk_kpis.*.enabled", "risk_kpis.*.threshold",
        "risk_kpis.*.min_trades", "risk_kpis.*.min_active_days",
        "risk_kpis.*.min_tail_days", "risk_kpis.*.min_sample_years",
    ),
    "champion_promotion": (
        "require_all_upstream_pass", "require_artifact_integrity",
        "require_no_post_forward_tuning", "require_onnx_export",
        "require_onnx_parity",
    ),
}

def kpi_ui_hard_gate_contract() -> dict[str, tuple[str, ...]]:
    return deepcopy(KPI_UI_HARD_GATE_CONTRACT)


def _legacy_acceptance(cfg: dict | None) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        return {}
    value = cfg.get("acceptance")
    return value if isinstance(value, dict) else {}


def _legacy_promotion(cfg: dict | None) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        return {}
    agent = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    value = agent.get("promotion") if isinstance(agent.get("promotion"), dict) else {}
    return value


def _risk_defaults(cfg: dict | None = None) -> dict[str, dict[str, Any]]:
    legacy = _legacy_acceptance(cfg).get("risk_kpis")
    if isinstance(legacy, dict) and legacy:
        merged = deepcopy(DEFAULT_RISK_KPIS)
        for key, spec in legacy.items():
            if isinstance(spec, dict):
                base = deepcopy(merged.get(key, {})); base.update(spec); merged[key] = base
        return merged
    return deepcopy(DEFAULT_RISK_KPIS)




def _stage_risk_defaults(stage: str, base: dict[str, dict[str, Any]], *, preserve_thresholds: bool = False) -> dict[str, dict[str, Any]]:
    """Return progressive hard-risk authority for one research stage.

    Advanced statistics remain computed everywhere, but early stages should not be
    dominated by fragile small-sample metrics. ``enabled`` means hard-gate authority,
    not whether the metric is calculated or displayed.
    """
    out=deepcopy(base); stage=str(stage).lower()
    hard={
        "discovery": {"sharpe","sortino","ulcer"},
        "cpcv": {"sharpe","sortino","ulcer","cvar"},
        "tournament": {"sharpe","sortino","calmar","psr","ulcer","cvar"},
        "fresh_forward": {"sharpe","sortino","calmar","psr","ulcer","cvar"},
    }.get(stage,set())
    stage_thresholds={
        "discovery": {"sharpe":0.15,"sortino":0.25,"ulcer":8.0},
        "cpcv": {"sharpe":0.20,"sortino":0.30,"ulcer":8.0,"cvar":-2.5},
        "tournament": {"sharpe":0.30,"sortino":0.50,"calmar":1.0,"psr":0.80,"ulcer":6.0,"cvar":-2.0},
        "fresh_forward": {"sharpe":0.40,"sortino":0.65,"calmar":1.25,"psr":0.85,"ulcer":5.0,"cvar":-1.5},
    }.get(stage,{})
    for key,spec in out.items():
        if not isinstance(spec,dict):
            continue
        spec["enabled"]=key in hard
        if key in stage_thresholds and not preserve_thresholds:
            spec["threshold"]=stage_thresholds[key]
    # DSR remains calculated but diagnostic by default. Its effective trial count is
    # valuable evidence, yet hard authority is too sample-hungry for ordinary Fresh
    # windows unless the Owner explicitly enables it.
    if "dsr" in out:
        out["dsr"]["enabled"]=False
    return out

def default_profiles(legacy_cfg: dict | None = None) -> dict[str, Any]:
    """Build v0.7.7 profiles, preserving legacy Owner thresholds on first migration.

    v0.7.5 used `acceptance` for Discovery/CPCV/Tournament and
    `agent.promotion` for Monte Carlo/Fresh Forward. Once `gate_kpis` exists,
    every gate is independent and this migration bridge is no longer consulted.
    """
    a = _legacy_acceptance(legacy_cfg)
    promo = _legacy_promotion(legacy_cfg)
    risk = _risk_defaults(legacy_cfg)
    # First migration must preserve explicit Owner thresholds from the legacy registry.
    # Stage defaults only seed fresh installs; they must never silently rewrite Owner KPI.
    preserve_legacy_thresholds = isinstance(_legacy_acceptance(legacy_cfg).get("risk_kpis"), dict) and bool(_legacy_acceptance(legacy_cfg).get("risk_kpis"))
    discovery_risk=_stage_risk_defaults("discovery",risk,preserve_thresholds=preserve_legacy_thresholds)
    cpcv_risk=_stage_risk_defaults("cpcv",risk,preserve_thresholds=preserve_legacy_thresholds)
    tournament_risk=_stage_risk_defaults("tournament",risk,preserve_thresholds=preserve_legacy_thresholds)
    fresh_risk=_stage_risk_defaults("fresh_forward",risk,preserve_thresholds=preserve_legacy_thresholds)
    return {
        "schema": SCHEMA,
        "discovery": {
            "profile_version": "DISCOVERY_KPI_V1",
            "max_drawdown_r": float(a.get("max_drawdown_r", 12.0)),
            "cv_max_worst_fold_drawdown_r": float(a.get("cv_max_worst_fold_drawdown_r", 18.0)),
            "cv_min_median_recovery_factor": float(a.get("cv_min_median_recovery_factor", 1.50)),
            "cv_min_worst_fold_recovery_factor": float(a.get("cv_min_worst_fold_recovery_factor", 1.0)),
            "cv_min_median_profit_factor": float(a.get("cv_min_median_profit_factor", 1.25)),
            "cv_min_overall_expectancy_r": float(a.get("cv_min_overall_expectancy_r", 0.10)),
            "cv_min_median_expectancy_r": float(a.get("cv_min_median_expectancy_r", 0.10)),
            "cv_min_worst_expectancy_r": float(a.get("cv_min_worst_expectancy_r", 0.0)),
            "cv_min_positive_fold_ratio": float(a.get("cv_min_positive_fold_ratio", 0.66)),
            "min_positive_month_ratio": float(a.get("min_positive_month_ratio", 0.55)),
            "min_positive_quarter_ratio": float(a.get("min_positive_quarter_ratio", 0.60)),
            "max_dominant_positive_regime_share": float(a.get("max_dominant_positive_regime_share", 0.75)),
            "max_top10_win_profit_share": float(a.get("max_top10_win_profit_share", 0.55)),
            "stress_min_expectancy_r": deepcopy(a.get("stress_min_expectancy_r") or {"spread_x1.25": 0.08, "spread_x1.50": 0.05}),
            "sensitivity_min_profitable_ratio": float(a.get("sensitivity_min_profitable_ratio", 0.66)),
            "risk_kpis": deepcopy(discovery_risk),
        },
        "cpcv": {
            "profile_version": "CPCV_KPI_V1",
            "cv_min_median_profit_factor": float(a.get("cv_min_median_profit_factor", 1.25)),
            "cv_min_median_expectancy_r": float(a.get("cv_min_median_expectancy_r", 0.10)),
            "cpcv_min_worst_expectancy_r": float(a.get("cpcv_min_worst_expectancy_r", a.get("cv_min_worst_expectancy_r", 0.0))),
            "cv_max_worst_fold_drawdown_r": float(a.get("cv_max_worst_fold_drawdown_r", 18.0)),
            "cv_min_median_recovery_factor": float(a.get("cv_min_median_recovery_factor", 1.50)),
            "cv_min_worst_fold_recovery_factor": float(a.get("cv_min_worst_fold_recovery_factor", 1.0)),
            "cv_min_positive_fold_ratio": float(a.get("cv_min_positive_fold_ratio", 0.66)),
            "cpcv_min_path_sample_ratio": 0.66,
            "worst_expectancy_epsilon": float(a.get("cpcv_worst_expectancy_epsilon", a.get("worst_expectancy_epsilon", 1e-9))),
            "pbo_enabled": False,
            "pbo_max": 0.20,
            "pbo_min_candidates": 4,
            "pbo_status": "COMPUTABLE_FROM_CROSS_STRATEGY_CPCV_GROUP_MATRIX_WHEN_ENABLED",
            "risk_kpis": deepcopy(cpcv_risk),
        },
        "tournament": {
            "profile_version": "TOURNAMENT_KPI_V1",
            "max_drawdown_r": float(a.get("max_drawdown_r", 12.0)),
            "min_recovery_factor": float(a.get("min_recovery_factor", 2.0)),
            "min_profit_factor": float(a.get("min_profit_factor", 1.35)),
            "min_expectancy_r": float(a.get("min_expectancy_r", 0.15)),
            "require_every_year_nonnegative": True,
            "min_positive_month_ratio": float(a.get("min_positive_month_ratio", 0.55)),
            "min_positive_quarter_ratio": float(a.get("min_positive_quarter_ratio", 0.60)),
            "max_dominant_positive_regime_share": float(a.get("max_dominant_positive_regime_share", 0.75)),
            "max_top10_win_profit_share": float(a.get("max_top10_win_profit_share", 0.55)),
            "stress_x1_50_min_expectancy_r": float((a.get("stress_min_expectancy_r") or {}).get("spread_x1.50", 0.05)),
            "risk_kpis": deepcopy(tournament_risk),
            "ranking_only_after_hard_pass": True,
            "top_k_elimination": False,
        },
        "monte_carlo": {
            "profile_version": "MONTE_CARLO_KPI_V1",
            "min_p05_profit_factor": float(promo.get("min_shadow_profit_factor", 1.35)),
            "min_p05_expectancy_r": float(promo.get("min_shadow_expectancy_r", 0.15)),
            "max_p95_drawdown_r": float(promo.get("max_shadow_drawdown_r", 12.0)),
            "min_p05_recovery_factor": float(promo.get("min_shadow_recovery_factor", 2.0)),
            "max_probability_loss": 1.0,
            "max_probability_ruin": 1.0,
            "min_survival_rate": 0.0,
            "ruin_floor_r": -20.0,
        },
        "fresh_forward": {
            "profile_version": "FRESH_FORWARD_KPI_V2_PRODUCTION",
            # Final untouched model-generalization gate. Champion Promotion adds no
            # second market test, so Fresh must carry the production-grade economic bar.
            "max_drawdown_r": float(promo.get("max_shadow_drawdown_r", 10.0)) if promo else 10.0,
            "min_recovery_factor": float(promo.get("min_shadow_recovery_factor", 3.0)) if promo else 3.0,
            "min_profit_factor": float(promo.get("min_shadow_profit_factor", 1.50)) if promo else 1.50,
            "min_expectancy_r": float(promo.get("min_shadow_expectancy_r", 0.50)) if promo else 0.50,
            "risk_kpis": deepcopy(fresh_risk),
            "degradation_enabled": False,
            "max_expectancy_degradation_ratio": 1.0,
            "max_pf_degradation_ratio": 1.0,
            "max_drawdown_expansion_ratio": 999.0,
        },
        "champion_promotion": {
            "profile_version": "CHAMPION_PROMOTION_V1",
            "require_all_upstream_pass": True,
            "require_artifact_integrity": True,
            "require_no_post_forward_tuning": True,
            "require_onnx_export": True,
            "require_onnx_parity": True,
        },
    }


def _repair_legacy_cvar_sign(stage: str, profile: dict, defaults: dict) -> None:
    """Migrate stale positive CVaR floors without weakening sign semantics.

    v1.3.2 made daily CVaR a signed lower-tail return floor. Older persisted
    gate profiles can still carry pre-repair positive thresholds such as +0.8,
    +1.0, +1.25 or +1.5 while ``allow_positive_tail_floor`` is false. Those
    values were never an explicit acknowledgement that even the worst 5% days
    must stay profitable; they are legacy sign-semantic artifacts.

    For that specific combination only, restore the current stage default. An
    explicitly acknowledged positive floor (allow_positive_tail_floor=true) is
    preserved verbatim. The migration is recorded on the KPI spec so frozen run
    evidence can explain why the effective threshold changed.
    """
    risk = profile.get("risk_kpis") if isinstance(profile.get("risk_kpis"), dict) else {}
    cvar = risk.get("cvar") if isinstance(risk.get("cvar"), dict) else None
    if not cvar:
        return
    try:
        threshold = float(cvar.get("threshold", -2.0))
    except Exception:
        return
    if threshold <= 0.0 or bool(cvar.get("allow_positive_tail_floor", False)):
        return
    # Use the v1.3.2+ stage semantics directly instead of deriving the repair
    # floor from a legacy-preserving defaults object. Otherwise the very legacy
    # threshold being repaired can contaminate the fallback.
    safe = {
        "discovery": -2.0,
        "cpcv": -2.5,
        "tournament": -2.0,
        "fresh_forward": -1.5,
    }.get(str(stage).lower(), -2.0)
    cvar["migrated_legacy_positive_tail_floor_from"] = threshold
    cvar["threshold"] = safe
    cvar["migration_reason"] = "V134_CVAR_SIGN_SEMANTICS_LEGACY_REPAIR"


def ensure_gate_kpi_profiles(cfg: dict) -> dict:
    root = cfg.setdefault("gate_kpis", {})
    defaults = default_profiles(cfg)
    root.setdefault("schema", SCHEMA)
    for gate in GATES:
        if not isinstance(root.get(gate), dict):
            root[gate] = deepcopy(defaults[gate])
        else:
            merged = deepcopy(defaults[gate])
            # Nested risk registry needs per-KPI merge, not wholesale replacement.
            current = root[gate]
            risk_current = current.get("risk_kpis") if isinstance(current.get("risk_kpis"), dict) else {}
            merged.update({k: deepcopy(v) for k, v in current.items() if k != "risk_kpis"})
            if "risk_kpis" in merged:
                for key, spec in risk_current.items():
                    if isinstance(spec, dict):
                        base = deepcopy(merged["risk_kpis"].get(key, {})); base.update(spec); merged["risk_kpis"][key] = base
            root[gate] = merged
        if gate in ("discovery", "cpcv", "tournament", "fresh_forward"):
            _repair_legacy_cvar_sign(gate, root[gate], defaults[gate])
    return root


def gate_profile(cfg: dict, gate: str) -> dict:
    root = ensure_gate_kpi_profiles(cfg)
    key = str(gate).strip().lower()
    if key not in GATES:
        raise KeyError(f"Unknown gate KPI profile: {gate}")
    return root[key]


def risk_cfg_for_gate(cfg: dict, gate: str) -> dict:
    """Return a copied cfg whose legacy risk registry points at one gate profile.

    Existing risk_kpi.py remains the single formula authority; only threshold ownership
    changes. This prevents formula drift while allowing independent per-gate thresholds.
    """
    out = deepcopy(cfg)
    profile = gate_profile(out, gate)
    out.setdefault("acceptance", {})["risk_kpis"] = deepcopy(profile.get("risk_kpis") or {})
    return out


def gate_profiles_snapshot(cfg: dict) -> dict:
    return deepcopy(ensure_gate_kpi_profiles(cfg))
