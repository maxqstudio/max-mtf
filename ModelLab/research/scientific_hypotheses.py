from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.contract import FEATURES
from models.model_registry import get_bounds, effective_bounds, enabled_families

KINDS = {
    "LABEL_GEOMETRY",
    "FEATURE_ABLATION",
    "TRAINING_MEMORY",
    "SELECTIVITY_POLICY",
    "REGIME_POLICY",
    "MODEL_ARCHITECTURE",
    "HYBRID_ABLATION",
    "SEED_STABILITY",
    "OBJECTIVE_RESEARCH",
}


def _f(v, lo, hi):
    return max(lo, min(hi, float(v)))


def _i(v, lo, hi):
    return max(lo, min(hi, int(round(float(v)))))


def validate_hypothesis(raw: Any, cfg: dict, serial: int = 1) -> dict | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip().upper()
    if kind not in KINDS:
        return None
    title = str(raw.get("title") or f"hypothesis_{serial}")[:120]
    rationale = str(raw.get("rationale") or "")[:900]
    expected = str(raw.get("expected_observation") or "")[:700]
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    clean = {}
    stage = "NEXT_GENERATION_GUIDED"
    executable = True

    try:
        if kind == "LABEL_GEOMETRY":
            base = cfg.get("label", {})
            # Execution geometry (horizon/SL/TP) is frozen upstream by Strategy Optimizer.
            # Scientist may research only label-separation thresholds.
            for key, lo, hi, conv in (
                ("min_edge_r", 0.0, 0.6, _f),
                ("min_margin_r", 0.0, 0.4, _f),
            ):
                if key in payload:
                    clean[key] = conv(payload[key], lo, hi)
            if not clean:
                return None
        elif kind == "FEATURE_ABLATION":
            zs = [str(x) for x in (payload.get("zero_features") or []) if str(x) in FEATURES]
            zs = list(dict.fromkeys(zs))[:8]
            if not zs:
                return None
            clean["zero_features"] = zs
        elif kind == "TRAINING_MEMORY":
            months = payload.get("months") or payload.get("preferred_months") or []
            if not isinstance(months, list): months = [months]
            vals = sorted(set(_i(x, 6, 72) for x in months))[:8]
            if not vals: return None
            clean["months"] = vals
            stage = "CURRENT_OR_NEXT_MODEL_SEARCH"
        elif kind == "SELECTIVITY_POLICY":
            vals = payload.get("take_thresholds") or []
            if not isinstance(vals, list): vals = [vals]
            vals = sorted(set(round(_f(x, 0.40, 0.95), 4) for x in vals))[:12]
            if not vals: return None
            clean["take_thresholds"] = vals
            stage = "OOF_POLICY_DISCOVERY"
        elif kind == "REGIME_POLICY":
            allowed = set(cfg.get("agent", {}).get("policy_discovery", {}).get("regime_modes", [])) | {
                "ALL","NON_SHOCK","TREND_RANGE","TREND","RANGE","TRANSITION","TREND_TRANSITION","RANGE_TRANSITION"
            }
            vals = [str(x).upper() for x in (payload.get("regime_modes") or [])]
            vals = [x for x in vals if x in allowed]
            vals = list(dict.fromkeys(vals))[:8]
            if not vals: return None
            clean["regime_modes"] = vals
            stage = "OOF_POLICY_DISCOVERY"
        elif kind == "MODEL_ARCHITECTURE":
            # R5: an architecture hypothesis must compile to an actual bounded search,
            # not merely say "stronger regularization" in prose.  The Scientist may
            # declare legal variable keys and tighter per-family ranges.
            fams = payload.get("family_priorities") if isinstance(payload.get("family_priorities"), dict) else {}
            bounds = {f:effective_bounds(cfg,f) for f in get_bounds()}
            clean["family_priorities"] = {str(k): _f(v, 0.35, 3.0) for k,v in fams.items() if str(k) in bounds}
            raw_vars = payload.get("variable_keys_by_family") if isinstance(payload.get("variable_keys_by_family"), dict) else {}
            raw_ranges = payload.get("parameter_ranges_by_family") if isinstance(payload.get("parameter_ranges_by_family"), dict) else {}
            vars_by_family = {}
            ranges_by_family = {}
            for fam, keys in raw_vars.items():
                fam=str(fam)
                if fam not in bounds: continue
                if isinstance(keys,str): keys=[keys]
                if not isinstance(keys,list): continue
                legal=[]
                for key in keys:
                    key=str(key)
                    if key in bounds[fam] and key != "training_memory_months" and key not in legal: legal.append(key)
                if legal: vars_by_family[fam]=legal[:12]
            for fam, ranges in raw_ranges.items():
                fam=str(fam)
                if fam not in bounds or not isinstance(ranges,dict): continue
                clean_ranges={}
                for key, pair in ranges.items():
                    key=str(key)
                    if key not in bounds[fam] or key == "training_memory_months": continue
                    if not isinstance(pair,(list,tuple)) or len(pair)!=2: continue
                    blo,bhi,btyp=bounds[fam][key]
                    try:
                        lo=_i(pair[0],blo,bhi) if btyp is int else _f(pair[0],blo,bhi)
                        hi=_i(pair[1],blo,bhi) if btyp is int else _f(pair[1],blo,bhi)
                    except Exception:
                        continue
                    if lo>hi: lo,hi=hi,lo
                    clean_ranges[key]=[lo,hi]
                if clean_ranges:
                    ranges_by_family[fam]=clean_ranges
                    existing=vars_by_family.setdefault(fam,[])
                    for key in clean_ranges:
                        if key not in existing and len(existing)<12: existing.append(key)
            if vars_by_family: clean["variable_keys_by_family"] = vars_by_family
            if ranges_by_family: clean["parameter_ranges_by_family"] = ranges_by_family
            stage = "CURRENT_OR_NEXT_MODEL_SEARCH"
            if not clean["family_priorities"] and not vars_by_family and not ranges_by_family: return None
        elif kind == "HYBRID_ABLATION":
            # R5: dynamic temporal->policy hybrids are executable.  An ablation names
            # concrete hybrid families; the compiler derives their single temporal
            # controls and tests both under the same downstream decision contract.
            from models.model_registry import family_spec, hybrid_parts
            fams=[]; pairs=[]
            for raw_f in (payload.get("families") or []):
                fam=str(raw_f).strip().lower()
                parts=hybrid_parts(fam)
                if not parts or family_spec(fam) is None:
                    continue
                temporal,_policy=parts
                if family_spec(temporal) is None:
                    continue
                if fam not in fams:
                    fams.append(fam); pairs.append({"single":temporal,"hybrid":fam})
                if len(fams)>=8: break
            if not fams: return None
            clean["families"] = fams
            clean["pairs"] = pairs
            stage = "CURRENT_OR_NEXT_MODEL_SEARCH"
        elif kind == "SEED_STABILITY":
            bounds={f:effective_bounds(cfg,f) for f in get_bounds()}; fams=[]
            for raw_f in (payload.get("families") or []):
                fam=str(raw_f).strip().lower()
                if fam in bounds and fam not in fams:
                    fams.append(fam)
                if len(fams)>=8: break
            if not fams: return None
            clean["families"]=fams
            actions=[]
            allowed_actions={"SHRINK_CAPACITY","INCREASE_REGULARIZATION","LOWER_LR","INCREASE_DROPOUT","REDUCE_ROUTER_COMPLEXITY"}
            for a in (payload.get("actions") or []):
                aa=str(a).strip().upper()
                if aa in allowed_actions and aa not in actions: actions.append(aa)
            clean["actions"]=actions or ["SHRINK_CAPACITY","INCREASE_REGULARIZATION"]
            raw_ranges=payload.get("parameter_ranges_by_family") if isinstance(payload.get("parameter_ranges_by_family"),dict) else {}
            ranges_by_family={}
            for fam,ranges in raw_ranges.items():
                fam=str(fam).strip().lower()
                if fam not in fams or not isinstance(ranges,dict): continue
                row={}
                for key,pair in ranges.items():
                    if key not in bounds.get(fam,{}) or not isinstance(pair,(list,tuple)) or len(pair)!=2: continue
                    blo,bhi,btyp=bounds[fam][key]
                    try:
                        lo=_i(pair[0],blo,bhi) if btyp is int else _f(pair[0],blo,bhi)
                        hi=_i(pair[1],blo,bhi) if btyp is int else _f(pair[1],blo,bhi)
                    except Exception: continue
                    if lo>hi: lo,hi=hi,lo
                    row[str(key)]=[lo,hi]
                if row: ranges_by_family[fam]=row
            if ranges_by_family: clean["parameter_ranges_by_family"]=ranges_by_family
            stage="CURRENT_OR_NEXT_MODEL_SEARCH"
        elif kind == "OBJECTIVE_RESEARCH":
            # Scientist may formulate ideas beyond the currently executable engine. They are retained as research backlog,
            # never silently ignored or auto-executed.
            clean = deepcopy(payload)
            executable = False
            stage = "SCIENTIST_BACKLOG_REQUIRES_IMPLEMENTATION"
    except Exception:
        return None

    return {
        "kind": kind,
        "title": title,
        "rationale": rationale,
        "expected_observation": expected,
        "payload": clean,
        "execution_stage": stage,
        "executable": executable,
    }



def strict_scientist_hypothesis_admission(raw: Any, cfg: dict, serial: int = 1) -> tuple[dict | None, dict]:
    """Fail-closed admission for executable LLM Scientist hypotheses.

    ``validate_hypothesis`` remains the deterministic compiler used by internal policy
    machinery.  This wrapper prevents an LLM's executable scientific intent from being
    silently clamped, intersected, filtered, or re-labelled before execution.
    """
    requested=deepcopy(raw) if isinstance(raw,dict) else raw
    payload=deepcopy(raw.get("payload") or {}) if isinstance(raw,dict) and isinstance(raw.get("payload"),dict) else {}
    kind=str(raw.get("kind") or "").strip().upper() if isinstance(raw,dict) else ""
    evidence={
        "schema":"MAX_SCIENTIST_HYPOTHESIS_ADMISSION_V1",
        "kind":kind,
        "requested_payload":deepcopy(payload),
        "executable_payload":None,
        "admission_status":"REJECTED",
        "rejection_reason":None,
        "exact_hypothesis":False,
        "scientific_attribution":"LLM_HYPOTHESIS_REJECTED",
        "transformation":None,
    }
    def reject(reason: str):
        evidence["rejection_reason"]=reason
        return None,evidence
    def finite_num(v):
        try:
            x=float(v)
            from math import isfinite
            return x if isfinite(x) else None
        except Exception:
            return None
    def bounded(v,lo,hi,*,integer=False):
        x=finite_num(v)
        if x is None: return False
        if integer and abs(x-round(x))>1e-12: return False
        return float(lo)<=x<=float(hi)
    if not isinstance(raw,dict) or kind not in KINDS:
        return reject("INVALID_HYPOTHESIS_SCHEMA_OR_KIND")

    def reject_cardinality(field: str, count: int, limit: int):
        return reject(
            f"HYPOTHESIS_CARDINALITY_EXCEEDS_EXECUTABLE_CONTRACT:{field}:requested={int(count)}:max={int(limit)}"
        )

    # The legacy deterministic compiler intentionally caps several list/search
    # dimensions.  LLM Scientist admission must reject an over-cardinality request
    # *before* that compiler can truncate it and falsely label the result exact.
    # These limits mirror the executable compiler contract; they do not narrow
    # Scientist authority inside the legal executable universe.
    if kind=="FEATURE_ABLATION":
        vals=payload.get("zero_features") or []
        if isinstance(vals,list) and len(vals)>8:
            return reject_cardinality("FEATURE_ABLATION.zero_features",len(vals),8)
    elif kind=="TRAINING_MEMORY":
        vals=payload.get("months",payload.get("preferred_months",[]))
        vals=vals if isinstance(vals,list) else [vals]
        if len(vals)>8:
            return reject_cardinality("TRAINING_MEMORY.windows",len(vals),8)
    elif kind=="SELECTIVITY_POLICY":
        vals=payload.get("take_thresholds") or []
        vals=vals if isinstance(vals,list) else [vals]
        if len(vals)>12:
            return reject_cardinality("SELECTIVITY_POLICY.take_thresholds",len(vals),12)
    elif kind=="REGIME_POLICY":
        vals=payload.get("regime_modes") or []
        if isinstance(vals,list) and len(vals)>8:
            return reject_cardinality("REGIME_POLICY.regime_modes",len(vals),8)
    elif kind=="HYBRID_ABLATION":
        vals=payload.get("families") or []
        if isinstance(vals,list) and len(vals)>8:
            return reject_cardinality("HYBRID_ABLATION.families",len(vals),8)
    elif kind=="SEED_STABILITY":
        vals=payload.get("families") or []
        if isinstance(vals,list) and len(vals)>8:
            return reject_cardinality("SEED_STABILITY.families",len(vals),8)
    elif kind=="MODEL_ARCHITECTURE":
        raw_vars=payload.get("variable_keys_by_family") or {}
        raw_ranges=payload.get("parameter_ranges_by_family") or {}
        if isinstance(raw_vars,dict) or isinstance(raw_ranges,dict):
            families=set(raw_vars if isinstance(raw_vars,dict) else {}) | set(raw_ranges if isinstance(raw_ranges,dict) else {})
            for fam in families:
                keys=(raw_vars.get(fam) or []) if isinstance(raw_vars,dict) else []
                keys=[keys] if isinstance(keys,str) else keys
                ranges=(raw_ranges.get(fam) or {}) if isinstance(raw_ranges,dict) else {}
                declared=[str(k) for k in keys] if isinstance(keys,list) else []
                ranged=[str(k) for k in ranges] if isinstance(ranges,dict) else []
                ordered_unique=list(dict.fromkeys(declared+ranged))
                if len(ordered_unique)>12:
                    return reject_cardinality(f"MODEL_ARCHITECTURE.variable_keys:{fam}",len(ordered_unique),12)

    # Backlog-only ideas are not executable and therefore cannot create experiment
    # identity drift. Preserve them exactly through the existing compiler.
    if kind!="OBJECTIVE_RESEARCH":
        supported={
            "LABEL_GEOMETRY":{"min_edge_r","min_margin_r"},
            "FEATURE_ABLATION":{"zero_features"},
            "TRAINING_MEMORY":{"months","preferred_months"},
            "SELECTIVITY_POLICY":{"take_thresholds"},
            "REGIME_POLICY":{"regime_modes"},
            "MODEL_ARCHITECTURE":{"family_priorities","variable_keys_by_family","parameter_ranges_by_family"},
            "HYBRID_ABLATION":{"families"},
            "SEED_STABILITY":{"families","actions","parameter_ranges_by_family"},
        }.get(kind,set())
        unknown=sorted(set(payload)-supported)
        if unknown:
            return reject("UNSUPPORTED_EXECUTABLE_PAYLOAD_KEY:"+",".join(unknown))

    if kind=="LABEL_GEOMETRY":
        limits={"min_edge_r":(0.0,0.6),"min_margin_r":(0.0,0.4)}
        for k,v in payload.items():
            if not bounded(v,*limits[k]): return reject(f"OUTSIDE_EXECUTABLE_HYPOTHESIS_BOUNDS:{k}")
    elif kind=="FEATURE_ABLATION":
        vals=payload.get("zero_features") or []
        if not isinstance(vals,list): return reject("INVALID_ZERO_FEATURES_TYPE")
        if any(str(x) not in FEATURES for x in vals): return reject("UNKNOWN_FEATURE_IN_ABLATION")
    elif kind=="TRAINING_MEMORY":
        if "months" in payload and "preferred_months" in payload:
            return reject("AMBIGUOUS_TRAINING_MEMORY_KEYS")
        vals=payload.get("months",payload.get("preferred_months",[])); vals=vals if isinstance(vals,list) else [vals]
        if not vals: return reject("EMPTY_TRAINING_MEMORY")
        if any(not bounded(x,6,72,integer=True) for x in vals): return reject("OUTSIDE_EXECUTABLE_HYPOTHESIS_BOUNDS:training_memory_months")
    elif kind=="SELECTIVITY_POLICY":
        vals=payload.get("take_thresholds") or []; vals=vals if isinstance(vals,list) else [vals]
        if not vals or any(not bounded(x,0.40,0.95) for x in vals): return reject("OUTSIDE_EXECUTABLE_HYPOTHESIS_BOUNDS:take_thresholds")
    elif kind=="REGIME_POLICY":
        vals=payload.get("regime_modes") or []
        if not isinstance(vals,list): return reject("INVALID_REGIME_MODES_TYPE")
        allowed=set(cfg.get("agent",{}).get("policy_discovery",{}).get("regime_modes",[]))|{"ALL","NON_SHOCK","TREND_RANGE","TREND","RANGE","TRANSITION","TREND_TRANSITION","RANGE_TRANSITION"}
        if not vals or any(str(x).upper() not in allowed for x in vals): return reject("UNSUPPORTED_REGIME_MODE")
    elif kind in {"MODEL_ARCHITECTURE","SEED_STABILITY"}:
        bounds={f:effective_bounds(cfg,f) for f in get_bounds()}
        fam_pri=payload.get("family_priorities") or {}
        if fam_pri and not isinstance(fam_pri,dict): return reject("INVALID_FAMILY_PRIORITIES_TYPE")
        for fam,v in (fam_pri.items() if isinstance(fam_pri,dict) else []):
            if str(fam) not in bounds: return reject(f"UNKNOWN_FAMILY:{fam}")
            if not bounded(v,0.35,3.0): return reject(f"OUTSIDE_EXECUTABLE_HYPOTHESIS_BOUNDS:family_priority:{fam}")
        if kind=="SEED_STABILITY":
            fams=payload.get("families") or []
            if not isinstance(fams,list) or not fams: return reject("INVALID_SEED_STABILITY_FAMILIES")
            if any(str(f).strip().lower() not in bounds for f in fams): return reject("UNKNOWN_SEED_STABILITY_FAMILY")
            allowed_actions={"SHRINK_CAPACITY","INCREASE_REGULARIZATION","LOWER_LR","INCREASE_DROPOUT","REDUCE_ROUTER_COMPLEXITY"}
            actions=payload.get("actions") or []
            if actions and (not isinstance(actions,list) or any(str(a).strip().upper() not in allowed_actions for a in actions)):
                return reject("UNSUPPORTED_SEED_STABILITY_ACTION")
        raw_vars=payload.get("variable_keys_by_family") or {}
        if raw_vars and not isinstance(raw_vars,dict): return reject("INVALID_VARIABLE_KEYS_BY_FAMILY_TYPE")
        for fam,keys in (raw_vars.items() if isinstance(raw_vars,dict) else []):
            fam=str(fam); keys=[keys] if isinstance(keys,str) else keys
            if fam not in bounds or not isinstance(keys,list): return reject(f"INVALID_VARIABLE_FAMILY:{fam}")
            for key in keys:
                if str(key) not in bounds[fam] or str(key)=="training_memory_months": return reject(f"UNSUPPORTED_VARIABLE_PARAMETER:{fam}:{key}")
        raw_ranges=payload.get("parameter_ranges_by_family") or {}
        if raw_ranges and not isinstance(raw_ranges,dict): return reject("INVALID_PARAMETER_RANGES_TYPE")
        for fam,ranges in (raw_ranges.items() if isinstance(raw_ranges,dict) else []):
            fam=str(fam)
            if fam not in bounds or not isinstance(ranges,dict): return reject(f"INVALID_RANGE_FAMILY:{fam}")
            for key,pair in ranges.items():
                key=str(key)
                if key not in bounds[fam] or key=="training_memory_months": return reject(f"UNSUPPORTED_RANGE_PARAMETER:{fam}:{key}")
                if not isinstance(pair,(list,tuple)) or len(pair)!=2: return reject(f"INVALID_RANGE_PAIR:{fam}:{key}")
                blo,bhi,btyp=bounds[fam][key]
                if not bounded(pair[0],blo,bhi,integer=(btyp is int)) or not bounded(pair[1],blo,bhi,integer=(btyp is int)):
                    return reject(f"OUTSIDE_EFFECTIVE_PARAMETER_BOUNDS:{fam}:{key}:requested={list(pair)}:allowed=[{blo},{bhi}]")
                if float(pair[0])>float(pair[1]): return reject(f"REVERSED_HYPOTHESIS_RANGE:{fam}:{key}")
    elif kind=="HYBRID_ABLATION":
        from models.model_registry import family_spec, hybrid_parts
        fams=payload.get("families") or []
        if not isinstance(fams,list) or not fams: return reject("INVALID_HYBRID_ABLATION_FAMILIES")
        for f in fams:
            fam=str(f).strip().lower(); parts=hybrid_parts(fam)
            if not parts or family_spec(fam) is None or family_spec(parts[0]) is None:
                return reject(f"UNKNOWN_HYBRID_FAMILY:{fam}")

    h=validate_hypothesis(raw,cfg,serial)
    if h is None:
        return reject("DETERMINISTIC_HYPOTHESIS_COMPILER_REJECTED")
    evidence["executable_payload"]=deepcopy(h.get("payload") or {})
    evidence["admission_status"]="ACCEPTED"
    evidence["rejection_reason"]=None
    evidence["exact_hypothesis"]=True
    evidence["scientific_attribution"]="LLM_HYPOTHESIS_EXACT_EXECUTABLE" if h.get("executable",True) else "LLM_BACKLOG_HYPOTHESIS_NOT_EXECUTED"
    return h,evidence

def merge_strategy_from_hypotheses(strategy: dict, hypotheses: list[dict]) -> dict:
    out = deepcopy(strategy or {})
    preferred = []
    for h in hypotheses or []:
        if h.get("kind") == "TRAINING_MEMORY":
            preferred.extend(h.get("payload", {}).get("months") or [])
        if h.get("kind") == "MODEL_ARCHITECTURE":
            pri = out.setdefault("family_priorities", {})
            for k,v in (h.get("payload", {}).get("family_priorities") or {}).items():
                pri[k] = v
    if preferred:
        out["preferred_training_memory_months"] = sorted(set(int(x) for x in preferred))
    return out


def apply_policy_agenda(cfg: dict, hypotheses: list[dict]) -> dict:
    out = deepcopy(cfg)
    pcfg = out.setdefault("agent", {}).setdefault("policy_discovery", {})
    thresholds = []
    regimes = []
    for h in hypotheses or []:
        if h.get("kind") == "SELECTIVITY_POLICY": thresholds += list(h.get("payload", {}).get("take_thresholds") or [])
        elif h.get("kind") == "REGIME_POLICY": regimes += list(h.get("payload", {}).get("regime_modes") or [])
    if thresholds:
        base = list(pcfg.get("take_threshold_grid") or [])
        merged = sorted(set(round(float(x),4) for x in base + thresholds))[:24]
        pcfg["take_threshold_grid"] = merged
        # Full-WFA trading_metrics reads deployment.take_threshold_grid.  Keep the
        # Scientist selectivity hypothesis executable in the actual qualification path.
        dcfg = out.setdefault("deployment", {})
        dbase = list(dcfg.get("take_threshold_grid") or [])
        dcfg["take_threshold_grid"] = sorted(set(round(float(x),4) for x in dbase + thresholds))[:24]
    if regimes:
        base = list(pcfg.get("regime_modes") or [])
        pcfg["regime_modes"] = list(dict.fromkeys(base + regimes))[:16]
    return out


def seed_stability_hypothesis_from_topology(topology: dict, cfg: dict) -> dict | None:
    """Create a bounded executable stability-repair hypothesis from deterministic
    CPCV seed evidence. This is a fail-safe scientific compiler, not a PASS/FAIL rule.
    """
    topo=topology if isinstance(topology,dict) else {}
    rows=topo.get("candidate_rows") or []
    fams=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        sc=row.get("seed_confirmation") if isinstance(row.get("seed_confirmation"),dict) else {}
        failed=False
        if sc:
            failed=(sc.get("passed") is False or str(sc.get("status") or "").upper() in {"FAIL","FAILED","SEED_UNSTABLE"})
            if not failed:
                failed=any(isinstance(sr,dict) and sr.get("passed") is False for sr in (sc.get("seed_results") or []))
        if failed:
            fam=str(row.get("family") or "").strip().lower()
            if fam and fam not in fams:
                fams.append(fam)
    if not fams:
        gates={**(topo.get("first_failed_gate_counts") or {}),**(topo.get("all_failed_gate_counts") or {})}
        if not any("SEED_STABILITY" in str(k).upper() and int(v or 0)>0 for k,v in gates.items()):
            return None
        byfam=topo.get("by_family") if isinstance(topo.get("by_family"),dict) else {}
        fams=[str(k).lower() for k in byfam][:8]
    if not fams:
        return None
    raw={
        "kind":"SEED_STABILITY",
        "title":"Repair stochastic seed instability",
        "rationale":"Deterministic CPCV seed confirmation shows initialization sensitivity; next Discovery should reduce stochastic capacity/variance before changing KPI gates or mining seeds.",
        "expected_observation":"The same fixed CPCV seed set should converge toward consistent PASS/FAIL and tighter lower-tail dispersion.",
        "payload":{"families":fams[:8],"actions":["SHRINK_CAPACITY","INCREASE_REGULARIZATION","LOWER_LR"]},
    }
    return validate_hypothesis(raw,cfg,1)
