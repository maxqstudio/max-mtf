from __future__ import annotations

"""Deterministic CPCV/CSCV-style Probability of Backtest Overfitting support.

PBO needs a cross-strategy matrix; it is not a single-candidate statistic.  MAX builds
that matrix from the same six CPCV chronological groups for every evaluated finalist.
Each cell is the median OOS expectancy for one candidate/group across the canonical
CPCV split/seed evidence in which that group was held out.
"""

from itertools import combinations
import math
import numpy as np

SCHEMA = "MAX_CPCV_PBO_V1"


def group_expectancy_from_seed_rows(seed_rows: list[dict], groups: int = 6) -> dict[str, float]:
    by_group={i:[] for i in range(int(groups))}
    for seed_row in seed_rows or []:
        ev=(seed_row or {}).get("evidence") or {}
        for path in ev.get("paths") or []:
            for gm in (path or {}).get("test_group_metrics") or []:
                try:
                    g=int(gm.get("group")); x=float(gm.get("expectancy_r"))
                except Exception:
                    continue
                if g in by_group and math.isfinite(x):
                    by_group[g].append(x)
    out={}
    for g,vals in by_group.items():
        if vals:
            out[str(g)]=float(np.median(np.asarray(vals,dtype=float)))
    return out


def _average_rank_ascending(values: np.ndarray, selected_index: int) -> float:
    """1=worst, N=best, deterministic average rank for ties."""
    v=float(values[int(selected_index)])
    lower=float(np.sum(values < v)); equal=float(np.sum(values == v))
    return 1.0 + lower + max(0.0,equal-1.0)/2.0


def compute_cpcv_pbo(rows: list[dict], *, groups: int = 6, min_candidates: int = 4) -> dict:
    candidates=[]
    for row in rows or []:
        ev=(row or {}).get("evidence") or {}
        gmap=ev.get("pbo_group_expectancy_r") if isinstance(ev.get("pbo_group_expectancy_r"),dict) else {}
        try:
            vec=np.asarray([float(gmap[str(g)]) for g in range(int(groups))],dtype=float)
        except Exception:
            continue
        if not np.isfinite(vec).all():
            continue
        candidates.append({"pool_id":row.get("pool_id"),"name":row.get("name"),"values":vec})
    n=len(candidates)
    if int(groups)%2!=0 or int(groups)<4:
        return {"schema":SCHEMA,"status":"NOT_COMPUTABLE_INVALID_GROUP_COUNT","candidate_count":n,"groups":int(groups),"pbo":None}
    if n < int(min_candidates):
        return {"schema":SCHEMA,"status":"NOT_COMPUTABLE_INSUFFICIENT_CANDIDATES","candidate_count":n,"minimum_candidates":int(min_candidates),"groups":int(groups),"pbo":None}
    matrix=np.vstack([c["values"] for c in candidates])
    half=int(groups)//2; parts=[]
    all_groups=tuple(range(int(groups)))
    for is_groups in combinations(all_groups,half):
        oos_groups=tuple(g for g in all_groups if g not in is_groups)
        # complementary halves are the same CSCV partition; retain one orientation.
        if tuple(is_groups) > tuple(oos_groups):
            continue
        is_perf=np.mean(matrix[:,list(is_groups)],axis=1)
        oos_perf=np.mean(matrix[:,list(oos_groups)],axis=1)
        winner=int(np.argmax(is_perf))
        rank=_average_rank_ascending(oos_perf,winner)
        # Mid-rank percentile stays strictly inside (0,1), avoiding infinite logits.
        omega=(rank-0.5)/float(n)
        omega=max(1e-12,min(1.0-1e-12,float(omega)))
        logit=float(math.log(omega/(1.0-omega)))
        parts.append({
            "is_groups":list(is_groups),"oos_groups":list(oos_groups),
            "selected_pool_id":candidates[winner]["pool_id"],"selected_name":candidates[winner]["name"],
            "is_expectancy_r":float(is_perf[winner]),"oos_expectancy_r":float(oos_perf[winner]),
            "oos_rank":float(rank),"candidate_count":n,"relative_oos_rank":omega,"logit":logit,
            "overfit":bool(logit<=0.0),
        })
    if not parts:
        return {"schema":SCHEMA,"status":"NOT_COMPUTABLE_NO_PARTITIONS","candidate_count":n,"groups":int(groups),"pbo":None}
    pbo=float(np.mean([1.0 if p["overfit"] else 0.0 for p in parts]))
    return {
        "schema":SCHEMA,"status":"COMPUTED","candidate_count":n,"groups":int(groups),
        "partition_count":len(parts),"performance_metric":"MEDIAN_OOS_EXPECTANCY_R_PER_CPCV_GROUP",
        "pbo":pbo,"partitions":parts,
        "candidate_ids":[c["pool_id"] for c in candidates],
    }
