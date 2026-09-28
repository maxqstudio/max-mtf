from __future__ import annotations

"""Advisory-only model-size helpers for the MAX Research UI.

This module never mutates Owner model settings and never grants PASS/FAIL.  It reuses
MAX's legal model registry, deterministic hardware/dataset envelopes and the existing
0..1 family-size resolver so the UI can explain what a slider position means and offer
an evidence-based starting point.
"""

from copy import deepcopy
from itertools import product
from math import log
from typing import Any

import numpy as np

from models.capacity_governor import _parameter_band
from host.compute_backend import resolve_compute_plan
from core.contract import FEATURES
from models.model_registry import (
    all_families,
    clamp_size_priority,
    family_spec,
    get_bounds,
    effective_bounds,
)
from models.models import CandidateSpec, estimate_candidate_parameter_count
from research.research_architect import recommended_parameter_envelopes
from core.temporal_index import expanding_folds

SCHEMA = "MAX_MODEL_SIZE_ADVISOR_V1"
GRID = tuple(round(i * 0.05, 2) for i in range(21))


def _q05(value: float) -> float:
    x = max(0.0, min(1.0, float(value)))
    return round(round(x / 0.05) * 0.05, 2)


def _intersect(legal: dict[str, tuple[Any, Any, type]], env: dict[str, Any] | None) -> dict[str, tuple[Any, Any, type]]:
    env = env if isinstance(env, dict) else {}
    out: dict[str, tuple[Any, Any, type]] = {}
    for key, (lo, hi, typ) in legal.items():
        raw = env.get(key)
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            try:
                a, b = float(raw[0]), float(raw[1])
                if a > b:
                    a, b = b, a
                nlo, nhi = max(float(lo), a), min(float(hi), b)
                if nlo <= nhi:
                    if typ is int:
                        out[key] = (int(round(nlo)), int(round(nhi)), typ)
                    else:
                        out[key] = (float(nlo), float(nhi), typ)
                    continue
            except Exception:
                pass
        out[key] = (lo, hi, typ)
    return out



def training_capacity_profile(identity: dict[str, Any], cfg: dict, *, sequence_hint: int | None = None) -> dict[str, Any]:
    """Build an advisory capacity basis using the *actual WFA min_train_rows authority*.

    This intentionally does not modify the historical capacity_governor's internal
    min-row heuristic.  The advisor has its own basis because the Owner asked the UI
    suggestion to reflect the training contract actually used by WFA.
    """
    rows = max(1, int((identity or {}).get("rows") or 0))
    split = cfg.get("split") or {}
    folds_n = max(1, int(split.get("walk_forward_folds", 3) or 3))
    purge = max(0, int(split.get("purge_bars", 24) or 0))
    min_train = max(1, int(split.get("min_train_rows", 1000) or 1000))
    min_val = max(1, int(split.get("min_validation_rows", 50) or 50))
    seq = max(8, int(sequence_hint if sequence_hint is not None else ((cfg.get("research_architecture") or {}).get("sequence_capacity_hint", 128) or 128)))
    status = "OK"
    reason = None
    try:
        folds = expanding_folds(rows, folds_n, purge, min_train_rows=min_train, min_validation_rows=min_val)
        tr = [int(len(a)) for a, _ in folds]
        va = [int(len(b)) for _, b in folds]
    except Exception as exc:
        # Fail closed for the suggestion: no fabricated large-model advice when the
        # configured WFA itself cannot be constructed.
        tr, va = [], []
        status = "INSUFFICIENT_WFA_DATA"
        reason = str(exc)
    basis_rows = int(min(tr)) if tr else 0
    band = _parameter_band(max(1, basis_rows), seq) if tr else None
    return {
        "schema": SCHEMA,
        "status": status,
        "reason": reason,
        "dataset_rows": rows,
        "wfa_train_rows_by_fold": tr,
        "wfa_validation_rows_by_fold": va,
        "minimum_wfa_train_rows": basis_rows,
        "configured_min_train_rows": min_train,
        "purge_bars": purge,
        "sequence_reference": seq,
        "capacity_band": band,
        # Shape expected by recommended_parameter_envelopes/recommended_capacity_envelopes.
        "reference_scenario": ({
            "training_memory_months": None,
            "estimated_train_rows": basis_rows,
            **(band or {}),
        } if band else {}),
    }


def deterministic_safe_envelopes(profile: dict[str, Any], cfg: dict, capacity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    try:
        compute = resolve_compute_plan(cfg)
    except Exception:
        compute = cfg.get("resolved_compute") or {}
    return recommended_parameter_envelopes(profile, capacity if capacity.get("status") == "OK" else None, compute)


def resolved_family_bounds(family: str, priority: float, safe_envelopes: dict[str, dict[str, Any]]) -> dict[str, tuple[Any, Any, type]]:
    """Resolve through the canonical candidate engine, not a UI-side replica.

    We construct an ephemeral compiled-plan preview containing the deterministic
    dataset/hardware envelope and the requested Owner size priority, then delegate to
    model_registry.effective_bounds().  This guarantees the tooltip and candidate
    generator share the same legal-envelope intersection, rounding, and slider logic.
    """
    fam = str(family).strip().lower()
    preview_cfg = {
        "agent": {
            "research_plan": {
                "parameter_envelopes": {fam: dict((safe_envelopes or {}).get(fam) or {})},
                "family_size_priorities": {fam: clamp_size_priority(priority)},
            }
        },
        "research_architecture": {"family_size_priorities": {fam: clamp_size_priority(priority)}},
    }
    return effective_bounds(preview_cfg, fam)


def _mid_params(bounds: dict[str, tuple[Any, Any, type]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, (lo, hi, typ) in bounds.items():
        if typ is int:
            out[key] = int(round((float(lo) + float(hi)) / 2.0))
        else:
            out[key] = (float(lo) + float(hi)) / 2.0
    return out


def _parameter_count_range(family: str, bounds: dict[str, tuple[Any, Any, type]], n_features: int) -> tuple[int | None, int | None]:
    spec = family_spec(family) or {}
    if str(spec.get("role") or "") != "temporal":
        return None, None
    size_keys = [k for k in (spec.get("size_parameters") or []) if k in bounds]
    if not size_keys:
        return None, None
    base = _mid_params(bounds)
    # All-low/all-high are monotonic for current executable size dimensions. Add mixed
    # corners for small key sets so future registry changes cannot silently break the
    # estimate. Current largest set is four keys (16 corners).
    corners = list(product((0, 1), repeat=len(size_keys))) if len(size_keys) <= 4 else [(0,) * len(size_keys), (1,) * len(size_keys)]
    counts: list[int] = []
    for corner in corners:
        p = dict(base)
        for bit, key in zip(corner, size_keys):
            lo, hi, typ = bounds[key]
            p[key] = hi if bit else lo
        try:
            n = estimate_candidate_parameter_count(CandidateSpec(family=family, name="advisor", params=p), n_features=n_features)
            if n is not None and int(n) > 0:
                counts.append(int(n))
        except Exception:
            continue
    return (min(counts), max(counts)) if counts else (None, None)


def _representative_parameter_count(family: str, bounds: dict[str, tuple[Any, Any, type]], n_features: int) -> int | None:
    spec = family_spec(family) or {}
    if str(spec.get("role") or "") != "temporal":
        return None
    try:
        return estimate_candidate_parameter_count(CandidateSpec(family=family, name="advisor_mid", params=_mid_params(bounds)), n_features=n_features)
    except Exception:
        return None


def _generic_data_priority(capacity: dict[str, Any]) -> float:
    band = capacity.get("capacity_band") or {}
    center = float(band.get("center_total_params") or 100_000.0)
    # This is the normalized form of MAX's existing capacity-governor center clamp.
    # No new sample-size thresholds are introduced here.
    return _q05((center - 100_000.0) / (1_250_000.0 - 100_000.0))


def suggested_priority(family: str, safe_envelopes: dict[str, dict[str, Any]], capacity: dict[str, Any], *, n_features: int | None = None) -> dict[str, Any]:
    fam = str(family).strip().lower()
    if capacity.get("status") != "OK":
        return {"status": "INSUFFICIENT_WFA_DATA", "suggested_priority": None, "reason": capacity.get("reason")}
    nfeat = int(n_features or len(FEATURES))
    generic = _generic_data_priority(capacity)
    meta = family_spec(fam) or {}
    if str(meta.get("role") or "") != "temporal":
        return {
            "status": "OK",
            "suggested_priority": generic,
            "method": "DATA_CAPACITY_SCALAR_FROM_EXISTING_GOVERNOR",
            "target_parameter_count": None,
        }
    band = capacity.get("capacity_band") or {}
    target = int(band.get("center_total_params") or 0)
    if target <= 0:
        return {"status": "OK", "suggested_priority": generic, "method": "DATA_CAPACITY_FALLBACK"}
    candidates: list[tuple[float, float, int]] = []
    for p in GRID:
        b = resolved_family_bounds(fam, p, safe_envelopes)
        count = _representative_parameter_count(fam, b, nfeat)
        if count is None or count <= 0:
            continue
        # Relative/log distance is scale-stable across 100k and multi-million models.
        dist = abs(log(float(count) / float(target)))
        candidates.append((dist, abs(p - generic), int(count), p))
    if not candidates:
        return {"status": "OK", "suggested_priority": generic, "method": "DATA_CAPACITY_FALLBACK", "target_parameter_count": target}
    candidates.sort(key=lambda x: (x[0], x[1], x[3]))
    _, _, count, p = candidates[0]
    return {
        "status": "OK",
        "suggested_priority": float(p),
        "method": "TEMPORAL_PARAMETER_COUNT_MATCH_TO_EXISTING_CAPACITY_CENTER",
        "target_parameter_count": target,
        "representative_parameter_count": int(count),
    }



def current_family_resolution(family: str, priority: float, safe_envelopes: dict[str, dict[str, Any]], *, n_features: int | None = None) -> dict[str, Any]:
    fam = str(family).strip().lower()
    nfeat = int(n_features or len(FEATURES))
    current = clamp_size_priority(priority)
    resolved = resolved_family_bounds(fam, current, safe_envelopes)
    spec = family_spec(fam) or {}
    size_keys = [k for k in (spec.get("size_parameters") or []) if k in resolved]
    pmin, pmax = _parameter_count_range(fam, resolved, nfeat)
    return {
        "family": fam,
        "current_priority": current,
        "current_bounds": {k: [v[0], v[1]] for k, v in resolved.items()},
        "size_parameters": size_keys,
        "estimated_parameter_count_range": [pmin, pmax] if pmin is not None and pmax is not None else None,
    }

def family_advice(family: str, current_priority: float, safe_envelopes: dict[str, dict[str, Any]], capacity: dict[str, Any], *, n_features: int | None = None) -> dict[str, Any]:
    fam = str(family).strip().lower()
    nfeat = int(n_features or len(FEATURES))
    current = clamp_size_priority(current_priority)
    resolved = resolved_family_bounds(fam, current, safe_envelopes)
    spec = family_spec(fam) or {}
    size_keys = [k for k in (spec.get("size_parameters") or []) if k in resolved]
    pmin, pmax = _parameter_count_range(fam, resolved, nfeat)
    suggestion = suggested_priority(fam, safe_envelopes, capacity, n_features=nfeat)
    sp = suggestion.get("suggested_priority")
    suggested_bounds = resolved_family_bounds(fam, float(sp), safe_envelopes) if sp is not None else {}
    manual_ranges: dict[str, dict[str, Any]] = {}
    legal = get_bounds([fam]).get(fam, {})
    safe = _intersect(legal, (safe_envelopes or {}).get(fam))
    for key, (lo, hi, typ) in legal.items():
        src = suggested_bounds.get(key) if key in size_keys and suggested_bounds else safe.get(key, (lo, hi, typ))
        manual_ranges[key] = {
            "suggested": [src[0], src[1]],
            "allowed": [lo, hi],
            "size_controlled": key in size_keys,
        }
    return {
        "schema": SCHEMA,
        "family": fam,
        "current_priority": current,
        "suggestion": suggestion,
        "current_bounds": {k: [v[0], v[1]] for k, v in resolved.items()},
        "size_parameters": size_keys,
        "estimated_parameter_count_range": [pmin, pmax] if pmin is not None and pmax is not None else None,
        "manual_parameter_ranges": manual_ranges,
        "basis": {
            "dataset_rows": capacity.get("dataset_rows"),
            "minimum_wfa_train_rows": capacity.get("minimum_wfa_train_rows"),
            "configured_min_train_rows": capacity.get("configured_min_train_rows"),
            "sequence_reference": capacity.get("sequence_reference"),
            "status": capacity.get("status"),
        },
        "authority": "ADVISORY_ONLY_NEVER_AUTO_APPLY",
    }


def build_advisor(identity: dict[str, Any], cfg: dict, profile: dict[str, Any], families: list[str] | None = None) -> dict[str, Any]:
    capacity = training_capacity_profile(identity, cfg)
    safe = deterministic_safe_envelopes(profile, cfg, capacity)
    priorities = ((cfg.get("research_architecture") or {}).get("family_size_priorities") or {})
    fams = families or [f for f in all_families(include_legacy=False, include_dynamic=False) if not (family_spec(f) or {}).get("legacy_alias")]
    advice = {
        fam: family_advice(fam, priorities.get(fam, 0.50), safe, capacity, n_features=len(FEATURES))
        for fam in fams if family_spec(fam)
    }
    return {
        "schema": SCHEMA,
        "capacity": capacity,
        "safe_envelopes": {f: {k: list(v) if isinstance(v, tuple) else v for k, v in (safe.get(f) or {}).items()} for f in safe},
        "families": advice,
        "authority": "ADVISORY_ONLY_NEVER_AUTO_APPLY",
    }
