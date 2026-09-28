from __future__ import annotations

from itertools import combinations
from typing import Callable

import numpy as np
import pandas as pd

from research.evaluation import trading_metrics, metrics_from_trades, trade_outcomes
from models.model_lab import feature_matrix, apply_fold_training_memory, _fit_with_heartbeat
from models.models import CandidateSpec, make_model, predict_model_proba, fit_model_indexed, model_training_diagnostics
from core.temporal_index import contiguous_chunks, describe_indices, contract_from_cfg
from research.sample_policy import auto_trade_sample
from research.risk_kpi import canonical_gate_rows, dsr_trial_count, psr_benchmark
from research.gate_kpi import gate_profile, risk_cfg_for_gate
from research.policy_discovery import policy_actions, policy_trading_metrics, policy_trade_outcomes
from strategy.strategy_geometry import resolved_strategy_horizon_bars

ProgressCallback = Callable[[dict], None]


def _groups(n: int, n_groups: int) -> list[np.ndarray]:
    if n_groups < 3:
        raise ValueError("CPCV membutuhkan minimal 3 groups")
    if n < n_groups * 50:
        raise ValueError("Dataset terlalu kecil untuk CPCV groups")
    return [np.asarray(x, dtype=int) for x in np.array_split(np.arange(n, dtype=int), n_groups) if len(x)]


def cpcv_splits(n: int, n_groups: int = 6, test_groups: int = 2, purge_bars: int = 24,
                embargo_bars: int = 24, max_combinations: int | None = None) -> list[tuple[np.ndarray, np.ndarray, tuple[int, ...]]]:
    """Combinatorial Purged CV over contiguous chronological groups.

    Test groups are combinations of chronological blocks. Training is the complement,
    with a purge before each test block and an embargo after it. In v0.7.3 this is the
    finalist-only robustness stage after the frozen WFA Pool. The 15 N=6,k=2 objects
    are combinatorial purged splits, not claimed as canonical reconstructed CPCV paths.
    """
    groups = _groups(int(n), int(n_groups))
    if not (1 <= int(test_groups) < len(groups)):
        raise ValueError("CPCV test_groups invalid")
    combos = list(combinations(range(len(groups)), int(test_groups)))
    if max_combinations is not None and int(max_combinations) > 0:
        combos = combos[: int(max_combinations)]
    out = []
    all_idx = np.arange(n, dtype=int)
    for combo in combos:
        test = np.unique(np.concatenate([groups[i] for i in combo]))
        keep = np.ones(n, dtype=bool)
        keep[test] = False
        for i in combo:
            g = groups[i]
            lo = max(0, int(g[0]) - int(purge_bars))
            hi = min(n, int(g[-1]) + 1 + int(embargo_bars))
            keep[lo:hi] = False
        train = all_idx[keep]
        if len(train) < 200 or len(test) < 50:
            continue
        out.append((train, test, combo))
    if not out:
        raise ValueError("CPCV tidak dapat membuat legal purged/embargo splits")
    return out



def canonical_cpcv_pairings(n_groups: int, test_groups: int = 2) -> list[list[tuple[int,int]]]:
    """Deterministic 1-factorization used to reconstruct canonical CPCV paths for k=2.

    For even N and k=2, every one of the C(N,2) split pairs is assigned exactly once
    across N-1 reconstructed paths; each path covers every chronological group exactly
    once. Existing CPCV economic/stress gates remain on the 15 purged stress splits;
    the seven Advanced risk/research KPI use these reconstructed paths as their
    CPCV hard-gate evidence. Canonical DD/recovery do not replace legacy split gates.
    """
    n_groups=int(n_groups); test_groups=int(test_groups)
    if test_groups != 2 or n_groups < 4 or n_groups % 2:
        return []
    fixed=n_groups-1
    rotating=list(range(n_groups-1))
    rounds=[]
    for _ in range(n_groups-1):
        lineup=[fixed]+rotating
        pairs=[]
        for i in range(n_groups//2):
            a,b=lineup[i],lineup[-1-i]
            pairs.append(tuple(sorted((int(a),int(b)))))
        rounds.append(sorted(pairs))
        rotating=[rotating[-1]]+rotating[:-1]
    # Defensive integrity check: every edge once and every path covers every group.
    flat=[p for r in rounds for p in r]
    expected=set(combinations(range(n_groups),2))
    if set(flat)!=expected or len(flat)!=len(expected):
        raise RuntimeError("Canonical CPCV pairing reconstruction integrity failure")
    for r in rounds:
        covered=[g for pair in r for g in pair]
        if sorted(covered)!=list(range(n_groups)):
            raise RuntimeError("Canonical CPCV path does not cover each group exactly once")
    return rounds


def _aggregate_group_attribution(group_rows: dict[int,list[dict]]) -> list[dict]:
    out=[]
    for group in sorted(group_rows):
        rows=[x for x in group_rows[group] if isinstance(x,dict)]
        def vals(key):
            z=[]
            for x in rows:
                try: z.append(float(x.get(key)))
                except Exception: pass
            return z
        ex=vals("expectancy_r"); pf=vals("profit_factor"); dd=vals("max_drawdown_r"); rec=vals("recovery_factor"); tr=vals("trades")
        out.append({
            "group":int(group),"evaluations":len(rows),
            "median_expectancy_r":float(np.median(ex)) if ex else None,
            "worst_expectancy_r":float(np.min(ex)) if ex else None,
            "negative_expectancy_evaluations":int(sum(v<0 for v in ex)),
            "median_profit_factor":float(np.median(pf)) if pf else None,
            "median_max_drawdown_r":float(np.median(dd)) if dd else None,
            "median_recovery_factor":float(np.median(rec)) if rec else None,
            "median_trades":float(np.median(tr)) if tr else None,
        })
    return out

def _contiguous_chunks(idx: np.ndarray) -> list[np.ndarray]:
    """Backward-compatible alias; chronology authority lives in temporal_index."""
    return contiguous_chunks(idx)


def cpcv_worst_expectancy_pass(value: float, cfg: dict) -> bool:
    """CPCV profile zero-floor with epsilon used only for floating-point noise."""
    a=gate_profile(cfg,"cpcv")
    threshold=float(a.get("cpcv_min_worst_expectancy_r",0.0))
    eps=max(0.0,float(a.get("worst_expectancy_epsilon",1e-9)))
    return float(value) >= (threshold-eps)


def candidate_cpcv(spec: CandidateSpec, df: pd.DataFrame, cfg: dict, take_threshold: float,
                   progress: ProgressCallback | None = None, decision_policy: dict | None = None) -> dict:
    """Run bounded CPCV qualification using the already-selected WFA threshold.

    CPCV does not tune the threshold. It only asks whether the frozen Discovery
    candidate remains robust across combinatorial purged/embargo partitions.
    """
    c = (cfg.get("split") or {})
    n_groups = int(c.get("cpcv_groups", 6))
    test_groups = int(c.get("cpcv_test_groups", 2))
    purge = int(c.get("purge_bars", 24))
    embargo = int(c.get("embargo_bars", purge))
    max_combos = int(c.get("cpcv_max_combinations", 15))
    horizon=int(resolved_strategy_horizon_bars(cfg))
    if (n_groups,test_groups,max_combos)!=(6,2,15):
        raise RuntimeError(f"CPCV_METHODOLOGY_CONTRACT: expected groups=6,test_groups=2,max_combinations=15; got {n_groups},{test_groups},{max_combos}")
    if purge < horizon or embargo < horizon:
        raise RuntimeError(f"CPCV_TEMPORAL_LEAKAGE_GUARD: purge={purge}, embargo={embargo}, horizon={horizon}")
    splits = cpcv_splits(len(df), n_groups, test_groups, purge, embargo, max_combos)
    if len(splits) != 15:
        raise RuntimeError(f"CPCV_METHODOLOGY_CONTRACT: expected exactly 15 legal purged splits, got {len(splits)}")
    X = feature_matrix(df, cfg)
    y=df["label"].to_numpy(np.int64)
    supervised_weight=df["supervised_weight"].to_numpy(np.float64) if "supervised_weight" in df.columns else np.ones(len(df),dtype=np.float64)
    paths = []
    group_arrays=_groups(len(df),n_groups)
    group_rows={i:[] for i in range(n_groups)}
    group_trade_ledger={}
    dsr_trials=dsr_trial_count(cfg)
    psr_benchmark_value=psr_benchmark(cfg)
    for path_no, (tr, va, combo) in enumerate(splits, 1):
        fit_tr, mem = apply_fold_training_memory(df, tr, spec, cfg)
        if progress:
            progress({"stage":"cpcv","current":path_no-1,"total":len(splits),"split_no":path_no,"split_total":len(splits),"test_groups":list(combo),"phase":"fit_start",
                      "message":f"CPCV {spec.name} · split {path_no}/{len(splits)} · groups {combo}"})
        model = make_model(spec, cfg)
        def hb(elapsed):
            if progress:
                progress({"stage":"cpcv","current":path_no-1,"total":len(splits),"split_no":path_no,"split_total":len(splits),"test_groups":list(combo),"phase":"fit_heartbeat","elapsed_sec":float(elapsed),
                          "message":f"CPCV {spec.name} · split {path_no}/{len(splits)} · training {elapsed:.0f}s"})
        model, elapsed = _fit_with_heartbeat(
            model, spec.family, X, y, heartbeat=hb, interval_sec=2.0,
            fit_fn=lambda: fit_model_indexed(model,spec.family,X,y,fit_tr,cfg,sample_weight=supervised_weight),
        )
        if progress:
            progress({"stage":"cpcv","current":path_no-1,"total":len(splits),"split_no":path_no,"split_total":len(splits),"test_groups":list(combo),"phase":"prediction",
                      "message":f"CPCV {spec.name} · split {path_no}/{len(splits)} · fit selesai, prediction"})
        pred_parts=[]; va_parts=[]
        chunks=_contiguous_chunks(va)
        for chunk_no, chunk in enumerate(chunks,1):
            if progress:
                progress({"stage":"cpcv","current":path_no-1,"total":len(splits),"split_no":path_no,"split_total":len(splits),"test_groups":list(combo),"phase":"predict_chunk",
                          "message":f"CPCV {spec.name} · split {path_no}/{len(splits)} · predict chunk {chunk_no}/{len(chunks)}"})
            pred = np.asarray(predict_model_proba(model, spec.family, X[:int(chunk[0])], X[chunk]), float)
            pred_parts.append(pred); va_parts.append(chunk)
        order = np.argsort(np.concatenate(va_parts))
        p = np.concatenate(pred_parts, axis=0)[order]
        vidx = np.concatenate(va_parts)[order]
        vdf = df.iloc[vidx]
        m = policy_trading_metrics(p,vdf,cfg,decision_policy) if decision_policy else trading_metrics(p, vdf, cfg, float(take_threshold))
        per_group=[]
        pair=tuple(sorted(int(x) for x in combo))
        for group_no in pair:
            mask=np.isin(vidx,group_arrays[group_no])
            gp=p[mask]; gdf=vdf.iloc[np.flatnonzero(mask)]
            gm=policy_trading_metrics(gp,gdf,cfg,decision_policy) if decision_policy else trading_metrics(gp,gdf,cfg,float(take_threshold))
            gm={**gm,"group":int(group_no),"source_split":path_no,"source_test_groups":list(pair),"validation_rows":int(len(gdf))}
            per_group.append(gm); group_rows[group_no].append(gm)
            if decision_policy:
                ga,gr=policy_trade_outcomes(gp,gdf,cfg,decision_policy)
            else:
                ga,gr=trade_outcomes(gp,gdf,cfg,float(take_threshold))
            take=(ga!=0)
            gts=gdf.loc[take,"signal_time"].to_numpy() if "signal_time" in gdf.columns else None
            group_trade_ledger[(pair,int(group_no))]={"trades":np.asarray(gr[take],float),"timestamps":gts}
        m.update({"path":path_no,"split":path_no,"test_groups":list(combo),"train_rows":int(len(fit_tr)),
                  "validation_rows":int(len(vidx)),"fit_seconds":float(elapsed),"training_memory":mem,
                  "train_topology":describe_indices(fit_tr),"validation_topology":describe_indices(vidx),
                  "model_training_diagnostics":model_training_diagnostics(model),
                  "test_group_metrics":per_group,"metric_semantics":"STRESS_SPLIT_CONCATENATED_TEST_GROUPS"})
        paths.append(m)
        if progress:
            progress({"stage":"cpcv","current":path_no,"total":len(splits),"split_completed":path_no,"split_no":path_no,"split_total":len(splits),"test_groups":list(combo),"phase":"split_done",
                      "profit_factor":float(m.get("profit_factor",0)),"expectancy_r":float(m.get("expectancy_r",0)),"max_drawdown_r":float(m.get("max_drawdown_r",0)),"recovery_factor":float(m.get("recovery_factor",0)),"trades":int(m.get("trades",0)),
                      "message":f"CPCV {spec.name} · split {path_no}/{len(splits)} · PF {m['profit_factor']:.3f} · Exp {m['expectancy_r']:+.4f}R · trades {m['trades']}"})

    reconstructed=[]
    pairings=canonical_cpcv_pairings(n_groups,test_groups)
    for canonical_no,matching in enumerate(pairings,1):
        trade_parts=[]; ts_parts=[]; sources=[]
        for group_no in range(n_groups):
            pair=next((q for q in matching if group_no in q),None)
            item=group_trade_ledger.get((pair,group_no)) if pair is not None else None
            if item is None:
                trade_parts=[]; break
            trade_parts.append(np.asarray(item.get("trades"),float))
            if item.get("timestamps") is not None: ts_parts.append(np.asarray(item.get("timestamps")))
            sources.append({"group":int(group_no),"test_groups":list(pair)})
        if not trade_parts:
            continue
        all_trades=np.concatenate(trade_parts) if trade_parts else np.asarray([],float)
        all_ts=np.concatenate(ts_parts) if ts_parts and len(ts_parts)==len(trade_parts) else None
        evaluation_start=evaluation_end=None
        if hasattr(df,"columns") and "signal_time" in df.columns and len(df):
            _eval_ts=pd.to_datetime(df["signal_time"],errors="coerce").dropna()
            if len(_eval_ts): evaluation_start=_eval_ts.min(); evaluation_end=_eval_ts.max()
        cm=metrics_from_trades(all_trades,n_rows=len(df),take_threshold=float(take_threshold),timestamps=all_ts,
                               multiple_testing_trials=dsr_trials,benchmark_sharpe=psr_benchmark_value,
                               evaluation_start=evaluation_start,evaluation_end=evaluation_end)
        cm.update({"canonical_path":canonical_no,"source_split_pairs":[list(x) for x in matching],"group_sources":sources,
                   "metric_semantics":"CANONICAL_RECONSTRUCTED_CHRONOLOGICAL_GROUP_PATH"})
        reconstructed.append(cm)

    a = gate_profile(cfg,"cpcv")
    exps=np.asarray([float(x.get("expectancy_r",-999)) for x in paths],float)
    pfs=np.asarray([float(x.get("profit_factor",0)) for x in paths],float)
    dds=np.asarray([float(x.get("max_drawdown_r",999999)) for x in paths],float)
    rec=np.asarray([float(x.get("recovery_factor",-999)) for x in paths],float)
    trades=np.asarray([int(x.get("trades",0)) for x in paths],int)
    sharpes=np.asarray([float(x.get("sharpe_ratio",0.0) or 0.0) for x in paths],float)
    sortinos=np.asarray([float(x.get("sortino_ratio",0.0) or 0.0) for x in paths],float)
    psrs=np.asarray([float(x.get("probabilistic_sharpe_ratio",0.5) or 0.5) for x in paths],float)
    dsrs=np.asarray([float(x.get("deflated_sharpe_ratio",0.5) or 0.5) for x in paths],float)
    ulcers=np.asarray([float(x.get("ulcer_index_r",0.0) or 0.0) for x in paths],float)
    cvars=np.asarray([float(x.get("cvar95_r",0.0) or 0.0) for x in paths],float)
    daily_cvars=[float(x.get("daily_cvar95_r")) for x in paths if x.get("daily_cvar95_r") is not None]
    calmars=[float(x.get("calmar_mar_ratio")) for x in paths if x.get("calmar_mar_ratio") is not None]
    start=pd.to_datetime(df["signal_time"],errors="coerce").min(); end=pd.to_datetime(df["signal_time"],errors="coerce").max()
    observed=float(test_groups/max(1,n_groups))
    sample=auto_trade_sample(int(df["period"].iloc[0]),start,end,cfg,"CPCV",observed_fraction=observed)
    # v0.7.6: CPCV owns an independent KPI profile; formulas remain deterministic.
    gates={
        "CPCV_MEDIAN_PF": float(np.median(pfs)) >= float(a.get("cv_min_median_profit_factor",1.25)),
        "CPCV_MEDIAN_EXPECTANCY": float(np.median(exps)) >= float(a.get("cv_min_median_expectancy_r",0.10)),
        "CPCV_WORST_EXPECTANCY": cpcv_worst_expectancy_pass(float(np.min(exps)),cfg),
        "CPCV_WORST_DD": float(np.max(dds)) <= float(a.get("cv_max_worst_fold_drawdown_r",18.0)),
        "CPCV_MEDIAN_RECOVERY": float(np.median(rec)) >= float(a.get("cv_min_median_recovery_factor",1.5)),
        "CPCV_WORST_RECOVERY": float(np.min(rec)) >= float(a.get("cv_min_worst_fold_recovery_factor",1.0)),
        "CPCV_POSITIVE_PATH_RATIO": float(np.mean(exps>0.0)) >= float(a.get("cv_min_positive_fold_ratio",0.66)),
        "CPCV_PATH_SAMPLE_RATIO": float(np.mean(trades>=int(sample["minimum_trades"]))) >= float(a.get("cpcv_min_path_sample_ratio",0.66)),
    }
    canonical_risk_gates, canonical_risk_summary = canonical_gate_rows(reconstructed,risk_cfg_for_gate(cfg,"cpcv"),prefix="CPCV_CANONICAL")
    for row in canonical_risk_gates:
        gates[row["name"]]=bool(row["passed"])
    gate_rows=[
        {"name":"CPCV_MEDIAN_PF","actual":float(np.median(pfs)),"threshold":float(a.get("cv_min_median_profit_factor",1.25)),"passed":gates["CPCV_MEDIAN_PF"]},
        {"name":"CPCV_MEDIAN_EXPECTANCY","actual":float(np.median(exps)),"threshold":float(a.get("cv_min_median_expectancy_r",0.10)),"passed":gates["CPCV_MEDIAN_EXPECTANCY"]},
        {"name":"CPCV_WORST_EXPECTANCY","actual":float(np.min(exps)),"threshold":float(a.get("cpcv_min_worst_expectancy_r",0.0)),"passed":gates["CPCV_WORST_EXPECTANCY"]},
        {"name":"CPCV_WORST_DD","actual":float(np.max(dds)),"threshold":float(a.get("cv_max_worst_fold_drawdown_r",18.0)),"passed":gates["CPCV_WORST_DD"]},
        {"name":"CPCV_MEDIAN_RECOVERY","actual":float(np.median(rec)),"threshold":float(a.get("cv_min_median_recovery_factor",1.5)),"passed":gates["CPCV_MEDIAN_RECOVERY"]},
        {"name":"CPCV_WORST_RECOVERY","actual":float(np.min(rec)),"threshold":float(a.get("cv_min_worst_fold_recovery_factor",1.0)),"passed":gates["CPCV_WORST_RECOVERY"]},
        {"name":"CPCV_POSITIVE_PATH_RATIO","actual":float(np.mean(exps>0.0)),"threshold":float(a.get("cv_min_positive_fold_ratio",0.66)),"passed":gates["CPCV_POSITIVE_PATH_RATIO"]},
        {"name":"CPCV_PATH_SAMPLE_RATIO","actual":float(np.mean(trades>=int(sample["minimum_trades"]))),"threshold":float(a.get("cpcv_min_path_sample_ratio",0.66)),"passed":gates["CPCV_PATH_SAMPLE_RATIO"]},
    ] + list(canonical_risk_gates)
    failed=[k for k,v in gates.items() if not v]
    return {
        "schema":"CP_CPCV_V3_DUAL_REPORT","temporal_index_contract":contract_from_cfg(cfg).__dict__,"passed":not failed,"first_failed_gate":failed[0] if failed else None,
        "reasons":failed,"gates":gates,"gate_rows":gate_rows,"profile":str(a.get("profile_version","CPCV_KPI_V1")),"groups":n_groups,"test_groups":test_groups,"purge_bars":purge,
        "embargo_bars":embargo,"combinations":len(paths),"take_threshold":float(take_threshold),
        "policy_schema":("CP_POLICY_V1" if decision_policy else None),"decision_policy":dict(decision_policy) if decision_policy else None,
        "auto_trade_sample_per_path":sample,
        "summary":{"median_profit_factor":float(np.median(pfs)),"median_expectancy_r":float(np.median(exps)),
                   "worst_expectancy_r":float(np.min(exps)),"worst_max_drawdown_r":float(np.max(dds)),
                   "median_recovery_factor":float(np.median(rec)),"worst_recovery_factor":float(np.min(rec)),
                   "positive_path_ratio":float(np.mean(exps>0.0)),"median_trades":float(np.median(trades)),
                   "median_sharpe_ratio":float(np.median(sharpes)),"median_sortino_ratio":float(np.median(sortinos)),
                   "median_calmar_mar_ratio":float(np.median(calmars)) if calmars else None,
                   "median_probabilistic_sharpe_ratio":float(np.median(psrs)),"median_deflated_sharpe_ratio":float(np.median(dsrs)),
                   "median_ulcer_index_r":float(np.median(ulcers)),"median_cvar95_r":float(np.median(cvars)),
                   "median_daily_cvar95_r":float(np.median(daily_cvars)) if daily_cvars else None,
                   "canonical_risk_kpi_summary":canonical_risk_summary,
                   "worst_expectancy_threshold_r":float(a.get("cpcv_min_worst_expectancy_r",0.0)),
                   "worst_expectancy_epsilon":float(a.get("worst_expectancy_epsilon",1e-9)),
                   "pbo":{"enabled":bool(a.get("pbo_enabled",False)),"status":str(a.get("pbo_status","NOT_COMPUTABLE")),"threshold_max":float(a.get("pbo_max",0.20)),"value":None}},
        "paths":paths, "terminology":"COMBINATORIAL_PURGED_SPLITS",
        "methodology_audit":{
            "schema":"CP_CPCV_METHODOLOGY_AUDIT_V1","authority_changed":True,
            "pass_fail_authority":"CURRENT_STRESS_SPLIT_GATES_PLUS_CANONICAL_RISK_KPI_GATES",
            "warning":"Existing economic/stress gates remain on 15 purged stress splits. Owner-approved Advanced risk KPI gates use canonical reconstructed chronological paths; canonical DD/recovery do not silently replace legacy stress-split DD/recovery gates.",
            "current_stress_split_view":{"count":len(paths),"terminology":"COMBINATORIAL_PURGED_SPLITS","path_dependent_metrics_are_stress_split_metrics":True},
            "canonical_reconstructed_path_view":{"supported":bool(reconstructed),"count":len(reconstructed),"paths":reconstructed,
                "terminology":"CANONICAL_RECONSTRUCTED_PATHS","chronology_safe":True if reconstructed else None,
                "risk_kpi_summary":canonical_risk_summary,"risk_kpi_gates":canonical_risk_gates},
            "group_attribution":_aggregate_group_attribution(group_rows),
        },
    }
