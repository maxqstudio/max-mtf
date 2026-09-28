from __future__ import annotations
import numpy as np
import pandas as pd

from strategy.strategy_geometry import extract_dataset_strategy_geometry, assert_strategy_geometry_matches_dataset


def _first_barrier(highs, lows, tp, sl, long_side=True):
    """Return (R outcome marker, ambiguous). +1 means TP, -1 means SL, None timeout."""
    for h, l in zip(highs, lows):
        if long_side:
            hit_tp = h >= tp; hit_sl = l <= sl
        else:
            hit_tp = l <= tp; hit_sl = h >= sl
        if hit_tp and hit_sl: return None, True
        if hit_tp: return 1, False
        if hit_sl: return -1, False
    return None, False


def _execution_eligibility(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    """Pre-model structural entry eligibility owned by the promoted Strategy Champion.

    EntryThreshold depends on the eventual model directional score and therefore is not
    a pre-training mask. Consensus/spread/shock/quote validity are known at row t and
    can safely prevent impossible BUY/SELL rows from consuming supervised capacity.
    """
    dc=cfg.get("deployment") or {}
    n=len(df); ok=np.ones(n,dtype=bool)
    try: ok &= pd.to_numeric(df["consensus"],errors="coerce").to_numpy(float) >= float(dc["min_consensus"])
    except Exception: ok &= False
    try: ok &= pd.to_numeric(df["spread_points"],errors="coerce").to_numpy(float) <= float(dc["max_spread_points"])
    except Exception: ok &= False
    try: ok &= pd.to_numeric(df["range_atr"],errors="coerce").to_numpy(float) < float(dc["shock_halt_range_atr"])
    except Exception: ok &= False
    try:
        bid=pd.to_numeric(df["decision_bid"],errors="coerce").to_numpy(float)
        ask=pd.to_numeric(df["decision_ask"],errors="coerce").to_numpy(float)
        ok &= np.isfinite(bid)&np.isfinite(ask)&(bid>0)&(ask>0)&(ask>=bid)
    except Exception: ok &= False
    return ok


def build_labels(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Build causal 3-class labels without destroying source chronology.

    v1.3.2 scientific repair:
    * every source row keeps an immutable ``source_row_id``;
    * rows with unavailable/ambiguous future outcome remain causal context but receive
      zero supervised weight instead of being physically removed;
    * structurally non-executable rows remain context and receive zero supervised weight;
    * actionable labels receive a bounded utility weight so training is weakly aligned
      with realized R while the runtime output contract stays [SELL,SKIP,BUY].
    """
    g = extract_dataset_strategy_geometry(df); assert_strategy_geometry_matches_dataset(df, cfg)
    lc = cfg["label"]; h=int(g["max_hold_bars"]); sl_atr=float(g["sl_atr"]); tp_atr=float(g["tp_atr"])
    min_edge=float(lc["min_edge_r"]); min_margin=float(lc["min_margin_r"]); rr=tp_atr/sl_atr
    utility_enabled=bool(lc.get("utility_weight_enabled",True)); utility_scale=max(0.0,float(lc.get("utility_weight_scale",0.50)))
    utility_cap=max(0.0,float(lc.get("utility_weight_cap_r",2.0)))

    out=df.copy()
    if "source_row_id" not in out.columns:
        out["source_row_id"]=np.arange(len(out),dtype=np.int64)
    else:
        out["source_row_id"]=pd.to_numeric(out["source_row_id"],errors="raise").astype(np.int64)
    n=len(out); long_r=np.full(n,np.nan); short_r=np.full(n,np.nan); ambiguous=np.zeros(n,dtype=bool)
    high=out["high"].to_numpy(float); low=out["low"].to_numpy(float); close=out["close"].to_numpy(float)
    atr=out["atr"].to_numpy(float); bid=out["decision_bid"].to_numpy(float); ask=out["decision_ask"].to_numpy(float)

    for i in range(0,max(0,n-h)):
        if (not np.isfinite(atr[i]) or atr[i]<=0 or not np.isfinite(bid[i]) or not np.isfinite(ask[i]) or bid[i]<=0 or ask[i]<=0 or ask[i]<bid[i]):
            continue
        stop_dist=sl_atr*atr[i]; take_dist=tp_atr*atr[i]; spread=ask[i]-bid[i]
        hs=high[i+1:i+1+h]; ls=low[i+1:i+1+h]
        mark,amb=_first_barrier(hs,ls,ask[i]+take_dist,ask[i]-stop_dist,True)
        if amb: ambiguous[i]=True
        elif mark==1: long_r[i]=rr
        elif mark==-1: long_r[i]=-1.0
        else: long_r[i]=np.clip((close[i+h]-ask[i])/stop_dist,-1.0,rr)
        ask_h=hs+spread; ask_l=ls+spread
        mark,amb=_first_barrier(ask_h,ask_l,bid[i]-take_dist,bid[i]+stop_dist,False)
        if amb: ambiguous[i]=True
        elif mark==1: short_r[i]=rr
        elif mark==-1: short_r[i]=-1.0
        else:
            timeout_ask=close[i+h]+spread
            short_r[i]=np.clip((bid[i]-timeout_ask)/stop_dist,-1.0,rr)

    out["long_r"]=long_r; out["short_r"]=short_r; out["ambiguous_barrier"]=ambiguous
    valid=np.isfinite(long_r)&np.isfinite(short_r)
    if lc.get("ambiguous_policy","drop")=="drop": valid &= ~ambiguous
    executable=_execution_eligibility(out,cfg)

    labels=np.ones(n,dtype=np.int64)  # context-only rows use SKIP placeholder with weight 0
    utility=np.zeros(n,dtype=np.float64)
    for i in np.flatnonzero(valid):
        lr,sr=float(long_r[i]),float(short_r[i]); best=max(lr,sr); margin=abs(lr-sr)
        if best < min_edge or margin < min_margin:
            labels[i]=1
        else:
            labels[i]=2 if lr>sr else 0
        if executable[i]:
            w=1.0
            if utility_enabled and labels[i] in (0,2):
                strength=max(0.0,best-min_edge)+0.5*max(0.0,margin-min_margin)
                w += utility_scale*min(utility_cap,strength)
            utility[i]=float(w)

    out["label"]=labels
    out["label_valid"]=valid
    out["execution_eligible"]=executable
    out["supervised_weight"]=utility
    out["label_utility_weight"]=utility
    out["label_context_only"]=(utility<=0.0)
    return out.reset_index(drop=True)
