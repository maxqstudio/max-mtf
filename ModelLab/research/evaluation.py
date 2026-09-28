from __future__ import annotations
import math
from copy import deepcopy
from statistics import NormalDist

import numpy as np

from strategy.strategy_geometry import resolved_strategy_sl_atr
import pandas as pd
from research.risk_kpi import dsr_trial_count, psr_benchmark
from sklearn.metrics import balanced_accuracy_score, f1_score, log_loss


def normalize_proba(proba: np.ndarray) -> np.ndarray:
    p = np.asarray(proba, dtype=np.float64)
    p = np.clip(p, 1e-12, None)
    den = p.sum(axis=1, keepdims=True)
    if np.any(~np.isfinite(den)) or np.any(den <= 0):
        raise ValueError("Invalid probability rows")
    return p / den


def decision_fields(proba: np.ndarray, df, cfg: dict) -> dict:
    dc=cfg["deployment"]; p=normalize_proba(proba)
    sell=p[:,0]; skip=p[:,1]; buy=p[:,2]; directional=buy-sell; take=1.0-skip
    rule=df["rule_meta_score"].to_numpy(float); consensus=df["consensus"].to_numpy(float)
    final=(1.0-float(dc["onnx_blend"]))*rule+float(dc["onnx_blend"])*directional
    return {"proba":p,"sell":sell,"skip":skip,"buy":buy,"directional":directional,"take":take,
            "rule":rule,"consensus":consensus,"final":np.clip(final,-1.0,1.0)}


def deployment_actions(proba: np.ndarray, df, cfg: dict, take_threshold: float) -> np.ndarray:
    dc=cfg["deployment"]; f=decision_fields(proba,df,cfg); final=f["final"]
    gate=(
        (f["take"]>=take_threshold)
        & (f["consensus"]>=float(dc["min_consensus"]))
        & (np.abs(final)>=float(dc["entry_threshold"]))
        & (df["spread_points"].to_numpy(float)<=float(dc["max_spread_points"]))
        & (df["range_atr"].to_numpy(float)<float(dc["shock_halt_range_atr"]))
    )
    action=np.zeros(len(df),dtype=np.int8); action[gate&(final>0)]=1; action[gate&(final<0)]=-1
    return action


def _execution_required_columns(df) -> bool:
    required={"high","low","atr","decision_bid","decision_ask","signal_time"}
    return hasattr(df,"columns") and required.issubset(set(df.columns))


def simulate_execution_from_actions(actions: np.ndarray, final_score: np.ndarray, df, cfg: dict) -> tuple[np.ndarray,np.ndarray,dict]:
    """Replay the EA single-position state machine on bar data.

    Position lifecycle matches Max.mq5 ordering at each decision bar: existing SL/TP
    exposure during the bar, then MaxHold, then REVERSE_EXIT at decision time, then a
    possible new entry if flat. Entries are suppressed unless the contiguous evaluation
    chunk contains the full MaxHold horizon, preventing CPCV/test-block boundary trades
    from being force-closed on missing context.
    """
    actions=np.asarray(actions,dtype=np.int8); final_score=np.asarray(final_score,dtype=float)
    if len(actions)!=len(df) or len(final_score)!=len(df): raise ValueError("execution simulation length mismatch")
    if not _execution_required_columns(df):
        # Compatibility only for old synthetic/minimal tests. Production CP32 always
        # uses the event-driven branch above and below.
        lr=df["long_r"].to_numpy(float); sr=df["short_r"].to_numpy(float)
        return actions.copy(),np.where(actions>0,lr,np.where(actions<0,sr,0.0)),{"schema":"LEGACY_STATELESS_COMPAT","production_parity":False}
    from strategy.strategy_geometry import resolved_strategy_horizon_bars,resolved_strategy_sl_atr,config_strategy_geometry
    g=config_strategy_geometry(cfg) or {}; h=max(1,int(resolved_strategy_horizon_bars(cfg))); sl_atr=float(resolved_strategy_sl_atr(cfg)); tp_atr=float(g.get("tp_atr",0.0))
    if sl_atr<=0 or tp_atr<=0: raise ValueError("STATEFUL_SIMULATOR_MISSING_STRATEGY_GEOMETRY")
    reverse=float((cfg.get("deployment") or {}).get("exit_reverse_threshold",0.0))
    src=(df["source_row_id"].to_numpy(np.int64) if "source_row_id" in df.columns else np.arange(len(df),dtype=np.int64))
    high=df["high"].to_numpy(float); low=df["low"].to_numpy(float); atr=df["atr"].to_numpy(float)
    bid=df["decision_bid"].to_numpy(float); ask=df["decision_ask"].to_numpy(float)
    n=len(df); remaining=np.zeros(n,dtype=np.int64)
    if n:
        remaining[-1]=0
        for i in range(n-2,-1,-1): remaining[i]=(remaining[i+1]+1) if int(src[i+1])==int(src[i])+1 else 0
    accepted=np.zeros(n,dtype=np.int8); realized=np.zeros(n,dtype=np.float64)
    pos=None; exit_counts={"TP":0,"SL":0,"TIME_EXIT":0,"REVERSE_EXIT":0,"AMBIGUOUS_WORST_CASE_SL":0}
    for i in range(n):
        # A position opened at prior close is exposed to current bar high/low first.
        if pos is not None:
            direction=pos["direction"]; spread=max(0.0,float(ask[i]-bid[i])); reason=None; rr=None
            if direction>0:
                hit_tp=bool(high[i]>=pos["tp"]); hit_sl=bool(low[i]<=pos["sl"])
            else:
                ah=float(high[i]+spread); al=float(low[i]+spread)
                hit_tp=bool(al<=pos["tp"]); hit_sl=bool(ah>=pos["sl"])
            if hit_tp and hit_sl:
                reason="AMBIGUOUS_WORST_CASE_SL"; rr=-1.0
            elif hit_sl:
                reason="SL"; rr=-1.0
            elif hit_tp:
                reason="TP"; rr=float(tp_atr/sl_atr)
            else:
                held=int(src[i]-pos["source_row_id"])
                if held>=h:
                    reason="TIME_EXIT"
                elif direction>0 and float(final_score[i])<=-reverse:
                    reason="REVERSE_EXIT"
                elif direction<0 and float(final_score[i])>=reverse:
                    reason="REVERSE_EXIT"
                if reason is not None:
                    exit_price=float(bid[i] if direction>0 else ask[i])
                    rr=((exit_price-pos["entry_price"])/pos["stop_dist"]) if direction>0 else ((pos["entry_price"]-exit_price)/pos["stop_dist"])
            if reason is not None:
                realized[int(pos["entry_idx"])]=float(rr); exit_counts[reason]=exit_counts.get(reason,0)+1; pos=None
        # EA may open again at the same decision after ManagePosition closes.
        if pos is None and int(actions[i])!=0 and int(remaining[i])>=h:
            if not (np.isfinite(atr[i]) and atr[i]>0 and np.isfinite(bid[i]) and np.isfinite(ask[i]) and ask[i]>=bid[i]>0):
                continue
            direction=int(actions[i]); stop_dist=float(sl_atr*atr[i]); entry=float(ask[i] if direction>0 else bid[i])
            if direction>0: sl=entry-stop_dist; tp=entry+tp_atr*atr[i]
            else: sl=entry+stop_dist; tp=entry-tp_atr*atr[i]
            pos={"direction":direction,"entry_idx":i,"source_row_id":int(src[i]),"entry_price":entry,"stop_dist":stop_dist,"sl":sl,"tp":tp}
            accepted[i]=direction
    if pos is not None:
        raise RuntimeError("STATEFUL_SIMULATOR_UNCLOSED_POSITION: entry-horizon guard failed")
    return accepted,realized,{"schema":"MAX_STATEFUL_EXECUTION_SIM_V1","production_parity":True,"single_position":True,"reverse_exit_threshold":reverse,"max_hold_bars":h,"exit_counts":exit_counts}


def trade_outcomes(proba: np.ndarray, df, cfg: dict, take_threshold: float) -> tuple[np.ndarray,np.ndarray]:
    f=decision_fields(proba,df,cfg); desired=deployment_actions(proba,df,cfg,take_threshold)
    act,r,_=simulate_execution_from_actions(desired,f["final"],df,cfg)
    return act,r

def _max_losing_streak(trades: np.ndarray) -> int:
    best = cur = 0
    for x in trades:
        if x < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def _max_underwater_duration(curve: np.ndarray) -> int:
    if len(curve) == 0:
        return 0
    peak = np.maximum.accumulate(curve)
    underwater = curve < peak
    best = cur = 0
    for flag in underwater:
        if bool(flag):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def _safe_sharpe_stats(trades: np.ndarray) -> tuple[float, float, float]:
    """Return non-annualized per-trade Sharpe, skewness and non-excess kurtosis."""
    x=np.asarray(trades,dtype=np.float64)
    x=x[np.isfinite(x)]
    n=len(x)
    if n < 2:
        return 0.0,0.0,3.0
    mean=float(np.mean(x)); sd=float(np.std(x,ddof=1))
    sharpe=(mean/sd) if sd>1e-12 else (999.0 if mean>0 else (0.0 if abs(mean)<=1e-12 else -999.0))
    centered=x-mean; pop_sd=float(np.std(x,ddof=0))
    if pop_sd<=1e-12:
        return float(sharpe),0.0,3.0
    skew=float(np.mean(centered**3)/(pop_sd**3))
    kurt=float(np.mean(centered**4)/(pop_sd**4))
    return float(sharpe),skew,kurt


def _probabilistic_sharpe(sharpe: float, n: int, skew: float, kurtosis: float, benchmark: float=0.0) -> float:
    """Bailey/Lopez-de-Prado PSR approximation using non-excess kurtosis."""
    if n < 2 or not all(np.isfinite(v) for v in (sharpe,skew,kurtosis,benchmark)):
        return 0.5
    den2=1.0-float(skew)*float(sharpe)+((float(kurtosis)-1.0)/4.0)*(float(sharpe)**2)
    den=math.sqrt(max(1e-12,den2))
    z=(float(sharpe)-float(benchmark))*math.sqrt(max(1,n-1))/den
    return float(max(0.0,min(1.0,NormalDist().cdf(z))))


def _deflated_sharpe(sharpe: float, n: int, skew: float, kurtosis: float, trials: int) -> tuple[float,float]:
    """Return DSR probability and the multiple-testing Sharpe benchmark used."""
    trials=max(1,int(trials or 1))
    if n < 2 or trials <= 1:
        return _probabilistic_sharpe(sharpe,n,skew,kurtosis,0.0),0.0
    den2=1.0-float(skew)*float(sharpe)+((float(kurtosis)-1.0)/4.0)*(float(sharpe)**2)
    sr_std=math.sqrt(max(1e-12,den2)/max(1,n-1))
    gamma=0.5772156649015329
    nd=NormalDist()
    p1=max(1e-12,min(1-1e-12,1.0-1.0/trials))
    p2=max(1e-12,min(1-1e-12,1.0-1.0/(trials*math.e)))
    expected_max=sr_std*((1.0-gamma)*nd.inv_cdf(p1)+gamma*nd.inv_cdf(p2))
    return _probabilistic_sharpe(sharpe,n,skew,kurtosis,expected_max),float(expected_max)


def metrics_from_trades(trades: np.ndarray, n_rows: int = 0, take_threshold: float | None = None,
                        timestamps=None, multiple_testing_trials: int = 1, benchmark_sharpe: float = 0.0,
                        evaluation_start=None, evaluation_end=None) -> dict:
    trades = np.asarray(trades, dtype=np.float64)
    finite=np.isfinite(trades); trades=trades[finite]
    if timestamps is not None:
        try:
            ts_all=pd.to_datetime(np.asarray(timestamps)[finite],errors="coerce")
        except Exception:
            ts_all=None
    else:
        ts_all=None
    n = int(len(trades))
    wins = trades[trades > 0]
    losses = trades[trades < 0]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    pf = gp / gl if gl > 0 else (999.0 if gp > 0 else 0.0)
    expectancy = float(trades.mean()) if n else 0.0
    win_rate = float((trades > 0).mean()) if n else 0.0
    curve = np.cumsum(trades) if n else np.array([], dtype=float)
    if n:
        peak = np.maximum.accumulate(np.r_[0.0, curve])[1:]
        drawdown=peak-curve
        max_dd = float(np.max(drawdown))
        ulcer_r=float(np.sqrt(np.mean(np.square(drawdown))))
    else:
        max_dd = 0.0; ulcer_r=0.0
    total_r = float(trades.sum()) if n else 0.0
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    payoff = avg_win / abs(avg_loss) if avg_loss < 0 else (999.0 if avg_win > 0 else 0.0)
    recovery = total_r / max_dd if max_dd > 1e-12 else (999.0 if total_r > 0 else 0.0)
    tail_n = max(1, int(math.ceil(n * 0.05))) if n else 0
    cvar95 = float(np.mean(np.sort(trades)[:tail_n])) if tail_n else 0.0
    daily_cvar95 = None
    daily_obs = 0
    daily_tail_n = 0
    if ts_all is not None and n:
        try:
            _tmp=pd.DataFrame({"ts":pd.to_datetime(ts_all,errors="coerce"),"r":trades})
            _tmp=_tmp.dropna(subset=["ts"])
            if not _tmp.empty:
                daily=_tmp.groupby(_tmp["ts"].dt.normalize(),sort=True)["r"].sum().to_numpy(float)
                daily_obs=int(len(daily))
                if daily_obs:
                    dn=max(1,int(math.ceil(daily_obs*0.05)))
                    daily_tail_n=int(dn)
                    daily_cvar95=float(np.mean(np.sort(daily)[:dn]))
        except Exception:
            daily_cvar95=None; daily_obs=0
    downside_all=np.minimum(trades,0.0) if n else np.array([],dtype=float)
    downside_dev = float(np.sqrt(np.mean(np.square(downside_all)))) if len(downside_all) else 0.0
    sortino=(expectancy/downside_dev) if downside_dev>1e-12 else (999.0 if expectancy>0 else 0.0)
    sharpe,skew,kurt=_safe_sharpe_stats(trades)
    psr=_probabilistic_sharpe(sharpe,n,skew,kurt,float(benchmark_sharpe))
    dsr,dsr_benchmark=_deflated_sharpe(sharpe,n,skew,kurt,int(multiple_testing_trials or 1))
    years=None; annualized_r=None; calmar=None
    try:
        if evaluation_start is not None and evaluation_end is not None:
            start=pd.to_datetime(evaluation_start,errors="coerce")
            end=pd.to_datetime(evaluation_end,errors="coerce")
            if pd.notna(start) and pd.notna(end) and end >= start:
                span_days=max((end-start).total_seconds()/86400.0,1.0/24.0)
                years=span_days/365.2425
        if years is None and ts_all is not None:
            valid=pd.DatetimeIndex(ts_all).dropna()
            if len(valid)>=2:
                span_days=max((valid.max()-valid.min()).total_seconds()/86400.0,1.0/24.0)
                years=span_days/365.2425
        if years is not None:
            annualized_r=total_r/max(years,1e-9)
            calmar=(annualized_r/max_dd) if max_dd>1e-12 else (999.0 if annualized_r>0 else 0.0)
    except Exception:
        pass
    median_trade = float(np.median(trades)) if n else 0.0
    positive_profit = float(wins.sum()) if len(wins) else 0.0
    if len(wins) and positive_profit > 0:
        k = max(1, int(math.ceil(len(wins) * 0.10)))
        top10_share = float(np.sort(wins)[-k:].sum() / positive_profit)
    else:
        top10_share = 0.0
    out = {
        "trades": n,
        "trade_rate": float(n / max(1, int(n_rows))) if n_rows else 0.0,
        "total_r": total_r,
        "expectancy_r": expectancy,
        "profit_factor": float(pf),
        "win_rate": win_rate,
        "max_drawdown_r": max_dd,
        "recovery_factor": float(recovery),
        "avg_win_r": avg_win,
        "avg_loss_r": avg_loss,
        "payoff_ratio": float(payoff),
        "median_trade_r": median_trade,
        "max_losing_streak": _max_losing_streak(trades),
        "max_underwater_trades": _max_underwater_duration(curve),
        "cvar95_r": cvar95,
        "expected_shortfall_95_r": cvar95,
        "daily_cvar95_r": daily_cvar95,
        "daily_expected_shortfall_95_r": daily_cvar95,
        "daily_tail_observations": daily_obs,
        "active_trade_days": daily_obs,
        "daily_tail_sample_count": daily_tail_n,
        "downside_deviation_r": downside_dev,
        "sharpe_ratio": float(sharpe),
        "sortino_ratio": float(sortino),
        "calmar_mar_ratio": None if calmar is None else float(calmar),
        "annualized_r": None if annualized_r is None else float(annualized_r),
        "sample_years": None if years is None else float(years),
        "probabilistic_sharpe_ratio": float(psr),
        "deflated_sharpe_ratio": float(dsr),
        "dsr_benchmark_sharpe": float(dsr_benchmark),
        "dsr_trial_count": int(max(1,int(multiple_testing_trials or 1))),
        "ulcer_index_r": float(ulcer_r),
        "return_skewness": float(skew),
        "return_kurtosis": float(kurt),
        "risk_metric_basis": "PER_TRADE_R_NON_ANNUALIZED; CALMAR=LINEAR_ANNUALIZED_R/MAX_DD_R; CVAR_GATE=DAILY_AGGREGATED_R_ES95",
        "top10_win_profit_share": top10_share,
    }
    if take_threshold is not None:
        out["take_threshold"] = float(take_threshold)
    return out


def trading_metrics(proba: np.ndarray, df, cfg: dict, take_threshold: float) -> dict:
    act, r = trade_outcomes(proba, df, cfg, take_threshold)
    mask=act != 0
    trades = r[mask]
    trials=dsr_trial_count(cfg)
    bench=psr_benchmark(cfg)
    timestamps=df.iloc[np.flatnonzero(mask)]["signal_time"].to_numpy() if hasattr(df,"columns") and "signal_time" in df.columns else None
    evaluation_start=evaluation_end=None
    if hasattr(df,"columns") and "signal_time" in df.columns and len(df):
        try:
            _all_ts=pd.to_datetime(df["signal_time"],errors="coerce").dropna()
            if len(_all_ts):
                evaluation_start=_all_ts.min(); evaluation_end=_all_ts.max()
        except Exception:
            pass
    return metrics_from_trades(trades, n_rows=len(df), take_threshold=take_threshold, timestamps=timestamps,
                               multiple_testing_trials=trials, benchmark_sharpe=bench,
                               evaluation_start=evaluation_start, evaluation_end=evaluation_end)


def classification_metrics(proba: np.ndarray, y: np.ndarray, calibration_bins: int = 10, sample_weight=None) -> dict:
    """Classification diagnostics on supervised targets only.

    Context-only rows (ambiguous, unavailable horizon, or structurally non-executable)
    carry zero supervised weight and must not dilute model-quality diagnostics. Utility
    weights are also respected so the diagnostics describe the same supervised objective
    used during fitting.
    """
    proba = normalize_proba(proba)
    y = np.asarray(y, dtype=np.int64)
    if len(y) != len(proba):
        raise ValueError("classification metric length mismatch")
    w = np.ones(len(y), dtype=np.float64) if sample_weight is None else np.asarray(sample_weight, dtype=np.float64)
    if len(w) != len(y):
        raise ValueError("classification sample_weight length mismatch")
    keep = np.isfinite(w) & (w > 0) & np.isfinite(proba).all(axis=1)
    if not np.any(keep):
        return {
            "balanced_accuracy": 0.0, "macro_f1": 0.0, "log_loss": float(np.log(3.0)),
            "brier_score": 2.0/3.0, "expected_calibration_error": 1.0,
            "supervised_rows": 0, "supervised_weight_sum": 0.0,
            "evidence_status": "INSUFFICIENT_EVIDENCE",
        }
    proba = proba[keep]; y = y[keep]; w = w[keep]
    pred = np.argmax(proba, axis=1)
    onehot = np.eye(3, dtype=np.float64)[y]
    row_brier=np.sum((proba-onehot)**2,axis=1)
    brier=float(np.average(row_brier,weights=w))
    conf=np.max(proba,axis=1); correct=(pred==y).astype(float)
    ece=0.0; total_w=float(np.sum(w))
    edges=np.linspace(0.0,1.0,int(max(2,calibration_bins))+1)
    for lo,hi in zip(edges[:-1],edges[1:]):
        mask=(conf>=lo)&(conf<=hi if hi>=1.0 else conf<hi)
        if not np.any(mask): continue
        bw=float(np.sum(w[mask]));
        if bw<=0: continue
        acc=float(np.average(correct[mask],weights=w[mask])); c=float(np.average(conf[mask],weights=w[mask]))
        ece += (bw/total_w)*abs(acc-c)
    return {
        "balanced_accuracy": float(balanced_accuracy_score(y,pred,sample_weight=w)),
        "macro_f1": float(f1_score(y,pred,average="macro",sample_weight=w,zero_division=0)),
        "log_loss": float(log_loss(y,proba,labels=[0,1,2],sample_weight=w)),
        "brier_score": brier, "expected_calibration_error": float(ece),
        "supervised_rows": int(len(y)), "supervised_weight_sum": total_w,
        "evidence_status": "OK",
    }


def confidence_bucket_diagnostics(proba: np.ndarray, df, cfg: dict, take_threshold: float) -> list[dict]:
    p = normalize_proba(proba)
    confidence = np.max(p, axis=1)
    act, r = trade_outcomes(p, df, cfg, take_threshold)
    rows = []
    for lo, hi in [(0.0, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 0.85), (0.85, 1.000001)]:
        mask = (confidence >= lo) & (confidence < hi) & (act != 0)
        m = metrics_from_trades(r[mask], n_rows=int(np.sum((confidence >= lo) & (confidence < hi))))
        rows.append({"confidence_min": lo, "confidence_max": min(1.0, hi), **m})
    return rows


def temporal_stability(proba: np.ndarray, df, cfg: dict, take_threshold: float) -> dict:
    act, r = trade_outcomes(proba, df, cfg, take_threshold)
    mask = act != 0
    if not np.any(mask):
        return {
            "active_months": 0, "positive_month_ratio": 0.0, "median_month_r": 0.0,
            "worst_month_r": 0.0, "longest_negative_month_streak": 0,
            "active_quarters": 0, "positive_quarter_ratio": 0.0, "median_quarter_r": 0.0,
            "worst_quarter_r": 0.0,
        }
    ts = pd.to_datetime(df.loc[mask, "signal_time"], errors="coerce")
    vals = pd.Series(r[mask], index=ts)
    vals = vals[~vals.index.isna()]
    monthly = vals.groupby(vals.index.to_period("M")).sum().sort_index()
    quarterly = vals.groupby(vals.index.to_period("Q")).sum().sort_index()
    neg_best = neg_cur = 0
    for v in monthly.to_numpy(float):
        if v < 0:
            neg_cur += 1
            neg_best = max(neg_best, neg_cur)
        else:
            neg_cur = 0
    return {
        "active_months": int(len(monthly)),
        "positive_month_ratio": float((monthly > 0).mean()) if len(monthly) else 0.0,
        "median_month_r": float(monthly.median()) if len(monthly) else 0.0,
        "worst_month_r": float(monthly.min()) if len(monthly) else 0.0,
        "longest_negative_month_streak": int(neg_best),
        "active_quarters": int(len(quarterly)),
        "positive_quarter_ratio": float((quarterly > 0).mean()) if len(quarterly) else 0.0,
        "median_quarter_r": float(quarterly.median()) if len(quarterly) else 0.0,
        "worst_quarter_r": float(quarterly.min()) if len(quarterly) else 0.0,
    }


def regime_diagnostics(proba: np.ndarray, df, cfg: dict, take_threshold: float) -> dict:
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
    act, r = trade_outcomes(proba, df, cfg, take_threshold)
    out = {}
    positive_totals = []
    for name in ("TREND", "RANGE", "SHOCK", "TRANSITION"):
        mask = (regime == name) & (act != 0)
        m = metrics_from_trades(r[mask], n_rows=int(np.sum(regime == name)))
        out[name] = m
        if m["total_r"] > 0:
            positive_totals.append(m["total_r"])
    total_positive = float(sum(positive_totals))
    out["dominant_positive_regime_share"] = (
        float(max(positive_totals) / total_positive) if positive_totals and total_positive > 0 else 0.0
    )
    out["definition"] = {
        "TREND": f"adx_scaled >= {trend_min}",
        "RANGE": f"adx_scaled <= {range_max}",
        "SHOCK": f"range_atr >= {shock_min} (priority)",
        "TRANSITION": "otherwise",
    }
    return out


def _spread_stressed_df(df, cfg: dict, multiplier: float):
    """Return a stress copy whose executable quotes reflect the wider spread.

    v1.3.2 stateful execution no longer consumes precomputed long_r/short_r as the
    trading authority, so spread stress must modify the decision quote itself. Bid is
    held fixed and ask is widened by the requested multiplier, matching a conservative
    executable-cost stress. Legacy R columns are adjusted too for compatibility-only
    diagnostics, but the state machine is authoritative.
    """
    stressed = df.copy()
    m = max(1.0, float(multiplier))
    bid = stressed["decision_bid"].to_numpy(float)
    ask = stressed["decision_ask"].to_numpy(float)
    base_spread = np.maximum(0.0, ask - bid)
    stressed["decision_ask"] = bid + base_spread * m
    stressed["spread_points"] = stressed["spread_points"].astype(float) * m
    sl_atr = float(resolved_strategy_sl_atr(cfg))
    if not np.isfinite(sl_atr) or sl_atr <= 0:
        raise ValueError("STRATEGY_GEOMETRY_NOT_RESOLVED_FOR_STRESS")
    stop_dist = sl_atr * stressed["atr"].to_numpy(float)
    extra_cost_r = np.divide(
        base_spread * max(0.0, m - 1.0),
        stop_dist,
        out=np.zeros(len(stressed), dtype=float),
        where=stop_dist > 0,
    )
    if "long_r" in stressed.columns:
        stressed["long_r"] = stressed["long_r"].to_numpy(float) - extra_cost_r
    if "short_r" in stressed.columns:
        stressed["short_r"] = stressed["short_r"].to_numpy(float) - extra_cost_r
    return stressed


def stress_diagnostics(proba: np.ndarray, df, cfg: dict, take_threshold: float) -> dict:
    acfg = cfg.get("acceptance", {})
    multipliers = [float(x) for x in acfg.get("stress_spread_multipliers", [1.25, 1.50])]
    spread = {}
    for mult in multipliers:
        sdf = _spread_stressed_df(df, cfg, mult)
        spread[f"spread_x{mult:.2f}"] = trading_metrics(proba, sdf, cfg, take_threshold)

    delta = float(acfg.get("sensitivity_take_delta", 0.03))
    thresholds = sorted(set(round(min(0.99, max(0.01, take_threshold + d)), 6) for d in (-delta, 0.0, delta)))
    threshold_rows = []
    profitable = 0
    for t in thresholds:
        m = trading_metrics(proba, df, cfg, t)
        threshold_rows.append({"take_threshold": t, **m})
        if m["expectancy_r"] > 0.0 and m["profit_factor"] >= 1.0:
            profitable += 1
    ratio = float(profitable / max(1, len(threshold_rows)))
    return {
        "spread": spread,
        "take_threshold_sensitivity": threshold_rows,
        "profitable_threshold_variant_ratio": ratio,
    }


def robust_score(m: dict) -> float:
    # Ranking score only. Acceptance is handled by explicit multi-gate KPI policy.
    pf_component = min(max(m["profit_factor"], 0.0), 3.0) - 1.0
    recovery_component = min(max(m.get("recovery_factor", 0.0), 0.0), 8.0)
    return (
        2.0 * m["expectancy_r"]
        + 0.20 * pf_component
        + 0.03 * recovery_component
        + 0.002 * math.sqrt(max(0, m["trades"])) * m["total_r"]
        - 0.02 * m["max_drawdown_r"]
    )
