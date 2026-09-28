from __future__ import annotations

"""Dataset/evidence-aware temporal model-capacity authority for MAX MTF.

Capacity has three different meanings and they must never be conflated:

* LEGAL: what the implementation can represent.
* RESOURCE: what the frozen machine/Owner budget can execute safely.
* SCIENTIFIC: what the candidate's actual chronological training information can
  reasonably justify exploring.

Historical recommended parameter envelopes remain useful *starting guidance*.  They
are deliberately not a hidden executable maximum.  Candidate admission is performed
on the executable model parameter count plus candidate-specific resource/scientific
checks in :mod:`models`.
"""

from copy import deepcopy
from math import ceil
from typing import Any

import numpy as np
import pandas as pd

from core.temporal_index import expanding_folds
from models.model_registry import hybrid_parts, is_hybrid_family

SCHEMA = "CP_DATASET_CAPACITY_PROFILE_V2_DYNAMIC_CANDIDATE_AWARE"
SCIENTIFIC_SCHEMA = "MAX_DYNAMIC_SCIENTIFIC_CAPACITY_V1"
CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY = "CUMULATIVE_COMMITTED_FULL_WFA_CURRENT_FACTORY"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(v)))


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _months_between(start: Any, end: Any) -> float:
    a = pd.to_datetime(start, errors="coerce")
    b = pd.to_datetime(end, errors="coerce")
    if pd.isna(a) or pd.isna(b) or b <= a:
        return 0.0
    return max(1.0 / 30.4375, float((b - a).total_seconds()) / (86400.0 * 30.4375))


def _parameter_band(train_rows: int, sequence_length: int) -> dict[str, Any]:
    """Reference-only dataset capacity band.

    This function intentionally remains a coarse *reference* for UI/Scientist context.
    Hard admission is candidate-aware and is calculated by
    :func:`candidate_scientific_capacity`.
    """
    rows = max(1, int(train_rows))
    seq = max(8, int(sequence_length))
    overlap_factor = _clamp(32.0 / float(seq), 0.0625, 1.0)
    effective = max(64, int(round(rows * overlap_factor)))
    center = int(round(_clamp(effective * 100.0, 75_000.0, 1_750_000.0)))
    preferred = [int(round(center * 0.60)), int(round(center * 1.60))]
    extended = [int(round(center * 0.40)), int(round(center * 3.00))]
    return {
        "train_rows": rows,
        "sequence_length": seq,
        "overlap_discount": round(overlap_factor, 6),
        "effective_sequence_samples_heuristic": int(effective),
        "preferred_total_params": preferred,
        "extended_total_params": extended,
        "center_total_params": center,
        "authority": "RECOMMENDED_STARTING_REFERENCE_NOT_EXECUTABLE_MAXIMUM",
    }


def build_dataset_capacity_profile(identity: dict[str, Any], cfg: dict, *, feature_count: int = 32,
                                   sequence_hint: int = 128) -> dict[str, Any]:
    rows = max(1, int((identity or {}).get("rows") or 0))
    split = cfg.get("split") or {}
    folds_n = max(1, int(split.get("walk_forward_folds", 3) or 3))
    purge = max(0, int(split.get("purge_bars", 0) or 0))
    try:
        folds = expanding_folds(rows, folds_n, purge, min_train_rows=200, min_validation_rows=50)
        train_rows = [int(len(tr)) for tr, _ in folds]
        val_rows = [int(len(va)) for _, va in folds]
    except Exception:
        train_rows = [max(200, int(rows * 0.50))]
        val_rows = [max(50, rows - train_rows[0])]

    months = _months_between((identity or {}).get("start"), (identity or {}).get("end"))
    rows_per_month = float(rows / months) if months > 0 else 0.0
    scenario_months = [6, 12, 18, 24, 36, 48, 60]
    if months > 0:
        scenario_months = [m for m in scenario_months if m <= int(ceil(months))] or [max(1, int(round(months)))]
    scenarios = []
    median_fold = int(np.median(train_rows)) if train_rows else max(1, rows // 2)
    for m in scenario_months:
        est = int(round(rows_per_month * m)) if rows_per_month > 0 else median_fold
        est = max(200, min(median_fold, est))
        band = _parameter_band(est, sequence_hint)
        scenarios.append({"training_memory_months": int(m), "estimated_train_rows": est, **band})

    ref = next((x for x in scenarios if int(x["training_memory_months"]) == 18), None)
    if ref is None:
        ref = min(scenarios, key=lambda x: abs(int(x["training_memory_months"]) - 18)) if scenarios else {
            "training_memory_months": None, "estimated_train_rows": median_fold, **_parameter_band(median_fold, sequence_hint)
        }

    return {
        "schema": SCHEMA,
        "dataset": {
            "symbol": (identity or {}).get("symbol"),
            "period": (identity or {}).get("period"),
            "start": (identity or {}).get("start"),
            "end": (identity or {}).get("end"),
            "snapshot_rows": rows,
            "feature_count": int(feature_count),
            "history_months": round(months, 2) if months > 0 else None,
            "rows_per_month": round(rows_per_month, 6) if rows_per_month > 0 else None,
        },
        "wfa": {
            "fold_count": int(len(train_rows)),
            "train_rows_by_fold": train_rows,
            "validation_rows_by_fold": val_rows,
            "min_train_rows": int(min(train_rows)),
            "median_train_rows": int(np.median(train_rows)),
            "max_train_rows": int(max(train_rows)),
            "purge_bars": purge,
        },
        "sequence_reference": {
            "sequence_hint": int(sequence_hint),
            "authority": "REFERENCE_ONLY_NOT_CANDIDATE_CAPACITY_AUTHORITY",
            "note": "Candidate capacity uses its actual sequence_length; this hint is UI/starting-context only.",
        },
        "training_memory_scenarios": scenarios,
        "reference_scenario": deepcopy(ref),
        "scientist_instruction": (
            "Choose training-memory and architecture jointly. Recommended envelopes are starting guidance only. "
            "Executable admission uses actual parameter count, candidate sequence/memory information, frozen resources, and legal architecture bounds."
        ),
    }


def hardware_parameter_ceiling(profile: dict[str, Any]) -> dict[str, Any]:
    """Broad parameter-count resource proxy.

    Architecture-specific RAM/VRAM/runtime estimates remain the hard resource authority.
    This proxy exists so capacity evidence can expose one comparable resource ceiling.
    """
    mem = profile.get("memory") or {}
    ram = float(mem.get("total_gib") or 0.0)
    gpus = list(((profile.get("nvidia") or {}).get("devices") or []))
    vram = float((gpus[0] if gpus else {}).get("memory_total_gib") or 0.0)
    cuda = bool((profile.get("torch") or {}).get("cuda_available"))
    if cuda and vram >= 20:
        ceiling = 80_000_000
    elif cuda and vram >= 11:
        ceiling = 40_000_000
    elif cuda and vram >= 7:
        ceiling = 20_000_000
    elif cuda and vram >= 4:
        ceiling = 8_000_000
    elif ram >= 24:
        ceiling = 3_000_000
    else:
        ceiling = 1_500_000
    return {
        "parameter_count_proxy_ceiling": int(ceiling),
        # compatibility field; no longer described as a scientific/safe envelope
        "soft_absolute_parameter_ceiling": int(ceiling),
        "cuda_available": cuda,
        "vram_gib": vram,
        "ram_gib": ram,
        "authority": "RESOURCE_PARAMETER_PROXY_PLUS_ARCHITECTURE_SPECIFIC_HARD_PREFLIGHT",
    }


def recommended_capacity_envelopes(capacity: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    ref = capacity.get("reference_scenario") or {}
    preferred = list(ref.get("preferred_total_params") or [150_000, 400_000])
    extended = list(ref.get("extended_total_params") or [100_000, 800_000])
    compute = hardware_parameter_ceiling(profile)
    resource_proxy = int(compute["parameter_count_proxy_ceiling"])
    # These are reference bands only. Candidate hard admission does NOT consume the
    # reference extended max as a universal ceiling.
    extended[1] = min(int(extended[1]), resource_proxy)
    preferred[1] = min(int(preferred[1]), int(extended[1]))
    return {
        "preferred_total_params": [int(preferred[0]), int(preferred[1])],
        "extended_total_params": [int(extended[0]), int(extended[1])],
        "compute": compute,
        "reference_training_memory_months": ref.get("training_memory_months"),
        "reference_train_rows": ref.get("estimated_train_rows"),
        "reference_sequence_length": ref.get("sequence_length"),
        "authority": "RECOMMENDED_STARTING_ENVELOPE_ONLY",
        "note": (
            "Reference preferred/extended bands guide normal Discovery. They are not an absolute executable maximum. "
            "Hard candidate admission uses min(LEGAL, RESOURCE, candidate-aware SCIENTIFIC) plus architecture-specific resource preflight."
        ),
    }


def _temporal_params(family: str, params: dict[str, Any]) -> tuple[str, dict[str, Any], bool]:
    fam = str(family or "").lower().strip()
    p = dict(params or {})
    if is_hybrid_family(fam):
        parts = hybrid_parts(fam)
        if not parts:
            return fam, p, False
        temporal = str(parts[0])
        prefix = "temporal_" if fam.startswith("hybrid::") else "gru_"
        tp = {k[len(prefix):]: v for k, v in p.items() if str(k).startswith(prefix)}
        if "training_memory_months" in p:
            tp["training_memory_months"] = p["training_memory_months"]
        return temporal, tp, True
    return fam, p, False


def _family_information_factor(family: str) -> float:
    # Parameter-per-effective-sample engineering allowance. This is deliberately
    # conservative and architecture-aware, while legal/resource ceilings remain hard.
    return {
        "gru": 420.0,
        "lstm": 400.0,
        "tcn": 450.0,
        "transformer": 460.0,
        "patchtst": 480.0,
        "itransformer": 480.0,
        "tft": 400.0,
        "transformer_moe": 520.0,
    }.get(str(family), 400.0)


def candidate_scientific_capacity(cfg: dict, family: str, params: dict[str, Any]) -> dict[str, Any]:
    """Candidate-aware scientific capacity from *actual* temporal memory/sequence.

    The result is a hard scientific parameter-count ceiling, but the heuristic itself is
    intentionally conservative evidence rather than a claim of statistical optimality.
    Raw candle count is never treated as IID sample count.
    """
    plan = (((cfg or {}).get("agent") or {}).get("research_plan") or {})
    profile = plan.get("dataset_capacity_profile") if isinstance(plan, dict) else None
    if not isinstance(profile, dict) or not profile:
        return {
            "schema": SCIENTIFIC_SCHEMA,
            "available": False,
            "authority": "LEGACY_OR_DATASET_PROFILE_UNAVAILABLE",
            "scientific_parameter_ceiling": None,
        }

    temporal_family, tp, hybrid = _temporal_params(family, params)
    if temporal_family not in {"gru","lstm","tcn","transformer","patchtst","itransformer","tft","transformer_moe"}:
        return {
            "schema": SCIENTIFIC_SCHEMA,
            "available": False,
            "authority": "NOT_APPLICABLE_TREE_MODEL",
            "scientific_parameter_ceiling": None,
        }

    ds = profile.get("dataset") or {}
    wfa = profile.get("wfa") or {}
    min_fold_rows = int(_num(wfa.get("min_train_rows")) or _num(wfa.get("median_train_rows")) or 0)
    if min_fold_rows <= 0:
        return {
            "schema": SCIENTIFIC_SCHEMA,
            "available": False,
            "authority": "DATASET_PROFILE_MISSING_WFA_ROWS",
            "scientific_parameter_ceiling": None,
        }
    rows_per_month = _num(ds.get("rows_per_month"))
    months = max(0.0, _num(tp.get("training_memory_months")))
    configured_min_rows = max(200, int(_num(((cfg or {}).get("split") or {}).get("min_train_rows"), 1000)))
    memory_candidate_rows = min_fold_rows
    memory_applied = False
    if rows_per_month > 0 and months > 0:
        proposed = max(1, int(round(rows_per_month * months)))
        # Mirror temporal_index.apply_training_memory: too-short candidate memory falls
        # back to the full fold rather than pretending fewer rows will be fitted.
        if proposed >= configured_min_rows:
            memory_candidate_rows = min(min_fold_rows, proposed)
            memory_applied = True

    seq = max(1, int(_num(tp.get("sequence_length"), 1)))
    split = (cfg or {}).get("split") or {}
    label = (cfg or {}).get("label") or {}
    horizon = max(
        int(_num(label.get("max_hold_bars"))),
        int(_num(label.get("horizon_bars"))),
        int(_num(split.get("purge_bars"))),
        int(_num(split.get("embargo_bars"))),
        1,
    )
    purge = max(int(_num(split.get("purge_bars"))), horizon)
    embargo = max(int(_num(split.get("embargo_bars"))), horizon)

    # Inner OOF temporal fits in a hybrid see a smaller chronological training prefix.
    # Resource cost handles the 3x repeated fits; scientific capacity uses the minimum
    # information actually available to an inner temporal encoder.
    oof_fraction = 0.45 if hybrid else 1.0
    min_temporal_train_rows = max(1, int(memory_candidate_rows * oof_fraction))
    eligible = max(0, min_temporal_train_rows - max(seq - 1, 0) - horizon)
    independence_span = max(32, seq, horizon, purge, embargo)
    overlap_discount = min(1.0, 32.0 / float(independence_span))
    effective_samples = max(1, int(eligible * overlap_discount))

    family_factor = _family_information_factor(temporal_family)
    scientific_ceiling = max(50_000, int(round(effective_samples * family_factor)))
    preferred_low = max(25_000, int(round(scientific_ceiling * 0.28)))
    preferred_high = max(preferred_low, int(round(scientific_ceiling * 0.68)))

    return {
        "schema": SCIENTIFIC_SCHEMA,
        "available": True,
        "authority": "CANDIDATE_AWARE_EFFECTIVE_INFORMATION_HARD_CEILING",
        "family": str(family),
        "temporal_family": temporal_family,
        "hybrid_temporal_oof": bool(hybrid),
        "training_memory_months": None if months <= 0 else float(months),
        "training_memory_applied_estimate": bool(memory_applied),
        "minimum_fold_train_rows": int(min_fold_rows),
        "minimum_temporal_train_rows": int(min_temporal_train_rows),
        "sequence_length": int(seq),
        "label_horizon_bars": int(horizon),
        "purge_bars": int(purge),
        "embargo_bars": int(embargo),
        "supervised_eligible_rows_estimate": int(eligible),
        "independence_span_bars": int(independence_span),
        "overlap_discount": round(float(overlap_discount), 8),
        "effective_sample_estimate": int(effective_samples),
        "family_information_factor": float(family_factor),
        "preferred_parameter_range": [int(preferred_low), int(preferred_high)],
        "scientific_parameter_ceiling": int(scientific_ceiling),
        "extended_parameter_ceiling": int(scientific_ceiling),
        "note": "Engineering scientific-capacity heuristic; qualification still requires WFA/CPCV/seed/Tournament/MC/Forward evidence.",
    }


def _neutral_capacity_evidence(reason: str = "INSUFFICIENT_COMMITTED_WFA_CAPACITY_EVIDENCE", sample_count: int = 0, *, authority: str | None = None) -> dict[str, Any]:
    return {
        "schema":"MAX_CAPACITY_EVIDENCE_SIGNAL_V2_FAMILY_SPECIFIC",
        "status":"HOLD",
        "reason":str(reason),
        "sample_count":int(sample_count),
        "generation_first":None,
        "generation_last":None,
        "unique_experiment_count":int(sample_count),
        "lower_median_score":None,
        "upper_median_score":None,
        "lower_pass_rate":None,
        "upper_pass_rate":None,
        "score_delta":None,
        "search_bias_delta":0.0,
        "target_quantile_shift":0.0,
        "expansion_factor":1.0,
        "authority":str(authority or "FAMILY_SPECIFIC_SEARCH_LOCATION_ONLY_NEVER_HARD_CEILING_OVERRIDE"),
        "capacity_effect":"SEARCH_LOCATION_ONLY_NEVER_HARD_CEILING_OVERRIDE",
    }


def cumulative_committed_full_wfa_capacity_rows(leaderboards: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Collect cumulative committed Full-WFA observations from one exact Factory.

    ``leaderboards`` is the Factory-local sequence of Supervisor generation leaderboards.
    Callers pass only committed generation blocks.  Eligibility is intentionally strict:
    only rows whose ``fidelity_stage`` starts with ``FULL_WFA`` are capacity evidence.
    Experiment fingerprints are the authoritative dedupe key when present.  Rows without
    a fingerprint are retained independently; they are never collapsed merely because
    family or parameter count happens to match.
    """
    out: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    for block_index, block in enumerate(leaderboards or [], start=1):
        if not isinstance(block, dict):
            continue
        try:
            generation = int(block.get("generation") or block_index)
        except Exception:
            generation = int(block_index)
        run_id = str(block.get("run_id") or "")
        rows = block.get("rows") or []
        if not isinstance(rows, list):
            continue
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if not str(row.get("fidelity_stage") or "").startswith("FULL_WFA"):
                continue
            fingerprint = str(row.get("experiment_fingerprint") or "").strip()
            if fingerprint:
                if fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(fingerprint)
                evidence_identity = f"experiment_fingerprint:{fingerprint}"
            else:
                # No speculative family/size dedupe: equal-sized independent experiments
                # remain valid observations when no authoritative fingerprint exists.
                evidence_identity = f"unfingerprinted:{generation}:{run_id}:{row_index}"
            item = deepcopy(row)
            item["_capacity_generation"] = int(generation)
            item["_capacity_evidence_identity"] = evidence_identity
            out.append(item)
    return out


def summarize_capacity_evidence(rows: list[dict[str, Any]] | None, *, family: str | None = None, authority: str | None = None) -> dict[str, Any]:
    """Deterministic *within-family* capacity-search signal.

    Absolute parameter counts are compared only inside one exact family identity.  A
    hybrid family therefore learns from its own hybrid rows; it never becomes a global
    temporal-capacity signal.  The output can move the search quantile but can never
    widen LEGAL/RESOURCE/SCIENTIFIC admission ceilings.
    """
    fam=(str(family).strip() if family is not None else None)
    usable=[]
    observed_families=set()
    seen_fingerprints=set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        row_family=str(row.get("family") or "").strip()
        if row_family:
            observed_families.add(row_family)
        if fam is not None and row_family != fam:
            continue
        # Global aggregation is deliberately disabled; callers must request one family.
        if fam is None:
            continue
        fingerprint=str(row.get("experiment_fingerprint") or "").strip()
        if fingerprint:
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
        try:
            pc=int(row.get("parameter_count") or (row.get("capacity_contract") or {}).get("parameter_count") or 0)
            score=float(row.get("selection_score"))
        except Exception:
            continue
        if pc > 0 and np.isfinite(score):
            try:
                generation=int(row.get("_capacity_generation") or row.get("factory_generation") or 0)
            except Exception:
                generation=0
            usable.append({
                "parameter_count":pc,
                "score":score,
                "passed":bool(row.get("cv_gate_pass")),
                "generation":generation,
                "identity":str(row.get("_capacity_evidence_identity") or (f"experiment_fingerprint:{fingerprint}" if fingerprint else f"row:{len(usable)}")),
            })
    if fam is None:
        out=_neutral_capacity_evidence("GLOBAL_CAPACITY_SIGNAL_DISABLED_USE_CAPACITY_EVIDENCE_BY_FAMILY",0,authority=authority)
        out.update({"schema":"MAX_CAPACITY_EVIDENCE_INDEX_V2","status":"NO_GLOBAL_SIGNAL","observed_families":sorted(observed_families)})
        return out
    generations=sorted({int(x["generation"]) for x in usable if int(x["generation"]) > 0})
    unique_count=len({str(x["identity"]) for x in usable})
    if len(usable) < 4:
        out=_neutral_capacity_evidence(sample_count=len(usable),authority=authority)
        out.update({
            "family":fam,
            "generation_first":generations[0] if generations else None,
            "generation_last":generations[-1] if generations else None,
            "unique_experiment_count":int(unique_count),
        })
        return out
    usable=sorted(usable,key=lambda x:x["parameter_count"])
    mid=len(usable)//2; lower=usable[:mid]; upper=usable[mid:]
    lo_score=float(np.median([x["score"] for x in lower])); hi_score=float(np.median([x["score"] for x in upper]))
    lo_pass=float(np.mean([1.0 if x["passed"] else 0.0 for x in lower])); hi_pass=float(np.mean([1.0 if x["passed"] else 0.0 for x in upper]))
    delta=hi_score-lo_score
    if delta > 0.03 and hi_pass >= lo_pass:
        status="EXPAND"; bias=0.18; factor=1.18
    elif delta < -0.03 or hi_pass + 0.20 < lo_pass:
        status="CONTRACT"; bias=-0.18; factor=0.82
    else:
        status="HOLD"; bias=0.0; factor=1.0
    return {
        "schema":"MAX_CAPACITY_EVIDENCE_SIGNAL_V2_FAMILY_SPECIFIC","family":fam,"status":status,
        "reason":"WITHIN_FAMILY_WFA_SIZE_GENERALIZATION_COMPARISON","sample_count":len(usable),
        "generation_first":generations[0] if generations else None,"generation_last":generations[-1] if generations else None,
        "unique_experiment_count":int(unique_count),
        "lower_median_score":round(lo_score,8),"upper_median_score":round(hi_score,8),
        "lower_pass_rate":round(lo_pass,6),"upper_pass_rate":round(hi_pass,6),"score_delta":round(delta,8),
        "search_bias_delta":float(bias),"target_quantile_shift":float(bias),"expansion_factor":float(factor),
        "authority":str(authority or "FAMILY_SPECIFIC_SEARCH_LOCATION_ONLY_NEVER_HARD_CEILING_OVERRIDE"),
        "capacity_effect":"SEARCH_LOCATION_ONLY_NEVER_HARD_CEILING_OVERRIDE",
    }


def summarize_capacity_evidence_by_family(rows: list[dict[str, Any]] | None, families: list[str] | None = None, *, authority: str | None = None) -> dict[str, Any]:
    """Build isolated capacity evidence for every exact family identity."""
    fams={str(x).strip() for x in (families or []) if str(x).strip()}
    for row in rows or []:
        if isinstance(row,dict) and str(row.get("family") or "").strip():
            fams.add(str(row.get("family")).strip())
    signals={fam:summarize_capacity_evidence(rows,family=fam,authority=authority) for fam in sorted(fams)}
    return {
        "schema":"MAX_CAPACITY_EVIDENCE_BY_FAMILY_V1",
        "authority":str(authority or "EXACT_FAMILY_IDENTITY_NO_CROSS_FAMILY_PARAMETER_SCALE_COMPARISON"),
        "family_isolation_authority":"EXACT_FAMILY_IDENTITY_NO_CROSS_FAMILY_PARAMETER_SCALE_COMPARISON",
        "families":signals,
    }

