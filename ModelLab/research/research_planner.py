from __future__ import annotations
import math
import random
from collections import defaultdict

from models.model_registry import enabled_families, get_bounds, effective_bounds, is_hybrid_family, hybrid_parts, configured_family_size_priorities
from models.models import CandidateSpec, random_candidate, spec_fingerprint, validate_candidate, generate_initial_population
from models.topology_allocation import configured_hybrid_priority, effective_hybrid_priority, allocation_counts, split_families
from research.creativity_governor import adaptive_creativity_profile, llm_research_influence, apply_llm_priority_influence


def _quantile(values: list[float], q: float) -> float | None:
    vals=sorted(float(x) for x in values)
    if not vals:
        return None
    if len(vals)==1:
        return vals[0]
    pos=max(0.0,min(1.0,float(q)))*(len(vals)-1)
    lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    if lo==hi:
        return vals[lo]
    w=pos-lo
    return vals[lo]*(1.0-w)+vals[hi]*w


def family_stats(board: list[dict], cfg: dict) -> dict:
    """Robust deterministic family evidence.

    Best-candidate evidence is retained for diagnostics, but allocation uses repeatable
    distributional evidence (PASS rate, median and lower quartile) so one lucky DL seed
    or one unusually favorable fold cannot monopolize the next generation.
    """
    stats={}
    for family in enabled_families(cfg):
        rows=[r for r in board if r.get("family")==family]
        ranked=sorted(rows,key=lambda r:(bool(r.get("cv_gate_pass")),float(r.get("selection_score",-1e99))),reverse=True)
        scores=[float(r.get("selection_score",-1e99)) for r in rows if r.get("selection_score") is not None]
        passed=sum(1 for r in rows if bool(r.get("cv_gate_pass")))
        failed_dist=[]
        for r in rows:
            fm=r.get("failure_margins") or {}
            c=(fm.get("closest_failed_gate") or {}).get("relative_margin")
            if c is not None:
                try: failed_dist.append(float(c))
                except Exception: pass
        stats[family]={
            "experiments":len(rows),
            "pass_count":passed,
            "pass_rate":float(passed/len(rows)) if rows else 0.0,
            "median_score":_quantile(scores,0.50),
            "p25_score":_quantile(scores,0.25),
            "score_spread_iqr":None if not scores else float((_quantile(scores,0.75) or 0.0)-(_quantile(scores,0.25) or 0.0)),
            "median_closest_gate_margin":_quantile(failed_dist,0.50),
            "best_score":float(ranked[0]["selection_score"]) if ranked else None,
            "best_pf":float(ranked[0].get("median_profit_factor",0)) if ranked else None,
            "best_expectancy_r":float(ranked[0].get("median_expectancy_r",0)) if ranked else None,
            "best_recovery_factor":float(ranked[0].get("median_recovery_factor",0)) if ranked else None,
            "best_positive_fold_ratio":float(ranked[0].get("positive_fold_ratio",0)) if ranked else None,
            "best_expectancy_std_r":float(ranked[0].get("expectancy_std_r",0)) if ranked else None,
            "mean_fit_seconds":float(sum(float(r.get("total_fit_seconds",0)) for r in rows)/len(rows)) if rows else None,
        }
    return stats


def _softmax_weights(values: dict[str,float]) -> dict[str,float]:
    if not values: return {}
    m=max(values.values())
    ex={k:math.exp(max(-20.0,min(20.0,v-m))) for k,v in values.items()}
    s=sum(ex.values()) or 1.0
    return {k:v/s for k,v in ex.items()}


def adaptive_family_weights(board: list[dict], cfg: dict, llm_strategy: dict | None = None) -> dict[str,float]:
    fams=enabled_families(cfg)
    # R10: a persisted Owner topology slider is stronger than the old staged-unlock
    # heuristic.  When present, SINGLE/HYBRID allocation is enforced directly by the
    # planner, so hybrids are eligible from round 1.  Legacy configs without this
    # authority retain the historical "temporal evidence first" behaviour.
    hybrid_only=bool(fams) and all(is_hybrid_family(f) for f in fams)
    topology_priority=configured_hybrid_priority(cfg,legacy_none=True)
    if topology_priority is None and not hybrid_only:
        eligible=[]
        observed={str(r.get("family") or "") for r in board}
        for f in fams:
            if not is_hybrid_family(f):
                eligible.append(f); continue
            parts=hybrid_parts(f)
            if parts and parts[0] in observed:
                eligible.append(f)
        fams=eligible or [f for f in fams if not is_hybrid_family(f)]
    if not fams:
        # Never allow an opaque StopIteration from the weighted selector. If the
        # operator enabled deployable families, preserve them; otherwise fail with
        # an explicit configuration error at the planner boundary.
        fams=list(enabled_families(cfg))
    if not fams:
        raise RuntimeError("No enabled deployable model families for research planner")
    stats=family_stats(board,cfg)
    raw={}
    for f in fams:
        st=stats[f]
        # Always reward under-explored families, but allocate exploitation from robust
        # evidence rather than the single best run. Lower-quartile evidence penalizes
        # unstable families while PASS rate rewards repeatability.
        explore_bonus=0.35/math.sqrt(1.0+st["experiments"])
        med=st.get("median_score") if st.get("median_score") is not None else 0.0
        p25=st.get("p25_score") if st.get("p25_score") is not None else med
        pass_bonus=1.25*float(st.get("pass_rate",0.0))
        gate_margin=st.get("median_closest_gate_margin")
        near_bonus=0.20*max(-1.0,min(1.0,float(gate_margin))) if gate_margin is not None else 0.0
        raw[f]=(0.65*float(med)+0.35*float(p25))/12.0 + pass_bonus + near_bonus + explore_bonus
    # Cross-generation Research Memory biases, but never monopolizes, family allocation.
    memory=(cfg.get("agent",{}) or {}).get("generation_memory") or {}
    for rank,e in enumerate(memory.get("elites") or []):
        fam=str(e.get("family") or "")
        if fam in raw:
            raw[fam] += max(0.05, 0.45/(1.0+rank))
    w=_softmax_weights(raw)
    pri=(llm_strategy or {}).get("family_priorities") or {}
    influence=llm_research_influence(cfg)
    if pri and influence>0:
        for f in fams:
            if f in pri:
                w[f]*=apply_llm_priority_influence(float(pri[f]),influence)
        s=sum(w.values()) or 1.0
        w={k:v/s for k,v in w.items()}
    # floor prevents premature family extinction
    floor=float(cfg.get("agent",{}).get("search",{}).get("min_family_weight",0.08))
    if fams:
        w={f:max(floor,w.get(f,0.0)) for f in fams}
        s=sum(w.values()); w={f:v/s for f,v in w.items()}
    return w


def _weighted_family(rng: random.Random, weights: dict[str,float]) -> str:
    if not weights:
        raise RuntimeError("Research planner has no eligible model-family weights")
    x=rng.random(); c=0.0
    last=next(iter(weights))
    for f,w in weights.items():
        c+=w; last=f
        if x<=c: return f
    return last


def _filtered_topology_weights(weights: dict[str,float], topology: str | None) -> dict[str,float]:
    if topology not in {"SINGLE","HYBRID"}:
        return dict(weights)
    want_hybrid = topology == "HYBRID"
    out={f:w for f,w in weights.items() if bool(is_hybrid_family(f))==want_hybrid}
    if not out:
        return {}
    total=sum(out.values()) or 1.0
    return {f:w/total for f,w in out.items()}


def _estimated_compute_share(specs: list[CandidateSpec], stats: dict) -> dict:
    single=0.0; hybrid=0.0
    for s in specs:
        observed=(stats.get(s.family) or {}).get("mean_fit_seconds")
        # Before evidence exists, a hybrid gets a conservative 2x unit cost because
        # it owns temporal OOF fitting plus a policy fit. This is telemetry only.
        cost=float(observed) if observed not in (None,0) else (2.0 if is_hybrid_family(s.family) else 1.0)
        if is_hybrid_family(s.family): hybrid+=cost
        else: single+=cost
    total=single+hybrid
    return {
        "single_estimated_units":single,"hybrid_estimated_units":hybrid,
        "single_estimated_share":(single/total if total else 0.0),
        "hybrid_estimated_share":(hybrid/total if total else 0.0),
        "basis":"OBSERVED_MEAN_FIT_SECONDS_OR_FALLBACK_SINGLE1_HYBRID2",
    }


def _mutate_value(rng, value, lo, hi, typ, scale):
    span=float(hi)-float(lo)
    try: base=float(value)
    except Exception: base=(float(lo)+float(hi))/2.0
    v=base+rng.uniform(-scale,scale)*span
    v=max(float(lo),min(float(hi),v))
    return int(round(v)) if typ is int else float(v)


def _top_specs(board, specs_by_name, family=None, limit=8):
    rows=[r for r in board if family is None or r.get("family")==family]
    rows=sorted(rows,key=lambda r:(bool(r.get("cv_gate_pass")),float(r.get("selection_score",-1e99))),reverse=True)
    out=[]
    for r in rows:
        s=specs_by_name.get(r.get("name"))
        if s is not None: out.append(s)
        if len(out)>=limit: break
    return out


def _local_mutation(base: CandidateSpec, cfg: dict, rng: random.Random, name: str, scale: float) -> CandidateSpec:
    bounds=effective_bounds(cfg,base.family)
    p=dict(base.params)
    keys=list(bounds); rng.shuffle(keys)
    nchange=1 if rng.random()<0.50 else min(3,len(keys))
    for key in keys[:nchange]:
        lo,hi,typ=bounds[key]
        p[key]=_mutate_value(rng,p[key],lo,hi,typ,scale)
    return CandidateSpec(base.family,name,p)


def _crossover(a: CandidateSpec,b: CandidateSpec,cfg: dict,rng: random.Random,name: str) -> CandidateSpec:
    bounds=effective_bounds(cfg,a.family); p={}
    for k,(lo,hi,typ) in bounds.items():
        av=float(a.params[k]); bv=float(b.params[k])
        if rng.random()<0.55:
            v=(av+bv)/2.0
        else:
            v=av if rng.random()<0.5 else bv
        p[k]=int(round(v)) if typ is int else float(v)
    # one mutation keeps children from being boring photocopies of their parents
    key=rng.choice(list(bounds)); lo,hi,typ=bounds[key]
    p[key]=_mutate_value(rng,p[key],lo,hi,typ,0.12)
    return CandidateSpec(a.family,name,p)


def _seed_hybrid_from_best_gru(spec: CandidateSpec, board, specs_by_name, cfg: dict, rng: random.Random) -> CandidateSpec:
    """Backward-compatible name; seeds any temporal→policy hybrid from its best temporal parent."""
    if not is_hybrid_family(spec.family):
        return spec
    parts=hybrid_parts(spec.family)
    if not parts:
        return spec
    temporal,_policy=parts
    parents=_top_specs(board,specs_by_name,temporal,limit=3)
    if not parents:
        return spec
    base=parents[0]; p=dict(spec.params); gp=base.params
    prefix="temporal_" if str(spec.family).startswith("hybrid::") else "gru_"
    bounds=effective_bounds(cfg,spec.family)
    for src,value in gp.items():
        if src=="training_memory_months": continue
        dst=prefix+src
        if dst not in bounds: continue
        lo,hi,typ=bounds[dst]; v=max(float(lo),min(float(hi),float(value)))
        if rng.random()<0.35: v=_mutate_value(rng,v,lo,hi,typ,0.08)
        p[dst]=int(round(v)) if typ is int else float(v)
    return CandidateSpec(spec.family,spec.name,p)


def _apply_strategy_preferences(spec: CandidateSpec, strategy: dict | None, rng: random.Random) -> CandidateSpec:
    strategy=strategy or {}
    months=list(strategy.get("preferred_training_memory_months") or [])
    if months and "training_memory_months" in spec.params:
        p=dict(spec.params); p["training_memory_months"]=int(rng.choice(months))
        return CandidateSpec(spec.family,spec.name,p)
    return spec


def _hybrid_ablation_population(cfg:dict, block:dict, n:int, round_no:int)->tuple[list[CandidateSpec],dict]:
    """Build deterministic single-vs-hybrid arms from the same temporal architecture draw.

    Owner topology allocation remains authoritative.  A hybrid draw supplies temporal_*
    parameters to its standalone temporal control whenever possible, so the experiment
    tests the policy head/topology rather than unrelated temporal capacity.
    """
    pairs=[x for x in (block.get("ablation_pairs") or []) if isinstance(x,dict)]
    if not pairs or n<=0:
        return [],{"phase":"HYBRID_ABLATION","reason":"NO_VALID_ABLATION_PAIRS"}
    hp=configured_hybrid_priority(cfg,legacy_none=True)
    singles=[str(x.get("single")) for x in pairs]; hybrids=[str(x.get("hybrid")) for x in pairs]
    if hp is None:
        target_single=n//2; target_hybrid=n-target_single
    else:
        alloc=allocation_counts(n,hp,single_available=bool(singles),hybrid_available=bool(hybrids))
        target_single=int(alloc.get("single",0)); target_hybrid=int(alloc.get("hybrid",0))
    rng=random.Random(int(cfg.get("seed",42))+round_no*15485863)
    out=[]; single_left=target_single; hybrid_left=target_hybrid; serial=1; group=0
    while (single_left>0 or hybrid_left>0) and group < max(n*3,12):
        pair=pairs[group % len(pairs)]; sfam=str(pair.get("single")); hfam=str(pair.get("hybrid")); group+=1
        h=random_candidate(cfg,hfam,rng,f"ablate_r{round_no:02d}_g{group:02d}_hybrid_{serial:02d}")
        # Derive the single arm from the hybrid temporal draw.
        sb=effective_bounds(cfg,sfam); sp={}
        for key,(lo,hi,typ) in sb.items():
            src="training_memory_months" if key=="training_memory_months" else "temporal_"+key
            if src in h.params:
                v=h.params[src]
                try:
                    vv=max(float(lo),min(float(hi),float(v))); sp[key]=int(round(vv)) if typ is int else float(vv)
                except Exception:
                    pass
        if len(sp)<len(sb):
            fallback=random_candidate(cfg,sfam,rng,f"ablate_r{round_no:02d}_g{group:02d}_single_seed_{serial:02d}")
            for k in sb: sp.setdefault(k,fallback.params[k])
        single=CandidateSpec(sfam,f"ablate_r{round_no:02d}_g{group:02d}_single_{serial:02d}",sp)
        if single_left>0:
            v=validate_candidate({"family":single.family,"name":single.name,"params":single.params},cfg,serial)
            if v is not None: out.append(v); single_left-=1; serial+=1
        if hybrid_left>0:
            v=validate_candidate({"family":h.family,"name":h.name,"params":h.params},cfg,serial)
            if v is not None: out.append(v); hybrid_left-=1; serial+=1
    rng.shuffle(out)
    return out[:n],{
        "phase":"HYBRID_ABLATION","mode":"PAIRED_TEMPORAL_CONTROL",
        "block_id":block.get("block_id"),"pairs":pairs,
        "target_single_candidates":target_single,"target_hybrid_candidates":target_hybrid,
        "single_candidates":sum(not is_hybrid_family(x.family) for x in out[:n]),
        "hybrid_candidates":sum(is_hybrid_family(x.family) for x in out[:n]),
        "configured_hybrid_priority":hp,
        "decision_contract":"FINAL_[PSELL,PSKIP,PBUY]_SAME_AUTHORITY",
    }


def plan_next_candidates(board: list[dict], specs_by_name: dict[str,CandidateSpec], cfg: dict, round_no: int, n: int, llm_strategy: dict | None = None, experiment_block: dict | None = None) -> tuple[list[CandidateSpec],dict]:
    """Adaptive exploration/exploitation/crossover planner.

    LLM may suggest priorities and exploration ratio, but Supervisor clamps them.
    Candidate parameters always remain inside the registry bounds.
    """
    if n<=0: return [],{}
    if experiment_block and str(experiment_block.get("mode"))=="HYBRID_ABLATION":
        return _hybrid_ablation_population(cfg,experiment_block,n,round_no)
    # Initial Discovery has no evidence to justify random preference. Use the
    # registry-driven stratified/space-filling generator as the normal round-1 path,
    # not merely as an emergency fallback. Adaptive mutation/crossover starts later.
    if round_no == 1 and not board:
        seeded=generate_initial_population(cfg,n,round_no=round_no)
        if experiment_block:
            from research.experiment_blocks import apply_block_to_spec
            seeded=[apply_block_to_spec(x,experiment_block,cfg,i) for i,x in enumerate(seeded,1)]
        valid=[]
        for i,x in enumerate(seeded,1):
            v=validate_candidate({"family":x.family,"name":x.name,"params":x.params},cfg,i)
            if v is not None:
                valid.append(v)
        hp=configured_hybrid_priority(cfg,legacy_none=True)
        hy=sum(1 for x in valid if is_hybrid_family(x.family))
        return valid,{
            "round":round_no,"requested":n,"phase":"STRATIFIED_INITIAL_DISCOVERY",
            "exploration_ratio":1.0,"explore_count":len(valid),"exploit_count":0,
            "family_weights":{},"family_stats":family_stats(board,cfg),
            "llm_strategy_used":llm_strategy or {},"configured_hybrid_priority":hp,
            "target_single_candidates":None if hp is None else allocation_counts(n,hp,single_available=any(not is_hybrid_family(f) for f in enabled_families(cfg)),hybrid_available=any(is_hybrid_family(f) for f in enabled_families(cfg))).get("single"),
            "target_hybrid_candidates":None if hp is None else allocation_counts(n,hp,single_available=any(not is_hybrid_family(f) for f in enabled_families(cfg)),hybrid_available=any(is_hybrid_family(f) for f in enabled_families(cfg))).get("hybrid"),
            "single_candidates":len(valid)-hy,"hybrid_candidates":hy,
            "estimated_compute_allocation":_estimated_compute_share(valid,family_stats(board,cfg)),
        "family_size_priority_schema":"CP_FAMILY_SIZE_PRIORITY_V1",
        "family_size_priorities":configured_family_size_priorities(cfg),
            "initial_sampling":"REGISTRY_STRATIFIED_SPACE_FILLING",
        }
    search=cfg.get("agent",{}).get("search",{})
    _profile=(llm_strategy or {}).get("_creativity_profile") if isinstance((llm_strategy or {}).get("_creativity_profile"),dict) else adaptive_creativity_profile(cfg,board=board,stale_rounds=int((llm_strategy or {}).get("_stale_rounds",0) or 0))
    default_explore=max(float(search.get("exploration_ratio",0.45)),float(_profile.get("target_exploration_ratio",0.45)))
    ranked=sorted(board,key=lambda r:(bool(r.get("cv_gate_pass")),float(r.get("selection_score",-1e99))),reverse=True)
    best=float(ranked[0].get("selection_score",-1e99)) if ranked else -1e99
    top=[float(r.get("selection_score",-1e99)) for r in ranked[:5]]
    span=(max(top)-min(top)) if len(top)>=2 else 999.0
    explore=default_explore
    if best<0: explore=max(explore,0.60)
    if len(top)>=3 and span<2.0: explore=max(explore,0.65)
    if llm_strategy and "exploration_ratio" in llm_strategy:
        llm_ratio=max(0.15,min(0.85,float(llm_strategy["exploration_ratio"])))
        weight=llm_research_influence(cfg)
        explore=(1-weight)*explore+weight*llm_ratio
    explore=max(0.15,min(0.85,explore))
    weights=adaptive_family_weights(board,cfg,llm_strategy)
    rng=random.Random(int(cfg.get("seed",42))+round_no*104729)
    topology_priority=effective_hybrid_priority(cfg,llm_strategy,legacy_none=True)
    topology_allocation=None
    topology_slots=[None]*n
    if topology_priority is not None:
        single_fams,hybrid_fams=split_families(weights.keys())
        topology_allocation=allocation_counts(
            n,topology_priority,single_available=bool(single_fams),hybrid_available=bool(hybrid_fams)
        )
        topology_slots=(
            ["SINGLE"]*int(topology_allocation.get("single",0)) +
            ["HYBRID"]*int(topology_allocation.get("hybrid",0))
        )
        rng.shuffle(topology_slots)
    n_explore=max(1,min(n-1 if n>1 else 1,int(round(n*explore))))
    n_exploit=n-n_explore
    crossover_ratio=float(search.get("crossover_ratio",0.30))
    out=[]; serial=1

    def _choose_family(slot):
        w=_filtered_topology_weights(weights,slot)
        return _weighted_family(rng,w or weights)

    for slot in topology_slots[:n_explore]:
        fam=_choose_family(slot)
        s=random_candidate(cfg,fam,rng,f"explore_r{round_no:02d}_{fam}_{serial:02d}")
        s=_seed_hybrid_from_best_gru(s,board,specs_by_name,cfg,rng)
        s=_apply_strategy_preferences(s,llm_strategy,rng)
        out.append(s); serial+=1

    for slot in topology_slots[n_explore:]:
        fam=_choose_family(slot)
        parents=_top_specs(board,specs_by_name,fam,limit=6)
        if len(parents)>=2 and rng.random()<crossover_ratio:
            a,b=rng.sample(parents,2)
            s=_crossover(a,b,cfg,rng,f"cross_r{round_no:02d}_{fam}_{serial:02d}")
        elif parents:
            # later rounds become more local, but never zero-radius
            scale=max(0.06,0.24/(1.0+0.18*round_no))*float(_profile.get("mutation_scale_multiplier",1.0))
            scale=max(0.04,min(0.40,scale))
            s=_local_mutation(parents[0 if rng.random()<0.6 else min(len(parents)-1,1)],cfg,rng,f"refine_r{round_no:02d}_{fam}_{serial:02d}",scale)
        else:
            s=random_candidate(cfg,fam,rng,f"explore_r{round_no:02d}_{fam}_{serial:02d}")
        s=_seed_hybrid_from_best_gru(s,board,specs_by_name,cfg,rng)
        s=_apply_strategy_preferences(s,llm_strategy,rng)
        out.append(s); serial+=1

    hybrid_only=bool(weights) and all(is_hybrid_family(f) for f in weights)
    if topology_priority is None:
        hybrid_cap=n if hybrid_only else max(0,int(search.get("hybrid_max_per_round",2)))
        hybrid_seen=0
        nonhybrid_weights={f:w for f,w in weights.items() if not is_hybrid_family(f)}
        if nonhybrid_weights:
            sw=sum(nonhybrid_weights.values()) or 1.0
            nonhybrid_weights={f:w/sw for f,w in nonhybrid_weights.items()}
        bounded=[]
        for s0 in out:
            s=s0
            if is_hybrid_family(s.family):
                if hybrid_seen >= hybrid_cap and nonhybrid_weights:
                    fam=_weighted_family(rng,nonhybrid_weights)
                    s=random_candidate(cfg,fam,rng,f"explore_r{round_no:02d}_{fam}_{serial:02d}")
                    serial+=1
                else:
                    hybrid_seen+=1
            bounded.append(s)
        out=bounded
    else:
        hybrid_cap=int((topology_allocation or {}).get("hybrid",0))

    if experiment_block:
        from research.experiment_blocks import apply_block_to_spec
        out=[apply_block_to_spec(s,experiment_block,cfg,i) for i,s in enumerate(out,1)]
    valid=[]
    for i,s in enumerate(out,1):
        v=validate_candidate({"family":s.family,"name":s.name,"params":s.params},cfg,i)
        if v is not None: valid.append(v)
    actual_hybrids=sum(1 for s in valid if is_hybrid_family(s.family))
    plan={
        "round":round_no,"requested":n,"exploration_ratio":explore,
        "explore_count":n_explore,"exploit_count":n_exploit,
        "family_weights":weights,"family_stats":family_stats(board,cfg),
        "llm_strategy_used":llm_strategy or {},
        "hybrid_stage_unlocked":bool(topology_priority is not None) or hybrid_only or any(r.get("family")=="gru" for r in board),
        "hybrid_only_mode":hybrid_only,
        "hybrid_max_per_round":hybrid_cap,
        "topology_priority_schema":"CP_TOPOLOGY_PRIORITY_V1" if topology_priority is not None else "LEGACY_HYBRID_CAP",
        "configured_hybrid_priority":topology_priority,
        "configured_single_priority":None if topology_priority is None else 1.0-float(topology_priority),
        "target_single_candidates":None if topology_allocation is None else int(topology_allocation.get("single",0)),
        "target_hybrid_candidates":None if topology_allocation is None else int(topology_allocation.get("hybrid",0)),
        "topology_constraint":None if topology_allocation is None else topology_allocation.get("constraint"),
        "single_candidates":len(valid)-actual_hybrids,
        "hybrid_candidates":actual_hybrids,
        "estimated_compute_allocation":_estimated_compute_share(valid,family_stats(board,cfg)),
        "family_size_priority_schema":"CP_FAMILY_SIZE_PRIORITY_V1",
        "family_size_priorities":configured_family_size_priorities(cfg),
        "experiment_block_id":(experiment_block or {}).get("block_id"),"experiment_block_mode":(experiment_block or {}).get("mode"),
        "generation_memory_used":bool((cfg.get("agent",{}) or {}).get("generation_memory")),
        "memory_elite_count":len(((cfg.get("agent",{}) or {}).get("generation_memory") or {}).get("elites") or []),
        "preferred_training_memory_months":list((llm_strategy or {}).get("preferred_training_memory_months") or []),
        "creativity_profile":_profile,
        "llm_research_influence":llm_research_influence(cfg),
    }
    return valid,plan
