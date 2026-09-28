from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from core.contract import FEATURES
from research.evaluation import (
    classification_metrics,
    metrics_from_trades,
    normalize_proba,
    decision_fields,
    simulate_execution_from_actions,
    _spread_stressed_df,
)
from research.kpi import walk_forward_acceptance, walk_forward_composite_score, locked_test_acceptance
from models.model_lab import expanding_folds, feature_matrix, _fit_with_heartbeat, _notify_fold, apply_fold_training_memory
from models.models import make_model, fit_model_indexed, predict_model_proba

POLICY_SCHEMA = "CP_POLICY_V1"


def _regime_labels(df, cfg: dict) -> np.ndarray:
    rcfg = cfg.get("diagnostics", {}).get("regime", {})
    trend_min = float(rcfg.get("trend_adx_min", 0.25))
    range_max = float(rcfg.get("range_adx_max", 0.18))
    shock_min = float(rcfg.get("shock_range_atr_min", 3.0))
    adx = df["adx_scaled"].to_numpy(float)
    rng = df["range_atr"].to_numpy(float)
    regime = np.full(len(df), "TRANSITION", dtype=object)
    regime[adx <= range_max] = "RANGE"
    regime[adx >= trend_min] = "TREND"
    regime[rng >= shock_min] = "SHOCK"
    return regime


def _regime_allowed(regime: np.ndarray, mode: str) -> np.ndarray:
    mode = str(mode or "ALL").upper()
    if mode == "ALL":
        return np.ones(len(regime), dtype=bool)
    if mode == "NON_SHOCK":
        return regime != "SHOCK"
    if mode == "TREND":
        return regime == "TREND"
    if mode == "RANGE":
        return regime == "RANGE"
    if mode == "TREND_RANGE":
        return (regime == "TREND") | (regime == "RANGE")
    if mode == "TRANSITION":
        return regime == "TRANSITION"
    if mode == "TREND_TRANSITION":
        return (regime == "TREND") | (regime == "TRANSITION")
    if mode == "RANGE_TRANSITION":
        return (regime == "RANGE") | (regime == "TRANSITION")
    return np.zeros(len(regime), dtype=bool)


def policy_actions(proba: np.ndarray, df, cfg: dict, policy: dict) -> np.ndarray:
    """Apply CP_POLICY_V1 without touching locked-test authority.

    The base fixed execution/risk gates remain intact. Policy Discovery may only
    become more selective using model probabilities/uncertainty/regime.
    """
    p = normalize_proba(proba)
    dc = cfg["deployment"]
    sell, skip, buy = p[:, 0], p[:, 1], p[:, 2]
    directional = buy - sell
    take = 1.0 - skip
    rule = df["rule_meta_score"].to_numpy(float)
    consensus = df["consensus"].to_numpy(float)
    blend = float(dc["onnx_blend"])
    final = (1.0 - blend) * rule + blend * directional
    entropy = -np.sum(p * np.log(np.clip(p, 1e-12, 1.0)), axis=1)
    regime = _regime_labels(df, cfg)

    gate = (
        (take >= float(policy.get("take_threshold", 0.65)))
        & (np.abs(buy - sell) >= float(policy.get("directional_margin", 0.0)))
        & (entropy <= float(policy.get("max_entropy", math.log(3.0) + 1e-6)))
        & (consensus >= float(dc["min_consensus"]))
        & (np.abs(final) >= float(dc["entry_threshold"]))
        & (df["spread_points"].to_numpy(float) <= float(dc["max_spread_points"]))
        & (df["range_atr"].to_numpy(float) < float(dc["shock_halt_range_atr"]))
        & _regime_allowed(regime, str(policy.get("regime_mode", "ALL")))
    )
    action = np.zeros(len(df), dtype=np.int8)
    action[gate & (final > 0) & (buy >= float(policy.get("buy_threshold", 0.0)))] = 1
    action[gate & (final < 0) & (sell >= float(policy.get("sell_threshold", 0.0)))] = -1
    return action


def policy_trade_outcomes(proba, df, cfg, policy):
    desired=policy_actions(proba,df,cfg,policy)
    fields=decision_fields(proba,df,cfg)
    act,r,_=simulate_execution_from_actions(desired,fields["final"],df,cfg)
    return act,r


def policy_trading_metrics(proba, df, cfg, policy):
    act, r = policy_trade_outcomes(proba, df, cfg, policy)
    mask=act != 0
    from research.risk_kpi import dsr_trial_count, psr_benchmark
    timestamps=df.loc[mask,"signal_time"].to_numpy() if hasattr(df,"columns") and "signal_time" in df.columns else None
    evaluation_start=evaluation_end=None
    if hasattr(df,"columns") and "signal_time" in df.columns and len(df):
        _all_ts=pd.to_datetime(df["signal_time"],errors="coerce").dropna()
        if len(_all_ts): evaluation_start=_all_ts.min(); evaluation_end=_all_ts.max()
    return metrics_from_trades(r[mask], n_rows=len(df), take_threshold=float(policy.get("take_threshold", 0.0)),
                              timestamps=timestamps, multiple_testing_trials=dsr_trial_count(cfg), benchmark_sharpe=psr_benchmark(cfg),
                              evaluation_start=evaluation_start,evaluation_end=evaluation_end)


def policy_temporal_stability(proba, df, cfg, policy):
    import pandas as pd
    act, r = policy_trade_outcomes(proba, df, cfg, policy)
    mask = act != 0
    if not np.any(mask):
        return {"active_months": 0, "positive_month_ratio": 0.0, "median_month_r": 0.0, "worst_month_r": 0.0,
                "longest_negative_month_streak": 0, "active_quarters": 0, "positive_quarter_ratio": 0.0,
                "median_quarter_r": 0.0, "worst_quarter_r": 0.0}
    ts = pd.to_datetime(df.loc[mask, "signal_time"], errors="coerce")
    vals = pd.Series(r[mask], index=ts)
    vals = vals[~vals.index.isna()]
    monthly = vals.groupby(vals.index.to_period("M")).sum().sort_index()
    quarterly = vals.groupby(vals.index.to_period("Q")).sum().sort_index()
    best = cur = 0
    for v in monthly.to_numpy(float):
        if v < 0: cur += 1; best = max(best, cur)
        else: cur = 0
    return {
        "active_months": int(len(monthly)), "positive_month_ratio": float((monthly > 0).mean()) if len(monthly) else 0.0,
        "median_month_r": float(monthly.median()) if len(monthly) else 0.0, "worst_month_r": float(monthly.min()) if len(monthly) else 0.0,
        "longest_negative_month_streak": int(best), "active_quarters": int(len(quarterly)),
        "positive_quarter_ratio": float((quarterly > 0).mean()) if len(quarterly) else 0.0,
        "median_quarter_r": float(quarterly.median()) if len(quarterly) else 0.0, "worst_quarter_r": float(quarterly.min()) if len(quarterly) else 0.0,
    }


def policy_regime_diagnostics(proba, df, cfg, policy):
    regimes = _regime_labels(df, cfg)
    act, r = policy_trade_outcomes(proba, df, cfg, policy)
    out = {}; positive = []
    for name in ("TREND", "RANGE", "SHOCK", "TRANSITION"):
        mask = (regimes == name) & (act != 0)
        m = metrics_from_trades(r[mask], n_rows=int(np.sum(regimes == name)))
        out[name] = m
        if m["total_r"] > 0: positive.append(m["total_r"])
    total = float(sum(positive))
    out["dominant_positive_regime_share"] = float(max(positive) / total) if positive and total > 0 else 0.0
    return out


def policy_stress_diagnostics(proba, df, cfg, policy):
    acfg = cfg.get("acceptance", {})
    spread = {}
    for mult in [float(x) for x in acfg.get("stress_spread_multipliers", [1.25, 1.50])]:
        sdf = _spread_stressed_df(df, cfg, mult)
        spread[f"spread_x{mult:.2f}"] = policy_trading_metrics(proba, sdf, cfg, policy)
    delta = float(acfg.get("sensitivity_take_delta", 0.03))
    base = float(policy.get("take_threshold", 0.65))
    rows = []; profitable = 0
    for t in sorted(set(round(min(0.99, max(0.01, base + d)), 6) for d in (-delta, 0.0, delta))):
        p2 = dict(policy); p2["take_threshold"] = t
        m = policy_trading_metrics(proba, df, cfg, p2)
        rows.append({"take_threshold": t, **m})
        if m["expectancy_r"] > 0 and m["profit_factor"] >= 1.0: profitable += 1
    return {"spread": spread, "take_threshold_sensitivity": rows,
            "profitable_threshold_variant_ratio": float(profitable / max(1, len(rows)))}


def collect_oof_predictions(spec, df, cfg, fold_callback=None):
    """Collect policy-search OOF predictions under the same WFA chronology as candidate_cv.

    Candidate training memory is applied per TRAIN fold only. Validation windows are never
    shortened, and temporal/hybrid families receive causal pre-validation context.
    """
    df=df.reset_index(drop=True)
    X = feature_matrix(df,cfg); y = df["label"].to_numpy(np.int64)
    folds = expanding_folds(df, cfg); out = []
    for fold_no, (tr, va) in enumerate(folds, 1):
        fit_tr, mem = apply_fold_training_memory(df,tr,spec,cfg)
        _notify_fold(fold_callback, fold_no, len(folds), phase="policy_oof_fit_start", train_rows=len(fit_tr), validation_rows=len(va), elapsed_sec=0.0)
        model = make_model(spec, cfg)
        def heartbeat(elapsed):
            _notify_fold(fold_callback, fold_no, len(folds), phase="policy_oof_fit_heartbeat", train_rows=len(fit_tr), validation_rows=len(va), elapsed_sec=elapsed)
        model, elapsed = _fit_with_heartbeat(
            model, spec.family, X, y, heartbeat=heartbeat, interval_sec=2.0,
            fit_fn=lambda: fit_model_indexed(model,spec.family,X,y,fit_tr,cfg,sample_weight=(df["supervised_weight"].to_numpy(float) if "supervised_weight" in df.columns else None)),
        )
        if list(getattr(model, "classes_", [])) != [0, 1, 2]:
            raise RuntimeError(f"{spec.name} OOF did not train all three classes")
        p = np.asarray(predict_model_proba(model,spec.family,X[:int(va[0])],X[va]), float)
        out.append({"fold": fold_no, "indices": va, "proba": p, "y": y[va], "df": df.iloc[va].copy(), "fit_seconds": float(elapsed), "training_memory":mem})
        _notify_fold(fold_callback, fold_no, len(folds), phase="policy_oof_fold_done", train_rows=len(fit_tr), validation_rows=len(va), elapsed_sec=elapsed)
    return out


def _policy_candidates(cfg: dict, seed: int, base_take: float, budget: int):
    pcfg = cfg.get("agent", {}).get("policy_discovery", {})
    take_grid = [float(x) for x in pcfg.get("take_threshold_grid", [0.60,0.65,0.70,0.75,0.80,0.85])]
    dir_grid = [float(x) for x in pcfg.get("direction_threshold_grid", [0.40,0.45,0.50,0.55,0.60,0.65])]
    margin_grid = [float(x) for x in pcfg.get("directional_margin_grid", [0.00,0.05,0.10,0.15,0.20])]
    entropy_grid = [float(x) for x in pcfg.get("max_entropy_grid", [1.10,1.00,0.90,0.80,0.70])]
    regime_modes = [str(x).upper() for x in pcfg.get("regime_modes", ["ALL","NON_SHOCK","TREND_RANGE","TREND","RANGE","TRANSITION","TREND_TRANSITION","RANGE_TRANSITION"])]
    rng = random.Random(int(seed))
    anchors = [
        {"take_threshold": max(base_take, 0.65), "buy_threshold":0.0,"sell_threshold":0.0,"directional_margin":0.0,"max_entropy":1.10,"regime_mode":"ALL"},
        {"take_threshold":0.70,"buy_threshold":0.45,"sell_threshold":0.45,"directional_margin":0.05,"max_entropy":1.00,"regime_mode":"NON_SHOCK"},
        {"take_threshold":0.75,"buy_threshold":0.50,"sell_threshold":0.50,"directional_margin":0.10,"max_entropy":0.90,"regime_mode":"TREND_RANGE"},
        {"take_threshold":0.80,"buy_threshold":0.55,"sell_threshold":0.55,"directional_margin":0.15,"max_entropy":0.80,"regime_mode":"TREND"},
        {"take_threshold":0.65,"buy_threshold":0.45,"sell_threshold":0.45,"directional_margin":0.05,"max_entropy":1.00,"regime_mode":"TRANSITION"},
    ]
    seen=set(); rows=[]
    def add(p):
        p={"schema":POLICY_SCHEMA, **p}
        key=tuple((k,p[k]) for k in ("take_threshold","buy_threshold","sell_threshold","directional_margin","max_entropy","regime_mode"))
        if key not in seen: seen.add(key); rows.append(p)
    for p in anchors: add(p)
    while len(rows) < int(budget):
        add({"take_threshold":rng.choice(take_grid), "buy_threshold":rng.choice(dir_grid), "sell_threshold":rng.choice(dir_grid),
             "directional_margin":rng.choice(margin_grid), "max_entropy":rng.choice(entropy_grid), "regime_mode":rng.choice(regime_modes)})
        if len(seen) >= len(take_grid)*len(dir_grid)*len(dir_grid)*len(margin_grid)*len(entropy_grid)*len(regime_modes): break
    return rows[:int(budget)]


def _aggregate_policy(policy: dict, folds: list[dict], cfg: dict) -> dict:
    trade_rows=[]; extras=[]; classes=[]
    for f in folds:
        p=f["proba"]; vdf=f["df"]; y=f["y"]
        trade=policy_trading_metrics(p,vdf,cfg,policy); trade_rows.append(trade)
        extras.append({"stress":policy_stress_diagnostics(p,vdf,cfg,policy), "temporal":policy_temporal_stability(p,vdf,cfg,policy), "regime":policy_regime_diagnostics(p,vdf,cfg,policy)})
        classes.append(classification_metrics(p,y,sample_weight=(vdf["supervised_weight"].to_numpy(float) if "supervised_weight" in vdf.columns else None)))
    exps=[r["expectancy_r"] for r in trade_rows]; pfs=[r["profit_factor"] for r in trade_rows]; dds=[r["max_drawdown_r"] for r in trade_rows]; recs=[r.get("recovery_factor",0.0) for r in trade_rows]
    def med_trade(key, default=0.0):
        vals=[]
        for r in trade_rows:
            v=r.get(key,default)
            if v is None: continue
            try: vals.append(float(v))
            except Exception: pass
        return float(np.median(vals)) if vals else float(default)
    def med_extra(section,key,default=0.0): return float(np.median([float((e.get(section) or {}).get(key,default)) for e in extras])) if extras else float(default)
    def med_stress(key): return float(np.median([float((((e.get("stress") or {}).get("spread") or {}).get(key) or {}).get("expectancy_r",-999.0)) for e in extras])) if extras else -999.0
    row={
        "policy":dict(policy), "folds":len(folds), "overall_expectancy_r":float(sum(r["total_r"] for r in trade_rows)/max(1,sum(r["trades"] for r in trade_rows))), "median_expectancy_r":float(np.median(exps)), "worst_expectancy_r":float(np.min(exps)), "expectancy_std_r":float(np.std(exps)),
        "median_profit_factor":float(np.median(pfs)), "profit_factor_std":float(np.std(pfs)), "median_max_drawdown_r":float(np.median(dds)), "worst_fold_max_drawdown_r":float(np.max(dds)), "median_recovery_factor":float(np.median(recs)), "worst_fold_recovery_factor":float(np.min(recs)),
        "positive_fold_ratio":float(np.mean(np.asarray(exps)>0.0)), "total_validation_trades":int(sum(r["trades"] for r in trade_rows)), "total_validation_r":float(sum(r["total_r"] for r in trade_rows)),
        "median_win_rate":med_trade("win_rate"), "median_payoff_ratio":med_trade("payoff_ratio"), "median_trade_r":med_trade("median_trade_r"), "median_cvar95_r":med_trade("cvar95_r"), "median_daily_cvar95_r":med_trade("daily_cvar95_r",-999.0),
        "median_fold_trades":med_trade("trades"), "median_active_trade_days":med_trade("active_trade_days"), "median_daily_tail_sample_count":med_trade("daily_tail_sample_count"), "median_sample_years":med_trade("sample_years",0.0),
        "median_downside_deviation_r":med_trade("downside_deviation_r"), "median_sharpe_ratio":med_trade("sharpe_ratio"), "median_sortino_ratio":med_trade("sortino_ratio"), "median_calmar_mar_ratio":med_trade("calmar_mar_ratio"), "median_probabilistic_sharpe_ratio":med_trade("probabilistic_sharpe_ratio",0.5), "median_deflated_sharpe_ratio":med_trade("deflated_sharpe_ratio",0.5), "median_ulcer_index_r":med_trade("ulcer_index_r"), "median_top10_win_profit_share":med_trade("top10_win_profit_share"), "median_max_losing_streak":med_trade("max_losing_streak"), "median_max_underwater_trades":med_trade("max_underwater_trades"),
        "median_positive_month_ratio":med_extra("temporal","positive_month_ratio"), "median_positive_quarter_ratio":med_extra("temporal","positive_quarter_ratio"), "median_regime_concentration":med_extra("regime","dominant_positive_regime_share"),
        "median_stress_x1_25_expectancy_r":med_stress("spread_x1.25"), "median_stress_x1_50_expectancy_r":med_stress("spread_x1.50"),
        "median_threshold_plateau":float(np.median([float((e.get("stress") or {}).get("profitable_threshold_variant_ratio",0.0)) for e in extras])) if extras else 0.0,
        "mean_balanced_accuracy":float(np.mean([c["balanced_accuracy"] for c in classes])), "mean_macro_f1":float(np.mean([c["macro_f1"] for c in classes])),
        "mean_log_loss":float(np.mean([c["log_loss"] for c in classes])), "mean_brier_score":float(np.mean([c["brier_score"] for c in classes])), "mean_expected_calibration_error":float(np.mean([c["expected_calibration_error"] for c in classes])),
    }
    score=walk_forward_composite_score(row,cfg); row["selection_score"]=float(score["score"]); row["score_schema"]=score["schema"]; row["score_breakdown"]=score["components"]; row["score_categories"]=score["categories"]
    row["cv_acceptance"]=walk_forward_acceptance(row,cfg); row["cv_gate_pass"]=bool(row["cv_acceptance"]["passed"]); row["cv_gate_reasons"]=list(row["cv_acceptance"]["reasons"])
    fold_diags=[]
    for i,r in enumerate(trade_rows):
        sp=(extras[i].get("stress") or {}).get("spread") or {}
        fold_diags.append({
            "fold":i+1,
            **{k:r.get(k) for k in ("profit_factor","expectancy_r","max_drawdown_r","recovery_factor","win_rate","payoff_ratio","median_trade_r","cvar95_r","top10_win_profit_share","max_losing_streak","max_underwater_trades","trades","total_r")},
            "positive_month_ratio":extras[i]["temporal"].get("positive_month_ratio",0.0),
            "positive_quarter_ratio":extras[i]["temporal"].get("positive_quarter_ratio",0.0),
            "regime_concentration":extras[i]["regime"].get("dominant_positive_regime_share",0.0),
            "stress_x1_25_expectancy_r":((sp.get("spread_x1.25") or {}).get("expectancy_r",-999.0)),
            "stress_x1_50_expectancy_r":((sp.get("spread_x1.50") or {}).get("expectancy_r",-999.0)),
            "threshold_plateau":extras[i]["stress"].get("profitable_threshold_variant_ratio",0.0),
        })
    row["fold_diagnostics"]=fold_diags
    return row


def discover_policy(spec, pre_df, cfg: dict, base_take: float, progress=None, fold_callback=None):
    pcfg=cfg.get("agent",{}).get("policy_discovery",{})
    budget=int(pcfg.get("max_policies",72)); seed=int(cfg.get("seed",42))+7919
    folds=collect_oof_predictions(spec,pre_df,cfg,fold_callback=fold_callback)
    candidates=_policy_candidates(cfg,seed,base_take,budget)
    board=[]
    for i,p in enumerate(candidates,1):
        row=_aggregate_policy(p,folds,cfg); row["policy_index"]=i; board.append(row); board.sort(key=lambda x:(bool(x.get("cv_gate_pass")),float(x["selection_score"])),reverse=True)
        if progress:
            progress({"stage":"policy_discovery","current":i,"total":len(candidates),"message":f"Policy {i}/{len(candidates)} · score {row['selection_score']:+.2f} · PF {row['median_profit_factor']:.3f} · Exp {row['median_expectancy_r']:+.4f}R", "policy_row":{"Policy #":i,"PASS":"YES" if row["cv_gate_pass"] else "NO","DD R":round(row["median_max_drawdown_r"],2),"Worst DD":round(row.get("worst_fold_max_drawdown_r",999),2),"Recovery":round(row["median_recovery_factor"],2),"Worst RF":round(row.get("worst_fold_recovery_factor",-999),2),"PF":round(row["median_profit_factor"],3),"Exp R":round(row["median_expectancy_r"],4),"Worst R":round(row["worst_expectancy_r"],4),"Positive folds":f"{100*row['positive_fold_ratio']:.0f}%","Trades":row["total_validation_trades"],"Regime":p["regime_mode"],"Take":p["take_threshold"],"BUY":p["buy_threshold"],"SELL":p["sell_threshold"],"Margin":p["directional_margin"],"Entropy":p["max_entropy"],"Score":round(row["selection_score"],2)}})
    winner=next((r for r in board if r["cv_gate_pass"]), board[0] if board else None)
    return {"schema":"POLICY_DISCOVERY_V1","budget":len(candidates),"winner":winner,"board":board,"oof_folds":len(folds)}


def build_policy_locked_test_kpi(proba, y, df, cfg, policy, parity):
    trade=policy_trading_metrics(proba,df,cfg,policy); classification=classification_metrics(proba,y,sample_weight=(df["supervised_weight"].to_numpy(float) if "supervised_weight" in df.columns else None)); stress=policy_stress_diagnostics(proba,df,cfg,policy); temporal=policy_temporal_stability(proba,df,cfg,policy); regime=policy_regime_diagnostics(proba,df,cfg,policy)
    return {"schema":str(cfg.get("acceptance",{}).get("schema","KPI_V5_HIERARCHICAL")),"profile":str(cfg.get("acceptance",{}).get("profile","SURVIVAL_STRICT_V1")),"policy_schema":POLICY_SCHEMA,"policy":dict(policy),"locked_test":trade,"classification":classification,"temporal_stability":temporal,"regime":regime,"confidence_buckets":[],"stress":stress,"onnx_parity":parity}


def write_policy_csv(path: str|Path, policy: dict):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    ordered=[("schema",POLICY_SCHEMA),("take_threshold",policy.get("take_threshold",0.65)),("buy_threshold",policy.get("buy_threshold",0.0)),("sell_threshold",policy.get("sell_threshold",0.0)),("directional_margin",policy.get("directional_margin",0.0)),("max_entropy",policy.get("max_entropy",1.10)),("regime_mode",policy.get("regime_mode","ALL"))]
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f,delimiter=";"); w.writerow(["key","value"]); [w.writerow([k,v]) for k,v in ordered]
    return path
