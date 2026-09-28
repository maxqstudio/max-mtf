from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

SCHEMA = "MAX_STRUCTURED_RESEARCH_MEMORY_V2"
EXPERIENCE_SCHEMA = "MAX_RESEARCH_EXPERIENCE_V2"
TERMINAL = {"SUPPORTED", "PARTIALLY_SUPPORTED", "FALSIFIED", "RETIRED"}

# Learning-stage classification is explicit and fail-closed.  Runtime components use
# several aliases (for example FRESH and LOCKED_TEST), so filtering literal strings is
# not sufficient protection for sealed evidence.
_STAGE_ALIASES = {
    "CHEAP_SCREEN": "DISCOVERY",
    "SCREEN": "DISCOVERY",
    "DISCOVERY_FULL_WFA": "FULL_WFA",
    "WFA": "FULL_WFA",
    "CV": "FULL_WFA",
    "POLICY_DISCOVERY": "OOF_POLICY_DISCOVERY",
    "FORWARD": "FRESH_FORWARD",
    "FORWARD_CHAMPIONSHIP": "FRESH_FORWARD",
    "FRESH": "FRESH_FORWARD",
    "FRESH_TEST": "FRESH_FORWARD",
    "LOCKED": "LOCKED_OOS",
    "LOCKED_TEST": "LOCKED_OOS",
    "LOCKED_FORWARD": "LOCKED_OOS",
    "MODEL_CHAMPION": "CHAMPION",
    "FACTORY_WINNER": "CHALLENGER",
    "ELIGIBLE_CHALLENGER": "CHALLENGER",
    "MODEL_CHALLENGER": "CHALLENGER",
}
ADAPTIVE_STAGES = {"DISCOVERY", "FULL_WFA", "MODEL_SEARCH", "OOF_POLICY_DISCOVERY", "POOL"}
VALIDATION_STAGES = {"CPCV", "TOURNAMENT", "MONTE_CARLO"}
PROTECTED_STAGES = {"FRESH_FORWARD", "LOCKED_OOS", "SHADOW", "PROMOTION", "CHALLENGER", "CHAMPION"}


def _stable(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stage_token(raw: Any) -> str:
    token = re.sub(r"[^A-Z0-9]+", "_", str(raw or "").strip().upper()).strip("_")
    return _STAGE_ALIASES.get(token, token)


def stage_learning_zone(raw: Any) -> str:
    """Return ADAPTIVE, VALIDATION, PROTECTED or UNKNOWN for a stage identifier."""
    stage = _stage_token(raw)
    if stage in ADAPTIVE_STAGES:
        return "ADAPTIVE"
    if stage in VALIDATION_STAGES:
        return "VALIDATION"
    if stage in PROTECTED_STAGES:
        return "PROTECTED"
    return "UNKNOWN"


def canonical_stage(raw: Any) -> str:
    return _stage_token(raw)


def _source_gate(h: dict) -> str | None:
    gate = h.get("source_failure_gate")
    if gate:
        return str(gate)
    topo = h.get("source_failure_topology") if isinstance(h.get("source_failure_topology"), dict) else {}
    gate = topo.get("dominant_first_failed_gate")
    return str(gate) if gate else None


def _dict(v: Any) -> dict:
    return deepcopy(v) if isinstance(v, dict) else {}


def _list(v: Any) -> list:
    return deepcopy(v) if isinstance(v, list) else []


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != {} and value != [] and value != "":
            return deepcopy(value)
    return None


def _compact_rich_fields(h: dict, *, payload: dict, decisive: dict) -> dict:
    observations = [deepcopy(x) for x in (h.get("observations") or []) if isinstance(x, dict)]
    last_obs = observations[-1] if observations else {}
    source_topology = _dict(h.get("source_failure_topology"))

    families: list[str] = []
    for f in payload.get("families") or []:
        sf = str(f).strip().lower()
        if sf and sf not in families:
            families.append(sf)
    for f in payload.get("family_priorities") or {}:
        sf = str(f).strip().lower()
        if sf and sf not in families:
            families.append(sf)
    for f in (h.get("families") or []):
        sf = str(f).strip().lower()
        if sf and sf not in families:
            families.append(sf)

    candidate_ids: list[str] = []
    for src in [h, decisive, last_obs, *observations]:
        if not isinstance(src, dict):
            continue
        vals = []
        for key in ("candidate_ids", "matching_candidate_ids"):
            val = src.get(key)
            vals.extend(val if isinstance(val, list) else ([val] if val else []))
        for key in ("candidate_id", "trained_candidate_id", "pool_id"):
            if src.get(key):
                vals.append(src.get(key))
        for val in vals:
            sv = str(val)
            if sv and sv not in candidate_ids:
                candidate_ids.append(sv)

    failure_gates: list[str] = []
    gate = _source_gate(h)
    if gate:
        failure_gates.append(gate)
    for key in ("first_failed_gate_counts", "all_failed_gate_counts"):
        counts = source_topology.get(key) if isinstance(source_topology.get(key), dict) else {}
        for g, count in counts.items():
            try:
                active = float(count) > 0
            except Exception:
                active = bool(count)
            sg = str(g)
            if active and sg not in failure_gates:
                failure_gates.append(sg)
    for src in (decisive, last_obs):
        if isinstance(src, dict):
            for g in src.get("failed_gates") or []:
                sg = str(g)
                if sg and sg not in failure_gates:
                    failure_gates.append(sg)

    label_policy = {k: deepcopy(payload[k]) for k in ("min_edge_r", "min_margin_r", "ambiguous_policy") if k in payload}
    training_memory = _first_present(payload.get("months"), payload.get("preferred_months"), h.get("training_memory"))
    feature_set = _first_present(h.get("feature_set"), {"zero_features": _list(payload.get("zero_features"))} if payload.get("zero_features") else None)
    topology = _first_present(
        h.get("topology"),
        {"pairs": _list(payload.get("pairs"))} if payload.get("pairs") else None,
        {"families": families} if families else None,
    )
    hyperparameters = _first_present(
        h.get("hyperparameters"),
        {
            "parameter_ranges_by_family": _dict(payload.get("parameter_ranges_by_family")),
            "variable_keys_by_family": _dict(payload.get("variable_keys_by_family")),
            "family_priorities": _dict(payload.get("family_priorities")),
        } if any(payload.get(k) for k in ("parameter_ranges_by_family", "variable_keys_by_family", "family_priorities")) else None,
    )
    state_before = _first_present(h.get("state_before"), source_topology or None)
    state_after = _first_present(h.get("state_after"), decisive or None, last_obs or None)
    kpi_deltas = _first_present(h.get("kpi_deltas"), decisive.get("kpi_deltas"), last_obs.get("kpi_deltas"))
    failure_margins = _first_present(h.get("failure_margins"), decisive.get("failure_margins"), last_obs.get("failure_margins"), last_obs.get("best_closest_margin"))
    fold_distribution = _first_present(h.get("fold_distribution"), decisive.get("fold_distribution"), last_obs.get("fold_distribution"), source_topology.get("worst_split_combination"))
    coverage = _first_present(h.get("coverage"), decisive.get("coverage"), last_obs.get("coverage"))
    sample_sufficiency = _first_present(h.get("sample_sufficiency"), decisive.get("sample_sufficiency"), last_obs.get("sample_sufficiency"))

    return {
        "parent_id": _first_present(h.get("parent_id"), h.get("parent_hypothesis_id"), payload.get("parent_id")),
        "experiment_id": _first_present(h.get("experiment_id"), h.get("experiment_block_id"), last_obs.get("block_id"), decisive.get("experiment_id")),
        "candidate_ids": candidate_ids[:32],
        "model_families": families[:12],
        "topology": topology,
        "hyperparameters": hyperparameters,
        "feature_set": feature_set,
        "label_policy": label_policy or None,
        "training_memory": training_memory,
        "experiment_action": {"kind": str(h.get("kind") or "").upper(), "payload": deepcopy(payload)},
        "hypothesis": {
            "title": str(h.get("title") or "")[:240],
            "rationale": str(h.get("rationale") or "")[:1600],
        },
        "predicted_effect": _first_present(h.get("predicted_effect"), h.get("expected_observation")),
        "state_before": state_before,
        "state_after": state_after,
        "kpi_deltas": kpi_deltas,
        "failed_gates": failure_gates[:64],
        "failure_margins": failure_margins,
        "fold_distribution": fold_distribution,
        "coverage": coverage,
        "sample_sufficiency": sample_sufficiency,
        "hypothesis_verdict": str(h.get("status") or "").upper(),
        "outcome": {
            "decisive_reason": decisive.get("reason"),
            "scientific_interpretation": last_obs.get("scientific_interpretation"),
            "observations": observations[-8:],
        },
    }


def hypothesis_to_experience(h: dict) -> dict | None:
    """Convert one committed hypothesis lifecycle row into structured learning evidence.

    Only terminal scientific outcomes from explicitly known adaptive/validation stages are
    admitted.  Protected stages and unknown aliases fail closed so Fresh/Locked/Shadow/
    Promotion evidence cannot become an adaptive reward channel.
    """
    if not isinstance(h, dict):
        return None
    status = str(h.get("status") or "").upper()
    if status not in TERMINAL:
        return None
    decisive = deepcopy(h.get("decisive_outcome") or {}) if isinstance(h.get("decisive_outcome"), dict) else {}
    raw_source_stage = h.get("source_stage") or decisive.get("stage") or "DISCOVERY"
    raw_decisive_stage = decisive.get("stage") or ""
    source_stage = canonical_stage(raw_source_stage)
    decisive_stage = canonical_stage(raw_decisive_stage) if raw_decisive_stage else ""
    source_zone = stage_learning_zone(source_stage)
    decisive_zone = stage_learning_zone(decisive_stage) if decisive_stage else source_zone
    if source_zone in {"PROTECTED", "UNKNOWN"} or decisive_zone in {"PROTECTED", "UNKNOWN"}:
        return None
    kind = str(h.get("kind") or "").upper()
    if not kind:
        return None
    hid = str(h.get("hypothesis_id") or _stable({"kind": kind, "title": h.get("title"), "payload": h.get("payload")})[:16])
    payload = deepcopy(h.get("payload") or {}) if isinstance(h.get("payload"), dict) else {}
    rich = _compact_rich_fields(h, payload=payload, decisive=decisive)
    row = {
        "schema": EXPERIENCE_SCHEMA,
        "hypothesis_id": hid,
        "action_kind": kind,
        "status": status,
        "source": str(h.get("source") or "UNKNOWN"),
        "source_stage": source_stage,
        "source_zone": source_zone,
        "source_generation": int(h.get("source_generation", 0) or 0),
        "source_failure_gate": _source_gate(h),
        "families": deepcopy(rich["model_families"]),
        "payload_fingerprint": _stable(payload),
        "decisive_stage": decisive_stage or None,
        "decisive_zone": decisive_zone if decisive_stage else None,
        "decisive_reason": decisive.get("reason"),
        "protected_evidence_used": False,
        "authority": "ADVISORY_LEARNING_EVIDENCE_ONLY",
        **rich,
    }
    row["experience_id"] = "EXP_" + _stable({k: row.get(k) for k in (
        "hypothesis_id", "action_kind", "status", "source_stage", "source_generation", "source_failure_gate", "decisive_stage"
    )})[:20].upper()
    return row


def _status_weight(status: str) -> float:
    return {"SUPPORTED": 1.0, "PARTIALLY_SUPPORTED": 0.6, "FALSIFIED": 0.0, "RETIRED": 0.15}.get(str(status).upper(), 0.0)


def _experience_is_admissible(x: dict) -> bool:
    if not isinstance(x, dict) or bool(x.get("protected_evidence_used")):
        return False
    if str(x.get("status") or "").upper() not in TERMINAL:
        return False
    source_zone = stage_learning_zone(x.get("source_stage") or "")
    decisive = x.get("decisive_stage")
    decisive_zone = stage_learning_zone(decisive) if decisive else source_zone
    return source_zone in {"ADAPTIVE", "VALIDATION"} and decisive_zone in {"ADAPTIVE", "VALIDATION"}


def _migrate_existing(x: dict) -> dict:
    out = deepcopy(x)
    if out.get("schema") == EXPERIENCE_SCHEMA:
        return out
    # Preserve old evidence IDs while making missing richness explicit rather than
    # pretending legacy V1 rows contained fields they never recorded.
    out["schema"] = EXPERIENCE_SCHEMA
    out["legacy_migrated"] = True
    out["source_stage"] = canonical_stage(out.get("source_stage") or "")
    if out.get("decisive_stage"):
        out["decisive_stage"] = canonical_stage(out.get("decisive_stage"))
    out["source_zone"] = stage_learning_zone(out.get("source_stage"))
    out["decisive_zone"] = stage_learning_zone(out.get("decisive_stage")) if out.get("decisive_stage") else None
    defaults = {
        "parent_id": None, "experiment_id": None, "candidate_ids": [], "model_families": deepcopy(out.get("families") or []),
        "topology": None, "hyperparameters": None, "feature_set": None, "label_policy": None, "training_memory": None,
        "experiment_action": {"kind": str(out.get("action_kind") or ""), "payload": None},
        "hypothesis": None, "predicted_effect": None, "state_before": None, "state_after": None, "kpi_deltas": None,
        "failed_gates": [str(out.get("source_failure_gate"))] if out.get("source_failure_gate") else [],
        "failure_margins": None, "fold_distribution": None, "coverage": None, "sample_sufficiency": None,
        "hypothesis_verdict": str(out.get("status") or "").upper(), "outcome": {"decisive_reason": out.get("decisive_reason")},
    }
    for key, value in defaults.items():
        out.setdefault(key, value)
    return out


def build_learning_stats(ledger: list[dict]) -> dict:
    by_kind: dict[str, dict] = {}
    by_gate_kind: dict[str, dict[str, dict]] = {}
    admitted = 0
    for x in ledger or []:
        if not _experience_is_admissible(x):
            continue
        admitted += 1
        kind = str(x.get("action_kind") or "").upper(); status = str(x.get("status") or "").upper()
        if not kind or status not in TERMINAL:
            continue
        row = by_kind.setdefault(kind, {"attempts": 0, "supported": 0, "partial": 0, "falsified": 0, "retired": 0, "weighted_success_sum": 0.0})
        row["attempts"] += 1
        if status == "SUPPORTED": row["supported"] += 1
        elif status == "PARTIALLY_SUPPORTED": row["partial"] += 1
        elif status == "FALSIFIED": row["falsified"] += 1
        elif status == "RETIRED": row["retired"] += 1
        row["weighted_success_sum"] += _status_weight(status)
        gate = str(x.get("source_failure_gate") or "UNKNOWN")
        grow = by_gate_kind.setdefault(gate, {}).setdefault(kind, {"attempts": 0, "weighted_success_sum": 0.0, "supported": 0, "partial": 0, "falsified": 0})
        grow["attempts"] += 1; grow["weighted_success_sum"] += _status_weight(status)
        if status == "SUPPORTED": grow["supported"] += 1
        elif status == "PARTIALLY_SUPPORTED": grow["partial"] += 1
        elif status == "FALSIFIED": grow["falsified"] += 1
    for group in [by_kind, *by_gate_kind.values()]:
        for row in group.values():
            n = max(0, int(row.get("attempts", 0)))
            row["posterior_utility"] = round((1.0 + float(row.get("weighted_success_sum", 0.0))) / (2.0 + n), 6)
    return {"by_action_kind": by_kind, "by_failure_gate": by_gate_kind, "experience_count": admitted}


def refresh_structured_memory(memory: dict, hypotheses: list[dict] | None = None, *, max_experiences: int = 2048) -> dict:
    """Return memory with append-stable, de-duplicated, protected-filtered experiences."""
    out = deepcopy(memory or {})
    existing = []
    rejected_existing = 0
    for raw in (out.get("experience_ledger") or []):
        if not isinstance(raw, dict):
            continue
        x = _migrate_existing(raw)
        if _experience_is_admissible(x):
            existing.append(x)
        else:
            rejected_existing += 1
    source_hypotheses = list(hypotheses if hypotheses is not None else (out.get("hypothesis_lifecycle") or []))
    rejected_hypotheses = 0
    for h in source_hypotheses:
        x = hypothesis_to_experience(h)
        if x is not None:
            existing.append(x)
        elif isinstance(h, dict) and str(h.get("status") or "").upper() in TERMINAL:
            rejected_hypotheses += 1
    uniq = {}
    for x in existing:
        eid = str(x.get("experience_id") or "")
        if eid and _experience_is_admissible(x):
            uniq[eid] = x
    ledger = list(uniq.values())[-max(1, int(max_experiences)):]
    out["structured_memory_schema"] = SCHEMA
    out["experience_ledger"] = ledger
    out["learning_policy_stats"] = build_learning_stats(ledger)
    out["learning_authority"] = "ADVISORY_ONLY_NO_PASS_FAIL_NO_PROMOTION"
    out["protected_stage_learning"] = "DENIED_FAIL_CLOSED_CANONICAL_STAGE_FILTER"
    out["learning_stage_contract"] = {
        "adaptive": sorted(ADAPTIVE_STAGES),
        "validation": sorted(VALIDATION_STAGES),
        "protected": sorted(PROTECTED_STAGES),
        "unknown_stage_policy": "REJECT",
    }
    out["learning_filter_diagnostics"] = {
        "rejected_existing_records": rejected_existing,
        "rejected_terminal_hypotheses": rejected_hypotheses,
    }
    out["structured_memory_updated_utc"] = _utc()
    return out
