from __future__ import annotations

import importlib.util
from copy import deepcopy
from typing import Any

from models.model_registry import (
    family_spec, make_hybrid_family, hybrid_parts, registry_for_scientist,
    temporal_families, policy_families, is_hybrid_family, dynamic_hybrid_families, configured_family_size_priorities, SIZE_PRIORITY_SCHEMA,
)
from models.capacity_governor import recommended_capacity_envelopes, summarize_capacity_evidence_by_family, summarize_capacity_evidence
from models.topology_allocation import clamp_hybrid_priority
from host.resource_preflight import compile_resource_capacity
from host.compute_backend import backend_for_family
from core.training_method_contract import training_method_context

SCHEMA = "CP_SCIENTIST_CAPACITY_RESEARCH_PLAN_V5_FAMILY_SIZE_PRIORITY"


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _hardware_numbers(profile: dict) -> tuple[float, float, bool, int]:
    mem = profile.get("memory") or {}
    ram = float(mem.get("total_gib") or 0.0)
    gpus = list(((profile.get("nvidia") or {}).get("devices") or []))
    vram = float((gpus[0] if gpus else {}).get("memory_total_gib") or 0.0)
    cuda = bool((profile.get("torch") or {}).get("cuda_available"))
    cpu=profile.get("cpu") or {}
    # Scheduling may use a conservative estimate when physical topology is unavailable,
    # but never relabel logical SMT threads as physical cores.
    physical=cpu.get("physical_cores")
    logical=max(1,int(cpu.get("logical_threads") or 1))
    planning=int(cpu.get("planning_cores") or physical or (logical//2 if logical>=4 else logical) or 1)
    return ram, vram, cuda, max(1,planning)


def _selection_policy(cfg: dict | None, base_families: set[str]) -> tuple[str, set[str]]:
    ra = ((cfg or {}).get("research_architecture") or {})
    mode = str(ra.get("family_selection_mode") or "AUTO").upper().strip()
    if mode not in {"AUTO", "MANUAL", "SCIENTIST_DIRECTED"}:
        mode = "AUTO"
    raw = ra.get("allowed_families") if isinstance(ra.get("allowed_families"), list) else []
    allowed = {str(x).strip().lower() for x in raw if str(x).strip().lower() in base_families}
    if mode == "AUTO":
        allowed = set(base_families)
    return mode, allowed


def capability_catalog(profile: dict, cfg: dict | None = None) -> dict[str, Any]:
    reg = registry_for_scientist(); ram, vram, cuda, cores = _hardware_numbers(profile)
    resolved = ((cfg or {}).get("resolved_compute") or {}) if isinstance(cfg,dict) else {}
    base_specs = reg.get("base_families") or {}
    selection_mode, allowed = _selection_policy(cfg, set(base_specs))
    out = {}
    for family, spec in (reg.get("base_families") or {}).items():
        reasons = []
        feasible = True
        if family == "xgboost" and not _module_available("xgboost"):
            feasible = False; reasons.append("XGBOOST_NOT_INSTALLED")
        if family == "lightgbm" and not _module_available("lightgbm"):
            feasible = False; reasons.append("LIGHTGBM_NOT_INSTALLED")
        if spec.get("requires_torch") and not _module_available("torch"):
            feasible = False; reasons.append("PYTORCH_NOT_INSTALLED")
        if resolved:
            backend = backend_for_family(resolved, family, spec)
        else:
            backend = "CUDA" if (spec.get("requires_torch") and cuda) else "CPU"
            if family == "xgboost" and cuda:
                backend = "CUDA_OR_CPU"
            if family == "lightgbm":
                backend = "CPU_OR_OPENCL"
        accelerated = backend in {"CUDA","ROCM","OPENCL_GPU"}
        compute_class = "LOW"
        if spec.get("role") == "temporal":
            compute_class = "MEDIUM" if accelerated or family in {"tcn", "gru", "lstm"} else "HIGH"
            if family in {"transformer","transformer_moe","patchtst","itransformer","tft"} and not accelerated:
                compute_class = "HIGH"
        permitted = family in allowed
        out[family] = {
            "feasible": bool(feasible), "reasons": reasons or ["OK"],
            "category": spec.get("category"), "role": spec.get("role"),
            "compute_class": compute_class, "preferred_backend": backend,
            "permitted": bool(permitted),
            "eligible": bool(feasible and permitted),
        }
    return {
        "schema": "CP_MODEL_FEASIBILITY_V1",
        "hardware": {
            "ram_gib": ram if ram > 0 else None, "vram_gib": vram if vram > 0 else None, "cuda_available": cuda,
            "physical_cores": (profile.get("cpu") or {}).get("physical_cores"),
            "logical_threads": (profile.get("cpu") or {}).get("logical_threads"),
            "planning_cores": cores,
            "core_count_source": (profile.get("cpu") or {}).get("core_count_source") or "LEGACY_OR_UNKNOWN",
            "ram_source": (profile.get("memory") or {}).get("source") or "LEGACY_OR_UNKNOWN",
        },
        "families": out,
        "selection": {
            "mode": selection_mode,
            "allowed_families": sorted(allowed),
            "eligible_families": sorted([f for f, row in out.items() if row.get("eligible")]),
        },
        "composition_grammar": reg.get("composition_grammar"),
        "temporal_families": reg.get("temporal_families"),
        "policy_families": reg.get("policy_families"),
    }


def recommended_parameter_envelopes(profile: dict, capacity: dict | None = None, compute_plan: dict | None = None) -> dict[str, dict[str, Any]]:
    """Hardware + dataset-aware recommendations using per-family backend truth."""
    ram, vram, cuda, cores = _hardware_numbers(profile)
    temporal_backend=str(((compute_plan or {}).get("temporal_dl") or {}).get("backend") or ("CUDA" if cuda else "CPU"))
    xgb_backend=str(((compute_plan or {}).get("xgboost") or {}).get("backend") or ("CUDA" if cuda else "CPU"))
    temporal_accel=temporal_backend in {"CUDA","ROCM"}
    xgb_accel=xgb_backend == "CUDA"
    gpu8 = temporal_accel and vram >= 7.0
    gpu_big = temporal_accel and vram >= 12.0
    cpu_only = not temporal_accel
    env = {
        "xgboost": {"max_depth": [2, 14 if xgb_accel else 10], "n_estimators": [100, 2500], "training_memory_months": [6, 96]},
        "lightgbm": {"max_depth": [3, 12], "num_leaves": [7, 255], "n_estimators": [100, 3000], "training_memory_months": [6, 96]},
        "random_forest": {"max_depth": [4, 28], "n_estimators": [100, 1200], "training_memory_months": [6, 96]},
        "gru": {
            "sequence_length": [32, 128 if cpu_only else (384 if gpu8 else 256)],
            "hidden_size": [32, 128 if cpu_only else (384 if gpu_big else 256)], "num_layers": [1, 3],
            "epochs": [10, 100], "batch_size": [32, 256 if cpu_only else 512],
        },
        "lstm": {
            "sequence_length": [32, 128 if cpu_only else (384 if gpu8 else 256)],
            "hidden_size": [32, 128 if cpu_only else (320 if gpu_big else 224)], "num_layers": [1, 3],
            "epochs": [10, 100], "batch_size": [32, 256 if cpu_only else 512],
        },
        "tcn": {
            "sequence_length": [32, 256 if cpu_only else 512], "tcn_channels": [16, 64 if cpu_only else (192 if gpu8 else 128)],
            "tcn_blocks": [2, 6], "kernel_size": [2, 5], "epochs": [10, 120],
        },
        "transformer": {
            "sequence_length": [32, 128 if cpu_only else (256 if gpu8 else 192)],
            "d_model": [32, 96 if cpu_only else (256 if gpu8 else 160)], "num_layers": [1, 4 if gpu8 else 2],
            "attention_heads": [1, 8 if gpu8 else 4], "epochs": [8, 80],
        },
    }
    cap = recommended_capacity_envelopes(capacity or {}, profile) if capacity else None
    high = int((cap or {}).get("preferred_total_params", [150000, 400000])[1])
    if high <= 450_000:
        moe = {"sequence_length":[64,192],"d_model":[32,80],"hidden_size":[32,80],"num_layers":[2,4],"attention_heads":[2,4],"expert_ffn":[64,256],"num_experts":[3,5],"top_k":[1,2],"epochs":[8,80],"batch_size":[16,256]}
    elif high <= 900_000:
        moe = {"sequence_length":[64,256],"d_model":[48,128],"hidden_size":[48,128],"num_layers":[2,4],"attention_heads":[2,8],"expert_ffn":[96,384],"num_experts":[3,6],"top_k":[1,2],"epochs":[8,100],"batch_size":[16,256]}
    else:
        moe = {"sequence_length":[64,384],"d_model":[64,192],"hidden_size":[64,192],"num_layers":[2,5],"attention_heads":[2,8],"expert_ffn":[128,768],"num_experts":[3,8],"top_k":[1,2],"epochs":[8,120],"batch_size":[8,256]}
    moe.update({"router_temperature":[0.5,1.5],"load_balance_coef":[0.001,0.05],"dropout":[0.05,0.30],
                "learning_rate":[0.0001,0.002],"weight_decay":[0.000001,0.01],"training_memory_months":[6,60]})
    env["transformer_moe"] = moe
    # Transformer-family alternatives remain capacity-bounded; they are research
    # alternatives, not automatic upgrades over simpler TCN/GRU/tree baselines.
    if high <= 450_000:
        env["patchtst"]={"sequence_length":[64,192],"d_model":[32,80],"hidden_size":[32,80],"num_layers":[1,3],"attention_heads":[2,4],"ffn_mult":[2,4],"patch_len":[8,24],"patch_stride":[4,16],"epochs":[8,80],"batch_size":[16,256],"training_memory_months":[6,60]}
        env["itransformer"]={"sequence_length":[64,192],"d_model":[32,96],"hidden_size":[32,96],"num_layers":[1,3],"attention_heads":[2,4],"ffn_mult":[2,4],"epochs":[8,80],"batch_size":[16,256],"training_memory_months":[6,60]}
        env["tft"]={"sequence_length":[48,160],"d_model":[24,72],"hidden_size":[24,72],"num_layers":[1,2],"attention_heads":[1,4],"ffn_mult":[2,3],"tft_lstm_layers":[1,2],"epochs":[8,70],"batch_size":[16,192],"training_memory_months":[6,48]}
    elif high <= 900_000:
        env["patchtst"]={"sequence_length":[64,256],"d_model":[48,128],"hidden_size":[48,128],"num_layers":[1,4],"attention_heads":[2,8],"ffn_mult":[2,4],"patch_len":[8,32],"patch_stride":[4,16],"epochs":[8,100],"batch_size":[16,256],"training_memory_months":[6,72]}
        env["itransformer"]={"sequence_length":[64,256],"d_model":[48,144],"hidden_size":[48,144],"num_layers":[1,4],"attention_heads":[2,8],"ffn_mult":[2,4],"epochs":[8,100],"batch_size":[16,256],"training_memory_months":[6,72]}
        env["tft"]={"sequence_length":[48,192],"d_model":[32,96],"hidden_size":[32,96],"num_layers":[1,3],"attention_heads":[1,4],"ffn_mult":[2,4],"tft_lstm_layers":[1,2],"epochs":[8,90],"batch_size":[16,192],"training_memory_months":[6,60]}
    else:
        env["patchtst"]={"sequence_length":[64,384],"d_model":[64,192],"hidden_size":[64,192],"num_layers":[1,5],"attention_heads":[2,8],"ffn_mult":[2,6],"patch_len":[8,48],"patch_stride":[4,24],"epochs":[8,120],"batch_size":[8,256],"training_memory_months":[6,96]}
        env["itransformer"]={"sequence_length":[64,384],"d_model":[64,192],"hidden_size":[64,192],"num_layers":[1,5],"attention_heads":[2,8],"ffn_mult":[2,6],"epochs":[8,120],"batch_size":[8,256],"training_memory_months":[6,96]}
        env["tft"]={"sequence_length":[48,256],"d_model":[48,128],"hidden_size":[48,128],"num_layers":[1,3],"attention_heads":[1,8],"ffn_mult":[2,4],"tft_lstm_layers":[1,3],"epochs":[8,110],"batch_size":[8,192],"training_memory_months":[6,72]}
    for fam in ("patchtst","itransformer","tft"):
        env[fam].update({"dropout":[0.05,0.30],"learning_rate":[0.0001,0.002],"weight_decay":[0.000001,0.01]})
    return env



def executable_parameter_envelope(family: str, recommended: dict | None = None) -> dict:
    """Executable generation envelope with capacity dimensions widened to legal bounds.

    Historical recommended envelopes remain the normal starting region. They are not
    allowed to become a hidden hard ceiling for temporal architecture capacity. Non-size
    optimizer/regularization knobs keep their conservative recommendation when present.
    Hard candidate admission is performed later from actual parameter count plus
    legal/resource/scientific capacity authority.
    """
    fam=str(family or "").lower().strip()
    spec=family_spec(fam) or {}
    legal=spec.get("search") or {}
    recommended=recommended if isinstance(recommended,dict) else {}
    role=str(spec.get("role") or "")
    size_keys=set(spec.get("size_parameters") or [])
    temporal_capacity_keys=set()
    architecture_shape_keys={
        "sequence_length","training_memory_months","attention_heads","kernel_size",
        "patch_len","patch_stride","tft_lstm_layers","top_k",
    }
    if role=="temporal":
        temporal_capacity_keys=set(size_keys)|{k for k in legal if k in architecture_shape_keys}
    elif is_hybrid_family(fam):
        temporal_capacity_keys={k for k in size_keys if str(k).startswith(("temporal_","gru_"))}
        for key in legal:
            sk=str(key)
            suffix=sk[len("temporal_"):] if sk.startswith("temporal_") else (sk[len("gru_"):] if sk.startswith("gru_") else sk)
            if suffix in architecture_shape_keys and (sk.startswith(("temporal_","gru_")) or sk=="training_memory_months"):
                temporal_capacity_keys.add(key)
        temporal_capacity_keys.add("training_memory_months")
    out={}
    for key,meta in legal.items():
        lo=meta.get("min"); hi=meta.get("max")
        raw=recommended.get(key)
        if key in temporal_capacity_keys:
            out[key]=[lo,hi]
        elif isinstance(raw,(list,tuple)) and len(raw)>=2:
            try:
                rlo=max(float(lo),float(raw[0])); rhi=min(float(hi),float(raw[1]))
                if rlo<=rhi:
                    typ=int if str(meta.get("type"))=="int" else float
                    out[key]=[int(round(rlo)) if typ is int else rlo,int(round(rhi)) if typ is int else rhi]
                else:
                    out[key]=[lo,hi]
            except Exception:
                out[key]=[lo,hi]
        else:
            out[key]=[lo,hi]
    return out


def hybrid_executable_parameter_envelope(family: str, recommended_env: dict) -> dict:
    """Hybrid executable envelope: widen temporal capacity only, keep tree guidance."""
    base=hybrid_recommended_parameter_envelope(family,recommended_env)
    return executable_parameter_envelope(family,base)

def _intersect_envelope(family: str, proposed: dict | None, fallback: dict | None) -> dict:
    """Intersect a proposal with deterministic executable envelope + legality.

    The fallback is an executable search envelope, not the historical recommended
    starting envelope. Candidate-specific resource/scientific capacity is still checked
    from actual executable parameter count before training.
    """
    spec=family_spec(family) or {}; legal=spec.get("search") or {}; out={}
    proposed=proposed if isinstance(proposed,dict) else {}
    fallback=fallback if isinstance(fallback,dict) else {}

    def parse(raw):
        if not (isinstance(raw,(list,tuple)) and len(raw)>=2):
            return None
        try:
            lo=float(raw[0]); hi=float(raw[1])
            return (lo,hi) if lo<=hi else (hi,lo)
        except Exception:
            return None

    for key,meta in legal.items():
        fr=parse(fallback.get(key)); pr=parse(proposed.get(key))
        chosen=None
        if fr is not None and pr is not None:
            lo=max(fr[0],pr[0]); hi=min(fr[1],pr[1])
            chosen=(lo,hi) if lo<=hi else fr
        elif pr is not None:
            chosen=pr
        elif fr is not None:
            chosen=fr
        if chosen is None:
            continue
        try:
            lo,hi=chosen
            nlo=max(float(meta.get("min")),lo); nhi=min(float(meta.get("max")),hi)
            if nlo<=nhi:
                typ=int if str(meta.get("type"))=="int" else float
                out[key]=[int(round(nlo)) if typ is int else nlo,int(round(nhi)) if typ is int else nhi]
        except Exception:
            continue
    return out


def _range_intersection(a, b):
    if not (isinstance(a,(list,tuple)) and len(a)>=2):
        return list(b[:2]) if isinstance(b,(list,tuple)) and len(b)>=2 else None
    if not (isinstance(b,(list,tuple)) and len(b)>=2):
        return list(a[:2])
    try:
        alo,ahi=float(a[0]),float(a[1]); blo,bhi=float(b[0]),float(b[1])
        if alo>ahi: alo,ahi=ahi,alo
        if blo>bhi: blo,bhi=bhi,blo
        lo=max(alo,blo); hi=min(ahi,bhi)
        return [lo,hi] if lo<=hi else None
    except Exception:
        return None


def hybrid_recommended_parameter_envelope(family: str, recommended_env: dict) -> dict:
    """Compose a dynamic hybrid safe envelope from its two base-family envelopes.

    This is the R6 repair authority: a hybrid component may never silently fall back
    to wider registry bounds than the same base family would receive standalone.
    Shared training-memory is the intersection of both component recommendations.
    """
    parts=hybrid_parts(family)
    if not parts:
        return {}
    temporal,policy=parts
    tenv=(recommended_env or {}).get(temporal) or {}
    penv=(recommended_env or {}).get(policy) or {}
    out={}
    prefix="temporal_" if str(family).startswith("hybrid::") else "gru_"
    for key,value in tenv.items():
        if key=="training_memory_months":
            continue
        if isinstance(value,(list,tuple)) and len(value)>=2:
            out[prefix+key]=list(value[:2])
    for key,value in penv.items():
        if key=="training_memory_months":
            continue
        if isinstance(value,(list,tuple)) and len(value)>=2:
            out["policy_"+key]=list(value[:2])
    tm=_range_intersection(tenv.get("training_memory_months"),penv.get("training_memory_months"))
    if tm is not None:
        out["training_memory_months"]=tm
    # Re-clamp to the composed registry search schema so future registry changes
    # cannot make this helper an accidental widening path.
    return _intersect_envelope(family,None,out)


def _feasible_set(catalog: dict) -> set[str]:
    # For research compilation, feasibility is not enough: MANUAL mode also
    # constrains the legal family universe chosen by the Owner.
    return {
        f for f, row in (catalog.get("families") or {}).items()
        if bool((row or {}).get("feasible")) and bool((row or {}).get("permitted", True))
    }


def _normalize_family(raw: str, feasible: set[str]) -> str | None:
    fam = str(raw or "").strip().lower()
    if not fam:
        return None
    if fam in feasible:
        return fam
    parts = hybrid_parts(fam)
    if parts and parts[0] in feasible and parts[1] in feasible:
        return make_hybrid_family(*parts)
    return None


def _ensure_topology_universe(active: list[str], feasible: set[str], hybrid_priority: float) -> tuple[list[str], list[str], list[str]]:
    """Ensure the executable portfolio can honor the Owner topology slider when legal.

    The Scientist still chooses families.  This compiler only adds the minimum legal
    component/composition needed to make the requested SINGLE/HYBRID allocation
    executable.  MANUAL family selection remains a harder authority because ``feasible``
    is already constrained by the Owner checklist.
    """
    active=list(dict.fromkeys(str(x).lower() for x in active if x))
    constraints=[]; auto_hybrids=[]
    p=clamp_hybrid_priority(hybrid_priority)

    def singles(): return [f for f in active if not is_hybrid_family(f)]
    def hybrids(): return [f for f in active if is_hybrid_family(f)]
    def role_pool(role):
        return [f for f in singles() if (family_spec(f) or {}).get("role")==role]

    # If a hybrid share is requested but Scientist supplied no hybrid, compose from
    # its active components first.  If one side is missing, add the smallest legal
    # component from the Owner-permitted feasible universe, then compose.
    if p > 0.0 and not hybrids():
        temporal=role_pool("temporal")
        policy=role_pool("policy")
        if not temporal:
            pref=("tcn","gru","patchtst","itransformer","transformer","lstm","tft","transformer_moe")
            pick=next((f for f in pref if f in feasible and (family_spec(f) or {}).get("role")=="temporal"),None)
            if pick:
                active.append(pick); temporal=[pick]
        if not policy:
            pref=("lightgbm","xgboost","random_forest")
            pick=next((f for f in pref if f in feasible and (family_spec(f) or {}).get("role")=="policy"),None)
            if pick:
                active.append(pick); policy=[pick]
        for t in temporal:
            for pol in policy:
                fam=make_hybrid_family(t,pol)
                if family_spec(fam) is not None and t in feasible and pol in feasible:
                    active.append(fam); auto_hybrids.append(fam)
                    if len(auto_hybrids)>=4: break
            if len(auto_hybrids)>=4: break
        if not hybrids():
            constraints.append("HYBRID_UNAVAILABLE_IN_ALLOWED_UNIVERSE")

    # Conversely, an explicit hybrid-only Scientist proposal must still expose a
    # single-model control when the Owner requests any non-zero SINGLE share.
    if p < 1.0 and not singles() and hybrids():
        parts=hybrid_parts(hybrids()[0])
        if parts:
            for component in parts:
                if component in feasible and component not in active:
                    active.append(component)
        if not singles():
            constraints.append("SINGLE_UNAVAILABLE_IN_ALLOWED_UNIVERSE")

    return list(dict.fromkeys(active)), constraints, auto_hybrids


def compile_research_plan(strategy: dict | None, profile: dict, cfg: dict, dataset_capacity: dict | None = None) -> dict[str, Any]:
    """Compile an LLM research idea into a deterministic, executable model universe."""
    strategy = strategy if isinstance(strategy, dict) else {}
    catalog = capability_catalog(profile, cfg); feasible = _feasible_set(catalog)
    recommended_env = recommended_parameter_envelopes(profile, dataset_capacity, (cfg.get("resolved_compute") or {}))
    selection = catalog.get("selection") or {}
    _sel_mode=str(selection.get("mode") or "AUTO").upper()
    if _sel_mode=="MANUAL" and not list(selection.get("allowed_families") or []):
        raise RuntimeError("MANUAL_FAMILY_SELECTION_EMPTY")
    if _sel_mode=="SCIENTIST_DIRECTED" and not list(selection.get("allowed_families") or []):
        raise RuntimeError("SCIENTIST_DIRECTED_FAMILY_ALLOWLIST_EMPTY")
    if not feasible:
        raise RuntimeError("NO_ELIGIBLE_MODEL_FAMILY_FOR_CURRENT_HARDWARE_AND_SELECTION")
    requested = strategy.get("active_families") if isinstance(strategy.get("active_families"), list) else []
    active: list[str] = []
    rejected: list[dict] = []
    for raw in requested:
        fam = _normalize_family(str(raw), feasible)
        if fam:
            active.append(fam)
        else:
            rejected.append({"request": str(raw), "reason": "NOT_FEASIBLE_OR_UNKNOWN"})

    hybrids = strategy.get("hybrid_compositions") if isinstance(strategy.get("hybrid_compositions"), list) else []
    for item in hybrids:
        if not isinstance(item, dict):
            rejected.append({"request": item, "reason": "INVALID_HYBRID_SPEC"}); continue
        temporal = str(item.get("temporal") or item.get("encoder") or "").lower().strip()
        policy = str(item.get("policy") or item.get("head") or "").lower().strip()
        if temporal in feasible and policy in feasible and temporal in temporal_families() and policy in policy_families():
            active.append(make_hybrid_family(temporal, policy))
        else:
            rejected.append({"request": item, "reason": "INCOMPATIBLE_OR_UNAVAILABLE_COMPONENT"})

    # v1.3.0 SCIENTIST_DIRECTED: Owner selects the allow-list, not a frozen active subset.
    # Keep every allowed+feasible base family in the Factory universe so the persistent
    # Scientist can perform family escape after evidence invalidates its initial focus.
    _selection_mode=str(selection.get("mode") or "AUTO").upper()
    if _selection_mode=="SCIENTIST_DIRECTED":
        # The Factory universe must retain every Owner-allowed feasible base family and,
        # when topology is Scientist-directed, every compatible hybrid. Otherwise a
        # later family/topology escape can silently lose the exact requested composition
        # and fall back to raw registry bounds instead of its safe component envelope.
        active=sorted(f for f in feasible if not is_hybrid_family(f)) or sorted(feasible)
        _tm=str(((cfg.get("research_architecture") or {}).get("topology_selection_mode") or "OWNER_FIXED")).upper()
        if _tm=="SCIENTIST_DIRECTED":
            base=set(active)
            for hf in dynamic_hybrid_families():
                parts=hybrid_parts(hf)
                if parts and parts[0] in base and parts[1] in base:
                    active.append(hf)
    elif not active:
        # Deterministic fallback must have capability parity with the registry, not a
        # hard-coded shortlist. AUTO/MANUAL retain their historical semantics.
        active = sorted(f for f in feasible if not is_hybrid_family(f))
        if not active:
            active = sorted(feasible)

    # A cheap nonlinear baseline is retained when available so complexity must prove value.
    require_baseline = bool(((cfg.get("research_architecture") or {}).get("require_baseline", True)))
    if require_baseline and not any(f in active for f in ("lightgbm", "xgboost")):
        # Never escape the Owner-selected MANUAL family universe. If no cheap
        # baseline was allowed, preserve that explicit choice.
        for fam in ("lightgbm", "xgboost"):
            if fam in feasible:
                active.insert(0, fam); break

    active = list(dict.fromkeys(active))
    ra = cfg.get("research_architecture") or {}
    _topology_mode=str(ra.get("topology_selection_mode") or "OWNER_FIXED").upper()
    if _topology_mode not in {"OWNER_FIXED","SCIENTIST_DIRECTED"}: _topology_mode="OWNER_FIXED"
    hybrid_priority=clamp_hybrid_priority(ra.get("hybrid_priority",0.50))
    _universe_priority=(0.50 if _topology_mode=="SCIENTIST_DIRECTED" else hybrid_priority)
    active, topology_constraints, auto_hybrids = _ensure_topology_universe(active, feasible, _universe_priority)
    proposed_envs=strategy.get("parameter_envelopes") if isinstance(strategy.get("parameter_envelopes"),dict) else {}
    parameter_envelopes={}
    executable_envs={}
    hybrid_recommended_envs={}
    for fam in active:
        if is_hybrid_family(fam):
            recommended_hybrid=hybrid_recommended_parameter_envelope(fam,recommended_env)
            executable_hybrid=hybrid_executable_parameter_envelope(fam,recommended_env)
            hybrid_recommended_envs[fam]=recommended_hybrid
            executable_envs[fam]=executable_hybrid
            parameter_envelopes[fam]=_intersect_envelope(fam,proposed_envs.get(fam),executable_hybrid)
        else:
            executable=executable_parameter_envelope(fam,recommended_env.get(fam) or {})
            executable_envs[fam]=executable
            parameter_envelopes[fam]=_intersect_envelope(fam,proposed_envs.get(fam),executable)
    parameter_envelopes={k:v for k,v in parameter_envelopes.items() if v}
    capacity_guidance=recommended_capacity_envelopes(dataset_capacity or {},profile) if dataset_capacity else {}
    family_size_priorities=configured_family_size_priorities(cfg)
    resource_budget={
        "safe_ram_fraction": float(ra.get("safe_ram_fraction", 0.75)),
        "safe_vram_fraction": float(ra.get("safe_vram_fraction", 0.80)),
        "max_single_experiment_minutes": int(ra.get("max_single_experiment_minutes", 120)),
        "max_experiments": int((cfg.get("agent") or {}).get("max_experiments", 36)),
    }
    resource_capacity=compile_resource_capacity(profile,resource_budget,dataset_capacity or {},cfg)
    plan = {
        "schema": SCHEMA,
        "mode": str(ra.get("mode") or "SCIENTIST_HARDWARE_ADAPTIVE"),
        "family_selection_mode": str(((catalog.get("selection") or {}).get("mode") or "AUTO")),
        "allowed_families": list(((catalog.get("selection") or {}).get("allowed_families") or [])),
        "eligible_families": list(((catalog.get("selection") or {}).get("eligible_families") or [])),
        "selection_source": ("SCIENTIST_DIRECTED_ALLOWLIST_UNIVERSE" if str(((catalog.get("selection") or {}).get("mode") or "AUTO")).upper()=="SCIENTIST_DIRECTED" else ("SCIENTIST" if (requested or hybrids) else "DETERMINISTIC_FALLBACK")),
        "hardware_profile_hash": profile.get("profile_hash"),
        "active_families": active,
        "requested_active_families": requested,
        "initial_scientist_focus_families": requested if str(((catalog.get("selection") or {}).get("mode") or "AUTO")).upper()=="SCIENTIST_DIRECTED" else [],
        "rejected_requests": rejected,
        "capability_catalog": catalog,
        "recommended_parameter_envelopes": recommended_env,
        "recommended_starting_parameter_envelopes": deepcopy(recommended_env),
        "hybrid_recommended_parameter_envelopes": hybrid_recommended_envs,
        "executable_parameter_envelopes": executable_envs,
        "parameter_envelopes": parameter_envelopes,
        "dataset_capacity_profile": deepcopy(dataset_capacity or {}),
        "capacity_guidance": capacity_guidance,
        "capacity_evidence": summarize_capacity_evidence([]),
        "capacity_evidence_by_family": summarize_capacity_evidence_by_family([], active),
        "family_size_priority_schema": SIZE_PRIORITY_SCHEMA,
        "family_size_priorities": family_size_priorities,
        "family_size_priority_authority": "OWNER_SEARCH_PREFERENCE_INSIDE_DYNAMIC_CAPACITY_NOT_HARD_BOUND_SLICE",
        "capacity_authority": {
            "schema":"MAX_DYNAMIC_MODEL_CAPACITY_AUTHORITY_V1",
            "legal":"MODEL_REGISTRY_IMPLEMENTATION_BOUNDS",
            "resource":"FROZEN_HARDWARE_ARCHITECTURE_SPECIFIC_PREFLIGHT",
            "scientific":"CANDIDATE_MEMORY_SEQUENCE_EFFECTIVE_INFORMATION",
            "recommended_envelope":"STARTING_GUIDANCE_ONLY_NOT_EXECUTABLE_MAXIMUM",
            "effective":"MIN_LEGAL_RESOURCE_SCIENTIFIC_ON_ACTUAL_PARAMETER_COUNT",
        },
        "topology_priority": {
            "schema": "CP_TOPOLOGY_PRIORITY_V1",
            "single": 1.0-hybrid_priority,
            "hybrid": hybrid_priority,
            "mode": _topology_mode,
            "allowed_topologies": ["SINGLE","HYBRID"] if _topology_mode=="SCIENTIST_DIRECTED" else (["SINGLE"] if hybrid_priority<=0 else (["HYBRID"] if hybrid_priority>=1 else ["SINGLE","HYBRID"])),
            "authority": "SCIENTIST_DIRECTED_WITHIN_OWNER_ALLOWLIST" if _topology_mode=="SCIENTIST_DIRECTED" else "OWNER_SLIDER_0_TO_1",
            "allocation_basis": "CANDIDATE_COUNT",
            "constraints": topology_constraints,
            "auto_composed_hybrids": auto_hybrids,
        },
        "resource_budget": resource_budget,
        "resource_capacity": resource_capacity,
        "model_training_method_contract": training_method_context(),
        "llm_strategy_snapshot": {k: deepcopy(strategy.get(k)) for k in ("focus", "active_families", "hybrid_compositions", "parameter_envelopes", "capacity_intent") if k in strategy},
    }
    return plan


def apply_research_plan(cfg: dict, plan: dict) -> dict:
    out = cfg
    out.setdefault("agent", {})["research_plan"] = deepcopy(plan)
    return out


def apply_strategy_parameter_envelopes(plan: dict, strategy: dict | None) -> dict:
    """Apply a later Scientist/Director envelope to the next generation only.

    This keeps the Factory-level family universe fixed while allowing closed-loop
    capacity tuning across Discovery generations.  Every override is re-clamped to
    registry legality and the original recommended envelope remains as fallback.
    """
    out=deepcopy(plan or {})
    strategy=strategy if isinstance(strategy,dict) else {}
    proposed=strategy.get("parameter_envelopes") if isinstance(strategy.get("parameter_envelopes"),dict) else {}
    if not proposed:
        return out
    rec=out.get("recommended_parameter_envelopes") if isinstance(out.get("recommended_parameter_envelopes"),dict) else {}
    hrec=out.get("hybrid_recommended_parameter_envelopes") if isinstance(out.get("hybrid_recommended_parameter_envelopes"),dict) else {}
    executable=out.get("executable_parameter_envelopes") if isinstance(out.get("executable_parameter_envelopes"),dict) else {}
    cur=out.get("parameter_envelopes") if isinstance(out.get("parameter_envelopes"),dict) else {}
    active=list(out.get("active_families") or [])
    for fam in active:
        if fam not in proposed:
            continue
        # Generation review may move/broaden relative to the previous Scientist
        # suggestion inside the frozen executable architecture envelope. Historical
        # recommended envelopes are starting guidance, not a hard maximum. Candidate
        # resource/scientific ceilings are re-evaluated from each exact candidate.
        safe_base=executable.get(fam) if isinstance(executable.get(fam),dict) else None
        if not isinstance(safe_base,dict) or not safe_base:
            safe_base=(hrec.get(fam) if is_hybrid_family(fam) else rec.get(fam))
        if not isinstance(safe_base,dict) or not safe_base:
            safe_base=cur.get(fam) if isinstance(cur.get(fam),dict) else {}
        row=_intersect_envelope(fam,proposed.get(fam),safe_base)
        if row:
            cur[fam]=row
    out["parameter_envelopes"]=cur
    out["generation_capacity_override_source"]="FACTORY_RESEARCH_DIRECTOR"
    return out
