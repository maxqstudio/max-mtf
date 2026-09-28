from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json

SCHEMA = "CP_RESEARCH_FEEDBACK_V1"
CPCV_TOPOLOGY_SCHEMA = "CP_CPCV_FAILURE_TOPOLOGY_V1"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def failure_group(gate: str | None) -> str:
    g = str(gate or "").upper()
    if any(x in g for x in ("DD", "DRAWDOWN", "RECOVERY", "RUIN", "TAIL")):
        return "survival"
    if any(x in g for x in ("EXPECTANCY", "PF", "PROFIT_FACTOR", "PAYOFF")):
        return "economic"
    if any(x in g for x in ("REGIME", "MONTH", "QUARTER", "PATH", "FOLD", "STABILITY")):
        return "stability"
    if "TRADE" in g or "SAMPLE" in g:
        return "sample"
    return "other"


def _margin(value, threshold, direction: str):
    try:
        v=float(value); t=float(threshold)
    except Exception:
        return None
    if direction == "min":
        return v-t
    return t-v


def cpcv_failure_topology(rows: list[dict], cfg: dict | None = None) -> dict:
    """Aggregate committed finalist evidence without changing CPCV authority.

    The current engine evaluates combinatorial purged test-group *splits*.  Legacy
    evidence may still call them paths; this topology keeps the raw field but reports
    them as split combinations to avoid claiming canonical reconstructed CPCV paths.
    """
    rows=[r for r in (rows or []) if isinstance(r,dict)]
    first=Counter(); all_failed=Counter(); fam=defaultdict(lambda:{"evaluated":0,"pass":0,"fail":0,"first_failed":Counter(),"all_failed":Counter()})
    combo_stats=defaultdict(lambda:{"candidate_count":0,"expectancies":[],"profit_factors":[],"drawdowns":[],"recoveries":[],"negative_expectancy":0})
    canonical_stats=defaultdict(lambda:{"candidate_count":0,"expectancies":[],"profit_factors":[],"drawdowns":[],"recoveries":[],"sharpe":[],"sortino":[]})
    group_stats=defaultdict(lambda:{"candidate_count":0,"median_expectancies":[],"worst_expectancies":[],"negative_evaluations":0,"evaluations":0})
    candidate_rows=[]
    seed_summary={"required_candidates":0,"stable_pass":0,"unstable_fail":0,"planned_seed_counts":Counter(),"failed_seed_counts":Counter()}
    for r in rows:
        passed=bool(r.get("passed")); fg=str(r.get("first_failed_gate") or ("PASS" if passed else "UNKNOWN"))
        reasons=[str(x) for x in (r.get("reasons") or [])]
        family=str(r.get("family") or "UNKNOWN")
        fam[family]["evaluated"]+=1; fam[family]["pass" if passed else "fail"]+=1
        if not passed:
            first[fg]+=1; fam[family]["first_failed"][fg]+=1
            for g in reasons: all_failed[g]+=1; fam[family]["all_failed"][g]+=1
        ev=r.get("evidence") if isinstance(r.get("evidence"),dict) else {}
        paths=ev.get("paths") or []
        worst_combo=None; worst_exp=None
        for p in paths:
            if not isinstance(p,dict): continue
            combo=tuple(p.get("test_groups") or [])
            key="("+",".join(str(x) for x in combo)+")"
            d=combo_stats[key]; d["candidate_count"]+=1
            try:
                e=float(p.get("expectancy_r")); d["expectancies"].append(e); d["negative_expectancy"]+=int(e<0)
                if worst_exp is None or e<worst_exp: worst_exp=e; worst_combo=key
            except Exception: pass
            for src,dst in (("profit_factor","profit_factors"),("max_drawdown_r","drawdowns"),("recovery_factor","recoveries")):
                try: d[dst].append(float(p.get(src)))
                except Exception: pass
        audit=ev.get("methodology_audit") if isinstance(ev.get("methodology_audit"),dict) else {}
        canon=((audit.get("canonical_reconstructed_path_view") or {}).get("paths") or []) if audit else []
        for cp in canon:
            if not isinstance(cp,dict): continue
            key=int(cp.get("canonical_path",0) or 0); d=canonical_stats[key]; d["candidate_count"]+=1
            for src,dst in (("expectancy_r","expectancies"),("profit_factor","profit_factors"),("max_drawdown_r","drawdowns"),("recovery_factor","recoveries"),("sharpe_ratio","sharpe"),("sortino_ratio","sortino")):
                try: d[dst].append(float(cp.get(src)))
                except Exception: pass
        for ga in (audit.get("group_attribution") or []):
            if not isinstance(ga,dict): continue
            key=int(ga.get("group",-1)); d=group_stats[key]; d["candidate_count"]+=1
            try: d["median_expectancies"].append(float(ga.get("median_expectancy_r")))
            except Exception: pass
            try: d["worst_expectancies"].append(float(ga.get("worst_expectancy_r")))
            except Exception: pass
            d["negative_evaluations"]+=int(ga.get("negative_expectancy_evaluations",0) or 0); d["evaluations"]+=int(ga.get("evaluations",0) or 0)
        s=r.get("summary") or {}
        seed_confirmation=deepcopy(r.get("seed_confirmation") or ev.get("seed_confirmation") or {})
        if isinstance(seed_confirmation,dict) and seed_confirmation:
            if bool(seed_confirmation.get("required",False)):
                seed_summary["required_candidates"]+=1
            planned=list(seed_confirmation.get("planned_seeds") or [])
            seed_summary["planned_seed_counts"][len(planned)] += 1
            seed_pass=seed_confirmation.get("passed")
            status_seed=str(seed_confirmation.get("status") or "").upper()
            if seed_pass is True or status_seed in {"PASS","STABLE_PASS"}:
                seed_summary["stable_pass"]+=1
            elif seed_pass is False or status_seed in {"FAIL","FAILED","SEED_UNSTABLE"}:
                seed_summary["unstable_fail"]+=1
            for sr in seed_confirmation.get("seed_results") or []:
                if isinstance(sr,dict) and sr.get("passed") is False:
                    try: seed_summary["failed_seed_counts"][int(sr.get("seed"))]+=1
                    except Exception: pass
        cex=[float(x.get("expectancy_r")) for x in canon if isinstance(x,dict) and x.get("expectancy_r") is not None]
        cdd=[float(x.get("max_drawdown_r")) for x in canon if isinstance(x,dict) and x.get("max_drawdown_r") is not None]
        candidate_rows.append({
            "pool_id":r.get("pool_id"),"rank":r.get("rank"),"family":family,"name":r.get("name"),
            "status":"PASS" if passed else "FAIL","first_failed_gate":None if passed else fg,"failed_gates":reasons,
            "combinations":int(ev.get("combinations",len(paths)) or len(paths)),
            "median_pf":s.get("median_profit_factor"),"median_expectancy_r":s.get("median_expectancy_r"),
            "worst_expectancy_r":s.get("worst_expectancy_r"),"worst_dd_r":s.get("worst_max_drawdown_r"),
            "median_recovery":s.get("median_recovery_factor"),"worst_recovery":s.get("worst_recovery_factor"),
            "positive_split_ratio":s.get("positive_path_ratio"),"worst_split_groups":worst_combo,
            "canonical_worst_expectancy_r":min(cex) if cex else None,"canonical_worst_drawdown_r":max(cdd) if cdd else None,
            "methodology_authority_changed":bool(audit.get("authority_changed",False)),
            "params":deepcopy(r.get("params") or {}),"take_threshold":r.get("take_threshold"),"training_seed":r.get("training_seed"),
            "seed_confirmation":seed_confirmation,
            "hypothesis_id":r.get("hypothesis_id"),"experiment_block_id":r.get("experiment_block_id"),
        })
    def median(xs):
        if not xs: return None
        ys=sorted(xs); n=len(ys); return ys[n//2] if n%2 else (ys[n//2-1]+ys[n//2])/2
    combos=[]
    for key,d in combo_stats.items():
        combos.append({
            "test_groups":key,"candidate_count":d["candidate_count"],"negative_expectancy_candidates":d["negative_expectancy"],
            "median_expectancy_r":median(d["expectancies"]),"median_profit_factor":median(d["profit_factors"]),
            "median_max_drawdown_r":median(d["drawdowns"]),"median_recovery_factor":median(d["recoveries"]),
        })
    combos.sort(key=lambda x:(float(x["median_expectancy_r"]) if x["median_expectancy_r"] is not None else 999.0, -int(x["negative_expectancy_candidates"])))
    fam_out={}
    for k,v in fam.items():
        fam_out[k]={"evaluated":v["evaluated"],"pass":v["pass"],"fail":v["fail"],"first_failed_gate_counts":dict(v["first_failed"]),"all_failed_gate_counts":dict(v["all_failed"])}
    canonical=[]
    for key,d in sorted(canonical_stats.items()):
        canonical.append({"canonical_path":key,"candidate_count":d["candidate_count"],
            "median_expectancy_r":median(d["expectancies"]),"median_profit_factor":median(d["profit_factors"]),
            "median_max_drawdown_r":median(d["drawdowns"]),"median_recovery_factor":median(d["recoveries"]),
            "median_sharpe_ratio":median(d["sharpe"]),"median_sortino_ratio":median(d["sortino"])})
    groups=[]
    for key,d in sorted(group_stats.items()):
        groups.append({"group":key,"candidate_count":d["candidate_count"],"median_of_median_expectancy_r":median(d["median_expectancies"]),
            "median_of_worst_expectancy_r":median(d["worst_expectancies"]),"negative_expectancy_evaluations":d["negative_evaluations"],"evaluations":d["evaluations"]})
    dominant=first.most_common(1)[0][0] if first else None
    return {
        "schema":CPCV_TOPOLOGY_SCHEMA,"authority":"CPCV_COMBINATORIAL_PURGED_SPLIT_DIAGNOSTIC",
        "evaluated":len(rows),"passed":sum(1 for r in rows if bool(r.get("passed"))),"failed":sum(1 for r in rows if not bool(r.get("passed"))),
        "first_failed_gate_counts":dict(first),"all_failed_gate_counts":dict(all_failed),
        "dominant_first_failed_gate":dominant,"dominant_failure_group":failure_group(dominant),
        "by_family":fam_out,"candidate_rows":candidate_rows,"split_combinations":combos,
        "worst_split_combination":combos[0] if combos else None,
        "canonical_reconstructed_paths":canonical,"group_attribution":groups,
        "seed_stability":{
            "required_candidates":int(seed_summary["required_candidates"]),
            "stable_pass":int(seed_summary["stable_pass"]),
            "unstable_fail":int(seed_summary["unstable_fail"]),
            "planned_seed_counts":dict(seed_summary["planned_seed_counts"]),
            "failed_seed_counts":dict(seed_summary["failed_seed_counts"]),
            "authority":"CPCV_FIXED_SEED_CONFIRMATION"
        },
        "methodology_note":"Legacy economic/stress gates remain on purged stress splits; seven Advanced KPI use canonical reconstructed paths as CPCV gate evidence; per-group attribution and fixed-seed confirmation remain forensic/qualification evidence as configured.",
        "created_utc":utcnow(),
    }


def generic_stage_topology(stage: str, rows: list[dict]) -> dict:
    first=Counter(); all_failed=Counter(); out=[]
    for r in rows or []:
        if not isinstance(r,dict): continue
        a=r.get("acceptance") if isinstance(r.get("acceptance"),dict) else {}
        passed=bool(a.get("passed",r.get("passed",False)))
        fg=a.get("first_failed_gate",r.get("first_failed_gate"))
        reasons=list(a.get("reasons",r.get("reasons",[])) or [])
        if not passed:
            first[str(fg or "UNKNOWN")]+=1
            for g in reasons: all_failed[str(g)]+=1
        out.append({"pool_id":r.get("pool_id"),"family":r.get("family"),"name":r.get("name"),"status":"PASS" if passed else "FAIL","first_failed_gate":fg,"failed_gates":reasons})
    dominant=first.most_common(1)[0][0] if first else None
    return {"schema":"CP_STAGE_FAILURE_TOPOLOGY_V1","stage":str(stage).upper(),"evaluated":len(out),"passed":sum(x["status"]=="PASS" for x in out),"failed":sum(x["status"]=="FAIL" for x in out),"first_failed_gate_counts":dict(first),"all_failed_gate_counts":dict(all_failed),"dominant_first_failed_gate":dominant,"dominant_failure_group":failure_group(dominant),"candidate_rows":out,"created_utc":utcnow()}


def dataset_header_context(columns: list[str], *, feature_contract: str, feature_count: int, research_contract_hash: str | None = None) -> dict:
    """The only dataset content exposed to the LLM: header/schema identity, never rows."""
    return {"columns":[str(x) for x in columns],"feature_contract":str(feature_contract),"feature_count":int(feature_count),"research_contract_hash":str(research_contract_hash or "")}


def feedback_memory_item(factory_id: str, stage: str, status: str, topology: dict, scientist_entry: dict | None, exposure: int, contract_hash: str) -> dict:
    s=dict(scientist_entry or {})
    return {
        "schema":SCHEMA,"factory_id":factory_id,"stage":str(stage).upper(),"status":str(status),
        "dataset_scope":"EXACT_RESEARCH_CONTRACT_ONLY","research_contract_hash":contract_hash,"exposure":int(exposure),
        "failure_topology":deepcopy(topology),"scientist_summary":s.get("summary"),"scientist_report":deepcopy(s.get("report") or {}),
        "strategy":deepcopy(s.get("strategy") or {}),"hypotheses":deepcopy(s.get("hypotheses") or []),
        "next_discovery_plan":deepcopy(s.get("next_discovery_plan") or {}),"learning_ready":bool(s.get("learning_ready",False)),
        "created_utc":utcnow(),
    }
