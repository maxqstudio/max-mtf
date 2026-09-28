from __future__ import annotations

import json
from pathlib import Path
from core.project_paths import CONFIG_DIR
from typing import Any

_REGISTRY_PATH = CONFIG_DIR / "models" / "model_registry.json"
SIZE_PRIORITY_SCHEMA = "CP_FAMILY_SIZE_PRIORITY_V1"

LEGACY_HYBRID_ALIASES = {
    "hybrid_gru_xgboost": ("gru", "xgboost"),
    "hybrid_gru_lightgbm": ("gru", "lightgbm"),
    "hybrid_gru_random_forest": ("gru", "random_forest"),
}


def load_registry() -> dict:
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def family_registry() -> dict:
    return load_registry().get("families", {})


def is_hybrid_family(family: str) -> bool:
    fam = str(family or "").strip().lower()
    return fam.startswith("hybrid::") or fam in LEGACY_HYBRID_ALIASES


def hybrid_parts(family: str) -> tuple[str, str] | None:
    fam = str(family or "").strip().lower()
    if fam in LEGACY_HYBRID_ALIASES:
        return LEGACY_HYBRID_ALIASES[fam]
    if fam.startswith("hybrid::"):
        parts = fam.split("::")
        if len(parts) == 3 and parts[1] and parts[2]:
            return parts[1], parts[2]
    return None


def make_hybrid_family(temporal: str, policy: str) -> str:
    return f"hybrid::{str(temporal).strip().lower()}::{str(policy).strip().lower()}"


def temporal_families() -> list[str]:
    return sorted(
        k for k, spec in family_registry().items()
        if spec.get("role") == "temporal" and bool(spec.get("deployable", True))
    )


def policy_families() -> list[str]:
    return sorted(
        k for k, spec in family_registry().items()
        if spec.get("role") == "policy" and bool(spec.get("deployable", True))
    )


def dynamic_hybrid_families() -> list[str]:
    reg = family_registry(); out = []
    for temporal in temporal_families():
        if not bool((reg.get(temporal) or {}).get("hybrid_compatible", False)):
            continue
        for policy in policy_families():
            if not bool((reg.get(policy) or {}).get("hybrid_compatible", False)):
                continue
            out.append(make_hybrid_family(temporal, policy))
    return sorted(out)


def _numeric_bounds(search: dict) -> dict[str, tuple[float, float, type]]:
    out = {}
    for key, meta in (search or {}).items():
        typ = int if str(meta.get("type")) == "int" else float
        out[key] = (meta["min"], meta["max"], typ)
    return out


def _hybrid_search(temporal: str, policy: str) -> dict:
    reg = family_registry(); ts = (reg.get(temporal) or {}).get("search") or {}; ps = (reg.get(policy) or {}).get("search") or {}
    out = {}
    for key, meta in ts.items():
        if key == "training_memory_months":
            continue
        out[f"temporal_{key}"] = dict(meta)
    for key, meta in ps.items():
        if key == "training_memory_months":
            continue
        out[f"policy_{key}"] = dict(meta)
    # Training-memory is an experiment dimension shared by the whole composition.
    tm = ts.get("training_memory_months") or ps.get("training_memory_months")
    if tm:
        out["training_memory_months"] = dict(tm)
    return out


def family_spec(family: str) -> dict[str, Any] | None:
    fam = str(family or "").strip().lower(); reg = family_registry()
    if fam in reg:
        return dict(reg[fam])
    parts = hybrid_parts(fam)
    if not parts:
        return None
    temporal, policy = parts
    ts, ps = reg.get(temporal), reg.get(policy)
    if not ts or not ps or ts.get("role") != "temporal" or ps.get("role") != "policy":
        return None
    if not bool(ts.get("hybrid_compatible", False)) or not bool(ps.get("hybrid_compatible", False)):
        return None
    return {
        "deployable": bool(ts.get("deployable", True) and ps.get("deployable", True)),
        "category": "HYBRID",
        "role": "composed_hybrid",
        "temporal_family": temporal,
        "policy_family": policy,
        "input_contract": "CP_HYBRID_TEMPORAL_POLICY_V1",
        "search": _hybrid_search(temporal, policy),
        "size_parameters": [f"temporal_{k}" for k in (ts.get("size_parameters") or [])] + [f"policy_{k}" for k in (ps.get("size_parameters") or [])],
    }


def all_families(*, include_legacy: bool = True, include_dynamic: bool = True) -> list[str]:
    reg = family_registry()
    base = [k for k, v in reg.items() if not v.get("legacy_alias")]
    if include_dynamic:
        base += dynamic_hybrid_families()
    if include_legacy:
        base += [k for k, v in reg.items() if v.get("legacy_alias")]
    return sorted(dict.fromkeys(base))


def get_bounds(families: list[str] | None = None) -> dict:
    names = families or all_families(include_legacy=True, include_dynamic=True)
    out = {}
    for family in names:
        spec = family_spec(family)
        if spec:
            out[family] = _numeric_bounds(spec.get("search") or {})
    return out


def get_distributions(families: list[str] | None = None) -> dict:
    names = families or all_families(include_legacy=True, include_dynamic=True)
    out = {}
    for family in names:
        spec = family_spec(family)
        if spec:
            out[family] = {k: str(v.get("distribution", "linear")) for k, v in (spec.get("search") or {}).items()}
    return out


def clamp_size_priority(value: Any, default: float = 0.50) -> float:
    try:
        value=float(value)
    except Exception:
        value=float(default)
    return max(0.0,min(1.0,value))

def configured_family_size_priorities(cfg: dict | None) -> dict[str,float]:
    """Return frozen Owner size priorities for base families.

    A compiled research plan wins over mutable UI config, mirroring topology-priority
    authority. Legacy runs default to 0.50, which preserves the full effective bounds.
    """
    plan=(((cfg or {}).get("agent") or {}).get("research_plan") or {})
    raw=plan.get("family_size_priorities") if isinstance(plan,dict) else None
    if not isinstance(raw,dict):
        raw=((cfg or {}).get("research_architecture") or {}).get("family_size_priorities")
    raw=raw if isinstance(raw,dict) else {}
    out={}
    for fam,spec in family_registry().items():
        if spec.get("legacy_alias"):
            continue
        out[fam]=clamp_size_priority(raw.get(fam,0.50))
    return out

def family_size_priority(cfg: dict | None, family: str) -> dict[str,float]:
    """Return component-aware size priority. Hybrids inherit each base component slider."""
    fam=str(family or "").strip().lower(); pri=configured_family_size_priorities(cfg)
    parts=hybrid_parts(fam)
    if parts:
        return {"temporal":clamp_size_priority(pri.get(parts[0],0.50)),"policy":clamp_size_priority(pri.get(parts[1],0.50))}
    return {"family":clamp_size_priority(pri.get(fam,0.50))}

def _size_priority_window(priority: float) -> tuple[float,float]:
    """Quantile window inside an already-safe bound. 0.50 is intentionally neutral.

    0.00 -> lower half, 0.25 -> lower 75%, 0.50 -> full envelope,
    0.75 -> upper 75%, 1.00 -> upper half. This makes the slider influential
    without pretending it can override dataset/hardware capacity ceilings.
    """
    p=clamp_size_priority(priority)
    return (0.0,0.5+p) if p<=0.5 else (p-0.5,1.0)

def _slice_numeric_bound(lo,hi,typ,priority: float):
    if float(hi)<=float(lo):
        return lo,hi,typ
    qlo,qhi=_size_priority_window(priority)
    nlo=float(lo)+qlo*(float(hi)-float(lo)); nhi=float(lo)+qhi*(float(hi)-float(lo))
    if typ is int:
        nlo=int(round(nlo)); nhi=int(round(nhi))
        nlo=max(int(lo),min(int(hi),nlo)); nhi=max(nlo,min(int(hi),nhi))
    return nlo,nhi,typ


def effective_bounds(cfg: dict | None, family: str) -> dict[str, tuple[float, float, type]]:
    """Legal registry bounds intersected with the Scientist-compiled plan envelope.

    Existing/legacy runs without a compiled plan retain the full legal registry bounds.
    """
    legal=get_bounds([family]).get(family,{})
    # The historical window_discovery section is now executable authority: it clamps
    # every candidate's training-memory dimension instead of being documentation-only.
    wd=(((cfg or {}).get("agent") or {}).get("window_discovery") or {})
    if bool(wd.get("enabled",False)) and "training_memory_months" in legal:
        lo,hi,typ=legal["training_memory_months"]
        wlo=max(float(lo),float(wd.get("min_months",lo))); whi=min(float(hi),float(wd.get("max_months",hi)))
        if wlo<=whi:
            legal=dict(legal); legal["training_memory_months"]=(int(round(wlo)) if typ is int else wlo,int(round(whi)) if typ is int else whi,typ)
    plan=(((cfg or {}).get("agent") or {}).get("research_plan") or {})
    envs=plan.get("parameter_envelopes") if isinstance(plan.get("parameter_envelopes"),dict) else {}
    env=envs.get(str(family)) if isinstance(envs,dict) else None
    env=env if isinstance(env,dict) else {}
    out={}
    for key,(lo,hi,typ) in legal.items():
        raw=env.get(key)
        if isinstance(raw,(list,tuple)) and len(raw)>=2:
            try:
                elo=float(raw[0]); ehi=float(raw[1])
                if elo>ehi: elo,ehi=ehi,elo
                nlo=max(float(lo),elo); nhi=min(float(hi),ehi)
                if nlo<=nhi:
                    out[key]=(int(round(nlo)) if typ is int else nlo,int(round(nhi)) if typ is int else nhi,typ)
                    continue
            except Exception:
                pass
        out[key]=(lo,hi,typ)
    # Model-size priority is a SEARCH PREFERENCE, not an executable hard-bound slice.
    # Hard capacity is candidate-specific (actual parameter count + legal/resource/
    # scientific authority). Applying the slider here previously trapped Large inside
    # old static envelopes and could also reject a scientifically valid Manual exact
    # candidate. AUTO generation consumes the priority as a sampling bias instead.
    return out

def enabled_families(cfg: dict) -> list[str]:
    """Return the current executable research universe.

    R7 prefers a deterministic, Scientist-compiled research plan.  When no plan is
    present (legacy run/resume), the R6 model toggles remain authoritative so old
    evidence and checkpoints remain reproducible.
    """
    plan = ((cfg.get("agent") or {}).get("research_plan") or {})
    active = plan.get("active_families") if isinstance(plan, dict) else None
    if isinstance(active, list) and active:
        valid = []
        for raw in active:
            fam = str(raw).strip().lower()
            spec = family_spec(fam)
            if spec and bool(spec.get("deployable", True)):
                valid.append(fam)
        if valid:
            return list(dict.fromkeys(valid))

    enabled = []
    models = cfg.get("models", {})
    for family, spec in family_registry().items():
        if spec.get("legacy_alias"):
            # Preserve explicit R6 hybrid toggles below.
            continue
        key = spec.get("enabled_key", family)
        if bool(models.get(key, False)) and bool(spec.get("deployable", True)):
            enabled.append(family)
    # R6 compatibility toggles.
    if bool(models.get("hybrid_xgboost", False)): enabled.append("hybrid_gru_xgboost")
    if bool(models.get("hybrid_lightgbm", False)): enabled.append("hybrid_gru_lightgbm")
    if bool(models.get("hybrid_random_forest", False)): enabled.append("hybrid_gru_random_forest")
    return list(dict.fromkeys(enabled))


def registry_for_scientist() -> dict[str, Any]:
    reg = family_registry()
    bases = {}
    for name, spec in reg.items():
        if spec.get("legacy_alias"):
            continue
        bases[name] = {
            "category": spec.get("category"), "role": spec.get("role"),
            "hybrid_compatible": bool(spec.get("hybrid_compatible", False)),
            "requires_torch": bool(spec.get("requires_torch", False)),
            "architecture_note": spec.get("architecture_note"),
            "strategy_expert_prior": list(spec.get("strategy_expert_prior") or []),
            "strategy_expert_prior_semantics": spec.get("strategy_expert_prior_semantics"),
            "expert_identity": spec.get("expert_identity"),
            "size_parameters": list(spec.get("size_parameters") or []),
            "search": spec.get("search") or {},
        }
    return {
        "schema": "CP_MODEL_CAPABILITY_REGISTRY_V1",
        "base_families": bases,
        "composition_grammar": "hybrid::<temporal_family>::<policy_family>",
        "temporal_families": temporal_families(),
        "policy_families": policy_families(),
        "dynamic_hybrid_count": len(dynamic_hybrid_families()),
        "size_priority_schema": SIZE_PRIORITY_SCHEMA,
        "size_priority_semantics": "0=Small preference, 0.50=balanced preference, 1=Large preference toward the upper currently justified region; sliders never widen or hard-slice legal/resource/scientific capacity",
    }
