from __future__ import annotations

from typing import Any

import numpy as np

from research.risk_kpi import gate_rows as risk_gate_rows, ensure_risk_kpi_config, DEFAULT_RISK_KPIS
from research.gate_kpi import gate_profile, risk_cfg_for_gate

from research.evaluation import (
    classification_metrics,
    confidence_bucket_diagnostics,
    regime_diagnostics,
    stress_diagnostics,
    temporal_stability,
    trading_metrics,
)


def _gate(name: str, passed: bool, actual: Any, threshold: Any, severity: str = "QUALITY", detail: str = "") -> dict:
    return {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
        "threshold": threshold,
        "severity": severity,
        "detail": detail,
    }





def _worst_expectancy_pass(actual: float, cfg: dict, key: str = "cv_min_worst_expectancy_r") -> bool:
    a=gate_profile(cfg,"discovery")
    threshold=float(a.get(key,0.0))
    epsilon=abs(float(a.get("worst_expectancy_epsilon",1e-9)))
    return float(actual)+epsilon >= threshold


def _overall_expectancy_r(cv: dict) -> float:
    value=cv.get("overall_expectancy_r")
    if value is not None:
        try: return float(value)
        except Exception: return -999.0
    try:
        trades=int(cv.get("total_validation_trades",0) or 0)
        total=float(cv.get("total_validation_r"))
        return float(total/trades) if trades>0 else -999.0
    except Exception:
        return -999.0

def _bounded_margin_higher(actual: float, target: float, scale: float) -> float:
    """Return a bounded [-1,1] desirability margin for higher-is-better KPIs."""
    scale=max(abs(float(scale)),1e-9)
    return float(np.tanh((float(actual)-float(target))/scale))


def _bounded_margin_lower(actual: float, target: float, scale: float) -> float:
    """Return a bounded [-1,1] desirability margin for lower-is-better KPIs."""
    scale=max(abs(float(scale)),1e-9)
    return float(np.tanh((float(target)-float(actual))/scale))


def _fold_extremes(cv: dict) -> dict:
    """Extract worst-fold survival evidence without hiding it behind medians."""
    folds = cv.get("fold_diagnostics") or []
    dds = [float(x.get("max_drawdown_r", 999999.0)) for x in folds if x.get("max_drawdown_r") is not None]
    recs = [float(x.get("recovery_factor", -999.0)) for x in folds if x.get("recovery_factor") is not None]
    return {
        "worst_fold_max_drawdown_r": float(cv.get("worst_fold_max_drawdown_r", max(dds) if dds else cv.get("median_max_drawdown_r", 999999.0))),
        "worst_fold_recovery_factor": float(cv.get("worst_fold_recovery_factor", min(recs) if recs else cv.get("median_recovery_factor", -999.0))),
    }


def _group_summary(gates: list[dict], order: list[tuple[str, str]]) -> list[dict]:
    rows=[]
    for key,label in order:
        gg=[g for g in gates if str(g.get("group"))==key]
        if not gg:
            continue
        failed=[g["name"] for g in gg if not g["passed"]]
        rows.append({"group":key,"label":label,"passed":not failed,"failed":failed,"gate_count":len(gg)})
    return rows


def _gate2(name: str, passed: bool, actual: Any, threshold: Any, severity: str, group: str, detail: str = "") -> dict:
    g=_gate(name,passed,actual,threshold,severity,detail)
    g["group"]=group
    return g


def walk_forward_composite_score(cv: dict, cfg: dict) -> dict:
    """Fixed-100 ranking score; acceptance remains independent hard-gate authority.

    v1.3.2 repair: score weights and reference targets no longer change when the Owner
    enables/disables or edits hard KPI gates. This preserves score comparability within
    the V5 schema and prevents adding a KPI from mechanically lowering every historical
    candidate score. Hard-gate failure margins remain available separately to Scientist.
    """
    ex=_fold_extremes(cv); components=[]

    # Stable ranking references. These are NOT acceptance thresholds.
    ref={
        "median_dd":12.0,"worst_dd":18.0,"median_rf":1.50,"worst_rf":1.0,
        "median_pf":1.25,"overall_exp":0.10,"median_exp":0.10,"worst_exp":0.0,
        "positive_folds":0.66,"exp_std":0.12,"pf_std":0.25,
        "stress125":0.05,"stress150":0.0,"plateau":0.66,
        "positive_months":0.55,"positive_quarters":0.60,"regime":0.75,
        "win_rate":0.50,"payoff":1.0,"median_trade":0.0,"top10":0.55,
    }
    risk_ref={k:dict(v) for k,v in DEFAULT_RISK_KPIS.items()}

    def value(key, default=0.0):
        v=cv.get(key,default)
        try:
            f=float(v)
            return f if np.isfinite(f) else float(default)
        except Exception:
            return float(default)

    def add(name, category, actual, target, weight, direction, scale):
        actual=float(actual); target=float(target); weight=float(weight)
        margin=_bounded_margin_higher(actual,target,scale) if direction=="higher" else _bounded_margin_lower(actual,target,scale)
        components.append({"name":name,"category":category,"actual":actual,"target":target,
                           "direction":direction,"weight":weight,"margin":margin,"contribution":weight*margin})

    # Fixed category weights: Survival 30, Economic 30, Fold 10, Stress 10,
    # Time/regime 5, Trade shape 5, Classification 2, Risk diagnostics 8 = 100.
    add("CV_MEDIAN_MAX_DD","1 · Survival",value("median_max_drawdown_r",999),ref["median_dd"],12,"lower",6.0)
    add("CV_WORST_FOLD_MAX_DD","1 · Survival",ex["worst_fold_max_drawdown_r"],ref["worst_dd"],7,"lower",8.0)
    add("CV_MEDIAN_RECOVERY","1 · Survival",value("median_recovery_factor"),ref["median_rf"],8,"higher",1.0)
    add("CV_WORST_FOLD_RECOVERY","1 · Survival",ex["worst_fold_recovery_factor"],ref["worst_rf"],3,"higher",0.75)

    add("CV_MEDIAN_PF","2 · Economic",value("median_profit_factor"),ref["median_pf"],7,"higher",0.35)
    add("CV_OVERALL_EXPECTANCY","2 · Economic",_overall_expectancy_r(cv),ref["overall_exp"],8,"higher",0.18)
    add("CV_MEDIAN_EXPECTANCY","2 · Economic",value("median_expectancy_r"),ref["median_exp"],7,"higher",0.18)
    add("CV_WORST_EXPECTANCY","2 · Economic",value("worst_expectancy_r"),ref["worst_exp"],5,"higher",0.18)
    cv_trade_min=int(cv.get("auto_min_validation_trades",90) or 90)
    add("CV_TRADES","2 · Economic",value("total_validation_trades"),cv_trade_min,3,"higher",max(30.0,float(cv_trade_min)*0.5))

    add("CV_POSITIVE_FOLDS","3 · Fold robustness",value("positive_fold_ratio"),ref["positive_folds"],5,"higher",0.25)
    add("CV_EXPECTANCY_STD","3 · Fold robustness",value("expectancy_std_r",999),ref["exp_std"],3,"lower",0.12)
    add("CV_PF_STD","3 · Fold robustness",value("profit_factor_std",999),ref["pf_std"],2,"lower",0.25)

    add("CV_STRESS_X1_25","4 · Stress",value("median_stress_x1_25_expectancy_r",-999),ref["stress125"],3,"higher",0.16)
    add("CV_STRESS_X1_50","4 · Stress",value("median_stress_x1_50_expectancy_r",-999),ref["stress150"],5,"higher",0.16)
    add("CV_THRESHOLD_PLATEAU","4 · Stress",value("median_threshold_plateau"),ref["plateau"],2,"higher",0.25)

    add("CV_POSITIVE_MONTHS","5 · Time / regime",value("median_positive_month_ratio"),ref["positive_months"],2,"higher",0.25)
    add("CV_POSITIVE_QUARTERS","5 · Time / regime",value("median_positive_quarter_ratio"),ref["positive_quarters"],1,"higher",0.25)
    add("CV_REGIME_CONCENTRATION","5 · Time / regime",value("median_regime_concentration",1.0),ref["regime"],2,"lower",0.20)

    add("CV_WIN_RATE","6 · Trade shape",value("median_win_rate"),ref["win_rate"],0.5,"higher",0.20)
    add("CV_PAYOFF","6 · Trade shape",value("median_payoff_ratio"),ref["payoff"],1.5,"higher",0.75)
    add("CV_MEDIAN_TRADE","6 · Trade shape",value("median_trade_r"),ref["median_trade"],1.5,"higher",0.15)
    add("CV_TOP10_WIN_SHARE","6 · Trade shape",value("median_top10_win_profit_share",1.0),ref["top10"],1.5,"lower",0.20)

    add("CV_BALANCED_ACCURACY","7 · Classification",value("mean_balanced_accuracy"),1/3,0.4,"higher",0.15)
    add("CV_MACRO_F1","7 · Classification",value("mean_macro_f1"),1/3,0.4,"higher",0.15)
    add("CV_LOG_LOSS","7 · Classification",value("mean_log_loss",99),float(np.log(3.0)),0.4,"lower",0.35)
    add("CV_BRIER","7 · Classification",value("mean_brier_score",99),2/3,0.4,"lower",0.25)
    add("CV_CALIBRATION_ERROR","7 · Classification",value("mean_expected_calibration_error",99),0.10,0.4,"lower",0.10)

    risk_weights={"sharpe":1.5,"sortino":1.5,"calmar":1.0,"psr":1.5,"dsr":1.5,"ulcer":0.5,"cvar":0.5}
    for key,w in risk_weights.items():
        spec=risk_ref[key]; metric=str(spec.get("wfa_metric") or "")
        threshold=float(spec.get("threshold",0.0)); direction=str(spec.get("direction","higher"))
        actual=value(metric, threshold)
        if key in {"psr","dsr"}: scale=0.10
        elif key=="ulcer": scale=max(1.0,abs(threshold)*0.50)
        elif key=="cvar": scale=max(0.5,abs(threshold)*0.50)
        else: scale=max(0.20,abs(threshold)*0.75)
        add(f"CV_{key.upper()}","8 · Risk diagnostics",actual,threshold,w,direction,scale)

    total_weight=float(sum(float(x["weight"]) for x in components))
    if abs(total_weight-100.0)>1e-9:
        raise RuntimeError(f"CV_SCORE_V5_WEIGHT_CONTRACT: {total_weight}")
    score=float(sum(x["contribution"] for x in components))
    by_category={}
    for x in components:
        d=by_category.setdefault(x["category"],{"contribution":0.0,"weight":0.0})
        d["contribution"]+=x["contribution"]; d["weight"]+=x["weight"]
    return {"schema":"CV_SCORE_V5_FIXED_100","score":score,"components":components,
            "weight_total":total_weight,"hard_gate_independent":True,
            "categories":[{"category":k,"contribution":float(v["contribution"]),"weight":float(v["weight"])} for k,v in by_category.items()]}

def walk_forward_acceptance(cv: dict, cfg: dict) -> dict:
    """Discovery Full-WFA authority using the independent Discovery KPI profile."""
    a=gate_profile(cfg,"discovery")
    ex=_fold_extremes(cv)
    stress_min=a.get("stress_min_expectancy_r",{}) if isinstance(a.get("stress_min_expectancy_r",{}),dict) else {}
    cv_trade_min=int(cv.get("auto_min_validation_trades",a.get("cv_min_validation_trades",90)))
    gates=[
        # Integrity / sample sufficiency. AUTO value is predeclared from timeframe + actual OOF exposure.
        _gate2("CV_MIN_TRADES",int(cv.get("total_validation_trades",0))>=cv_trade_min,int(cv.get("total_validation_trades",0)),cv_trade_min,"MANDATORY","integrity"),
        # Survival authority FIRST
        _gate2("CV_MEDIAN_MAX_DD",float(cv.get("median_max_drawdown_r",999999))<=float(a.get("max_drawdown_r",12.0)),float(cv.get("median_max_drawdown_r",999999)),float(a.get("max_drawdown_r",12.0)),"CRITICAL","survival"),
        _gate2("CV_WORST_FOLD_MAX_DD",ex["worst_fold_max_drawdown_r"]<=float(a.get("cv_max_worst_fold_drawdown_r",18.0)),ex["worst_fold_max_drawdown_r"],float(a.get("cv_max_worst_fold_drawdown_r",18.0)),"CRITICAL","survival"),
        _gate2("CV_MEDIAN_RECOVERY",float(cv.get("median_recovery_factor",-999))>=float(a.get("cv_min_median_recovery_factor",1.50)),float(cv.get("median_recovery_factor",-999)),float(a.get("cv_min_median_recovery_factor",1.50)),"CRITICAL","survival"),
        _gate2("CV_WORST_FOLD_RECOVERY",ex["worst_fold_recovery_factor"]>=float(a.get("cv_min_worst_fold_recovery_factor",1.0)),ex["worst_fold_recovery_factor"],float(a.get("cv_min_worst_fold_recovery_factor",1.0)),"CRITICAL","survival"),
        # Economic edge, still mandatory
        _gate2("CV_MEDIAN_PF",float(cv.get("median_profit_factor",0))>=float(a.get("cv_min_median_profit_factor",1.25)),float(cv.get("median_profit_factor",0)),float(a.get("cv_min_median_profit_factor",1.25)),"MANDATORY","economic"),
        _gate2("CV_OVERALL_EXPECTANCY",_overall_expectancy_r(cv)>=float(a.get("cv_min_overall_expectancy_r",0.10)),_overall_expectancy_r(cv),float(a.get("cv_min_overall_expectancy_r",0.10)),"MANDATORY","economic","Trade-weighted OOF Mean R = total validation R / total validation trades"),
        _gate2("CV_MEDIAN_EXPECTANCY",float(cv.get("median_expectancy_r",-999))>=float(a.get("cv_min_median_expectancy_r",0.10)),float(cv.get("median_expectancy_r",-999)),float(a.get("cv_min_median_expectancy_r",0.10)),"MANDATORY","economic"),
        _gate2("CV_WORST_EXPECTANCY",_worst_expectancy_pass(float(cv.get("worst_expectancy_r",-999)),cfg),float(cv.get("worst_expectancy_r",-999)),float(a.get("cv_min_worst_expectancy_r",0.0)),"MANDATORY","economic","Zero-floor with floating-point epsilon"),
        # Cross-fold / time / regime robustness
        _gate2("CV_POSITIVE_FOLD_RATIO",float(cv.get("positive_fold_ratio",0))>=float(a.get("cv_min_positive_fold_ratio",0.66)),float(cv.get("positive_fold_ratio",0)),float(a.get("cv_min_positive_fold_ratio",0.66)),"MANDATORY","robustness"),
        _gate2("CV_POSITIVE_MONTH_RATIO",float(cv.get("median_positive_month_ratio",0))>=float(a.get("min_positive_month_ratio",0.55)),float(cv.get("median_positive_month_ratio",0)),float(a.get("min_positive_month_ratio",0.55)),"MANDATORY","robustness"),
        _gate2("CV_POSITIVE_QUARTER_RATIO",float(cv.get("median_positive_quarter_ratio",0))>=float(a.get("min_positive_quarter_ratio",0.60)),float(cv.get("median_positive_quarter_ratio",0)),float(a.get("min_positive_quarter_ratio",0.60)),"MANDATORY","robustness"),
        _gate2("CV_REGIME_CONCENTRATION",float(cv.get("median_regime_concentration",1.0))<=float(a.get("max_dominant_positive_regime_share",0.75)),float(cv.get("median_regime_concentration",1.0)),float(a.get("max_dominant_positive_regime_share",0.75)),"MANDATORY","robustness"),
        _gate2("CV_TOP10_WIN_CONCENTRATION",float(cv.get("median_top10_win_profit_share",1.0))<=float(a.get("max_top10_win_profit_share",0.55)),float(cv.get("median_top10_win_profit_share",1.0)),float(a.get("max_top10_win_profit_share",0.55)),"MANDATORY","robustness"),
        # Execution stress must survive too
        _gate2("CV_STRESS_SPREAD_X1.25_EXPECTANCY",float(cv.get("median_stress_x1_25_expectancy_r",-999))>=float(stress_min.get("spread_x1.25",0.08)),float(cv.get("median_stress_x1_25_expectancy_r",-999)),float(stress_min.get("spread_x1.25",0.08)),"MANDATORY","stress"),
        _gate2("CV_STRESS_SPREAD_X1.50_EXPECTANCY",float(cv.get("median_stress_x1_50_expectancy_r",-999))>=float(stress_min.get("spread_x1.50",0.05)),float(cv.get("median_stress_x1_50_expectancy_r",-999)),float(stress_min.get("spread_x1.50",0.05)),"MANDATORY","stress"),
        _gate2("CV_TAKE_THRESHOLD_PLATEAU",float(cv.get("median_threshold_plateau",0))>=float(a.get("sensitivity_min_profitable_ratio",0.66)),float(cv.get("median_threshold_plateau",0)),float(a.get("sensitivity_min_profitable_ratio",0.66)),"MANDATORY","stress"),
    ]
    gates.extend(risk_gate_rows(cv,risk_cfg_for_gate(cfg,"discovery"),mode="wfa",prefix="CV",group="risk_adjusted"))
    reasons=[g["name"] for g in gates if not g["passed"]]
    groups=_group_summary(gates,[("integrity","Integrity"),("sample_sufficiency","Risk KPI evidence sufficiency"),("survival","Survival · DD/RF"),("economic","Economic edge"),("risk_adjusted","Advanced risk/research KPI"),("robustness","Cross-time/regime robustness"),("stress","Execution stress")])
    return {"schema":"MAX_GATE_KPI_PROFILES_V1","profile":str(a.get("profile_version","DISCOVERY_KPI_V1")),
            "stage":"DISCOVERY_WFA","authority":"HIERARCHICAL_ALL_MANDATORY","passed":not reasons,
            "first_failed_gate":reasons[0] if reasons else None,"reasons":reasons,"groups":groups,"gates":gates}

def build_locked_test_kpi(proba: np.ndarray, y: np.ndarray, df, cfg: dict, take_threshold: float, parity: dict) -> dict:
    trade = trading_metrics(proba, df, cfg, take_threshold)
    classification = classification_metrics(proba, y)
    stress = stress_diagnostics(proba, df, cfg, take_threshold)
    temporal = temporal_stability(proba, df, cfg, take_threshold)
    regime = regime_diagnostics(proba, df, cfg, take_threshold)
    confidence = confidence_bucket_diagnostics(proba, df, cfg, take_threshold)
    a = cfg.get("acceptance", {})
    return {
        "schema": str(a.get("schema", "KPI_V5_HIERARCHICAL")),
        "profile": str(a.get("profile", "SURVIVAL_H1_V1")),
        "locked_test": trade,
        "classification": classification,
        "temporal_stability": temporal,
        "regime": regime,
        "confidence_buckets": confidence,
        "stress": stress,
        "onnx_parity": parity,
    }


def locked_test_acceptance(report: dict, cfg: dict) -> dict:
    """Hierarchical locked/fresh-holdout authority. Survival cannot be offset by PF."""
    a=cfg.get("acceptance",{}); m=report.get("locked_test") or {}; parity=report.get("onnx_parity") or {}
    stress=report.get("stress") or {}; temporal=report.get("temporal_stability") or {}; regime=report.get("regime") or {}
    gates=[
        _gate2("ONNX_PARITY",float(parity.get("max_abs_error",999))<=float(a.get("max_onnx_abs_error",1e-4)),float(parity.get("max_abs_error",999)),float(a.get("max_onnx_abs_error",1e-4)),"CRITICAL","integrity"),
        _gate2("TEST_MIN_TRADES",int(m.get("trades",0))>=int(m.get("auto_min_trades",a.get("min_test_trades",50))),int(m.get("trades",0)),int(m.get("auto_min_trades",a.get("min_test_trades",50))),"MANDATORY","integrity"),
        # Survival FIRST
        _gate2("TEST_MAX_DRAWDOWN",float(m.get("max_drawdown_r",999999))<=float(a.get("max_drawdown_r",12.0)),float(m.get("max_drawdown_r",999999)),float(a.get("max_drawdown_r",12.0)),"CRITICAL","survival"),
        _gate2("TEST_RECOVERY_FACTOR",float(m.get("recovery_factor",-999))>=float(a.get("min_recovery_factor",2.0)),float(m.get("recovery_factor",-999)),float(a.get("min_recovery_factor",2.0)),"CRITICAL","survival"),
        # Economic edge remains mandatory
        _gate2("TEST_PROFIT_FACTOR",float(m.get("profit_factor",0))>=float(a.get("min_profit_factor",1.35)),float(m.get("profit_factor",0)),float(a.get("min_profit_factor",1.35)),"MANDATORY","economic"),
        _gate2("TEST_EXPECTANCY",float(m.get("expectancy_r",-999))>=float(a.get("min_expectancy_r",0.15)),float(m.get("expectancy_r",-999)),float(a.get("min_expectancy_r",0.15)),"MANDATORY","economic"),
        # Temporal/regime concentration
        _gate2("TEST_POSITIVE_MONTH_RATIO",float(temporal.get("positive_month_ratio",0))>=float(a.get("min_positive_month_ratio",0.55)),float(temporal.get("positive_month_ratio",0)),float(a.get("min_positive_month_ratio",0.55)),"MANDATORY","robustness"),
        _gate2("TEST_POSITIVE_QUARTER_RATIO",float(temporal.get("positive_quarter_ratio",0))>=float(a.get("min_positive_quarter_ratio",0.60)),float(temporal.get("positive_quarter_ratio",0)),float(a.get("min_positive_quarter_ratio",0.60)),"MANDATORY","robustness"),
        _gate2("TEST_REGIME_CONCENTRATION",float(regime.get("dominant_positive_regime_share",1.0))<=float(a.get("max_dominant_positive_regime_share",0.75)),float(regime.get("dominant_positive_regime_share",1.0)),float(a.get("max_dominant_positive_regime_share",0.75)),"MANDATORY","robustness","Maximum share of positive regime profit contributed by one regime"),
        _gate2("TEST_TOP10_WIN_CONCENTRATION",float(m.get("top10_win_profit_share",1.0))<=float(a.get("max_top10_win_profit_share",0.55)),float(m.get("top10_win_profit_share",1.0)),float(a.get("max_top10_win_profit_share",0.55)),"MANDATORY","robustness","Maximum share of gross winning R contributed by top 10% winning trades"),
    ]
    gates.extend(risk_gate_rows(m,cfg,mode="point",prefix="TEST",group="risk_adjusted"))
    spread_cfg=[float(x) for x in a.get("stress_spread_multipliers",[1.25,1.50])]; spread_min=a.get("stress_min_expectancy_r",{}); spread_rows=stress.get("spread") or {}
    for mult in spread_cfg:
        key=f"spread_x{mult:.2f}"; sm=spread_rows.get(key) or {}; th=float(spread_min.get(key,0.0)) if isinstance(spread_min,dict) else float(spread_min)
        gates.append(_gate2(f"STRESS_{key.upper()}_EXPECTANCY",float(sm.get("expectancy_r",-999))>=th,float(sm.get("expectancy_r",-999)),th,"MANDATORY","stress"))
    ratio=float(stress.get("profitable_threshold_variant_ratio",0)); th=float(a.get("sensitivity_min_profitable_ratio",0.66))
    gates.append(_gate2("TAKE_THRESHOLD_PLATEAU",ratio>=th,ratio,th,"MANDATORY","stress","Share of take-threshold variants with PF>=1 and positive expectancy"))
    reasons=[g["name"] for g in gates if not g["passed"]]
    diagnostics={"win_rate":m.get("win_rate"),"payoff_ratio":m.get("payoff_ratio"),"median_trade_r":m.get("median_trade_r"),
                 "max_losing_streak":m.get("max_losing_streak"),"cvar95_r":m.get("cvar95_r"),"max_underwater_trades":m.get("max_underwater_trades"),
                 "positive_month_ratio":temporal.get("positive_month_ratio"),"positive_quarter_ratio":temporal.get("positive_quarter_ratio"),
                 "dominant_positive_regime_share":regime.get("dominant_positive_regime_share"),"top10_win_profit_share":m.get("top10_win_profit_share"),
                 "brier_score":(report.get("classification") or {}).get("brier_score"),"expected_calibration_error":(report.get("classification") or {}).get("expected_calibration_error")}
    groups=_group_summary(gates,[("integrity","Integrity"),("survival","Survival · DD/RF"),("economic","Economic edge"),("risk_adjusted","Advanced risk/research KPI"),("robustness","Time/regime robustness"),("stress","Execution stress")])
    return {"schema":str(a.get("schema","KPI_V5_HIERARCHICAL")),"profile":str(a.get("profile","SURVIVAL_H1_V1")),"stage":"LOCKED_TEST",
            "authority":"HIERARCHICAL_ALL_MANDATORY","passed":not reasons,"first_failed_gate":reasons[0] if reasons else None,
            "reasons":reasons,"groups":groups,"gates":gates,"diagnostics":diagnostics}

def monte_carlo_acceptance(mc: dict, cfg: dict) -> dict:
    """Independent Monte Carlo tail/robustness gate; no Fresh/Shadow KPI reuse."""
    p=gate_profile(cfg,"monte_carlo")
    robust=mc.get("robust_metrics") if isinstance(mc.get("robust_metrics"),dict) else mc
    probs=mc.get("probabilities") if isinstance(mc.get("probabilities"),dict) else {}
    gates=[
        _gate2("MC_P05_PROFIT_FACTOR",float(robust.get("profit_factor",0))>=float(p.get("min_p05_profit_factor",1.35)),float(robust.get("profit_factor",0)),float(p.get("min_p05_profit_factor",1.35)),"MANDATORY","economic"),
        _gate2("MC_P05_EXPECTANCY",float(robust.get("expectancy_r",-999))>=float(p.get("min_p05_expectancy_r",0.15)),float(robust.get("expectancy_r",-999)),float(p.get("min_p05_expectancy_r",0.15)),"MANDATORY","economic"),
        _gate2("MC_P95_MAX_DRAWDOWN",float(robust.get("max_drawdown_r",999999))<=float(p.get("max_p95_drawdown_r",12.0)),float(robust.get("max_drawdown_r",999999)),float(p.get("max_p95_drawdown_r",12.0)),"CRITICAL","survival"),
        _gate2("MC_P05_RECOVERY",float(robust.get("recovery_factor",-999))>=float(p.get("min_p05_recovery_factor",2.0)),float(robust.get("recovery_factor",-999)),float(p.get("min_p05_recovery_factor",2.0)),"CRITICAL","survival"),
        _gate2("MC_PROBABILITY_LOSS",float(probs.get("loss",1.0))<=float(p.get("max_probability_loss",1.0)),float(probs.get("loss",1.0)),float(p.get("max_probability_loss",1.0)),"MANDATORY","distribution"),
        _gate2("MC_PROBABILITY_RUIN",float(probs.get("ruin",1.0))<=float(p.get("max_probability_ruin",1.0)),float(probs.get("ruin",1.0)),float(p.get("max_probability_ruin",1.0)),"CRITICAL","distribution"),
        _gate2("MC_SURVIVAL_RATE",float(probs.get("survival",0.0))>=float(p.get("min_survival_rate",0.0)),float(probs.get("survival",0.0)),float(p.get("min_survival_rate",0.0)),"CRITICAL","distribution"),
    ]
    reasons=[g["name"] for g in gates if not g["passed"]]
    return {"schema":"MAX_GATE_KPI_PROFILES_V1","profile":str(p.get("profile_version","MONTE_CARLO_KPI_V1")),"stage":"MONTE_CARLO",
            "authority":"HIERARCHICAL_ALL_MANDATORY","passed":not reasons,"first_failed_gate":reasons[0] if reasons else None,
            "reasons":reasons,"groups":_group_summary(gates,[("survival","Survival"),("economic","Economic tail"),("distribution","Distribution robustness")]),"gates":gates}


def fresh_forward_acceptance(metrics: dict, cfg: dict) -> dict:
    """Independent untouched Fresh Forward gate used only by ONNX Factory."""
    p=gate_profile(cfg,"fresh_forward")
    total=float(metrics.get("total_r",0)); dd=float(metrics.get("max_drawdown_r",999999)); rec=float(metrics.get("recovery_factor",shadow_recovery_factor(total,dd)))
    required=int(metrics.get("auto_min_trades",0) or 0)
    gates=[
        _gate2("FRESH_MIN_TRADES",int(metrics.get("trades",0))>=required,int(metrics.get("trades",0)),required,"MANDATORY","integrity"),
        _gate2("FRESH_MAX_DRAWDOWN",dd<=float(p.get("max_drawdown_r",12.0)),dd,float(p.get("max_drawdown_r",12.0)),"CRITICAL","survival"),
        _gate2("FRESH_RECOVERY_FACTOR",rec>=float(p.get("min_recovery_factor",2.0)),rec,float(p.get("min_recovery_factor",2.0)),"CRITICAL","survival"),
        _gate2("FRESH_PROFIT_FACTOR",float(metrics.get("profit_factor",0))>=float(p.get("min_profit_factor",1.35)),float(metrics.get("profit_factor",0)),float(p.get("min_profit_factor",1.35)),"MANDATORY","economic"),
        _gate2("FRESH_EXPECTANCY",float(metrics.get("expectancy_r",-999))>=float(p.get("min_expectancy_r",0.15)),float(metrics.get("expectancy_r",-999)),float(p.get("min_expectancy_r",0.15)),"MANDATORY","economic"),
    ]
    gates.extend(risk_gate_rows(metrics,risk_cfg_for_gate(cfg,"fresh_forward"),mode="point",prefix="FRESH",group="risk_adjusted"))
    reasons=[g["name"] for g in gates if not g["passed"]]
    return {"schema":"MAX_GATE_KPI_PROFILES_V1","profile":str(p.get("profile_version","FRESH_FORWARD_KPI_V1")),"stage":"FRESH_FORWARD",
            "authority":"HIERARCHICAL_ALL_MANDATORY","passed":not reasons,"first_failed_gate":reasons[0] if reasons else None,"reasons":reasons,
            "groups":_group_summary(gates,[("integrity","Integrity"),("sample_sufficiency","Risk KPI evidence sufficiency"),("survival","Survival"),("economic","Economic edge"),("risk_adjusted","Risk-adjusted")]),"gates":gates,"recovery_factor":rec}


def shadow_recovery_factor(total_r: float, max_drawdown_r: float) -> float:
    total_r = float(total_r)
    dd = float(max_drawdown_r)
    if dd > 1e-12:
        return total_r / dd
    return 999.0 if total_r > 0 else 0.0


def shadow_acceptance(shadow: dict, cfg: dict, *, apply_risk_kpis: bool = True) -> dict:
    """Fresh-forward authority, survival first and fail-closed.

    Monte Carlo may set apply_risk_kpis=False because path/time KPI were already
    gated on chronological Tournament evidence and IID bootstrap has no calendar.
    """
    pc=cfg.get("agent",{}).get("promotion",{}); sh_total=float(shadow.get("total_r",0)); sh_dd=float(shadow.get("max_drawdown_r",999999)); sh_rec=float(shadow.get("recovery_factor",shadow_recovery_factor(sh_total,sh_dd)))
    gates=[
        _gate2("SHADOW_MIN_TRADES",int(shadow.get("trades",0))>=int(shadow.get("auto_min_trades",pc.get("min_shadow_trades",50))),int(shadow.get("trades",0)),int(shadow.get("auto_min_trades",pc.get("min_shadow_trades",50))),"MANDATORY","integrity"),
        _gate2("SHADOW_MAX_DRAWDOWN",sh_dd<=float(pc.get("max_shadow_drawdown_r",12.0)),sh_dd,float(pc.get("max_shadow_drawdown_r",12.0)),"CRITICAL","survival"),
        _gate2("SHADOW_RECOVERY_FACTOR",sh_rec>=float(pc.get("min_shadow_recovery_factor",2.0)),sh_rec,float(pc.get("min_shadow_recovery_factor",2.0)),"CRITICAL","survival"),
        _gate2("SHADOW_PROFIT_FACTOR",float(shadow.get("profit_factor",0))>=float(pc.get("min_shadow_profit_factor",1.35)),float(shadow.get("profit_factor",0)),float(pc.get("min_shadow_profit_factor",1.35)),"MANDATORY","economic"),
        _gate2("SHADOW_EXPECTANCY",float(shadow.get("expectancy_r",-999))>=float(pc.get("min_shadow_expectancy_r",0.15)),float(shadow.get("expectancy_r",-999)),float(pc.get("min_shadow_expectancy_r",0.15)),"MANDATORY","economic"),
    ]
    if apply_risk_kpis:
        gates.extend(risk_gate_rows(shadow,cfg,mode="point",prefix="SHADOW",group="risk_adjusted"))
    reasons=[g["name"] for g in gates if not g["passed"]]
    return {"stage":"SHADOW_FORWARD","authority":"HIERARCHICAL_ALL_MANDATORY","passed":not reasons,"first_failed_gate":reasons[0] if reasons else None,
            "reasons":reasons,"groups":_group_summary(gates,[("integrity","Integrity"),("sample_sufficiency","Risk KPI evidence sufficiency"),("survival","Survival · DD/RF"),("economic","Economic edge"),("risk_adjusted","Advanced risk/research KPI")]),"gates":gates,"recovery_factor":sh_rec}

def champion_relative_assessment(challenger: dict, champion: dict, pc: dict) -> dict:
    """Non-inferiority + improvement-count gate for same-window shadow evidence."""
    c_pf = float(challenger.get("profit_factor", 0.0)); b_pf = float(champion.get("profit_factor", 0.0))
    c_exp = float(challenger.get("expectancy_r", 0.0)); b_exp = float(champion.get("expectancy_r", 0.0))
    c_dd = float(challenger.get("max_drawdown_r", 999999.0)); b_dd = float(champion.get("max_drawdown_r", 999999.0))
    c_rec = float(challenger.get("recovery_factor", 0.0)); b_rec = float(champion.get("recovery_factor", 0.0))

    max_pf_reg = float(pc.get("max_pf_regression_vs_champion", 0.03))
    max_exp_reg = float(pc.get("max_expectancy_regression_r_vs_champion", 0.02))
    max_dd_ratio = float(pc.get("max_drawdown_ratio_vs_champion", 1.15))
    min_rec_ratio = float(pc.get("min_recovery_ratio_vs_champion", 0.90))
    min_improvements = int(pc.get("min_improved_dimensions_vs_champion", 2))

    non_inferior = {
        "profit_factor": c_pf >= b_pf - max_pf_reg,
        "expectancy_r": c_exp >= b_exp - max_exp_reg,
        "max_drawdown_r": c_dd <= (b_dd * max_dd_ratio if b_dd > 0 else c_dd),
        "recovery_factor": c_rec >= b_rec * min_rec_ratio,
    }
    improvements = {
        "profit_factor": c_pf > b_pf,
        "expectancy_r": c_exp > b_exp,
        "max_drawdown_r": c_dd < b_dd,
        "recovery_factor": c_rec > b_rec,
    }
    improvement_count = sum(bool(v) for v in improvements.values())
    passed = all(non_inferior.values()) and improvement_count >= min_improvements
    return {
        "passed": bool(passed),
        "non_inferior": non_inferior,
        "improvements": improvements,
        "improvement_count": int(improvement_count),
        "min_improvements_required": min_improvements,
        "deltas": {
            "profit_factor": c_pf - b_pf,
            "expectancy_r": c_exp - b_exp,
            "max_drawdown_r": c_dd - b_dd,
            "recovery_factor": c_rec - b_rec,
        },
    }
