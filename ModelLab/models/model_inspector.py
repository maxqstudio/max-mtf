from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.model_registry import family_spec, hybrid_parts, is_hybrid_family
from models.models import CandidateSpec, estimate_candidate_parameter_count


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line:
                    continue
                try:
                    row=json.loads(line)
                except Exception:
                    continue
                if isinstance(row,dict):
                    out.append(row)
    except Exception:
        pass
    return out


def _first_dict(*values: Any) -> dict:
    for value in values:
        if isinstance(value,dict) and value:
            return dict(value)
    return {}


def _raw_value(row: dict, *keys: str) -> Any:
    for key in keys:
        value=row.get(key)
        if value not in (None, ""):
            return value
    return None


def _pool_candidate(factory_dir: Path | None, row: dict) -> dict:
    if not factory_dir:
        return {}
    pool=_read_json(factory_dir/"candidate_pool.json",[])
    if not isinstance(pool,list):
        return {}
    pid=str(_raw_value(row,"pool_id","ID","id") or "")
    name=str(_raw_value(row,"name","Model","model_name") or "")
    if pid:
        for cand in pool:
            if isinstance(cand,dict) and str(cand.get("pool_id") or "")==pid:
                return dict(cand)
    if name:
        for cand in pool:
            if isinstance(cand,dict) and str(cand.get("name") or "")==name:
                return dict(cand)
    return {}


def _trial_candidate(factory_dir: Path | None, row: dict) -> dict:
    if not factory_dir:
        return {}
    name=str(_raw_value(row,"name","Model","model_name") or "")
    family=str(_raw_value(row,"family","Family","model_family") or "")
    if not name:
        return {}
    candidates=[]
    # Factory merged ledger is preferred because it carries generation/source-run identity.
    candidates.extend(_read_jsonl(factory_dir/"all_trials.jsonl"))
    # Older runs may only have per-supervisor ledgers.
    if not candidates:
        for p in sorted((factory_dir/"research_runs").glob("*/all_trials.jsonl")):
            candidates.extend(_read_jsonl(p))
    matches=[]
    for cand in candidates:
        if str(cand.get("name") or cand.get("original_name") or "")==name:
            if family and str(cand.get("family") or "") not in {family, family.lower()}:
                # UI may carry display family labels; name identity is stronger here.
                pass
            matches.append(cand)
    if not matches:
        return {}
    # Prefer authoritative FULL_WFA over cheap-screen copies, then latest ledger row.
    matches.sort(key=lambda x:(0 if str(x.get("trial_stage") or x.get("fidelity_stage") or "").upper().startswith("FULL") else 1))
    return dict(matches[0])


def _manifest_from_run(run_dir: Path | None) -> dict:
    if not run_dir:
        return {}
    return _read_json(run_dir/"model_manifest.json",{}) if run_dir.exists() else {}


def _tree_complexity(family: str, params: dict) -> dict:
    fam=str(family or "").lower()
    prefix=""
    policy_family=fam
    if is_hybrid_family(fam):
        parts=hybrid_parts(fam)
        if parts:
            _temporal,policy_family=parts
            prefix="policy_" if fam.startswith("hybrid::") else "policy_"
    spec=family_spec(policy_family) or {}
    if spec.get("role") not in {"policy","tree"} and policy_family not in {"lightgbm","xgboost","random_forest"}:
        return {}
    def val(name: str):
        return params.get(prefix+name, params.get(name))
    out={"family":policy_family}
    for key in ("n_estimators","max_depth","num_leaves","min_child_weight","subsample","colsample_bytree"):
        value=val(key)
        if value is not None:
            out[key]=value
    # Exact fitted node count is data-dependent. Expose only a deterministic structural
    # upper bound implied by the frozen hyperparameters, clearly labelled as an upper bound.
    try:
        trees=int(out.get("n_estimators")) if out.get("n_estimators") is not None else None
    except Exception:
        trees=None
    upper_per_tree=None
    basis=None
    try:
        leaves=int(out.get("num_leaves")) if out.get("num_leaves") is not None else None
    except Exception:
        leaves=None
    try:
        depth=int(out.get("max_depth")) if out.get("max_depth") is not None else None
    except Exception:
        depth=None
    if leaves is not None and leaves > 0:
        upper_per_tree=max(1,2*leaves-1); basis="2*num_leaves-1"
    elif depth is not None and 0 <= depth <= 30:
        upper_per_tree=(1 << (depth+1)) - 1; basis="full_binary_tree(max_depth)"
    if trees is not None and trees > 0 and upper_per_tree is not None:
        out["structural_node_upper_bound"]=int(trees*upper_per_tree)
        out["structural_upper_bound_basis"]=basis
    return out


def _parameter_count_from_evidence(*rows: dict) -> int | None:
    for row in rows:
        if not isinstance(row,dict):
            continue
        for key in ("parameter_count","trainable_parameter_count"):
            value=row.get(key)
            try:
                if value is not None:
                    return int(value)
            except Exception:
                pass
        cap=row.get("capacity_contract")
        if isinstance(cap,dict):
            try:
                if cap.get("parameter_count") is not None:
                    return int(cap.get("parameter_count"))
            except Exception:
                pass
        wfa=row.get("wfa_evidence")
        if isinstance(wfa,dict):
            try:
                if wfa.get("parameter_count") is not None:
                    return int(wfa.get("parameter_count"))
            except Exception:
                pass
    return None


def candidate_detail(*, factory_dir: str | Path | None = None, row: dict | None = None, run_dir: str | Path | None = None) -> dict:
    """Resolve one displayed model row back to frozen candidate evidence.

    This is read-only UI provenance. It never reconstructs acceptance results or mutates
    candidate configuration. Exact stored parameters win; executable temporal parameter
    count is computed only when it is absent from evidence.
    """
    row=dict(row or {})
    fd=Path(factory_dir) if factory_dir else None
    rd=Path(run_dir) if run_dir else None
    pool=_pool_candidate(fd,row)
    trial=_trial_candidate(fd,row)
    manifest=_manifest_from_run(rd)

    wfa=_first_dict(pool.get("wfa_evidence") if pool else None, row.get("wfa_evidence"))
    params=_first_dict(
        row.get("params"), row.get("full_params"),
        pool.get("params") if pool else None,
        wfa.get("params") if wfa else None,
        trial.get("full_params") if trial else None,
        trial.get("params") if trial else None,
        manifest.get("hyperparameters") if manifest else None,
    )
    family=str(_raw_value(row,"family","model_family") or pool.get("family") or trial.get("family") or manifest.get("model_family") or "")
    name=str(_raw_value(row,"name","Model","model_name") or pool.get("name") or trial.get("name") or manifest.get("model_name") or "")
    pool_id=str(_raw_value(row,"pool_id","ID") or pool.get("pool_id") or "")
    trained_id=str(_raw_value(row,"trained_candidate_id","Trained ID") or pool.get("trained_candidate_id") or trial.get("trained_candidate_id") or manifest.get("trained_candidate_id") or "")
    seed=_raw_value(row,"training_seed","Seed")
    if seed is None: seed=pool.get("training_seed") if pool else None
    if seed is None: seed=trial.get("training_seed") if trial else None
    threshold=_raw_value(row,"take_threshold","Threshold")
    if threshold is None: threshold=pool.get("take_threshold") if pool else None
    if threshold is None: threshold=trial.get("take_threshold") if trial else None
    if threshold is None: threshold=manifest.get("take_threshold") if manifest else None

    parameter_count=_parameter_count_from_evidence(row,pool,wfa,trial,manifest)
    count_scope="EVIDENCE"
    if parameter_count is None and family and params:
        try:
            parameter_count=estimate_candidate_parameter_count(CandidateSpec(family,name or "candidate",params),32)
            count_scope="EXECUTABLE_ARCHITECTURE" if parameter_count is not None else "DATA_DEPENDENT_OR_UNAVAILABLE"
        except Exception:
            parameter_count=None
            count_scope="DATA_DEPENDENT_OR_UNAVAILABLE"

    tree=_tree_complexity(family,params) if family and params else {}
    role=(family_spec(family) or {}).get("role") if family else None
    if is_hybrid_family(family):
        parameter_label="Temporal leg trainable parameters"
    elif role=="temporal":
        parameter_label="Trainable parameters"
    elif tree:
        parameter_label="Trainable parameters"
        count_scope="TREE_STRUCTURE_DATA_DEPENDENT"
    else:
        parameter_label="Trainable parameters"

    source="display_row"
    if manifest and params==manifest.get("hyperparameters"): source="model_manifest.json"
    elif pool and params==pool.get("params"): source="candidate_pool.json"
    elif wfa and params==wfa.get("params"): source="candidate_pool.wfa_evidence"
    elif trial and params in (trial.get("full_params"),trial.get("params")): source="all_trials.jsonl"

    return {
        "schema":"MAX_MODEL_DETAIL_INSPECTOR_V1",
        "model":name or "—",
        "family":family or "—",
        "pool_id":pool_id or None,
        "trained_candidate_id":trained_id or None,
        "training_seed":seed,
        "take_threshold":threshold,
        "parameters":params,
        "parameter_count":parameter_count,
        "parameter_count_scope":count_scope,
        "parameter_count_label":parameter_label,
        "tree_complexity":tree,
        "source":source,
        "run_dir":str(rd) if rd else None,
    }


def parameter_groups(family: str, params: dict) -> list[dict]:
    fam=str(family or "")
    rows=[]
    for key in sorted((params or {}).keys()):
        if key.startswith("temporal_"):
            group="Temporal"
        elif key.startswith("policy_"):
            group="Policy"
        elif key.startswith("gru_") and fam.startswith("hybrid_"):
            group="Temporal"
        elif key in {"training_memory_months","sequence_length","batch_size","epochs","learning_rate","weight_decay","dropout"}:
            group="Training"
        else:
            group="Model"
        rows.append({"Group":group,"Parameter":key,"Value":params.get(key)})
    return rows
