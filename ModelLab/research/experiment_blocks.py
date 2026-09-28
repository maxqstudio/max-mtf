from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, json
from models.model_registry import get_bounds, get_distributions, enabled_families, family_spec, hybrid_parts, effective_bounds
from models.models import CandidateSpec, validate_candidate

SCHEMA="CP_EXPERIMENT_BLOCK_V2_DECISIVE_FALSIFICATION"
LIFECYCLE_SCHEMA="CP_HYPOTHESIS_LIFECYCLE_V1"
ACTIVE={"PROPOSED","PREFLIGHT_APPROVED","ACTIVE","EXTEND","EXPLOIT"}
TERMINAL={"SUPPORTED","PARTIALLY_SUPPORTED","FALSIFIED","RETIRED"}

KIND_KEYS={
 "TRAINING_MEMORY":{"training_memory_months"},
 "MODEL_ARCHITECTURE":set(),
 "SELECTIVITY_POLICY":{"take_threshold"},
 "REGIME_POLICY":set(),
 "LABEL_GEOMETRY":set(),
 "FEATURE_ABLATION":set(),
 "HYBRID_ABLATION":set(),
 "SEED_STABILITY":set(),
 "OBJECTIVE_RESEARCH":set(),
}

def _hid(h:dict)->str:
    raw=json.dumps({"kind":h.get("kind"),"title":h.get("title"),"payload":h.get("payload")},sort_keys=True,default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def normalize_hypothesis(h:dict, source:str="UNKNOWN", generation:int=0)->dict:
    x=deepcopy(h or {}); x["hypothesis_id"]=str(x.get("hypothesis_id") or _hid(x)); x["schema"]=LIFECYCLE_SCHEMA
    # When rehydrating exact-contract Research Memory, retain the original authority
    # (especially STAGE_SCIENTIST) so downstream-failure learning keeps priority.
    x["source"]=(str(x.get("source") or source) if str(source).upper()=="RESEARCH_MEMORY" else source)
    x["source_generation"]=int(generation); x["status"]=str(x.get("status") or "PROPOSED").upper()
    x.setdefault("created_utc",datetime.now(timezone.utc).isoformat()); x.setdefault("observations",[])
    return x

def reconcile_hypotheses(existing:list[dict], incoming:list[dict], *, source:str, generation:int)->list[dict]:
    by={str(x.get("hypothesis_id") or _hid(x)):deepcopy(x) for x in existing if isinstance(x,dict)}
    for h in incoming or []:
        if not isinstance(h,dict): continue
        n=normalize_hypothesis(h,source,generation); hid=n["hypothesis_id"]
        if hid in by:
            old=by[hid]; old.update({k:v for k,v in n.items() if k not in {"created_utc","observations","status"}}); by[hid]=old
        else: by[hid]=n
    return list(by.values())

def choose_active_hypothesis(hypotheses:list[dict], failure_topology:dict|None=None)->dict|None:
    hs=[h for h in hypotheses if str(h.get("status","PROPOSED")).upper() in ACTIVE and bool(h.get("executable",True))]
    if not hs: return None
    # Exact-contract downstream lessons are the reason a new Discovery cycle exists, so
    # they must not be shadowed by an older routine WFA/Director hypothesis. Within the
    # same authority class, prefer a hypothesis that addresses the dominant failure
    # group and then the most recently appended lifecycle entry.
    grp=str((failure_topology or {}).get("dominant_failure_group") or "").lower()
    pref={"survival":["MODEL_ARCHITECTURE","TRAINING_MEMORY","SELECTIVITY_POLICY"],"economic":["SELECTIVITY_POLICY","MODEL_ARCHITECTURE","HYBRID_ABLATION"],"stability":["SEED_STABILITY","TRAINING_MEMORY","MODEL_ARCHITECTURE"],"sample":["SELECTIVITY_POLICY"]}
    order=pref.get(grp,[])
    positions={id(h):i for i,h in enumerate(hypotheses)}
    def key(h):
        source=str(h.get("source") or "").upper()
        source_priority=0 if source=="STAGE_SCIENTIST" else (1 if source=="FACTORY_DIRECTOR" else 2)
        kind_priority=order.index(h.get("kind")) if h.get("kind") in order else 99
        return (source_priority,kind_priority,-positions.get(id(h),0))
    return min(hs,key=key)

def _default_architecture_variables(family:str, bounds:dict)->set[str]:
    """Select interpretable architecture knobs for any registered family/composition."""
    fam=str(family or "").lower()
    spec=family_spec(fam) or {}
    parts=hybrid_parts(fam)
    if parts:
        # A composed hypothesis may change both representation and policy capacity.
        keys={k for k in bounds if k.startswith("temporal_") or k.startswith("policy_")}
    elif spec.get("role")=="temporal":
        keys={
            "sequence_length","hidden_size","num_layers","dropout","weight_decay","learning_rate",
            "batch_size","epochs","tcn_channels","tcn_blocks","kernel_size","d_model",
            "attention_heads","ffn_mult",
        }
    elif fam=="xgboost":
        keys={"max_depth","min_child_weight","subsample","colsample_bytree","reg_alpha","reg_lambda","learning_rate","n_estimators"}
    elif fam=="lightgbm":
        keys={"max_depth","num_leaves","min_child_samples","subsample","colsample_bytree","reg_alpha","reg_lambda","learning_rate","n_estimators"}
    elif fam=="random_forest":
        keys={"max_depth","min_samples_leaf","max_features","n_estimators"}
    else:
        keys=set(bounds)-{"training_memory_months","take_threshold"}
    return {k for k in keys if k in bounds}


def _default_stability_variables(family:str, bounds:dict)->set[str]:
    fam=str(family or "").lower()
    parts=hybrid_parts(fam)
    prefixes=("temporal_",) if parts else ("",)
    base={"dropout","weight_decay","learning_rate","hidden_size","d_model","num_layers","ffn_mult","expert_ffn","num_experts","top_k","router_temperature","load_balance_coef","batch_size","epochs"}
    keys=set()
    for prefix in prefixes:
        for k in base:
            kk=prefix+k
            if kk in bounds: keys.add(kk)
    return keys or _default_architecture_variables(family,bounds)


def compile_experiment_block(h:dict|None, anchor:CandidateSpec|None, cfg:dict, *, generation:int, block_no:int, budget:int)->dict:
    if not h:
        return {"schema":SCHEMA,"block_id":f"GEN{generation:02d}-CONTROL-{block_no:02d}","hypothesis_id":None,"mode":"CONTROL_EXPLORATION","budget":int(budget),"frozen_keys":[],"variable_keys":[],"family":None,"status":"ACTIVE"}
    kind=str(h.get("kind") or "")
    payload=h.get("payload") if isinstance(h.get("payload"),dict) else {}
    if kind=="HYBRID_ABLATION":
        from models.topology_allocation import configured_hybrid_priority
        pairs=list(payload.get("pairs") or [])
        hp=configured_hybrid_priority(cfg,legacy_none=True)
        feasible=bool(pairs) and not (hp is not None and (float(hp)<=0.0 or float(hp)>=1.0))
        return {"schema":SCHEMA,"block_id":f"GEN{generation:02d}-{str(h.get('hypothesis_id') or _hid(h))[:8]}-{block_no:02d}","hypothesis_id":str(h.get("hypothesis_id") or _hid(h)),"kind":kind,"title":h.get("title"),"hypothesis_payload":deepcopy(payload),"mode":"HYBRID_ABLATION" if feasible else "HYPOTHESIS_DEFERRED","ablation_pairs":pairs,"budget":int(budget),"status":"ACTIVE" if feasible else "DEFERRED","deferred_reason":None if feasible else "OWNER_TOPOLOGY_PRIORITY_EXCLUDES_ONE_ABLATION_ARM","origin_stage":str(h.get("source_stage") or "FULL_WFA").upper(),"proxy_authority":"FULL_WFA","decisive_authority":str(h.get("source_stage") or "FULL_WFA").upper(),"falsification_rule":"Hybrid arm must materially improve robust Full-WFA/CPCV evidence over its temporal-only control under the same decision contract.","created_utc":datetime.now(timezone.utc).isoformat()}
    if anchor is None:
        return {"schema":SCHEMA,"block_id":f"GEN{generation:02d}-CONTROL-{block_no:02d}","hypothesis_id":None,"mode":"CONTROL_EXPLORATION","budget":int(budget),"frozen_keys":[],"variable_keys":[],"family":None,"status":"ACTIVE","deferred_hypothesis_id":str(h.get("hypothesis_id") or _hid(h)),"deferred_reason":"NO_ANCHOR_FOR_HYPOTHESIS_BLOCK"}
    fam=anchor.family; bounds=effective_bounds(cfg,fam)
    variable=set(KIND_KEYS.get(kind,set())) & set(bounds)
    parameter_ranges={}
    if kind=="MODEL_ARCHITECTURE":
        by_family=payload.get("variable_keys_by_family") if isinstance(payload.get("variable_keys_by_family"),dict) else {}
        declared=by_family.get(fam) if isinstance(by_family.get(fam),list) else []
        parameter_ranges=deepcopy((payload.get("parameter_ranges_by_family") or {}).get(fam) or {})
        range_keys=set(str(x) for x in parameter_ranges) & set(bounds)
        variable=((set(str(x) for x in declared) | range_keys) & set(bounds)) if (declared or range_keys) else _default_architecture_variables(fam,bounds)
    if kind=="SEED_STABILITY":
        allowed_fams=set(str(x) for x in (payload.get("families") or []))
        if fam not in allowed_fams:
            variable=set()
        else:
            variable=_default_stability_variables(fam,bounds)
            parameter_ranges=deepcopy((payload.get("parameter_ranges_by_family") or {}).get(fam) or {})
            variable |= set(parameter_ranges) & set(bounds)
    if kind=="TRAINING_MEMORY" and "training_memory_months" not in bounds: variable=set()
    # Unsupported/indirect hypothesis types can still freeze estimator knobs while their
    # deterministic policy compiler (e.g. selectivity agenda) changes the relevant policy.
    frozen=sorted(set(bounds)-variable)
    origin_stage=str(h.get("source_stage") or "FULL_WFA").upper()
    downstream=origin_stage in {"CPCV","TOURNAMENT","MONTE_CARLO"}
    target_gate=((h.get("source_failure_topology") or {}).get("dominant_first_failed_gate") if isinstance(h.get("source_failure_topology"),dict) else None)
    falsification=(
        f"Full-WFA is a prerequisite proxy only. Decisive authority is {origin_stage}; the hypothesis is not SUPPORTED until matching downstream evidence clears the originating mechanism/stage."
        if downstream else
        "No material improvement in authoritative Full-WFA lower-tail/failure margins within the declared block budget."
    )
    return {"schema":SCHEMA,"block_id":f"GEN{generation:02d}-{str(h.get('hypothesis_id') or _hid(h))[:8]}-{block_no:02d}","hypothesis_id":str(h.get("hypothesis_id") or _hid(h)),"kind":kind,"title":h.get("title"),"hypothesis_payload":deepcopy(payload),"mode":"HYPOTHESIS_DIRECTED","family":fam,"anchor_name":anchor.name,"anchor_params":deepcopy(anchor.params),"variable_keys":sorted(variable),"parameter_ranges":parameter_ranges,"frozen_keys":frozen,"budget":int(budget),"status":"ACTIVE","origin_stage":origin_stage,"source_factory":h.get("source_factory"),"source_status":h.get("source_status"),"source_failure_gate":target_gate,"proxy_authority":"FULL_WFA","decisive_authority":origin_stage if downstream else "FULL_WFA","falsification_rule":falsification,"created_utc":datetime.now(timezone.utc).isoformat()}

def _remap_to_range(value, full_meta, narrowed, distribution: str):
    blo,bhi,btyp=full_meta
    lo,hi=narrowed
    if float(hi) <= float(lo):
        return int(round(lo)) if btyp is int else float(lo)
    try:
        v=float(value)
        if distribution=="log" and float(blo)>0 and float(bhi)>0 and float(lo)>0 and float(hi)>0:
            import math
            den=math.log(float(bhi))-math.log(float(blo))
            u=0.5 if abs(den)<1e-15 else (math.log(max(float(blo),min(float(bhi),v)))-math.log(float(blo)))/den
            out=math.exp(math.log(float(lo))+max(0.0,min(1.0,u))*(math.log(float(hi))-math.log(float(lo))))
        else:
            den=float(bhi)-float(blo)
            u=0.5 if abs(den)<1e-15 else (max(float(blo),min(float(bhi),v))-float(blo))/den
            out=float(lo)+max(0.0,min(1.0,u))*(float(hi)-float(lo))
        return int(round(out)) if btyp is int else float(out)
    except Exception:
        return int(round(lo)) if btyp is int else float(lo)

def apply_block_to_spec(spec:CandidateSpec, block:dict, cfg:dict, serial:int)->CandidateSpec:
    if not block or block.get("mode")!="HYPOTHESIS_DIRECTED" or spec.family!=block.get("family"): return spec
    anchor=block.get("anchor_params") or {}; variable=set(block.get("variable_keys") or []); p=dict(spec.params)
    bounds=effective_bounds(cfg,spec.family)
    distributions=get_distributions().get(spec.family,{})
    # Freeze every non-variable dimension to the anchor, so a block tests one hypothesis rather than parameter soup.
    for k,v in anchor.items():
        if k not in variable and k in p: p[k]=v
    kind=str(block.get("kind") or "")
    payload=block.get("hypothesis_payload") if isinstance(block.get("hypothesis_payload"),dict) else {}
    if kind in {"MODEL_ARCHITECTURE","SEED_STABILITY"}:
        for k,narrowed in (block.get("parameter_ranges") or {}).items():
            if k in variable and k in p and k in bounds and isinstance(narrowed,(list,tuple)) and len(narrowed)==2:
                p[k]=_remap_to_range(p[k],bounds[k],narrowed,distributions.get(k,"linear"))
    elif kind=="TRAINING_MEMORY" and "training_memory_months" in variable:
        months=[int(x) for x in (payload.get("months") or []) if x is not None]
        if months:
            p["training_memory_months"]=months[(max(1,int(serial))-1)%len(months)]
    return CandidateSpec(spec.family,f"eb_{block.get('block_id')}_{serial:02d}",p)

def evaluate_block(block:dict, full_rows:list[dict], cfg:dict)->dict:
    """Evaluate the Discovery proxy without falsely closing downstream-origin hypotheses."""
    rows=[r for r in full_rows if str(r.get("experiment_block_id") or "")==str(block.get("block_id"))]
    if str(block.get("mode"))=="HYPOTHESIS_DEFERRED":
        return {"schema":SCHEMA,"block_id":block.get("block_id"),"hypothesis_id":block.get("hypothesis_id"),"completed_trials":0,"passed_trials":0,"proxy_authority":"FULL_WFA","status":"DEFERRED","reason":block.get("deferred_reason"),"scientific_interpretation":"Hypothesis retained but not executed because deterministic Owner authority excludes a required arm."}
    passed=sum(bool(r.get("cv_gate_pass")) for r in rows)
    near=[]
    for r in rows:
        m=(r.get("failure_margins") or {}).get("closest_failed_gate") or {}
        if m.get("relative_margin") is not None: near.append(float(m["relative_margin"]))
    decisive=str(block.get("decisive_authority") or "FULL_WFA").upper()
    proxy_status="INCONCLUSIVE"
    status="INCONCLUSIVE"
    if passed>0:
        proxy_status="SUPPORTED"
        status=(f"AWAITING_{decisive}" if decisive!="FULL_WFA" else "SUPPORTED")
    elif len(rows)>=int(block.get("budget",0) or 0) and rows:
        proxy_status="FALSIFIED"
        status="FALSIFIED"
    candidate_ids=[]
    for r in rows:
        cid=r.get("trained_candidate_id") or r.get("pool_id") or r.get("candidate_id") or r.get("name")
        if cid is not None and str(cid) not in candidate_ids:
            candidate_ids.append(str(cid))
    trades=[int(r.get("total_validation_trades",0) or 0) for r in rows if r.get("total_validation_trades") is not None]
    exp=[float(r.get("overall_expectancy_r",r.get("median_expectancy_r",0)) or 0) for r in rows if r.get("overall_expectancy_r") is not None or r.get("median_expectancy_r") is not None]
    worst=[float(r.get("worst_expectancy_r",0) or 0) for r in rows if r.get("worst_expectancy_r") is not None]
    result={"schema":SCHEMA,"block_id":block.get("block_id"),"experiment_id":block.get("block_id"),"hypothesis_id":block.get("hypothesis_id"),"completed_trials":len(rows),"passed_trials":passed,"best_closest_margin":max(near) if near else None,
            "candidate_ids":candidate_ids[:32],
            "coverage":{"candidate_count":len(rows),"total_validation_trades":sum(trades) if trades else None,"min_candidate_trades":min(trades) if trades else None,"max_candidate_trades":max(trades) if trades else None},
            "fold_distribution":{"best_overall_expectancy_r":max(exp) if exp else None,"worst_overall_expectancy_r":min(exp) if exp else None,"worst_fold_expectancy_r":min(worst) if worst else None},
            "failure_margins":{"best_closest_relative_margin":max(near) if near else None},
            "proxy_authority":"FULL_WFA","proxy_status":proxy_status,"decisive_authority":decisive,"source_failure_gate":block.get("source_failure_gate"),"status":status,
            "scientific_interpretation":("WFA proxy passed; downstream decisive test still pending." if status.startswith("AWAITING_") else ("Full-WFA proxy falsified the treatment before downstream testing." if status=="FALSIFIED" else "No decisive conclusion."))}
    if str(block.get("mode"))=="HYBRID_ABLATION":
        from models.model_registry import is_hybrid_family
        arms={"SINGLE":[],"HYBRID":[]}
        for r in rows:
            arms["HYBRID" if is_hybrid_family(str(r.get("family") or "")) else "SINGLE"].append(r)
        def _summary(xs):
            if not xs: return {"n":0,"pass":0,"pass_rate":None,"median_score":None}
            vals=sorted(float(x.get("selection_score",-1e99)) for x in xs)
            n=len(vals); med=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
            n_pass=sum(bool(x.get("cv_gate_pass")) for x in xs)
            return {"n":len(xs),"pass":n_pass,"pass_rate":n_pass/len(xs),"median_score":med}
        summaries={k:_summary(v) for k,v in arms.items()}
        result["ablation_arms"]=summaries
        result["paired_contract"]="SAME_FINAL_SELL_SKIP_BUY_AUTHORITY"
        # A hybrid-ablation hypothesis is about incremental value of the hybrid arm,
        # not merely whether any candidate in the block happened to PASS.  Full-WFA
        # gate survival is the proxy authority; selection score is reported only as
        # supporting diagnostics and cannot manufacture SUPPORT when pass rates tie.
        single=summaries["SINGLE"]; hybrid=summaries["HYBRID"]
        both_present=single["n"]>0 and hybrid["n"]>0
        budget_complete=len(rows)>=int(block.get("budget",0) or 0) and bool(rows)
        hybrid_better=bool(both_present and hybrid["pass_rate"] is not None and single["pass_rate"] is not None and hybrid["pass_rate"]>single["pass_rate"])
        if hybrid_better:
            result["proxy_status"]="SUPPORTED"
            result["status"]=(f"AWAITING_{decisive}" if decisive!="FULL_WFA" else "SUPPORTED")
            result["scientific_interpretation"]="Hybrid arm improved Full-WFA gate-survival rate over its temporal-only control under the same final decision contract."
        elif budget_complete and both_present:
            result["proxy_status"]="FALSIFIED"
            result["status"]="FALSIFIED"
            result["scientific_interpretation"]="Hybrid arm did not improve Full-WFA gate-survival rate over its temporal-only control; the incremental-hybrid hypothesis is falsified at the proxy stage."
        else:
            result["proxy_status"]="INCONCLUSIVE"
            result["status"]="INCONCLUSIVE"
            result["scientific_interpretation"]="Hybrid ablation is incomplete; both controlled arms must accumulate the planned Full-WFA evidence before conclusion."
        result["ablation_decision_rule"]="HYBRID_PASS_RATE_GT_SINGLE_PASS_RATE"
    return result


def resolve_decisive_hypotheses(hypotheses:list[dict], stage_rows:list[dict], stage:str, stage_status:str)->tuple[list[dict],list[dict]]:
    """Close downstream-origin hypotheses only with matching committed downstream evidence.

    Matching is by hypothesis_id propagated from Experiment Block -> Pool -> downstream row.
    A full downstream PASS is strong support. Clearing the originating failed gate while
    failing another gate is PARTIALLY_SUPPORTED. If the terminal stage completes and the
    originating gate remains failed for all matching candidates, the hypothesis is FALSIFIED.
    """
    stage=str(stage or "").upper(); out=deepcopy(hypotheses or []); decisions=[]
    terminal_failure=("NO_SURVIVOR" in str(stage_status).upper() or "FAIL" in str(stage_status).upper())
    for h in out:
        if not isinstance(h,dict): continue
        hid=str(h.get("hypothesis_id") or "")
        expected=f"AWAITING_{stage}"
        if str(h.get("status") or "").upper()!=expected or not hid: continue
        rows=[r for r in (stage_rows or []) if str((r or {}).get("hypothesis_id") or "")==hid]
        if not rows:
            decisions.append({"hypothesis_id":hid,"stage":stage,"status":"INCONCLUSIVE","reason":"NO_MATCHING_DOWNSTREAM_CANDIDATE"})
            continue
        target=str(h.get("source_failure_gate") or ((h.get("source_failure_topology") or {}).get("dominant_first_failed_gate") if isinstance(h.get("source_failure_topology"),dict) else "") or "")
        full_pass=any(bool(r.get("passed") or ((r.get("acceptance") or {}).get("passed"))) for r in rows)
        gate_cleared=False
        if target:
            for r in rows:
                ev=r.get("evidence") if isinstance(r.get("evidence"),dict) else {}
                acc=r.get("acceptance") if isinstance(r.get("acceptance"),dict) else {}
                gates=ev.get("gates") if isinstance(ev.get("gates"),dict) else {}
                if not gates and isinstance(acc.get("gates"),dict):
                    gates=acc.get("gates")
                if target in gates and bool(gates.get(target)):
                    gate_cleared=True; break
        if full_pass:
            status="SUPPORTED"; reason="MATCHING_DOWNSTREAM_PASS"
        elif gate_cleared:
            status="PARTIALLY_SUPPORTED"; reason="ORIGINATING_GATE_CLEARED_BUT_STAGE_STILL_FAILED"
        elif terminal_failure:
            status="FALSIFIED"; reason="ORIGINATING_FAILURE_PERSISTED_IN_DECISIVE_STAGE"
        else:
            status=expected; reason="DECISIVE_STAGE_NOT_TERMINAL"
        candidate_ids=[]
        failed_gates=[]
        coverage_trades=[]
        for r in rows:
            cid=r.get("trained_candidate_id") or r.get("pool_id") or r.get("candidate_id") or r.get("name")
            if cid is not None and str(cid) not in candidate_ids:
                candidate_ids.append(str(cid))
            acc=r.get("acceptance") if isinstance(r.get("acceptance"),dict) else {}
            ev=r.get("evidence") if isinstance(r.get("evidence"),dict) else {}
            for g in list(acc.get("reasons") or [])+list(ev.get("reasons") or []):
                sg=str(g)
                if sg and sg not in failed_gates: failed_gates.append(sg)
            for src in (r, r.get("metrics") if isinstance(r.get("metrics"),dict) else {}, ev.get("summary") if isinstance(ev.get("summary"),dict) else {}):
                if isinstance(src,dict):
                    for key in ("trades","total_validation_trades","total_trades"):
                        if src.get(key) is not None:
                            try: coverage_trades.append(int(src.get(key))); break
                            except Exception: pass
        decision={"schema":"CP_HYPOTHESIS_DECISIVE_OUTCOME_V2","hypothesis_id":hid,"experiment_id":h.get("experiment_id") or h.get("experiment_block_id"),"stage":stage,"stage_status":stage_status,"matching_candidates":len(rows),"matching_candidate_ids":candidate_ids[:32],"source_failure_gate":target or None,"failed_gates":failed_gates[:64],"coverage":{"candidate_count":len(rows),"observed_trade_counts":coverage_trades[:32]},"status":status,"reason":reason,"created_utc":datetime.now(timezone.utc).isoformat()}
        h["status"]=status; h["decisive_outcome"]=decision; h.setdefault("observations",[]).append(decision); decisions.append(decision)
    return out,decisions
