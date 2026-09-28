from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
import json
import math
import random
import hashlib
from typing import Any

from sklearn.ensemble import RandomForestClassifier
from sklearn.utils.class_weight import compute_sample_weight

from models.model_registry import enabled_families, get_bounds, get_distributions, effective_bounds, is_hybrid_family, hybrid_parts, family_spec, family_size_priority
from host.compute_backend import resolve_compute_plan
from models.topology_allocation import configured_hybrid_priority, allocation_counts, split_families
from host.resource_preflight import estimate_candidate_resources, evaluate_resource_limits, candidate_resource_parameter_ceiling
from models.capacity_governor import candidate_scientific_capacity
from core.temporal_index import contract_from_cfg


@dataclass
class CandidateSpec:
    family: str
    name: str
    params: dict

    def __post_init__(self):
        self.family = str(self.family)
        self.params = canonicalize_candidate_params(self.family, self.params)


def canonicalize_candidate_params(family: str, params: dict) -> dict:
    """Normalize parameters to their *effective* estimator meaning.

    This prevents the research memory from treating no-op hyperparameter differences
    as novel experiments (notably PyTorch GRU dropout when num_layers == 1).
    """
    fam = str(family)
    out = dict(params or {})
    if fam in {"gru","lstm"} and int(out.get("num_layers", 1) or 1) <= 1:
        out["dropout"] = 0.0
    if fam == "tcn" and "tcn_channels" in out:
        # tcn_channels is the executable width; hidden_size is a legacy shadow knob.
        out.pop("hidden_size", None)
    if fam in {"transformer","transformer_moe","patchtst","itransformer","tft"}:
        # d_model is the executable width for Transformer-family models.  Keep old
        # artifacts reproducible when d_model is absent, otherwise eliminate the
        # shadow hidden_size dimension so fingerprints represent effective models.
        if "d_model" in out:
            out.pop("hidden_size", None)
        d=max(1,int(out.get("d_model",out.get("hidden_size",64)) or 64)); h=max(1,int(out.get("attention_heads",1) or 1))
        divisors=[x for x in range(min(8,d),0,-1) if d % x == 0]
        out["attention_heads"] = h if d % h == 0 else (divisors[0] if divisors else 1)
        if fam == "transformer_moe":
            ne=max(2,int(out.get("num_experts",4) or 4)); out["num_experts"]=ne
            out["top_k"]=max(1,min(int(out.get("top_k",1) or 1),ne))
        if fam == "patchtst":
            seq=max(8,int(out.get("sequence_length",128) or 128)); pl=max(2,min(int(out.get("patch_len",16) or 16),seq))
            out["patch_len"]=pl; out["patch_stride"]=max(1,min(int(out.get("patch_stride",8) or 8),pl))
    if is_hybrid_family(fam):
        parts=hybrid_parts(fam) or ("gru","")
        temporal=parts[0]
        prefix="temporal_" if fam.startswith("hybrid::") else "gru_"
        if temporal in {"gru","lstm"} and int(out.get(prefix+"num_layers",1) or 1) <= 1:
            out[prefix+"dropout"] = 0.0
        if temporal == "tcn" and prefix+"tcn_channels" in out:
            out.pop(prefix+"hidden_size", None)
        if temporal in {"transformer","transformer_moe","patchtst","itransformer","tft"}:
            if prefix+"d_model" in out:
                out.pop(prefix+"hidden_size", None)
            d=max(1,int(out.get(prefix+"d_model",out.get(prefix+"hidden_size",64)) or 64)); h=max(1,int(out.get(prefix+"attention_heads",1) or 1))
            divisors=[x for x in range(min(8,d),0,-1) if d % x == 0]
            out[prefix+"attention_heads"] = h if d % h == 0 else (divisors[0] if divisors else 1)
            if temporal == "transformer_moe":
                ne=max(2,int(out.get(prefix+"num_experts",4) or 4)); out[prefix+"num_experts"]=ne
                out[prefix+"top_k"]=max(1,min(int(out.get(prefix+"top_k",1) or 1),ne))
            if temporal == "patchtst":
                seq=max(8,int(out.get(prefix+"sequence_length",128) or 128)); pl=max(2,min(int(out.get(prefix+"patch_len",16) or 16),seq))
                out[prefix+"patch_len"]=pl; out[prefix+"patch_stride"]=max(1,min(int(out.get(prefix+"patch_stride",8) or 8),pl))
    return out


def spec_fingerprint(spec: CandidateSpec) -> str:
    return json.dumps({"family": spec.family, "params": canonicalize_candidate_params(spec.family, spec.params)}, sort_keys=True, separators=(",", ":"))


def experiment_fingerprint(spec: CandidateSpec, cfg: dict) -> str:
    """Fingerprint the executable research experiment, not only estimator params.

    The same model hyperparameters under a different label/feature/deployment contract
    are a different experiment and may be researched again. Exact cross-Factory repeats
    under the same contract are skipped.
    """
    payload = {
        "spec": {"family": spec.family, "params": canonicalize_candidate_params(spec.family, spec.params)},
        "label": cfg.get("label") or {},
        "feature_research": cfg.get("feature_research") or {},
        "deployment": {"take_threshold_grid": (cfg.get("deployment") or {}).get("take_threshold_grid")},
        "split": {
            "purge_bars": (cfg.get("split") or {}).get("purge_bars"),
            "embargo_bars": (cfg.get("split") or {}).get("embargo_bars"),
            "walk_forward_folds": (cfg.get("split") or {}).get("walk_forward_folds"),
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def trained_candidate_id(spec: CandidateSpec, cfg: dict, take_threshold: float | None, research_contract_hash: str | None = None) -> str:
    """Identity of one fitted/selected candidate instance.

    ``spec_fingerprint`` intentionally groups equal hyperparameter specifications.
    A trained instance also depends on the deterministic training seed and the final
    threshold selected by WFA, so those must not disappear from provenance.
    """
    import hashlib
    payload = {
        "schema": "CP_TRAINED_CANDIDATE_ID_V1",
        "spec": {"family": spec.family, "params": canonicalize_candidate_params(spec.family, spec.params)},
        "training_seed": int(cfg.get("seed", 42) or 42),
        "take_threshold": None if take_threshold is None else float(take_threshold),
        "research_contract_hash": str(research_contract_hash or ""),
        "experiment_fingerprint": experiment_fingerprint(spec, cfg),
    }
    raw=json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _coerce(v: Any, lo: float, hi: float, typ):
    v = int(round(float(v))) if typ is int else float(v)
    v = max(lo, min(hi, v))
    return int(v) if typ is int else float(v)


def validate_candidate(raw: dict, cfg: dict, serial: int = 1) -> CandidateSpec | None:
    bounds = get_bounds()
    family = str(raw.get("family", "")).strip().lower()
    if family not in set(enabled_families(cfg)) or family not in bounds:
        return None
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        return None
    clean = {}
    # R5 regularization knobs are backward-compatible with older Scientist proposals
    # and historical specs. Missing newly-added regularizers resolve to the estimator
    # neutral defaults rather than invalidating the whole proposal.
    optional_defaults = {
        "reg_alpha": 0.0, "reg_lambda": 1.0,
        "policy_reg_alpha": 0.0, "policy_reg_lambda": 1.0,
    }
    family_bounds = effective_bounds(cfg, family)
    for key, (lo, hi, typ) in family_bounds.items():
        if key not in params:
            if key in optional_defaults:
                clean[key] = _coerce(optional_defaults[key], lo, hi, typ)
                continue
            return None
        try:
            clean[key] = _coerce(params[key], lo, hi, typ)
        except Exception:
            return None
    import re
    clean = canonicalize_candidate_params(family, clean)
    name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(raw.get("name") or f"candidate_{family}_{serial:03d}"))[:64]
    spec=CandidateSpec(family, name, clean)
    if not candidate_capacity_contract(spec,cfg).get("passed",True):
        return None
    return spec




def _scientist_semantic_canonicalization_allowed(family: str, key: str, requested: Any, executable: Any, params: dict) -> tuple[bool, str | None]:
    """Allow only canonicalizations that are semantically no-op for the executable model.

    Scientific attribution is stricter than deterministic AUTO candidate generation.  A
    concrete LLM proposal may not be silently converted into a different architecture.
    The only accepted numeric change is dropout -> 0 for a single-layer GRU/LSTM where
    the framework ignores recurrent dropout anyway.  Shadow/no-op keys removed by the
    canonicalizer are accepted only when they are explicitly non-executable aliases.
    """
    fam=str(family)
    k=str(key)
    if fam in {"gru","lstm"} and k=="dropout" and int(params.get("num_layers",1) or 1)<=1:
        try:
            if float(executable)==0.0:
                return True, "SINGLE_LAYER_RECURRENT_DROPOUT_IS_EXECUTION_NOOP"
        except Exception:
            pass
    if is_hybrid_family(fam):
        parts=hybrid_parts(fam) or ("","")
        temporal=parts[0]
        prefix="temporal_" if fam.startswith("hybrid::") else "gru_"
        if temporal in {"gru","lstm"} and k==prefix+"dropout" and int(params.get(prefix+"num_layers",1) or 1)<=1:
            try:
                if float(executable)==0.0:
                    return True, "SINGLE_LAYER_RECURRENT_DROPOUT_IS_EXECUTION_NOOP"
            except Exception:
                pass
    return False, None


def strict_scientist_candidate_admission(raw: dict, cfg: dict, serial: int = 1) -> tuple[CandidateSpec | None, dict]:
    """Fail-closed admission for concrete LLM Scientist proposals.

    Unlike ``validate_candidate`` (which remains appropriate for deterministic planners
    that canonicalize *before* executable identity is frozen), this function never clamps
    an LLM-requested numeric value into the current effective envelope.  A proposal is
    either admitted as the experiment the Scientist actually requested, or rejected with
    machine-readable provenance.
    """
    evidence = {
        "schema": "MAX_SCIENTIST_CANDIDATE_ADMISSION_V1",
        "authority": "STRICT_EFFECTIVE_BOUNDS_FAIL_CLOSED",
        "requested_family": str((raw or {}).get("family") or "").strip().lower() if isinstance(raw,dict) else "",
        "requested_name": str((raw or {}).get("name") or "")[:64] if isinstance(raw,dict) else "",
        "requested_params": deepcopy((raw or {}).get("params") or {}) if isinstance(raw,dict) and isinstance((raw or {}).get("params"),dict) else {},
        "executable_params": None,
        "admission_status": "REJECTED",
        "rejection_reason": None,
        "canonicalization": [],
        "effective_parameter_bounds": {},
    }
    if not isinstance(raw,dict):
        evidence["rejection_reason"]="PROPOSAL_NOT_OBJECT"
        return None,evidence
    family=evidence["requested_family"]
    bounds=get_bounds()
    if family not in set(enabled_families(cfg)) or family not in bounds:
        evidence["rejection_reason"]="FAMILY_NOT_EXECUTABLE_IN_CURRENT_PLAN"
        return None,evidence
    params=raw.get("params")
    if not isinstance(params,dict):
        evidence["rejection_reason"]="PARAMS_NOT_OBJECT"
        return None,evidence
    family_bounds=effective_bounds(cfg,family)
    evidence["effective_parameter_bounds"]={k:[lo,hi] for k,(lo,hi,_typ) in family_bounds.items()}
    unknown=sorted(set(params)-set(family_bounds))
    if unknown:
        evidence["rejection_reason"]="UNKNOWN_OR_NONEXECUTABLE_PARAMETERS:"+",".join(unknown)
        return None,evidence
    optional_defaults={
        "reg_alpha":0.0,"reg_lambda":1.0,
        "policy_reg_alpha":0.0,"policy_reg_lambda":1.0,
    }
    typed={}
    for key,(lo,hi,typ) in family_bounds.items():
        if key not in params:
            if key in optional_defaults:
                dv=optional_defaults[key]
                if float(dv)<float(lo) or float(dv)>float(hi):
                    evidence["rejection_reason"]=f"OPTIONAL_DEFAULT_OUTSIDE_EFFECTIVE_BOUNDS:{key}"
                    return None,evidence
                typed[key]=int(dv) if typ is int else float(dv)
                evidence["canonicalization"].append({
                    "parameter":key,"requested":None,"executable":typed[key],
                    "kind":"NEUTRAL_OPTIONAL_DEFAULT_INSERTION",
                })
                continue
            evidence["rejection_reason"]=f"MISSING_REQUIRED_PARAMETER:{key}"
            return None,evidence
        value=params[key]
        try:
            numeric=float(value)
        except Exception:
            evidence["rejection_reason"]=f"NON_NUMERIC_PARAMETER:{key}"
            return None,evidence
        if not math.isfinite(numeric):
            evidence["rejection_reason"]=f"NON_FINITE_PARAMETER:{key}"
            return None,evidence
        if typ is int:
            if abs(numeric-round(numeric))>1e-12:
                evidence["rejection_reason"]=f"NON_INTEGER_PARAMETER:{key}"
                return None,evidence
            typed_value=int(round(numeric))
        else:
            typed_value=float(numeric)
        if float(typed_value)<float(lo) or float(typed_value)>float(hi):
            evidence["rejection_reason"]=(
                f"OUTSIDE_EFFECTIVE_PARAMETER_BOUNDS:{key}:requested={typed_value}:allowed=[{lo},{hi}]"
            )
            return None,evidence
        typed[key]=typed_value

    executable=canonicalize_candidate_params(family,typed)
    all_keys=sorted(set(typed)|set(executable))
    for key in all_keys:
        rv=typed.get(key,"__MISSING__")
        ev=executable.get(key,"__MISSING__")
        if rv==ev:
            continue
        allowed,reason=_scientist_semantic_canonicalization_allowed(family,key,rv,ev,typed)
        if not allowed:
            evidence["rejection_reason"]=(
                f"NON_EQUIVALENT_CANONICALIZATION_REQUIRED:{key}:requested={rv}:executable={ev}"
            )
            return None,evidence
        evidence["canonicalization"].append({
            "parameter":key,"requested":None if rv=="__MISSING__" else rv,
            "executable":None if ev=="__MISSING__" else ev,
            "kind":reason,
        })

    import re
    name=re.sub(r"[^a-zA-Z0-9_.-]+","_",str(raw.get("name") or f"candidate_{family}_{serial:03d}"))[:64]
    spec=CandidateSpec(family,name,executable)
    capacity=candidate_capacity_contract(spec,cfg)
    if not capacity.get("passed",True):
        evidence["rejection_reason"]="CANDIDATE_CAPACITY_CONTRACT_REJECTED"
        evidence["capacity"]={k:deepcopy(v) for k,v in capacity.items() if k in {
            "schema","family","passed","capacity_admission_status","capacity_reason","rejecting_authority",
            "actual_parameter_count","legal_ceiling","resource_ceiling","scientific_ceiling","effective_ceiling",
            "preferred_range","extended_ceiling","capacity_band","capacity_percentile","first_failed_gate","failed_gates"
        }}
        return None,evidence
    evidence["executable_params"]=deepcopy(spec.params)
    evidence["admission_status"]="ACCEPTED"
    evidence["rejection_reason"]=None
    return spec,evidence

def _sample_value(rng: random.Random, lo, hi, typ, distribution="linear", u=None):
    if u is None:
        u = rng.random()
    u = min(1.0, max(0.0, float(u)))
    if distribution == "log" and float(lo) > 0 and float(hi) > 0:
        value = math.exp(math.log(float(lo)) + u * (math.log(float(hi)) - math.log(float(lo))))
    else:
        value = float(lo) + u * (float(hi) - float(lo))
    return _coerce(value, lo, hi, typ)


def _priority_sample_u(base_u: float, priority: float) -> float:
    p=max(0.0,min(1.0,float(priority)))
    u=max(0.0,min(1.0,float(base_u)))
    if p < 0.5:
        # Small prefers lower capacity but can still sample outside the old static table.
        return u * (0.35 + 0.70*p)
    if p > 0.5:
        floor=(p-0.5)*0.72
        return floor + (1.0-floor)*u
    return u


def _stable_retry_unit(name: str, key: str, attempt: int, base_u: float) -> float:
    raw=f"{name}|{key}|{attempt}|{float(base_u):.12f}".encode("utf-8")
    n=int.from_bytes(hashlib.sha256(raw).digest()[:8],"big")
    return n/float((1<<64)-1)


def _family_capacity_signal(cfg: dict, family: str) -> dict:
    plan=(((cfg or {}).get("agent") or {}).get("research_plan") or {})
    by_family=plan.get("capacity_evidence_by_family") if isinstance(plan,dict) else None
    if isinstance(by_family,dict):
        families=by_family.get("families") if isinstance(by_family.get("families"),dict) else by_family
        row=families.get(str(family)) if isinstance(families,dict) else None
        if isinstance(row,dict):
            return row
    return {"status":"HOLD","search_bias_delta":0.0,"target_quantile_shift":0.0,"expansion_factor":1.0,
            "authority":"NO_FAMILY_CAPACITY_EVIDENCE_NEUTRAL"}


def _bounded_search_priority(owner_priority: float, evidence: dict) -> float:
    delta=float((evidence or {}).get("search_bias_delta",0.0) or 0.0)
    return max(0.0,min(1.0,float(owner_priority)+max(-0.25,min(0.25,delta))))


def random_candidate(cfg: dict, family: str, rng: random.Random, name: str, stratified_u: dict | None = None) -> CandidateSpec:
    """Generate one deterministic candidate inside current dynamic capacity.

    The original stratified coordinates are frozen for candidate identity.  Capacity
    retries only contract capacity-driving coordinates and use candidate-specific
    deterministic caps, so separate strata do not converge to one common fixed point.
    Family-specific evidence moves the search *location* only; it never widens hard
    LEGAL/RESOURCE/SCIENTIFIC ceilings.
    """
    bounds=effective_bounds(cfg,family)
    dist=get_distributions().get(family,{})
    meta=family_spec(family) or {}
    size_keys=set(meta.get("size_parameters") or [])
    pri=family_size_priority(cfg,family)
    if is_hybrid_family(family):
        owner_temporal=float(pri.get("temporal",0.50)); policy_priority=float(pri.get("policy",0.50))
    else:
        owner_temporal=policy_priority=float(pri.get("family",0.50))
    evidence=_family_capacity_signal(cfg,family)
    temporal_priority=_bounded_search_priority(owner_temporal,evidence)

    frozen_us={k:(float(stratified_u[k]) if stratified_u is not None and k in stratified_u else rng.random()) for k in bounds}
    last_authority=None
    backoff_level=1.0
    for attempt in range(28):
        # Attempt 0 is the exact stratified/evidence-biased draw. Later attempts use
        # the previous actual/effective parameter ratio to jump toward a safe region
        # while candidate-specific lanes preserve the original stratum identity.
        progress=max(0.035,min(1.0,backoff_level))
        params={}
        for key,(lo,hi,typ) in bounds.items():
            base=frozen_us[key]
            is_temporal_size=(key in size_keys and (not is_hybrid_family(family) or key.startswith(("temporal_","gru_"))))
            is_policy_size=(key in size_keys and is_hybrid_family(family) and key.startswith("policy_"))
            if is_temporal_size:
                original=_priority_sample_u(base,temporal_priority)
                if attempt:
                    lane=0.70+0.30*_stable_retry_unit(name,key,attempt,base)
                    u=min(original,progress*lane)
                else:
                    u=original
            elif is_policy_size:
                # Tree-side hybrid complexity keeps its own family controls.
                u=_priority_sample_u(base,policy_priority)
            elif key.endswith("sequence_length") or key in {"sequence_length","batch_size","epochs"}:
                # These dimensions only back off after RESOURCE pressure.  Scientific
                # pressure is solved by model-size dimensions, preserving chronology.
                if attempt and last_authority=="RESOURCE":
                    lane=0.74+0.26*_stable_retry_unit(name,key,attempt,base)
                    u=min(base,progress*lane)
                else:
                    u=base
            else:
                # Non-capacity coordinates remain at their original stratum.
                u=base
            params[key]=_sample_value(rng,lo,hi,typ,dist.get(key,"linear"),u=u)
        spec=CandidateSpec(family,name,canonicalize_candidate_params(family,params))
        contract=candidate_capacity_contract(spec,cfg)
        if contract.get("passed",True):
            return spec
        last_authority=str(contract.get("rejecting_authority") or "CAPACITY")
        actual=contract.get("actual_parameter_count")
        effective=contract.get("effective_ceiling")
        try:
            ratio=float(effective)/max(1.0,float(actual)) if actual is not None and effective is not None else None
        except Exception:
            ratio=None
        if ratio is not None and ratio > 0.0:
            # Most temporal architectures are super-linear in their primary width, so
            # sqrt converts a parameter-count excess into a useful coordinate backoff.
            target=max(0.05,min(0.94,(ratio ** 0.5)*0.94))
            backoff_level=min(backoff_level*0.88,target)
        else:
            backoff_level=max(0.05,backoff_level*0.82)
    raise RuntimeError(f"AUTO_CAPACITY_GENERATION_EXHAUSTED:{family}:{last_authority}")

def generate_initial_population(cfg: dict, count: int | None = None, round_no: int = 1) -> list[CandidateSpec]:
    """Generate a deterministic registry population honoring Owner topology priority.

    R10 uses the same 0..1 SINGLE/HYBRID allocation in the fail-safe generator as in
    the adaptive planner. Legacy configs without topology authority preserve the old
    staged single-first behaviour.
    """
    families_all = enabled_families(cfg)
    if not families_all:
        return []
    if count is None:
        count = max(1, int(cfg.get("agent", {}).get("round_size", 6)))
    count = max(1, int(count))
    priority=configured_hybrid_priority(cfg,legacy_none=True)
    if priority is None:
        families = [f for f in families_all if not is_hybrid_family(f)] or families_all
        # Historical behaviour covered every enabled family on the initial fallback.
        count=max(len(families),count)
        topology_groups=[(families,count)]
    else:
        singles,hybrids=split_families(families_all)
        alloc=allocation_counts(count,priority,single_available=bool(singles),hybrid_available=bool(hybrids))
        topology_groups=[]
        if alloc["single"]: topology_groups.append((singles,int(alloc["single"])))
        if alloc["hybrid"]: topology_groups.append((hybrids,int(alloc["hybrid"])))

    rng = random.Random(int(cfg.get("seed", 42)) + round_no * 7919)
    out=[]; serial=1
    for families,n_total in topology_groups:
        if not families or n_total<=0:
            continue
        ordered=list(families); rng.shuffle(ordered)
        allocations={f:0 for f in ordered}
        for j in range(n_total):
            allocations[ordered[j % len(ordered)]] += 1
        for family in ordered:
            n=allocations[family]
            if n<=0: continue
            keys=list(effective_bounds(cfg,family).keys())
            strata={}
            for key in keys:
                vals=[(j + rng.random())/n for j in range(n)]
                rng.shuffle(vals); strata[key]=vals
            for j in range(n):
                us={k:strata[k][j] for k in keys}
                cand=random_candidate(cfg,family,rng,f"discover_r{round_no:02d}_{family}_{serial:02d}",us)
                cap=candidate_capacity_contract(cand,cfg)
                if not cap.get("passed",True):
                    raise RuntimeError(f"AUTO_GENERATOR_EMITTED_OUTSIDE_CAPACITY:{family}:{cap.get('first_failed_gate')}")
                out.append(cand)
                serial += 1
    rng.shuffle(out)
    return out[:count]



def architecture_capacity_fingerprint(spec: CandidateSpec) -> str:
    """Normalized fingerprint for meaningful capacity/search architecture identity.

    Optimizer-only floating dimensions (learning rate/dropout/weight decay) are excluded
    so Discovery diversity cannot be satisfied by numerically tiny optimizer changes.
    """
    fam=str(spec.family)
    meta=family_spec(fam) or {}
    keys=[]
    if is_hybrid_family(fam):
        size=list(meta.get("size_parameters") or [])
        keys.extend(size)
        for k in ("temporal_sequence_length","gru_sequence_length","training_memory_months"):
            if k in spec.params: keys.append(k)
    elif meta.get("role")=="temporal":
        keys.extend(list(meta.get("size_parameters") or []))
        for k in ("sequence_length","training_memory_months"):
            if k in spec.params: keys.append(k)
    else:
        keys.extend(list(meta.get("size_parameters") or []))
    payload={"family":fam,"dimensions":{k:spec.params.get(k) for k in sorted(set(keys))}}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")).hexdigest()

def candidate_specs(cfg: dict):
    # Backward-compatible entry point used by Manual Research.
    # Candidates are generated from the registry, not hand-coded parameter tuples.
    n=max(3,int(cfg.get("agent",{}).get("round_size",6)))
    return generate_initial_population(cfg,n,round_no=1)



def candidate_input_shape(spec: CandidateSpec, n_features: int = 32) -> list[int]:
    meta=family_spec(spec.family) or {}
    if meta.get("role") == "temporal":
        return [1, int(spec.params.get("sequence_length", 12)), int(n_features)]
    if is_hybrid_family(spec.family):
        return [1, int(n_features) + 4]
    return [1, int(n_features)]

def candidate_runtime_contract(spec: CandidateSpec, n_features: int = 32) -> dict:
    if is_hybrid_family(spec.family):
        parts=hybrid_parts(spec.family) or ("gru","unknown")
        seq_key="temporal_sequence_length" if str(spec.family).startswith("hybrid::") else "gru_sequence_length"
        return {
            "schema":"CP_HYBRID_TEMPORAL_POLICY_V1",
            "temporal_family":parts[0],"policy_family":parts[1],
            "temporal_input":[1,int(spec.params.get(seq_key,12)),int(n_features)],
            "temporal_output":[1,2],
            "policy_input":[1,int(n_features)+4],
            "policy_output":[1,3],
            "risk_authority":"DETERMINISTIC_EA",
        }
    meta=family_spec(spec.family) or {}
    schema="CP_TEMPORAL_MODEL_V1" if meta.get("role")=="temporal" else "CP_SINGLE_MODEL_V1"
    return {"schema":schema,"family":spec.family,"input":candidate_input_shape(spec,n_features),"output":[1,3]}

def _temporal_parameter_count(family: str, params: dict, n_features: int = 32, n_classes: int = 3) -> int | None:
    try:
        import numpy as np
        from research.temporal_research import TemporalNet
        p=canonicalize_candidate_params(str(family),params)
        model=TemporalNet(
            architecture=str(family),n_features=int(n_features),n_classes=int(n_classes),
            hidden_size=int(p.get("hidden_size",64)),num_layers=int(p.get("num_layers",1)),dropout=float(p.get("dropout",0.1)),
            tcn_channels=int(p.get("tcn_channels",p.get("hidden_size",64))),tcn_blocks=int(p.get("tcn_blocks",3)),kernel_size=int(p.get("kernel_size",3)),
            d_model=int(p.get("d_model",p.get("hidden_size",64))),attention_heads=int(p.get("attention_heads",4)),ffn_mult=int(p.get("ffn_mult",2)),
            expert_ffn=int(p.get("expert_ffn",max(64,int(p.get("d_model",p.get("hidden_size",64)))*2))),num_experts=int(p.get("num_experts",4)),top_k=int(p.get("top_k",1)),
            router_temperature=float(p.get("router_temperature",1.0)),load_balance_coef=float(p.get("load_balance_coef",0.01)),
            patch_len=int(p.get("patch_len",16)),patch_stride=int(p.get("patch_stride",8)),tft_lstm_layers=int(p.get("tft_lstm_layers",1)),
            sequence_length=int(p.get("sequence_length",128)),mean=np.zeros(int(n_features),dtype=np.float32),std=np.ones(int(n_features),dtype=np.float32),
        )
        return int(sum(x.numel() for x in model.parameters()))
    except Exception:
        return None


def estimate_candidate_parameter_count(spec: CandidateSpec, n_features: int = 32) -> int | None:
    """Executable torch parameter count for temporal or hybrid temporal components.

    Tree models return None because estimator node counts are data-dependent.  Dynamic
    hybrids report the temporal representation component, which is the part governed
    by the dataset-aware neural capacity budget.
    """
    fam=str(spec.family)
    meta=family_spec(fam) or {}
    if meta.get("role") == "temporal":
        return _temporal_parameter_count(fam,spec.params,n_features,3)
    if is_hybrid_family(fam):
        parts=hybrid_parts(fam)
        if not parts:
            return None
        temporal,_policy=parts
        prefix="temporal_" if fam.startswith("hybrid::") else "gru_"
        tp={}
        for key,value in spec.params.items():
            if key.startswith(prefix):
                tp[key[len(prefix):]]=value
        if not tp:
            return None
        return _temporal_parameter_count(temporal,tp,n_features,2)
    return None



_LEGAL_TEMPORAL_PARAMETER_CEILING_V1={
    # Implementation ceilings, NOT recommended research sizes. Transformer/TFT are
    # bound to their exact executable registry maxima at n_features=32 in this build.
    # Every other family deliberately retains its pre-build legal authority unchanged.
    "gru":5_568_003,
    "lstm":7_423_491,
    "tcn":7_361_539,
    "transformer":64_444_419,
    "patchtst":14_247_555,
    "itransformer":14_217_219,
    "tft":16_875_459,
    "transformer_moe":207_916_083,
}

_OLD_REACHABLE_MAX_PARAMETER_COUNT_V201_HEADROOM={
    "transformer":25_493_507,
    "tft":4_814_627,
}

_LEGAL_HEADROOM_ARCHITECTURE_KEYS={
    "transformer":("sequence_length","d_model","num_layers","attention_heads","ffn_mult"),
    "tft":("sequence_length","d_model","num_layers","attention_heads","ffn_mult","tft_lstm_layers"),
}

def legal_capacity_headroom_evidence(family: str, n_features: int = 32) -> dict:
    """Machine-readable legal-headroom proof for the two widened families.

    The registry architecture bounds define the legal shape universe; the recorded
    reachable maximum is verified against the same executable TemporalNet parameter
    counter used for candidate admission. This function does not alter RESOURCE or
    SCIENTIFIC capacity and is intentionally limited to Transformer/TFT.
    """
    fam=str(family or "").strip().lower()
    if fam not in _LEGAL_HEADROOM_ARCHITECTURE_KEYS:
        raise ValueError(f"LEGAL_HEADROOM_EVIDENCE_NOT_APPLICABLE:{fam}")
    legal=get_bounds([fam]).get(fam,{})
    keys=_LEGAL_HEADROOM_ARCHITECTURE_KEYS[fam]
    architecture_bounds={k:[legal[k][0],legal[k][1]] for k in keys if k in legal}
    # Parameter-count maxima use upper structural bounds. Non-structural training
    # controls are set to harmless legal values because they do not create parameters.
    rep={k:legal[k][1] for k in keys if k in legal}
    rep.update({
        "dropout":0.0,
        "learning_rate":float(legal.get("learning_rate",(0.001,0.001,float))[0]),
        "batch_size":int(legal.get("batch_size",(8,8,int))[0]),
        "epochs":int(legal.get("epochs",(4,4,int))[0]),
        "weight_decay":0.0,
        "training_memory_months":int(legal.get("training_memory_months",(3,3,int))[0]),
    })
    rep=canonicalize_candidate_params(fam,rep)
    reachable=_temporal_parameter_count(fam,rep,n_features,3)
    legal_ceiling=_LEGAL_TEMPORAL_PARAMETER_CEILING_V1[fam]
    return {
        "schema":"MAX_V201_TRANSFORMER_TFT_LEGAL_CAPACITY_HEADROOM_V1",
        "authority":"ACTUAL_EXECUTABLE_MODEL_PARAMETER_COUNT_AT_LEGAL_REGISTRY_BOUNDS",
        "family":fam,
        "legal_architecture_bounds":architecture_bounds,
        "reachable_max_parameter_count":None if reachable is None else int(reachable),
        "representative_max_configuration":rep,
        "old_reachable_max_parameter_count":int(_OLD_REACHABLE_MAX_PARAMETER_COUNT_V201_HEADROOM[fam]),
        "new_reachable_max_parameter_count":None if reachable is None else int(reachable),
        "legal_parameter_ceiling":int(legal_ceiling),
        "legal_ceiling_matches_reachable_max":bool(reachable is not None and int(reachable)==int(legal_ceiling)),
        "capacity_effect":"LEGAL_ARCHITECTURE_HEADROOM_ONLY_RESOURCE_AND_SCIENTIFIC_UNCHANGED",
    }

def _legal_temporal_parameter_ceiling(family: str, n_features: int = 32) -> int | None:
    """Registry implementation ceiling, separate from research recommendation."""
    fam=str(family or "")
    if is_hybrid_family(fam):
        parts=hybrid_parts(fam)
        fam=str(parts[0]) if parts else fam
    base=_LEGAL_TEMPORAL_PARAMETER_CEILING_V1.get(fam)
    if base is None:
        return None
    # Legal-ceiling evidence is normalized at the production 32-feature CP32 contract.
    # Candidate actual parameter count is always measured from its executable model.
    return int(base)


def _resource_parameter_proxy_ceiling(plan: dict) -> int | None:
    guidance=plan.get("capacity_guidance") if isinstance(plan,dict) else {}
    compute=(guidance or {}).get("compute") if isinstance(guidance,dict) else {}
    raw=(compute or {}).get("parameter_count_proxy_ceiling")
    if raw is None:
        raw=(compute or {}).get("soft_absolute_parameter_ceiling")
    try:
        return max(1,int(raw)) if raw is not None else None
    except Exception:
        return None


def _capacity_band_label(parameter_count: int | None, preferred: list[int] | None, effective: int | None) -> tuple[str | None,float | None]:
    if parameter_count is None or effective in (None,0):
        return None,None
    pct=float(parameter_count)/max(1.0,float(effective))
    pref=preferred or []
    if len(pref)>=2:
        if parameter_count < int(pref[0]): label="BELOW_PREFERRED"
        elif parameter_count <= int(pref[1]): label="PREFERRED"
        else: label="EXTENDED"
    else:
        label="ADMITTED"
    return label,round(pct,8)

def candidate_capacity_contract(spec: CandidateSpec, cfg: dict, n_features: int = 32) -> dict:
    """Three-ceiling dynamic capacity admission on the actual executable model.

    Temporal/DL candidates must satisfy LEGAL architecture, RESOURCE execution and
    candidate-aware SCIENTIFIC information ceilings.  Historical recommended envelopes
    are evidence/search guidance only. Tree models keep family-specific complexity and
    resource preflight; neural parameter-count logic is not imposed on them.
    """
    count=estimate_candidate_parameter_count(spec,n_features)
    plan=(((cfg or {}).get("agent") or {}).get("research_plan") or {})
    guidance=plan.get("capacity_guidance") if isinstance(plan,dict) else None
    historical_preferred=list((guidance or {}).get("preferred_total_params") or []) if isinstance(guidance,dict) else []

    legal_ceiling=_legal_temporal_parameter_ceiling(spec.family,n_features) if count is not None else None
    resource_capacity_evidence=(candidate_resource_parameter_ceiling(
        spec.family,spec.params,cfg,n_features,
        search_upper=min(1_000_000_000,max(50_000_000,int(legal_ceiling or 0)*8))
    ) if count is not None else {"available":False,"resource_parameter_ceiling":None,"authority":"NOT_APPLICABLE_TREE_MODEL"})
    resource_ceiling=resource_capacity_evidence.get("resource_parameter_ceiling") if isinstance(resource_capacity_evidence,dict) else None
    try:
        resource_ceiling=int(resource_ceiling) if resource_ceiling is not None else None
    except Exception:
        resource_ceiling=None
    scientific=candidate_scientific_capacity(cfg,spec.family,spec.params) if count is not None else {
        "available":False,"authority":"NOT_APPLICABLE_TREE_MODEL","scientific_parameter_ceiling":None
    }
    scientific_ceiling=scientific.get("scientific_parameter_ceiling") if isinstance(scientific,dict) else None
    try:
        scientific_ceiling=int(scientific_ceiling) if scientific_ceiling is not None else None
    except Exception:
        scientific_ceiling=None

    # Legacy/current-run compatibility: when a frozen dataset profile is absent, retain
    # the historical extended reference as the parameter-count authority instead of
    # fabricating candidate-aware scientific evidence.
    legacy_extended=list((guidance or {}).get("extended_total_params") or []) if isinstance(guidance,dict) else []
    if count is not None and scientific_ceiling is None and len(legacy_extended)>=2:
        try:
            scientific_ceiling=int(legacy_extended[1])
            scientific=dict(scientific or {})
            scientific.update({
                "available":False,"authority":"LEGACY_REFERENCE_CAPACITY_FALLBACK",
                "scientific_parameter_ceiling":scientific_ceiling,
            })
        except Exception:
            scientific_ceiling=None

    ceiling_values=[int(x) for x in (legal_ceiling,resource_ceiling,scientific_ceiling) if x is not None and int(x)>=0]
    effective_ceiling=min(ceiling_values) if ceiling_values else None

    failed=[]
    rejecting_authority=None
    if count is not None:
        if legal_ceiling is not None and int(count)>int(legal_ceiling):
            failed.append("LEGAL_PARAMETER_COUNT_CEILING_EXCEEDED"); rejecting_authority=rejecting_authority or "LEGAL"
        if resource_ceiling is not None and int(count)>int(resource_ceiling):
            failed.append("RESOURCE_PARAMETER_COUNT_PROXY_CEILING_EXCEEDED"); rejecting_authority=rejecting_authority or "RESOURCE"
        if scientific_ceiling is not None and int(count)>int(scientific_ceiling):
            failed.append("SCIENTIFIC_PARAMETER_COUNT_CEILING_EXCEEDED"); rejecting_authority=rejecting_authority or "SCIENTIFIC"

    resource_estimate=estimate_candidate_resources(spec.family,spec.params,count,cfg,n_features)
    resource_capacity=plan.get("resource_capacity") if isinstance(plan,dict) else {}
    resource_gate=evaluate_resource_limits(resource_estimate,resource_capacity if isinstance(resource_capacity,dict) else {})
    if not resource_gate.get("passed",True):
        failed.extend(list(resource_gate.get("failed_gates") or []))
        rejecting_authority=rejecting_authority or "RESOURCE"

    preferred=list((scientific or {}).get("preferred_parameter_range") or [])
    if effective_ceiling is not None:
        if len(preferred)>=2:
            preferred=[min(int(preferred[0]),int(effective_ceiling)),min(int(preferred[1]),int(effective_ceiling))]
            preferred[0]=min(preferred[0],preferred[1])
        else:
            preferred=[max(1,int(effective_ceiling*0.28)),max(1,int(effective_ceiling*0.68))]
    band,percentile=_capacity_band_label(count,preferred,effective_ceiling)
    passed=(not failed)
    status=("PASS_"+str(band or "CAPACITY")) if passed else str(rejecting_authority or "CAPACITY")+"_REJECTED"

    return {
        "schema":"MAX_CANDIDATE_DYNAMIC_CAPACITY_CONTRACT_V1",
        "family":spec.family,
        "passed":bool(passed),
        "capacity_admission_status":"ACCEPTED" if passed else "REJECTED",
        "capacity_reason":"WITHIN_MIN_LEGAL_RESOURCE_SCIENTIFIC" if passed else (failed[0] if failed else "UNKNOWN"),
        "rejecting_authority":rejecting_authority,
        "parameter_count":None if count is None else int(count),
        "actual_parameter_count":None if count is None else int(count),
        "status":status,
        "legal_ceiling":None if legal_ceiling is None else int(legal_ceiling),
        "legal_ceiling_source":"REGISTRY_MAX_EXECUTABLE_PARAMETER_COUNT_CP32_V1" if legal_ceiling is not None else None,
        "resource_ceiling":None if resource_ceiling is None else int(resource_ceiling),
        "resource_capacity_evidence":deepcopy(resource_capacity_evidence),
        "scientific_ceiling":None if scientific_ceiling is None else int(scientific_ceiling),
        "effective_ceiling":None if effective_ceiling is None else int(effective_ceiling),
        "preferred_range":preferred or None,
        "extended_ceiling":None if effective_ceiling is None else int(effective_ceiling),
        "historical_recommended_starting_range":historical_preferred or None,
        "first_failed_gate":failed[0] if failed else None,
        "failed_gates":failed,
        "count_scope":("TEMPORAL_TORCH_COMPONENT" if is_hybrid_family(spec.family) else "FULL_TEMPORAL_MODEL") if count is not None else None,
        "training_memory_months":scientific.get("training_memory_months") if isinstance(scientific,dict) else None,
        "sequence_length":scientific.get("sequence_length") if isinstance(scientific,dict) else None,
        "minimum_fold_train_rows":scientific.get("minimum_fold_train_rows") if isinstance(scientific,dict) else None,
        "effective_sample_estimate":scientific.get("effective_sample_estimate") if isinstance(scientific,dict) else None,
        "scientific_capacity_evidence":scientific,
        "owner_size_priority":family_size_priority(cfg,spec.family),
        "size_priority":family_size_priority(cfg,spec.family),
        "size_parameters":list((family_spec(spec.family) or {}).get("size_parameters") or []),
        "capacity_band":band,
        "capacity_percentile":percentile,
        "capacity_evidence_signal":deepcopy(_family_capacity_signal(cfg,spec.family)),
        "resource_estimate":resource_estimate,
        "resource_limits":resource_gate.get("limits") or {},
        "resource_preflight_authority":"FROZEN_FACTORY_HARDWARE_PLUS_OWNER_BUDGET" if bool(resource_estimate.get("available")) else "LEGACY_OR_UNAVAILABLE",
        "authority":"MIN_LEGAL_RESOURCE_SCIENTIFIC_ACTUAL_EXECUTABLE_PARAMETER_COUNT",
    }


def make_model(spec: CandidateSpec, cfg: dict):
    seed = int(cfg.get("seed", 42))
    threads = int(cfg.get("cpu_threads", 4))
    p = canonicalize_candidate_params(spec.family, spec.params)
    p.pop("training_memory_months", None)
    plan = cfg.get("resolved_compute") or resolve_compute_plan(cfg)
    if spec.family == "xgboost":
        from xgboost import XGBClassifier
        extra = {"device":"cuda"} if (plan.get("xgboost") or {}).get("backend") == "CUDA" else {}
        return XGBClassifier(**p, objective="multi:softprob", num_class=3, eval_metric="mlogloss", tree_method="hist", n_jobs=threads, random_state=seed, **extra)
    if spec.family == "lightgbm":
        from lightgbm import LGBMClassifier
        extra = {"device_type":"gpu"} if (plan.get("lightgbm") or {}).get("backend") == "OPENCL_GPU" else {}
        if "subsample" in p and float(p.get("subsample",1.0)) < 0.999999: p.setdefault("subsample_freq",1)
        return LGBMClassifier(**p, objective="multiclass", num_class=3, n_jobs=threads, random_state=seed, verbosity=-1, **extra)
    if spec.family == "random_forest":
        return RandomForestClassifier(**p, n_jobs=threads, random_state=seed, class_weight="balanced_subsample")
    if spec.family == "gru":
        from research.gru_research import GRUClassifier
        return GRUClassifier(**p, patience=int(cfg.get("models",{}).get("gru_patience",4)), random_state=seed, threads=threads, device=str((plan.get("temporal_dl") or {}).get("torch_device","cpu")), compute_backend=str((plan.get("temporal_dl") or {}).get("backend","CPU")))
    if (family_spec(spec.family) or {}).get("role") == "temporal":
        from research.temporal_research import TemporalClassifier
        return TemporalClassifier(architecture=spec.family, **p, patience=int(cfg.get("models",{}).get("gru_patience",4)), random_state=seed, threads=threads, device=str((plan.get("temporal_dl") or {}).get("torch_device","cpu")), compute_backend=str((plan.get("temporal_dl") or {}).get("backend","CPU")))
    if is_hybrid_family(spec.family):
        from research.hybrid_research import HybridStackClassifier
        temporal,policy=hybrid_parts(spec.family) or ("gru","")
        return HybridStackClassifier(policy, temporal_family=temporal, **p, patience=int(cfg.get("models",{}).get("gru_patience",4)), inner_folds=int(cfg.get("models",{}).get("hybrid_oof_inner_folds",2)), random_state=seed, threads=threads, compute_plan=plan)
    raise ValueError(spec.family)

def fit_model(model, family: str, X, y, sample_weight=None, cfg: dict | None = None):
    import numpy as np
    X=np.asarray(X); y=np.asarray(y,dtype=np.int64)
    utility=np.ones(len(y),dtype=np.float64) if sample_weight is None else np.asarray(sample_weight,dtype=np.float64)
    if len(utility)!=len(y): raise ValueError("sample_weight length mismatch")
    keep=np.isfinite(utility)&(utility>0)
    if not np.any(keep): raise ValueError("No supervised rows remain after execution-eligibility masking")
    fam=str(family)
    if ((family_spec(fam) or {}).get("role") == "temporal" or is_hybrid_family(fam)) and cfg is not None:
        # Production full-window refits retain the same Strategy-geometry authority as
        # WFA/CPCV. They must not fall back to an unpurged internal early-stop split.
        c=contract_from_cfg(cfg)
        return model.fit_indexed(
            X,y,np.arange(len(X),dtype=int),purge_bars=int(c.purge_bars),
            embargo_bars=int(c.embargo_bars),label_horizon_bars=int(c.label_horizon_bars),
            sample_weight=utility,
        )
    Xf=X[keep]; yf=y[keep]; uf=utility[keep]
    if fam in {"xgboost", "lightgbm"}:
        sw=compute_sample_weight(class_weight="balanced",y=yf)*uf
        return model.fit(Xf,yf,sample_weight=sw)
    if fam=="random_forest":
        return model.fit(Xf,yf,sample_weight=uf)
    # Direct estimator fitting is retained for probes/tests. Temporal estimators use an
    # explicit fixed-epoch/no-early-stop path when no cfg/horizon authority is supplied.
    return model.fit(X,y,sample_weight=utility)


def fit_model_indexed(model, family: str, X, y, train_idx, cfg: dict | None = None, sample_weight=None):
    """Fit a candidate without collapsing discontinuous temporal chronology.

    Classical estimators receive the selected rows normally. Temporal and hybrid
    estimators receive original row ids so their sequence builders can stop at gaps
    instead of fabricating adjacency across CPCV-held-out blocks.
    """
    import numpy as np
    tr = np.asarray(train_idx, dtype=int)
    fam = str(family)
    if (family_spec(fam) or {}).get("role") == "temporal" or is_hybrid_family(fam):
        if not hasattr(model, "fit_indexed"):
            raise RuntimeError(f"Temporal family {fam} lacks fit_indexed chronology contract")
        c=contract_from_cfg(cfg or {})
        return model.fit_indexed(
            X, y, tr,
            purge_bars=int(c.purge_bars),
            embargo_bars=int(c.embargo_bars),
            label_horizon_bars=int(c.label_horizon_bars),
            sample_weight=sample_weight,
        )
    sw=None if sample_weight is None else np.asarray(sample_weight)[tr]
    return fit_model(model,fam,np.asarray(X)[tr],np.asarray(y)[tr],sample_weight=sw,cfg=cfg)


def model_training_diagnostics(model) -> dict:
    """Return JSON-safe local scientific diagnostics from the fitted production model.

    This is evidence only: it never participates in ranking or PASS/FAIL.  Temporal
    internal-validation geometry and MoE routing diagnostics are exposed so WFA/CPCV/
    Tournament/Forward evidence can be independently audited.
    """
    import numpy as np

    def clean(v):
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, np.generic):
            return v.item()
        if isinstance(v, np.ndarray):
            return [clean(x) for x in v.tolist()]
        if isinstance(v, dict):
            return {str(k): clean(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        return str(v)

    out = {}
    for key, attr in (
        ("internal_earlystop_validation", "internal_validation_"),
        ("routing_diagnostics", "routing_diagnostics_"),
        ("router_gradient_health", "router_gradient_health_"),
        ("hybrid_temporal_internal_validation", "temporal_internal_validation_"),
        ("hybrid_temporal_routing_diagnostics", "temporal_routing_diagnostics_"),
    ):
        value = getattr(model, attr, None)
        if value is not None:
            out[key] = clean(value)
    if hasattr(model, "stacking_schema_"):
        out["hybrid_stacking_schema"] = clean(getattr(model, "stacking_schema_", None))
    if hasattr(model, "internal_label_horizon_bars_"):
        out["hybrid_internal_label_horizon_bars"] = clean(getattr(model, "internal_label_horizon_bars_", None))
    return out


FINAL_DECISION_CLASSES = (0, 1, 2)  # SELL, SKIP, BUY


def normalize_final_decision_proba(model, raw):
    """Normalize every standalone/hybrid model to the canonical SELL/SKIP/BUY schema.

    Tree estimators can legally expose fewer columns when a bounded training fold loses
    one class.  The research/evaluation contract must nevertheless remain [N,3] with
    a stable class order, so missing classes are represented by zero probability.
    Temporal and hybrid models normally arrive already in canonical order.
    """
    import numpy as np
    arr=np.asarray(raw,dtype=np.float64)
    if arr.ndim!=2:
        raise ValueError(f"Final decision probability must be [N,C], got {arr.shape}")
    classes=list(getattr(model,"classes_",[]))
    if not classes:
        classes=list(range(arr.shape[1]))
    if arr.shape[1]==3 and classes==[0,1,2]:
        return arr
    if len(classes)!=arr.shape[1]:
        raise ValueError(f"Probability/class mismatch: shape={arr.shape}, classes={classes}")
    out=np.zeros((arr.shape[0],3),dtype=np.float64)
    for j,c in enumerate(classes):
        ci=int(c)
        if ci not in FINAL_DECISION_CLASSES:
            raise ValueError(f"Unknown final decision class {c}; expected SELL/SKIP/BUY = 0/1/2")
        out[:,ci]=arr[:,j]
    sums=out.sum(axis=1,keepdims=True)
    if np.any(~np.isfinite(out)) or np.any(sums<=0):
        raise ValueError("Final decision probabilities are non-finite or have zero mass")
    return out/sums


def predict_model_proba(model, family: str, history_X, target_X):
    """Causal inference helper with canonical SELL/SKIP/BUY final output."""
    fam=str(family)
    if (family_spec(fam) or {}).get("role")=="temporal" or is_hybrid_family(fam):
        if hasattr(model,"predict_proba_with_context"):
            return normalize_final_decision_proba(model,model.predict_proba_with_context(history_X,target_X))
    return normalize_final_decision_proba(model,model.predict_proba(target_X))
