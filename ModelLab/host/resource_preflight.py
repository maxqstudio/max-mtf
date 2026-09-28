from __future__ import annotations

"""Deterministic candidate resource preflight for CPMF.

The estimator is intentionally conservative and transparent.  It is not a benchmark
and does not predict wall-clock runtime exactly.  Its purpose is to make the Owner's
RAM/VRAM/time budgets executable *before* training starts, using only frozen Factory
inputs (hardware snapshot, dataset-capacity profile, candidate parameters).
"""

import math
from typing import Any

from models.model_registry import family_spec, hybrid_parts, is_hybrid_family

SCHEMA = "CP_CANDIDATE_RESOURCE_PREFLIGHT_V1"
CAPACITY_SCHEMA = "CP_FROZEN_RESOURCE_CAPACITY_V1"
_GIB = float(1024 ** 3)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        value = float(value)
    except Exception:
        value = float(default)
    return max(float(lo), min(float(hi), value))


def compile_resource_capacity(profile: dict, resource_budget: dict, dataset_capacity: dict | None, cfg: dict | None = None) -> dict:
    """Freeze hardware/resource limits into the research plan.

    Free-memory figures are snapshot evidence.  Limits use the stricter of the Owner
    fraction of total memory and 95% of currently-free memory so a Factory does not
    reserve resources that were already unavailable at START RESEARCH.
    """
    profile = profile if isinstance(profile, dict) else {}
    budget = resource_budget if isinstance(resource_budget, dict) else {}
    dataset_capacity = dataset_capacity if isinstance(dataset_capacity, dict) else {}
    mem = profile.get("memory") or {}
    devices = list(((profile.get("nvidia") or {}).get("devices") or []))
    primary = devices[0] if devices else {}
    ram_total = _num(mem.get("total_gib"))
    ram_free = _num(mem.get("available_gib"))
    vram_total = _num(primary.get("memory_total_gib"))
    vram_free = _num(primary.get("memory_free_gib"))
    safe_ram = _clamp(budget.get("safe_ram_fraction", 0.75), 0.05, 0.99, 0.75)
    safe_vram = _clamp(budget.get("safe_vram_fraction", 0.80), 0.05, 0.99, 0.80)
    max_minutes = max(1.0, _num(budget.get("max_single_experiment_minutes", 120), 120))

    def limit(total: float, free: float, frac: float) -> float | None:
        if total <= 0:
            return None
        by_total = total * frac
        if free > 0:
            return round(min(by_total, free * 0.95), 4)
        return round(by_total, 4)

    cpu = profile.get("cpu") or {}
    physical=cpu.get("physical_cores")
    logical=max(1,int(_num(cpu.get("logical_threads"),1)))
    cores=max(1,int(_num(cpu.get("planning_cores") or physical or (logical//2 if logical>=4 else logical),1)))
    cuda = bool((profile.get("torch") or {}).get("cuda_available"))
    compute_mode = str(((cfg or {}).get("compute") or {}).get("mode") or "AUTO").upper().replace("/HIP", "")
    if compute_mode not in {"AUTO", "CPU", "CUDA", "ROCM", "VULKAN"}:
        compute_mode = "AUTO"
    temporal_backend_intent = "CUDA" if cuda and compute_mode in {"AUTO", "CUDA"} else "CPU"

    ds = dataset_capacity.get("dataset") or {}
    wfa = dataset_capacity.get("wfa") or {}
    ref = dataset_capacity.get("reference_scenario") or {}
    return {
        "schema": CAPACITY_SCHEMA,
        "estimator_schema": SCHEMA,
        "hardware_profile_hash": profile.get("profile_hash"),
        "hardware": {
            "ram_total_gib": ram_total or None,
            "ram_available_gib": ram_free or None,
            "vram_total_gib": vram_total or None,
            "vram_free_gib": vram_free or None,
            "cuda_available": cuda,
            "physical_cores": int(physical) if physical not in (None,"") else None,
            "logical_threads": logical,
            "planning_cores": cores,
            "core_count_source": cpu.get("core_count_source") or "LEGACY_OR_UNKNOWN",
            "ram_source": mem.get("source") or "LEGACY_OR_UNKNOWN",
            "compute_mode": compute_mode,
            "temporal_backend_intent": temporal_backend_intent,
        },
        "limits": {
            "ram_gib": limit(ram_total, ram_free, safe_ram),
            "vram_gib": limit(vram_total, vram_free, safe_vram) if temporal_backend_intent == "CUDA" else None,
            "estimated_minutes": round(max_minutes, 4),
            "safe_ram_fraction": safe_ram,
            "safe_vram_fraction": safe_vram,
        },
        "dataset_reference": {
            "rows_per_month": _num(ds.get("rows_per_month")) or None,
            "min_train_rows": int(_num(wfa.get("min_train_rows")) or _num(ref.get("estimated_train_rows")) or 0) or None,
            "median_train_rows": int(_num(wfa.get("median_train_rows")) or _num(ref.get("estimated_train_rows")) or 0) or None,
            "max_train_rows": int(_num(wfa.get("max_train_rows")) or _num(wfa.get("median_train_rows")) or _num(ref.get("estimated_train_rows")) or 0) or None,
            "reference_train_rows": int(_num(ref.get("estimated_train_rows")) or 0) or None,
            "walk_forward_folds": max(1, int(_num(wfa.get("fold_count")) or _num(((cfg or {}).get("split") or {}).get("walk_forward_folds")) or 3)),
        },
        "authority": "HARD_PREFLIGHT_ON_ESTIMATED_PEAK_RAM_VRAM_AND_WFA_RUNTIME",
        "estimator_note": "Engineering upper-bound heuristic, not a wall-clock benchmark. Rejection is fail-closed when an available frozen resource limit is exceeded.",
    }


def _training_rows(plan: dict, params: dict) -> int:
    rc = plan.get("resource_capacity") if isinstance(plan, dict) else {}
    ref = (rc or {}).get("dataset_reference") or {}
    # Resource safety uses the largest chronological WFA train fold. Scientific
    # capacity separately uses the minimum fold so neither authority substitutes for
    # the other. Candidate training-memory may cap this estimate below.
    rows = int(_num(ref.get("max_train_rows")) or _num(ref.get("median_train_rows")) or _num(ref.get("reference_train_rows")) or 0)
    rows_per_month = _num(ref.get("rows_per_month"))
    months = _num((params or {}).get("training_memory_months"))
    if rows_per_month > 0 and months > 0:
        candidate_rows = max(200, int(round(rows_per_month * months)))
        rows = min(rows, candidate_rows) if rows > 0 else candidate_rows
    return max(200, rows or 10_000)


def _resolved_backend(cfg: dict, kind: str, fallback: str) -> str:
    plan = (cfg or {}).get("resolved_compute") or {}
    if kind == "temporal":
        row = plan.get("temporal_dl") or {}
    elif kind == "xgboost":
        row = plan.get("xgboost") or {}
    elif kind == "lightgbm":
        row = plan.get("lightgbm") or {}
    else:
        row = {}
    return str(row.get("backend") or fallback or "CPU").upper()


def _attention_tokens(family: str, params: dict, n_features: int) -> int:
    seq = max(2, int(_num(params.get("sequence_length"), 128)))
    if family == "patchtst":
        patch = max(2, min(seq, int(_num(params.get("patch_len"), 16))))
        stride = max(1, min(patch, int(_num(params.get("patch_stride"), 8))))
        return max(1, 1 + max(0, seq - patch) // stride)
    if family == "itransformer":
        return max(1, int(n_features))
    return seq


def _temporal_resources(family: str, params: dict, parameter_count: int | None, train_rows: int,
                        n_features: int, cores: int, backend: str, vram_total: float) -> dict:
    seq = max(2, int(_num(params.get("sequence_length"), 128)))
    batch = max(1, int(_num(params.get("batch_size"), 64)))
    epochs = max(1, int(_num(params.get("epochs"), 16)))
    layers = max(1, int(_num(params.get("num_layers"), params.get("tcn_blocks", 1))))
    width = max(4, int(_num(params.get("d_model"), params.get("hidden_size", params.get("tcn_channels", 64)))))
    count = max(0, int(parameter_count or 0))

    # CPMF materializes causal [N,T,F] float32 tensors before training.
    seq_tensor = float(train_rows) * seq * max(1, n_features) * 4.0
    source_matrix = float(train_rows) * max(1, n_features) * 4.0
    training_state = float(count) * 16.0  # weights + grads + Adam moments, fp32 upper-bound proxy

    if family in {"transformer", "transformer_moe", "patchtst", "itransformer", "tft"}:
        tokens = _attention_tokens(family, params, n_features)
        heads = max(1, int(_num(params.get("attention_heads"), 1)))
        # Scores/probabilities/backward workspace plus token activations.
        attention = float(batch) * heads * tokens * tokens * layers * 4.0 * 3.0
        representations = float(batch) * tokens * width * layers * 4.0 * 12.0
        moe = 0.0
        if family == "transformer_moe":
            experts = max(2, int(_num(params.get("num_experts"), 4)))
            moe = float(batch) * tokens * width * experts * 4.0 * 3.0
        device_workspace = attention + representations + moe
        arch_factor = {
            "transformer": 1.35, "patchtst": 1.25, "itransformer": 1.15,
            "tft": 1.55, "transformer_moe": 1.90,
        }.get(family, 1.35)
    elif family in {"gru", "lstm"}:
        gate_factor = 8.0 if family == "lstm" else 6.0
        device_workspace = float(batch) * seq * width * layers * 4.0 * gate_factor
        arch_factor = 1.10 if family == "gru" else 1.25
    else:  # TCN and any future simple temporal architecture.
        blocks = max(1, int(_num(params.get("tcn_blocks"), layers)))
        device_workspace = float(batch) * seq * width * blocks * 4.0 * 6.0
        arch_factor = 1.05

    ram_bytes = (0.30 * _GIB) + seq_tensor * 1.35 + source_matrix * 3.0 + training_state * 1.15
    accel = backend in {"CUDA", "ROCM"}
    vram_bytes = (0.25 * _GIB) + training_state * 1.10 + device_workspace if accel else 0.0

    # Work unit: row * million-parameters * epoch.  Architecture/sequence factors
    # deliberately penalize attention and long contexts while remaining deterministic.
    param_m = max(0.05, float(count) / 1_000_000.0)
    seq_factor = max(0.50, math.sqrt(float(seq) / 128.0))
    units = float(train_rows) * float(epochs) * param_m * seq_factor * arch_factor
    if accel:
        accel_scale = max(0.60, min(3.0, (vram_total or 8.0) / 8.0))
        rate = 65_000.0 * accel_scale
    else:
        rate = 5_500.0 * max(0.50, min(4.0, float(cores) / 6.0))
    minutes = 0.35 + units / max(1.0, rate)
    return {
        "peak_ram_gib": ram_bytes / _GIB,
        "peak_vram_gib": vram_bytes / _GIB if accel else 0.0,
        "fit_minutes": minutes,
        "sequence_length": seq,
        "batch_size": batch,
        "epochs": epochs,
        "backend": backend,
    }


def _tree_resources(family: str, params: dict, train_rows: int, n_features: int, cores: int, backend: str) -> dict:
    estimators = max(1, int(_num(params.get("n_estimators"), 300)))
    depth = max(1, int(_num(params.get("max_depth"), 8)))
    classes = 3
    if family == "lightgbm":
        leaves = max(2, int(_num(params.get("num_leaves"), 31)))
        leaves = min(leaves, max(2, train_rows // max(1, int(_num(params.get("min_child_samples"), 20)))))
        nodes = estimators * classes * max(3, 2 * leaves - 1)
        algo_factor = 0.70
        rate = 2_200.0
    elif family == "xgboost":
        leaf_cap = min(2 ** min(depth, 20), max(2, train_rows // 2))
        nodes = estimators * classes * max(3, 2 * leaf_cap - 1)
        algo_factor = 1.00
        rate = 1_500.0 if backend != "CUDA" else 4_500.0
    else:  # random_forest
        min_leaf = max(1, int(_num(params.get("min_samples_leaf"), 1)))
        leaf_cap = min(2 ** min(depth, 20), max(2, train_rows // min_leaf))
        nodes = estimators * max(3, 2 * leaf_cap - 1)
        algo_factor = 0.85
        rate = 1_800.0

    model_bytes = float(nodes) * 64.0
    data_bytes = float(train_rows) * max(1, n_features) * 4.0
    ram_bytes = (0.20 * _GIB) + data_bytes * 8.0 + model_bytes * 2.25
    vram_bytes = 0.0
    if backend in {"CUDA", "OPENCL_GPU"}:
        vram_bytes = (0.20 * _GIB) + data_bytes * 10.0 + model_bytes * 1.25

    # million row-feature-depth-estimator operations, scaled by physical cores.
    complexity = max(1.0, math.log2(max(2.0, float(depth + 1))))
    units = float(train_rows) * estimators * max(1, n_features) * complexity / 1_000_000.0
    core_scale = max(0.60, min(4.0, float(cores) / 6.0))
    minutes = 0.20 + (units * algo_factor) / max(1.0, rate * core_scale)
    return {
        "peak_ram_gib": ram_bytes / _GIB,
        "peak_vram_gib": vram_bytes / _GIB if backend in {"CUDA", "OPENCL_GPU"} else 0.0,
        "fit_minutes": minutes,
        "backend": backend,
        "estimated_nodes_upper": int(nodes),
        "n_estimators": estimators,
        "max_depth": depth,
    }


def estimate_candidate_resources(family: str, params: dict, parameter_count: int | None, cfg: dict, n_features: int = 32) -> dict:
    """Estimate peak resources and total WFA candidate runtime from frozen authority."""
    plan = (((cfg or {}).get("agent") or {}).get("research_plan") or {})
    rc = plan.get("resource_capacity") if isinstance(plan, dict) else None
    if not isinstance(rc, dict) or rc.get("schema") != CAPACITY_SCHEMA:
        return {"schema": SCHEMA, "status": "NOT_APPLICABLE_OR_LEGACY", "available": False}

    hw = rc.get("hardware") or {}
    ref = rc.get("dataset_reference") or {}
    cores = max(1, int(_num(hw.get("planning_cores") or hw.get("physical_cores") or 1, 1)))
    vram_total = _num(hw.get("vram_total_gib"))
    fallback_temporal = str(hw.get("temporal_backend_intent") or "CPU")
    train_rows = _training_rows(plan, params or {})
    folds = max(1, int(_num(ref.get("walk_forward_folds"), 3)))
    fam = str(family or "").lower()
    meta = family_spec(fam) or {}

    temporal = None
    policy = None
    if meta.get("role") == "temporal":
        backend = _resolved_backend(cfg, "temporal", fallback_temporal)
        temporal = _temporal_resources(fam, params, parameter_count, train_rows, n_features, cores, backend, vram_total)
    elif meta.get("role") == "policy":
        fallback = "CPU"
        backend = _resolved_backend(cfg, fam, fallback)
        policy = _tree_resources(fam, params, train_rows, n_features, cores, backend)
    elif is_hybrid_family(fam):
        parts = hybrid_parts(fam)
        if parts:
            tfam, pfam = parts
            tprefix = "temporal_" if fam.startswith("hybrid::") else "gru_"
            tp = {k[len(tprefix):]: v for k, v in (params or {}).items() if k.startswith(tprefix)}
            pp = {k[len("policy_"):]: v for k, v in (params or {}).items() if k.startswith("policy_")}
            if "training_memory_months" in (params or {}):
                tp["training_memory_months"] = params["training_memory_months"]
                pp["training_memory_months"] = params["training_memory_months"]
            tbackend = _resolved_backend(cfg, "temporal", fallback_temporal)
            pbackend = _resolved_backend(cfg, pfam, "CPU")
            temporal = _temporal_resources(tfam, tp, parameter_count, train_rows, n_features, cores, tbackend, vram_total)
            policy = _tree_resources(pfam, pp, train_rows, n_features + 4, cores, pbackend)

    components = [x for x in (temporal, policy) if isinstance(x, dict)]
    if not components:
        return {"schema": SCHEMA, "status": "UNKNOWN_FAMILY", "available": False, "train_rows": train_rows}

    peak_ram = sum(float(x.get("peak_ram_gib") or 0.0) for x in components)
    peak_vram = max([float(x.get("peak_vram_gib") or 0.0) for x in components] or [0.0])
    if temporal and policy:
        # Hybrid fit trains two inner OOF temporal models plus the final temporal model.
        # Peak memory is sequential; runtime is cumulative.
        per_outer_minutes = 3.0 * float(temporal.get("fit_minutes") or 0.0) + float(policy.get("fit_minutes") or 0.0)
        # OOF meta matrix + component coexistence adds modest host-memory overhead.
        peak_ram += float(train_rows) * (n_features + 4) * 4.0 * 2.0 / _GIB
    else:
        per_outer_minutes = sum(float(x.get("fit_minutes") or 0.0) for x in components)
    total_minutes = per_outer_minutes * folds

    return {
        "schema": SCHEMA,
        "status": "ESTIMATED",
        "available": True,
        "train_rows": int(train_rows),
        "walk_forward_folds": int(folds),
        "peak_ram_gib": round(peak_ram, 4),
        "peak_vram_gib": round(peak_vram, 4),
        "estimated_wfa_minutes": round(total_minutes, 4),
        "temporal": temporal,
        "policy": policy,
        "estimator_note": rc.get("estimator_note"),
    }


def candidate_resource_parameter_ceiling(family: str, params: dict, cfg: dict, n_features: int = 32, *, search_upper: int = 500_000_000) -> dict:
    """Invert the production resource estimator into a candidate-shape parameter ceiling.

    This is deliberately candidate-aware: sequence length, batch size, epochs, layers,
    accelerator backend, chronological WFA rows/folds and hybrid inner-OOF multiplication
    all participate through :func:`estimate_candidate_resources`.  It replaces broad
    hardware parameter buckets as hard authority; those buckets may remain planning
    guidance only.
    """
    fam=str(family or "").lower().strip()
    meta=family_spec(fam) or {}
    if meta.get("role") != "temporal" and not is_hybrid_family(fam):
        return {
            "available":False,"resource_parameter_ceiling":None,
            "authority":"NOT_APPLICABLE_TREE_MODEL",
            "binding_gates":[],
        }
    plan=(((cfg or {}).get("agent") or {}).get("research_plan") or {})
    rc=plan.get("resource_capacity") if isinstance(plan,dict) else None
    if not isinstance(rc,dict) or rc.get("schema") != CAPACITY_SCHEMA:
        return {
            "available":False,"resource_parameter_ceiling":None,
            "authority":"FROZEN_RESOURCE_CAPACITY_UNAVAILABLE",
            "binding_gates":[],
        }
    upper=max(1,int(search_upper or 1))
    def passes(count:int):
        est=estimate_candidate_resources(fam,params,int(count),cfg,n_features)
        gate=evaluate_resource_limits(est,rc)
        return bool(gate.get("passed",True)),est,gate
    ok1,est1,gate1=passes(1)
    if not ok1:
        return {
            "available":True,"resource_parameter_ceiling":0,
            "authority":"CANDIDATE_SHAPE_RESOURCE_ESTIMATOR_INVERTED_HARD_CEILING",
            "binding_gates":list(gate1.get("failed_gates") or []),
            "minimum_count_estimate":est1,
        }
    oku,estu,gateu=passes(upper)
    if oku:
        return {
            "available":True,"resource_parameter_ceiling":upper,
            "authority":"CANDIDATE_SHAPE_RESOURCE_ESTIMATOR_INVERTED_HARD_CEILING",
            "binding_gates":[],"search_upper_reached":True,
        }
    lo,hi=1,upper
    while lo+1<hi:
        mid=(lo+hi)//2
        ok,_,_=passes(mid)
        if ok: lo=mid
        else: hi=mid
    _,_,first_fail=passes(hi)
    return {
        "available":True,"resource_parameter_ceiling":int(lo),
        "authority":"CANDIDATE_SHAPE_RESOURCE_ESTIMATOR_INVERTED_HARD_CEILING",
        "binding_gates":list(first_fail.get("failed_gates") or []),
        "first_rejected_parameter_count":int(hi),
    }


def evaluate_resource_limits(estimate: dict, resource_capacity: dict) -> dict:
    limits = (resource_capacity or {}).get("limits") or {}
    failed = []
    if not bool((estimate or {}).get("available")):
        return {"passed": True, "failed_gates": [], "first_failed_gate": None, "limits": limits}

    ram_limit = limits.get("ram_gib")
    vram_limit = limits.get("vram_gib")
    time_limit = limits.get("estimated_minutes")
    if ram_limit is not None and _num(estimate.get("peak_ram_gib")) > _num(ram_limit):
        failed.append("ESTIMATED_PEAK_RAM_EXCEEDS_OWNER_BUDGET")
    if vram_limit is not None and _num(estimate.get("peak_vram_gib")) > _num(vram_limit):
        failed.append("ESTIMATED_PEAK_VRAM_EXCEEDS_OWNER_BUDGET")
    if time_limit is not None and _num(estimate.get("estimated_wfa_minutes")) > _num(time_limit):
        failed.append("ESTIMATED_WFA_RUNTIME_EXCEEDS_OWNER_BUDGET")
    return {
        "passed": not failed,
        "failed_gates": failed,
        "first_failed_gate": failed[0] if failed else None,
        "limits": limits,
    }
