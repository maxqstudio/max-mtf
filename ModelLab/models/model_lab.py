from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from core.project_paths import MODELLAB_ROOT, CONFIG_DIR
from factory.challenger_registry import register_eligible_challenger
from typing import Callable, Optional

import joblib
import numpy as np
import pandas as pd

from core.contract import FEATURES, REQUIRED_COLUMNS, CONTRACT_ID
from data.labels import build_labels
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry
from data.dataset_integrity import integrity_summary, writer_lock, read_csv_auto
from research.evaluation import classification_metrics, trading_metrics, stress_diagnostics, temporal_stability, regime_diagnostics
from research.kpi import build_locked_test_kpi, locked_test_acceptance, walk_forward_acceptance, walk_forward_composite_score
from models.models import candidate_specs, make_model, fit_model, fit_model_indexed, candidate_input_shape, predict_model_proba, estimate_candidate_parameter_count, model_training_diagnostics
from core.temporal_index import expanding_folds as _canonical_expanding_folds, apply_training_memory

ProgressCallback = Optional[Callable[[dict], None]]


def _emit(cb: ProgressCallback, stage: str, current: int, total: int, message: str, **extra):
    if cb is None:
        return
    payload = {"stage": stage, "current": int(current), "total": int(max(total, 1)), "message": message}
    payload.update(extra)
    cb(payload)


def load_cfg(path):
    """Load config and resolve the machine-local CPU resource profile.

    Calibration is intentionally a sidecar and never changes scientific KPI/contracts.
    Every real execution path that calls ``load_cfg`` therefore consumes the same
    bounded thread policy instead of leaving calibration as an unused utility.
    """
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    try:
        from host.cpu_resource import load_or_calibrate, apply_cpu_profile
        rc = ((cfg.get("compute") or {}).get("cpu_resource") or {})
        if bool(rc.get("enabled", True)):
            cal_path = CONFIG_DIR / "cpu_calibration.json"
            profile = load_or_calibrate(cal_path, cfg)
            cfg = apply_cpu_profile(cfg, profile)
    except Exception as exc:
        # Calibration must never make scientific execution unavailable. Keep the
        # configured CPU policy and expose the diagnostic to callers/UI.
        cfg.setdefault("compute", {}).setdefault("cpu_resource", {})["calibration_error"] = str(exc)
    return cfg


def load_training_csv(path):
    with writer_lock(path):
        integrity = integrity_summary(path, _lock_held=True)
        if integrity["duplicate_extra_rows"]:
            raise ValueError(
                f"Training CSV memiliki {integrity['duplicate_extra_rows']} duplicate identity rows fisik. "
                "Research dihentikan fail-closed; jalankan CLEAN LEGACY DUPLICATES terlebih dahulu."
            )
        df = read_csv_auto(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "Training CSV is not CP32_V1 / v1.02-ready. Missing columns: " + ", ".join(missing)
        )
    if not (df["contract"].astype(str) == CONTRACT_ID).all():
        raise ValueError("Unexpected feature contract. Expected CP32_V1 only.")
    if df[["symbol", "period"]].drop_duplicates().shape[0] != 1:
        raise ValueError("One training run must contain exactly one symbol/timeframe.")
    df["signal_time"] = pd.to_datetime(df["signal_time"], errors="raise")
    df = df.sort_values("signal_time", kind="stable").reset_index(drop=True)
    numeric = [c for c in REQUIRED_COLUMNS if c not in {"contract", "signal_time", "decision_bar_time", "symbol"}]
    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    vals = df[FEATURES].to_numpy(dtype=float)
    if not np.isfinite(vals).all():
        bad = {c:int((~np.isfinite(pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float))).sum()) for c in FEATURES}
        bad = {k:v for k,v in bad.items() if v}
        raise ValueError("Non-finite in features: " + str(bad))
    return df


def feature_matrix(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    """Return CP32 matrix with optional research-only zero-mask while preserving [N,32] contract."""
    X = df[FEATURES].to_numpy(np.float32).copy()
    zero = list((cfg.get("feature_research") or {}).get("zero_features") or [])
    if zero:
        index = {name:i for i,name in enumerate(FEATURES)}
        unknown = [name for name in zero if name not in index]
        if unknown:
            raise ValueError("Unknown feature mask entries: " + ", ".join(unknown))
        for name in zero:
            X[:, index[name]] = 0.0
    return X


def split_locked_test(df, cfg):
    test_frac = float(cfg["split"]["locked_test_fraction"])
    purge = int(cfg["split"]["purge_bars"])
    cut = int(len(df) * (1.0 - test_frac))
    pre = df.iloc[:max(0, cut - purge)].reset_index(drop=True)
    test = df.iloc[min(len(df), cut + purge):].reset_index(drop=True)
    if len(pre) < int(cfg["split"].get("min_train_rows", 1000)):
        raise ValueError(f"Too few pre-test rows after purge: {len(pre)}")
    if len(test) < 50:
        raise ValueError(f"Too few locked-test rows after purge: {len(test)}")
    return pre, test


def research_region(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Resolve the single upstream research authority for this run.

    Champion Factory generations use the whole immutable Discovery snapshot as OOF
    development data because Tournament is a separate later window. Legacy standalone
    runs retain the historical internal locked split for backward compatibility.
    """
    full_oof=bool((cfg.get("agent") or {}).get("discovery_full_oof_only",False))
    if full_oof:
        pre=df.reset_index(drop=True)
        retired=df.iloc[0:0].copy().reset_index(drop=True)
        return pre,retired,{"schema":"CP_RESEARCH_REGION_V2","mode":"FULL_DISCOVERY_OOF","rows":int(len(pre)),"retired_rows":0}
    pre,retired=split_locked_test(df,cfg)
    return pre,retired,{"schema":"CP_RESEARCH_REGION_V2","mode":"LEGACY_INTERNAL_LOCKED_SPLIT","rows":int(len(pre)),"retired_rows":int(len(retired))}


def expanding_folds(df, cfg):
    """Compatibility wrapper around the single temporal-index authority."""
    split = cfg.get("split") or {}
    return _canonical_expanding_folds(
        len(df), int(split.get("walk_forward_folds", 3)), int(split.get("purge_bars", 24)),
        min_train_rows=int(split.get("min_train_rows", 1000)), min_validation_rows=int(split.get("min_validation_rows", 50)),
    )


def _notify_fold(cb, fold_no: int, fold_total: int, **meta):
    if cb is None:
        return
    try:
        cb(fold_no, fold_total, meta)
    except TypeError:
        # Backward compatibility with v0.3 two-argument callbacks.
        cb(fold_no, fold_total)


def _fit_with_heartbeat(model, family: str, X, y, heartbeat=None, interval_sec: float = 2.0, fit_fn=None):
    """Fit in a worker thread so the Streamlit thread can keep emitting progress.

    This is not parallel model search. It only prevents long sklearn/XGB/LGBM fits
    from looking frozen while the native training code is busy.
    """
    import threading
    import time

    runner = fit_fn or (lambda: fit_model(model, family, X, y))
    if heartbeat is None:
        runner()
        return model, 0.0

    state = {"error": None}

    def target():
        try:
            runner()
        except BaseException as exc:  # propagate after join
            state["error"] = exc

    t0 = time.perf_counter()
    thread = threading.Thread(target=target, name=f"fit-{family}", daemon=True)
    thread.start()
    while thread.is_alive():
        thread.join(timeout=max(0.25, float(interval_sec)))
        if thread.is_alive():
            heartbeat(time.perf_counter() - t0)
    elapsed = time.perf_counter() - t0
    if state["error"] is not None:
        raise state["error"]
    return model, elapsed



def apply_candidate_memory(df: pd.DataFrame, spec, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Restrict candidate research to recent calendar memory without touching later holdouts.

    The operator-selected source window remains the outer authority. Each candidate may
    use only the most recent N months inside the dataframe passed to this function.
    If that slice is too small for legal walk-forward construction, the candidate falls
    back to the full supplied dataframe and records the fallback explicitly.
    """
    requested=int((getattr(spec,"params",{}) or {}).get("training_memory_months",0) or 0)
    if requested<=0 or df.empty:
        return df.reset_index(drop=True), {"requested_months":requested,"applied":False,"fallback":"FULL_WINDOW","rows":int(len(df))}
    ts=pd.to_datetime(df["signal_time"],errors="coerce")
    end=ts.max(); start=end-pd.DateOffset(months=requested)
    sub=df.loc[ts>=start].copy().reset_index(drop=True)
    min_rows=max(400,int(cfg.get("split",{}).get("min_train_rows",1000)))
    if len(sub)<min_rows:
        return df.reset_index(drop=True), {"requested_months":requested,"applied":False,"fallback":"TOO_FEW_ROWS","rows":int(len(df)),"candidate_rows":int(len(sub)),"start":str(start),"end":str(end)}
    return sub, {"requested_months":requested,"applied":True,"fallback":None,"rows":int(len(sub)),"start":str(pd.to_datetime(sub["signal_time"]).min()),"end":str(pd.to_datetime(sub["signal_time"]).max())}

def apply_fold_training_memory(df: pd.DataFrame, train_idx, spec, cfg: dict) -> tuple[np.ndarray, dict]:
    """Compatibility wrapper; authority lives in temporal_index.apply_training_memory."""
    return apply_training_memory(df, train_idx, spec, cfg)


def candidate_cv(spec, df, cfg, fold_callback=None):
    import time

    # Preserve the full outer evaluation window. Candidate training memory is applied
    # independently to each fold's TRAIN indices below, never to validation rows.
    df = df.reset_index(drop=True)
    X = feature_matrix(df, cfg)
    y = df["label"].to_numpy(np.int64)
    supervised_weight=df["supervised_weight"].to_numpy(np.float64) if "supervised_weight" in df.columns else np.ones(len(df),dtype=np.float64)
    threshold_grid = [float(x) for x in cfg["deployment"]["take_threshold_grid"]]
    per_threshold = {t: [] for t in threshold_grid}
    per_threshold_extra = {t: [] for t in threshold_grid}
    class_rows = []
    fit_seconds = []
    folds = expanding_folds(df, cfg)

    fold_memory=[]
    fold_training_diagnostics=[]
    for fold_no, (tr, va) in enumerate(folds, 1):
        fit_tr, mem_info = apply_fold_training_memory(df,tr,spec,cfg)
        fold_memory.append({"fold":fold_no,**mem_info})
        _notify_fold(
            fold_callback, fold_no, len(folds), phase="fit_start",
            train_rows=int(len(fit_tr)), validation_rows=int(len(va)), elapsed_sec=0.0,
        )
        model = make_model(spec, cfg)

        def heartbeat(elapsed):
            _notify_fold(
                fold_callback, fold_no, len(folds), phase="fit_heartbeat",
                train_rows=int(len(fit_tr)), validation_rows=int(len(va)), elapsed_sec=float(elapsed),
            )

        model, elapsed = _fit_with_heartbeat(
            model, spec.family, X, y, heartbeat=heartbeat, interval_sec=2.0,
            fit_fn=lambda: fit_model_indexed(model, spec.family, X, y, fit_tr, cfg, sample_weight=supervised_weight),
        )
        fit_seconds.append(float(elapsed))
        fold_training_diagnostics.append(model_training_diagnostics(model))
        if list(getattr(model, "classes_", [])) != [0, 1, 2]:
            raise RuntimeError(f"{spec.name} did not train all three classes: {getattr(model, 'classes_', None)}")
        p = np.asarray(predict_model_proba(model, spec.family, X[:int(va[0])], X[va]), float)
        cm = classification_metrics(p, y[va], sample_weight=supervised_weight[va])
        class_rows.append(cm)
        vdf = df.iloc[va]
        for t in threshold_grid:
            trade = trading_metrics(p, vdf, cfg, t)
            per_threshold[t].append(trade)
            stress = stress_diagnostics(p, vdf, cfg, t)
            temporal = temporal_stability(p, vdf, cfg, t)
            regime = regime_diagnostics(p, vdf, cfg, t)
            per_threshold_extra[t].append({
                "stress": stress,
                "temporal": temporal,
                "regime": regime,
            })

        preview_t = min(threshold_grid, key=lambda x: abs(x - 0.52))
        pm = per_threshold[preview_t][-1]
        _notify_fold(
            fold_callback, fold_no, len(folds), phase="fold_done",
            train_rows=int(len(tr)), validation_rows=int(len(va)), elapsed_sec=float(elapsed),
            preview_profit_factor=float(pm["profit_factor"]),
            preview_expectancy_r=float(pm["expectancy_r"]),
            preview_trades=int(pm["trades"]),
            macro_f1=float(cm["macro_f1"]),
        )

    class_summary = {
        "mean_balanced_accuracy": float(np.mean([x["balanced_accuracy"] for x in class_rows])),
        "mean_macro_f1": float(np.mean([x["macro_f1"] for x in class_rows])),
        "mean_log_loss": float(np.mean([x["log_loss"] for x in class_rows])),
        "mean_brier_score": float(np.mean([x["brier_score"] for x in class_rows])),
        "mean_expected_calibration_error": float(np.mean([x["expected_calibration_error"] for x in class_rows])),
    }

    total_validation_rows = int(sum(len(va) for _tr, va in folds))
    # AUTO sample authority is based on the actual OOF validation exposure, not the
    # whole outer window. This prevents a three-year Discovery from demanding three
    # years of trades when only ~half of the chronology is actually out-of-fold.
    auto_sample = None
    try:
        from research.sample_policy import auto_trade_sample
        full_start=pd.to_datetime(df["signal_time"],errors="coerce").min()
        full_end=pd.to_datetime(df["signal_time"],errors="coerce").max()
        validation_fraction=float(total_validation_rows/max(1,len(df)))
        auto_sample=auto_trade_sample(int(df["period"].iloc[0]),full_start,full_end,cfg,"DISCOVERY",observed_fraction=validation_fraction)
    except Exception:
        auto_sample=None
    def _aggregate_wfa_rows(rows, extras, take_threshold_value):
        exps = [r["expectancy_r"] for r in rows]
        pfs = [r["profit_factor"] for r in rows]
        dds = [r["max_drawdown_r"] for r in rows]
        recs = [r.get("recovery_factor", 0.0) for r in rows]
        trades = sum(r["trades"] for r in rows)
        totals = sum(r["total_r"] for r in rows)

        def med_trade(key, default=0.0):
            vals=[]
            for r in rows:
                v=r.get(key,default)
                if v is None: continue
                try: vals.append(float(v))
                except Exception: pass
            return float(np.median(vals)) if vals else float(default)

        def med_extra(section, key, default=0.0):
            vals=[float((e.get(section) or {}).get(key,default)) for e in extras]
            return float(np.median(vals)) if vals else float(default)

        def med_stress_expectancy(mult_key):
            vals=[]
            for e in extras:
                sp=((e.get("stress") or {}).get("spread") or {}).get(mult_key) or {}
                vals.append(float(sp.get("expectancy_r",-999.0)))
            return float(np.median(vals)) if vals else -999.0

        agg = {
            "take_threshold": float(take_threshold_value),
            "auto_min_validation_trades": int(auto_sample["minimum_trades"]) if auto_sample and auto_sample.get("minimum_trades") is not None else int(cfg.get("acceptance",{}).get("cv_min_validation_trades",90)),
            "auto_trade_sample": auto_sample,
            "folds": len(rows),
            "overall_expectancy_r": float(totals / trades) if trades > 0 else -999.0,
            "median_expectancy_r": float(np.median(exps)),
            "worst_expectancy_r": float(np.min(exps)),
            "expectancy_std_r": float(np.std(exps)),
            "median_profit_factor": float(np.median(pfs)),
            "profit_factor_std": float(np.std(pfs)),
            "median_max_drawdown_r": float(np.median(dds)),
            "worst_fold_max_drawdown_r": float(np.max(dds)),
            "median_recovery_factor": float(np.median(recs)),
            "worst_fold_recovery_factor": float(np.min(recs)),
            "positive_fold_ratio": float(np.mean(np.asarray(exps) > 0.0)),
            "total_validation_trades": int(trades),
            "total_validation_rows": total_validation_rows,
            "trade_coverage_ratio": float(trades / max(1,total_validation_rows)),
            "total_validation_r": float(totals),
            "median_win_rate": med_trade("win_rate"),
            "median_payoff_ratio": med_trade("payoff_ratio"),
            "median_trade_r": med_trade("median_trade_r"),
            "median_cvar95_r": med_trade("cvar95_r"),
            "median_daily_cvar95_r": med_trade("daily_cvar95_r", -999.0),
            "median_fold_trades": med_trade("trades"),
            "median_active_trade_days": med_trade("active_trade_days"),
            "median_daily_tail_sample_count": med_trade("daily_tail_sample_count"),
            "median_sample_years": med_trade("sample_years",0.0),
            "median_expected_shortfall_95_r": med_trade("expected_shortfall_95_r"),
            "median_downside_deviation_r": med_trade("downside_deviation_r"),
            "median_sharpe_ratio": med_trade("sharpe_ratio"),
            "median_sortino_ratio": med_trade("sortino_ratio"),
            "median_calmar_mar_ratio": med_trade("calmar_mar_ratio"),
            "median_probabilistic_sharpe_ratio": med_trade("probabilistic_sharpe_ratio",0.5),
            "median_deflated_sharpe_ratio": med_trade("deflated_sharpe_ratio",0.5),
            "median_ulcer_index_r": med_trade("ulcer_index_r"),
            "median_top10_win_profit_share": med_trade("top10_win_profit_share"),
            "median_max_losing_streak": med_trade("max_losing_streak"),
            "median_max_underwater_trades": med_trade("max_underwater_trades"),
            "median_positive_month_ratio": med_extra("temporal","positive_month_ratio"),
            "median_positive_quarter_ratio": med_extra("temporal","positive_quarter_ratio"),
            "median_regime_concentration": med_extra("regime","dominant_positive_regime_share"),
            "median_stress_x1_25_expectancy_r": med_stress_expectancy("spread_x1.25"),
            "median_stress_x1_50_expectancy_r": med_stress_expectancy("spread_x1.50"),
            "median_threshold_plateau": float(np.median([float((e.get("stress") or {}).get("profitable_threshold_variant_ratio",0.0)) for e in extras])) if extras else 0.0,
            **class_summary,
        }
        score = walk_forward_composite_score(agg, cfg)
        agg["selection_score"] = float(score["score"])
        agg["score_schema"] = score["schema"]
        agg["score_breakdown"] = score["components"]
        agg["score_categories"] = score["categories"]
        acc = walk_forward_acceptance(agg, cfg)
        agg["cv_gate_pass"] = bool(acc["passed"])
        agg["cv_gate_reasons"] = list(acc["reasons"])
        return agg

    # Final deployment threshold is selected from all WFA evidence, but those same
    # folds no longer grade that choice.  A leave-one-fold-out selector chooses the
    # threshold for each held fold using only the other WFA folds; WFA acceptance and
    # ranking are computed from these nested held-fold outcomes. CPCV then evaluates
    # the one frozen deployment threshold independently.
    threshold_aggregates={}
    deployment_best=None
    for t, rows in per_threshold.items():
        agg=_aggregate_wfa_rows(rows,per_threshold_extra[t],t)
        threshold_aggregates[float(t)]=agg
        if deployment_best is None or (bool(agg["cv_gate_pass"]),agg["selection_score"]) > (bool(deployment_best.get("cv_gate_pass")),deployment_best["selection_score"]):
            deployment_best=agg

    nested_rows=[]; nested_extras=[]; nested_thresholds=[]
    fold_count=len(folds)
    for hold_i in range(fold_count):
        selector_best=None; selector_t=None
        train_fold_idx=[j for j in range(fold_count) if j!=hold_i]
        for t in threshold_grid:
            srows=[per_threshold[t][j] for j in train_fold_idx]
            sextras=[per_threshold_extra[t][j] for j in train_fold_idx]
            sagg=_aggregate_wfa_rows(srows,sextras,t)
            key=(bool(sagg.get("cv_gate_pass")),float(sagg.get("selection_score",-1e99)))
            if selector_best is None or key>selector_best:
                selector_best=key; selector_t=float(t)
        nested_thresholds.append(float(selector_t))
        nested_rows.append(per_threshold[float(selector_t)][hold_i])
        nested_extras.append(per_threshold_extra[float(selector_t)][hold_i])

    best=_aggregate_wfa_rows(nested_rows,nested_extras,float(deployment_best["take_threshold"]))
    best["deployment_take_threshold"]=float(deployment_best["take_threshold"])
    best["take_threshold"]=float(deployment_best["take_threshold"])
    best["threshold_selection_mode"]="NESTED_LEAVE_ONE_WFA_FOLD_OUT_V1"
    best["wfa_fold_selected_thresholds"]=nested_thresholds
    best["threshold_grid_trials"]=len(threshold_grid)
    best["deployment_threshold_full_wfa_diagnostic"]={
        "take_threshold":float(deployment_best["take_threshold"]),
        "selection_score":float(deployment_best["selection_score"]),
        "cv_gate_pass_if_reused_for_grading":bool(deployment_best["cv_gate_pass"]),
        "authority":"DEPLOYMENT_SELECTION_ONLY_NOT_WFA_ACCEPTANCE",
    }
    selected_rows=nested_rows
    selected_extras=nested_extras
    fold_diag=[]
    acfg=cfg.get("acceptance",{})
    for i,r in enumerate(selected_rows):
        va=folds[i][1]; vdf=df.iloc[va]
        regime_detail=selected_extras[i].get("regime") or {}
        failed=[]
        _eps=abs(float(acfg.get("worst_expectancy_epsilon",1e-9)))
        if float(r.get("expectancy_r",-999)) + _eps < float(acfg.get("cv_min_worst_expectancy_r",0.0)):
            failed.append("WORST_EXPECTANCY")
        if float(r.get("max_drawdown_r",999)) > float(acfg.get("cv_max_worst_fold_drawdown_r",18.0)):
            failed.append("WORST_DRAWDOWN")
        if float(r.get("recovery_factor",-999)) < float(acfg.get("cv_min_worst_fold_recovery_factor",1.0)):
            failed.append("WORST_RECOVERY")
        hostile=[]
        for rg in ("TREND","RANGE","TRANSITION","SHOCK"):
            gm=regime_detail.get(rg) or {}
            if int(gm.get("trades",0))>0 and float(gm.get("expectancy_r",0.0))<0:
                hostile.append({"regime":rg,"trades":int(gm.get("trades",0)),"expectancy_r":float(gm.get("expectancy_r",0.0)),"profit_factor":float(gm.get("profit_factor",0.0)),"total_r":float(gm.get("total_r",0.0))})
        fold_diag.append({
            "fold":i+1,"evaluation_take_threshold":float(nested_thresholds[i]),"validation_start":str(pd.to_datetime(vdf["signal_time"],errors="coerce").min()),
            "validation_end":str(pd.to_datetime(vdf["signal_time"],errors="coerce").max()),
            "validation_rows":int(len(vdf)),"fit_seconds":float(fit_seconds[i]),
            "model_training_diagnostics":fold_training_diagnostics[i],
            "profit_factor":float(r["profit_factor"]),"expectancy_r":float(r["expectancy_r"]),
            "max_drawdown_r":float(r["max_drawdown_r"]),"recovery_factor":float(r.get("recovery_factor",0.0)),
            "win_rate":float(r.get("win_rate",0.0)),"payoff_ratio":float(r.get("payoff_ratio",0.0)),
            "median_trade_r":float(r.get("median_trade_r",0.0)),"cvar95_r":float(r.get("cvar95_r",0.0)),
            "top10_win_profit_share":float(r.get("top10_win_profit_share",0.0)),
            "max_losing_streak":int(r.get("max_losing_streak",0)),"max_underwater_trades":int(r.get("max_underwater_trades",0)),
            "positive_month_ratio":float((selected_extras[i].get("temporal") or {}).get("positive_month_ratio",0.0)),
            "positive_quarter_ratio":float((selected_extras[i].get("temporal") or {}).get("positive_quarter_ratio",0.0)),
            "regime_concentration":float(regime_detail.get("dominant_positive_regime_share",0.0)),
            "regime_breakdown":{k:v for k,v in regime_detail.items() if k in ("TREND","RANGE","TRANSITION","SHOCK")},
            "hostile_regimes":hostile,"failed_survival_gates":failed,
            "stress_x1_25_expectancy_r":float((((selected_extras[i].get("stress") or {}).get("spread") or {}).get("spread_x1.25") or {}).get("expectancy_r",-999.0)),
            "stress_x1_50_expectancy_r":float((((selected_extras[i].get("stress") or {}).get("spread") or {}).get("spread_x1.50") or {}).get("expectancy_r",-999.0)),
            "threshold_plateau":float((selected_extras[i].get("stress") or {}).get("profitable_threshold_variant_ratio",0.0)),
            "trades":int(r["trades"]),"coverage_ratio":float(int(r["trades"])/max(1,len(vdf))),"total_r":float(r["total_r"]),
        })
    best["fold_diagnostics"] = fold_diag
    if fold_diag:
        best["worst_fold_by_expectancy"] = min(fold_diag,key=lambda x:x["expectancy_r"])
        best["worst_fold_by_drawdown"] = max(fold_diag,key=lambda x:x["max_drawdown_r"])
    requested_memory=int((getattr(spec,"params",{}) or {}).get("training_memory_months",0) or 0)
    memory_info={"requested_months":requested_memory,"mode":"PER_FOLD_TRAIN_ONLY","validation_window_preserved":True,"folds":fold_memory,"applied":any(bool(x.get("applied")) for x in fold_memory)}
    best["training_memory"] = memory_info
    best["training_memory_months"] = requested_memory
    best["parameter_count"] = estimate_candidate_parameter_count(spec,len(FEATURES))
    _tr_rows=[int((x or {}).get("rows",0) or 0) for x in fold_memory if isinstance(x,dict)]
    best["median_effective_train_rows"] = int(np.median(_tr_rows)) if _tr_rows else None
    best["total_fit_seconds"] = float(sum(fit_seconds))
    best["mean_fit_seconds"] = float(np.mean(fit_seconds)) if fit_seconds else 0.0
    acc = walk_forward_acceptance(best, cfg)
    best["cv_gate_pass"] = bool(acc["passed"])
    best["cv_gate_reasons"] = list(acc["reasons"])
    return best

def acceptance(metrics, parity, cfg, kpi_report=None):
    # Compatibility wrapper. v0.6.0 authority lives in kpi.locked_test_acceptance.
    from research.kpi import locked_test_acceptance
    if kpi_report is None:
        kpi_report = {"locked_test": metrics, "onnx_parity": parity, "stress": {}}
    result = locked_test_acceptance(kpi_report, cfg)
    return bool(result["passed"]), list(result["reasons"])


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()




def _period_label(period) -> str:
    try: p=int(float(period))
    except Exception: return str(period or "?")
    mapping={1:"M1",2:"M2",3:"M3",4:"M4",5:"M5",6:"M6",10:"M10",12:"M12",15:"M15",20:"M20",30:"M30",16385:"H1",16386:"H2",16387:"H3",16388:"H4",16390:"H6",16392:"H8",16396:"H12",16408:"D1",32769:"W1",49153:"MN1",60:"H1",120:"H2",180:"H3",240:"H4",360:"H6",480:"H8",720:"H12",1440:"D1",10080:"W1",43200:"MN1"}
    return mapping.get(p,f"P{p}")

def _dataset_provenance(raw: pd.DataFrame, csv_path: str) -> dict:
    period=int(raw["period"].iloc[0]); symbol=str(raw["symbol"].iloc[0])
    return {"identity_schema":"DATASET_ID_V2","symbol":symbol,"period":period,"timeframe":_period_label(period),
            "source_csv_name":Path(csv_path).name,"source_csv_sha256":sha256_file(csv_path),"source_rows":int(len(raw)),
            "source_start":str(raw["signal_time"].min()),"source_end":str(raw["signal_time"].max())}

def run_pipeline(csv_path, config_path="config.json", out_dir="runs", progress: ProgressCallback = None):
    csv_path = str(csv_path)
    config_path = str(config_path)
    out_dir = str(out_dir)

    _emit(progress, "load", 0, 1, "Membaca dataset CP32…")
    cfg = load_cfg(config_path)
    raw = load_training_csv(csv_path)
    cfg, strategy_geometry = synchronize_cfg_with_dataset_geometry(cfg, raw)
    provenance = _dataset_provenance(raw, csv_path)
    provenance["strategy_geometry"] = strategy_geometry
    _emit(progress, "label", 0, 1, f"Membangun forward labels dari {len(raw):,} bar…")
    labeled = build_labels(raw, cfg)
    supervised_rows=int((labeled.get("supervised_weight",0)>0).sum()) if "supervised_weight" in labeled.columns else len(labeled)
    if supervised_rows < int(cfg["split"].get("min_train_rows",1000)) + 200:
        raise ValueError(f"Too few supervised labeled rows: {supervised_rows}/{len(labeled)} context rows")

    run_id = datetime.now(timezone.utc).strftime("RUN_%Y%m%d_%H%M%S_UTC")
    out = Path(out_dir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "run_config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    labeled.to_csv(out / "labeled_dataset.csv", index=False)

    pre, test = split_locked_test(labeled, cfg)
    specs = candidate_specs(cfg)
    if not specs:
        raise ValueError("No deployable model families enabled.")

    board = []
    total_candidates = len(specs)
    for idx, spec in enumerate(specs, 1):
        def _fold_cb(fold_no, fold_total, meta=None):
            meta = meta or {}
            phase = meta.get("phase", "fit_start")
            elapsed = float(meta.get("elapsed_sec", 0.0))
            train_rows = int(meta.get("train_rows", 0))
            val_rows = int(meta.get("validation_rows", 0))
            if phase == "fit_heartbeat":
                msg = f"{spec.name}: fold {fold_no}/{fold_total} · training {elapsed:.0f}s · train {train_rows:,} rows"
            elif phase == "fold_done":
                msg = (f"{spec.name}: fold {fold_no}/{fold_total} selesai · {elapsed:.1f}s · "
                       f"PF {float(meta.get('preview_profit_factor',0)):.3f} · "
                       f"Exp {float(meta.get('preview_expectancy_r',0)):+.4f}R · trades {int(meta.get('preview_trades',0))}")
            else:
                msg = f"{spec.name}: fold {fold_no}/{fold_total} mulai · train {train_rows:,} · val {val_rows:,}"
            _emit(progress, "cv", idx - 1, total_candidates, msg,
                  candidate=spec.name, candidate_index=idx, candidate_total=total_candidates,
                  fold=fold_no, fold_total=fold_total, **meta)
        _emit(progress, "cv", idx - 1, total_candidates,
              f"Menguji {spec.name} ({spec.family})…",
              candidate=spec.name, candidate_index=idx, candidate_total=total_candidates)
        cv = candidate_cv(spec, pre, cfg, fold_callback=_fold_cb)
        cv_acc = walk_forward_acceptance(cv, cfg)
        cv["cv_gate_pass"] = bool(cv_acc.get("passed"))
        cv["cv_gate_reasons"] = list(cv_acc.get("reasons") or [])
        cv["cv_first_failed_gate"] = cv_acc.get("first_failed_gate")
        board.append({"family": spec.family, "name": spec.name, "params": spec.params, **cv})
        _emit(progress, "cv", idx, total_candidates,
              (f"{spec.name} selesai · score {float(cv['selection_score']):+.4f} · "
               f"PF {float(cv['median_profit_factor']):.3f} · Exp {float(cv['median_expectancy_r']):+.4f}R · "
               f"Worst {float(cv['worst_expectancy_r']):+.4f}R · DD {float(cv['median_max_drawdown_r']):.2f}R · "
               f"trades {int(cv['total_validation_trades'])} · fit {float(cv.get('total_fit_seconds',0)):.1f}s"),
              candidate=spec.name, candidate_index=idx, candidate_total=total_candidates,
              candidate_score=float(cv['selection_score']),
              result_row={
                  "Exp": idx,
                  "Round": 1,
                  "Model": spec.name,
                  "Family": spec.family,
                  "Score": round(float(cv['selection_score']), 2),
                  "PASS": "YES" if bool(cv.get("cv_gate_pass")) else "NO",
                  "First fail": str(cv.get("cv_first_failed_gate") or ""),
                  "Fails": int(len(cv.get("cv_gate_reasons") or [])),
                  "DD R": round(float(cv.get("median_max_drawdown_r",999)), 2),
                  "Worst DD": round(float(cv.get("worst_fold_max_drawdown_r",999)), 2),
                  "Recovery": round(float(cv.get("median_recovery_factor",-999)), 2),
                  "Worst RF": round(float(cv.get("worst_fold_recovery_factor",-999)), 2),
                  "PF": round(float(cv['median_profit_factor']), 3),
                  "Exp R": round(float(cv['median_expectancy_r']), 4),
                  "Worst R": round(float(cv['worst_expectancy_r']), 4),
                  "Positive folds": f"{100.0*float(cv.get('positive_fold_ratio',0.0)):.0f}%",
                  "Stress 1.50": round(float(cv.get('median_stress_x1_50_expectancy_r',-999.0)), 4),
                  "Plateau": f"{100.0*float(cv.get('median_threshold_plateau',0.0)):.0f}%",
                  "Trades": int(cv['total_validation_trades']),
                  "Fit s": round(float(cv.get('total_fit_seconds', 0.0)), 1),
              })

    for row in board:
        cv_gate = walk_forward_acceptance(row, cfg)
        row["cv_gate_pass"] = bool(cv_gate["passed"])
        row["cv_gate_reasons"] = list(cv_gate["reasons"])
        row["cv_first_failed_gate"] = cv_gate.get("first_failed_gate")
    # Acceptance class first. Composite score ranks only inside PASS/FAIL class.
    board = sorted(board, key=lambda x: (bool(x.get("cv_gate_pass")), float(x.get("selection_score", -1e99))), reverse=True)
    pd.DataFrame(board).to_json(out / "cv_leaderboard.json", orient="records", indent=2)
    eligible_rows = [r for r in board if bool(r.get("cv_gate_pass"))]
    winner_row = eligible_rows[0] if eligible_rows else board[0]
    winner_spec = next(s for s in specs if s.name == winner_row["name"])
    cv_acceptance = walk_forward_acceptance(winner_row, cfg)
    with open(out / "cv_acceptance.json", "w", encoding="utf-8") as f:
        json.dump(cv_acceptance, f, indent=2)
    if not cv_acceptance["passed"]:
        manifest = {
            "run_id": run_id, "status": "RESEARCH_REJECTED", "reject_reasons": cv_acceptance["reasons"],
            "feature_contract": CONTRACT_ID, "feature_count": len(FEATURES), "feature_order": FEATURES,
            "class_order": ["SELL", "SKIP", "BUY"], "model_family": winner_spec.family,
            "model_name": winner_spec.name, "hyperparameters": winner_spec.params,
            "take_threshold": winner_row["take_threshold"], "deployment": cfg["deployment"],
            "label_policy": cfg["label"], "cv_selection": winner_row, "cv_acceptance": cv_acceptance,
            "dataset_provenance": provenance, "symbol": provenance["symbol"], "period": provenance["period"], "timeframe": provenance["timeframe"],
            "source_start": provenance["source_start"], "source_end": provenance["source_end"],
            "source_csv_sha256": provenance["source_csv_sha256"], "train_rows": int(len(pre)),
            "locked_test_rows": int(len(test)), "locked_test_opened": False,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
        }
        with open(out / "model_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        with open(out / "REPORT.md", "w", encoding="utf-8") as f:
            f.write(f"# ComplexPolicy Model Run {run_id}\n\n**Status:** RESEARCH_REJECTED\n\n")
            f.write("Locked test was NOT opened because walk-forward KPI gates failed.\n\n```json\n")
            f.write(json.dumps(cv_acceptance, indent=2)); f.write("\n```\n")
        _emit(progress, "done", 1, 1, f"RESEARCH_REJECTED · {winner_spec.name} · locked test tetap sealed", winner=winner_spec.name)
        return {"run": str(out), "status": "RESEARCH_REJECTED", "winner": winner_spec.name, "reasons": cv_acceptance["reasons"], "manifest": manifest}

    _emit(progress, "winner", 0, 1, f"Refit winner: {winner_spec.name}…", winner=winner_spec.name)
    pre_fit, memory_info = apply_candidate_memory(pre, winner_spec, cfg)
    Xpre = feature_matrix(pre_fit, cfg)
    ypre = pre_fit["label"].to_numpy(np.int64)
    Xtest = feature_matrix(test, cfg)
    ytest = test["label"].to_numpy(np.int64)

    winner = make_model(winner_spec, cfg)
    fit_model(winner,winner_spec.family,Xpre,ypre,sample_weight=(pre_fit["supervised_weight"].to_numpy(np.float64) if "supervised_weight" in pre_fit.columns else None),cfg=cfg)
    if list(getattr(winner, "classes_", [])) != [0, 1, 2]:
        raise RuntimeError(f"Winner did not train all three classes: {getattr(winner, 'classes_', None)}")
    ptest = np.asarray(winner.predict_proba(Xtest), float)
    class_test = classification_metrics(ptest, ytest, sample_weight=(test["supervised_weight"].to_numpy(np.float64) if "supervised_weight" in test.columns else None))
    trade_test = trading_metrics(ptest, test, cfg, float(winner_row["take_threshold"]))

    joblib.dump(winner, out / "winner_model.joblib")

    _emit(progress, "onnx", 0, 1, "Mengekspor Challenger ONNX dan memeriksa parity…")
    from models.onnx_export import export_tabular, verify_onnx
    onnx_path = export_tabular(winner, winner_spec.family, out / "challenger.onnx", len(FEATURES))
    parity = verify_onnx(onnx_path, winner, Xtest, max_rows=1000)
    kpi_report = build_locked_test_kpi(ptest, ytest, test, cfg, float(winner_row["take_threshold"]), parity)
    kpi_acceptance = locked_test_acceptance(kpi_report, cfg)
    with open(out / "kpi_report.json", "w", encoding="utf-8") as f:
        json.dump(kpi_report, f, indent=2)
    with open(out / "kpi_acceptance.json", "w", encoding="utf-8") as f:
        json.dump(kpi_acceptance, f, indent=2)
    passed, reasons = bool(kpi_acceptance["passed"]), list(kpi_acceptance["reasons"])

    pred = test[["signal_time", "decision_bar_time", "close", "long_r", "short_r", "label"]].copy()
    pred["p_sell"] = ptest[:, 0]
    pred["p_skip"] = ptest[:, 1]
    pred["p_buy"] = ptest[:, 2]
    pred.to_csv(out / "locked_test_predictions.csv", index=False)

    manifest = {
        "run_id": run_id,
        "status": "ELIGIBLE_CHALLENGER" if passed else "REJECTED",
        "reject_reasons": reasons,
        "feature_contract": CONTRACT_ID,
        "feature_count": len(FEATURES),
        "feature_order": FEATURES,
        "class_order": ["SELL", "SKIP", "BUY"],
        "model_family": winner_spec.family,
        "model_name": winner_spec.name,
        "hyperparameters": winner_spec.params,
        "take_threshold": winner_row["take_threshold"],
        "deployment": cfg["deployment"],
        "label_policy": cfg["label"],
        "cv_selection": winner_row,
        "cv_acceptance": cv_acceptance,
        "locked_test_classification": class_test,
        "locked_test_trading": trade_test,
        "kpi_schema": "KPI_V5_HIERARCHICAL",
        "kpi_acceptance": kpi_acceptance,
        "kpi_report": kpi_report,
        "onnx_parity": parity,
        "onnx_sha256": sha256_file(onnx_path),
        "dataset_provenance": provenance,
        "symbol": provenance["symbol"], "period": provenance["period"], "timeframe": provenance["timeframe"],
        "source_start": provenance["source_start"], "source_end": provenance["source_end"],
        "source_csv_sha256": provenance["source_csv_sha256"],
        "training_memory": memory_info,
        "train_rows": int(len(pre_fit)),
        "locked_test_rows": int(len(test)),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "current_ea_input_shape": candidate_input_shape(winner_spec,len(FEATURES)),
        "onnx_output_shape": [1, 3],
    }
    if manifest["status"] == "ELIGIBLE_CHALLENGER":
        manifest = register_eligible_challenger(out, manifest, MODELLAB_ROOT)
    with open(out / "model_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    with open(out / "REPORT.md", "w", encoding="utf-8") as f:
        f.write(f"# ComplexPolicy Model Run {run_id}\n\n")
        f.write(f"**Status:** {manifest['status']}\n\n")
        f.write(f"**Winner:** {winner_spec.name} ({winner_spec.family})\n\n")
        f.write("## Walk-forward acceptance\n\n```json\n")
        f.write(json.dumps(cv_acceptance, indent=2))
        f.write("\n```\n\n## Locked-test KPI acceptance\n\n```json\n")
        f.write(json.dumps(kpi_acceptance, indent=2))
        f.write("\n```\n\n## Locked test trading\n\n```json\n")
        f.write(json.dumps(trade_test, indent=2))
        f.write("\n```\n\n## Classification\n\n```json\n")
        f.write(json.dumps(class_test, indent=2))
        f.write("\n```\n\n## ONNX parity\n\n```json\n")
        f.write(json.dumps(parity, indent=2))
        f.write("\n```\n")
        if reasons:
            f.write("\n## Reject reasons\n\n" + "\n".join(f"- {r}" for r in reasons) + "\n")

    _emit(progress, "done", 1, 1,
          f"{manifest['status']} — {winner_spec.name}",
          run=str(out), status=manifest["status"], winner=winner_spec.name)

    return {
        "run": str(out),
        "status": manifest["status"],
        "winner": winner_spec.name,
        "reasons": reasons,
        "manifest": manifest,
    }


def main():
    ap = argparse.ArgumentParser(description="ComplexPolicy CPU-only Champion/Challenger model builder")
    ap.add_argument("--csv", required=True, help="Max_MTF_Training.csv from Max EA")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--out", default="runs")
    args = ap.parse_args()

    def cli_progress(p):
        print(f"[{p['stage'].upper()}] {p['message']}", flush=True)

    result = run_pipeline(args.csv, args.config, args.out, progress=cli_progress)
    print(json.dumps({k: result[k] for k in ("run", "status", "winner", "reasons")}, indent=2))
    return 0 if result["status"] == "ELIGIBLE_CHALLENGER" else 2


if __name__ == "__main__":
    raise SystemExit(main())
