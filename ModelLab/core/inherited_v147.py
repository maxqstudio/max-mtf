from __future__ import annotations

import hashlib
import json
import math
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strategy.strategy_geometry import config_strategy_geometry, extract_dataset_strategy_geometry
from data.dataset_integrity import read_csv_auto

GEOMETRY_LABEL_FIELDS={"sl_atr","tp_atr","horizon_bars","max_hold_bars"}
GEOMETRY_SPLIT_FIELDS={"purge_bars","embargo_bars"}
KNOWN_RECOVERABLE_FAILURES={"STRATEGY_GEOMETRY_RUNTIME_MISMATCH"}

def _read(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default

def _same(a: Any,b: Any,tol: float=1e-9)->bool:
    try:
        aa=float(a); bb=float(b)
        return math.isfinite(aa) and math.isfinite(bb) and abs(aa-bb)<=tol*max(1.0,abs(aa),abs(bb))
    except Exception:
        return False

def sha256_file(path: Path)->str:
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def strip_strategy_geometry_from_label(label: dict|None)->dict:
    out=deepcopy(label or {}) if isinstance(label,dict) else {}
    for k in GEOMETRY_LABEL_FIELDS:
        out.pop(k,None)
    return out

def sanitize_research_overrides(overrides: dict|None)->dict:
    out=deepcopy(overrides or {}) if isinstance(overrides,dict) else {}
    if isinstance(out.get("label"),dict):
        out["label"]=strip_strategy_geometry_from_label(out["label"])
    return out

def canonical_candidate_cfg(base_cfg: dict,candidate: dict)->dict:
    """Replay candidate research knobs without letting them override Strategy geometry."""
    out=deepcopy(base_cfg)
    ov=sanitize_research_overrides(candidate.get("research_overrides") or {})
    if isinstance(ov.get("label"),dict):
        merged=deepcopy(out.get("label") or {})
        merged.update(ov["label"])
        out["label"]=strip_strategy_geometry_from_label(merged)
    if isinstance(ov.get("feature_research"),dict):
        out["feature_research"]=deepcopy(ov["feature_research"])
    # Explicitly restore canonical geometry/split authority from the base config.
    if isinstance(base_cfg.get("strategy_geometry"),dict):
        out["strategy_geometry"]=deepcopy(base_cfg["strategy_geometry"])
    bsplit=base_cfg.get("split") if isinstance(base_cfg.get("split"),dict) else {}
    split=out.setdefault("split",{})
    for k in GEOMETRY_SPLIT_FIELDS:
        if k in bsplit:
            split[k]=deepcopy(bsplit[k])
    if candidate.get("training_seed") is not None:
        out["seed"]=int(candidate.get("training_seed"))
    return out

def geometry_tuple(cfg: dict)->tuple[float,float,int,int,int]:
    g=config_strategy_geometry(cfg)
    if not g:
        raise RuntimeError("STRATEGY_GEOMETRY_AUTHORITY_MISSING")
    hold=int(g["max_hold_bars"]); split=cfg.get("split") if isinstance(cfg.get("split"),dict) else {}
    purge=int(split.get("purge_bars",0) or 0); embargo=int(split.get("embargo_bars",0) or 0)
    return float(g["sl_atr"]),float(g["tp_atr"]),hold,purge,embargo

def _geometry_matches(actual: tuple, expected: tuple)->bool:
    return _same(actual[0],expected[0]) and _same(actual[1],expected[1]) and tuple(map(int,actual[2:]))==tuple(map(int,expected[2:]))

def _candidate_identity_match(candidate: dict,row: dict)->bool:
    if not isinstance(row,dict): return False
    if str(row.get("family") or "")!=str(candidate.get("family") or ""): return False
    if str(row.get("name") or "")!=str(candidate.get("name") or ""): return False
    if (row.get("params") or {})!=(candidate.get("params") or {}): return False
    cid=str(candidate.get("trained_candidate_id") or "").strip(); rid=str(row.get("trained_candidate_id") or "").strip()
    return (not cid or not rid or cid==rid)

def _source_full_wfa_proof(run_dir: Path,candidate: dict)->dict:
    leaderboard_path=run_dir/"cv_leaderboard.json"; manifest_path=run_dir/"model_manifest.json"
    leaderboard=_read(leaderboard_path,[]) if leaderboard_path.exists() else []
    if isinstance(leaderboard,list):
        for row in leaderboard:
            if (_candidate_identity_match(candidate,row) and bool(row.get("cv_gate_pass"))
                    and str(row.get("fidelity_stage") or "").startswith("FULL_WFA")):
                return {"authority":"CV_LEADERBOARD_FULL_WFA_PASS","path":leaderboard_path,"row":row}
    manifest=_read(manifest_path,{}) if manifest_path.exists() else {}
    if isinstance(manifest,dict):
        selection=manifest.get("cv_selection") if isinstance(manifest.get("cv_selection"),dict) else {}
        manifest_row={
            "family":manifest.get("model_family"),"name":manifest.get("model_name"),
            "params":manifest.get("hyperparameters") or {},
            "trained_candidate_id":selection.get("trained_candidate_id"),
        }
        if (_candidate_identity_match(candidate,manifest_row) and bool((manifest.get("cv_acceptance") or {}).get("passed"))
                and str(selection.get("fidelity_stage") or "").startswith("FULL_WFA")):
            return {"authority":"MODEL_MANIFEST_CV_ACCEPTANCE_PASS","path":manifest_path,"row":selection}
    raise RuntimeError(f"INHERITED_V147_WFA_SOURCE_PASS_EVIDENCE_MISSING: {candidate.get('pool_id')} source_run={run_dir.name}")

def prove_candidate_full_wfa_geometry(factory_dir: Path,candidate: dict,canonical_cfg: dict)->dict:
    wfa=candidate.get("wfa_evidence") if isinstance(candidate.get("wfa_evidence"),dict) else {}
    if not bool((candidate.get("discovery_acceptance") or {}).get("passed")) or not bool(wfa.get("cv_gate_pass")) or not str(wfa.get("fidelity_stage") or "").startswith("FULL_WFA"):
        raise RuntimeError(f"INHERITED_V147_WFA_SOURCE_NOT_FULL_PASS: {candidate.get('pool_id')}")
    source_run=str(candidate.get("source_run") or "").strip()
    if not source_run:
        raise RuntimeError(f"INHERITED_V147_WFA_SOURCE_RUN_MISSING: {candidate.get('pool_id')}")
    run_dir=Path(factory_dir)/"research_runs"/source_run; cfg_path=run_dir/"run_config.json"
    if not cfg_path.exists():
        raise RuntimeError(f"INHERITED_V147_WFA_SOURCE_EVIDENCE_MISSING: {candidate.get('pool_id')} source_run={source_run}")
    pass_proof=_source_full_wfa_proof(run_dir,candidate)
    source_cfg=_read(cfg_path,{})
    snapshot=Path(factory_dir)/"discovery_immutable.csv"
    snapshot_sha=sha256_file(snapshot) if snapshot.exists() else ""
    source_snapshot_sha=str(((source_cfg.get("research_window") or {}).get("authority_snapshot_sha256") or ""))
    if not snapshot_sha or source_snapshot_sha!=snapshot_sha:
        raise RuntimeError(f"INHERITED_V147_WFA_SOURCE_SNAPSHOT_MISMATCH: {candidate.get('pool_id')} source_run={source_run}")
    expected=geometry_tuple(canonical_cfg); actual=geometry_tuple(source_cfg)
    if not _geometry_matches(actual,expected):
        raise RuntimeError(
            f"INHERITED_V147_WFA_SOURCE_GEOMETRY_MISMATCH: {candidate.get('pool_id')} "
            f"source={actual} canonical={expected}"
        )
    proof_path=Path(pass_proof["path"])
    return {
        "pool_id":str(candidate.get("pool_id") or ""),"source_run":source_run,
        "source_run_config":"research_runs/"+source_run+"/run_config.json",
        "source_run_config_sha256":sha256_file(cfg_path),"discovery_snapshot_sha256":snapshot_sha,
        "full_wfa_evidence_authority":pass_proof["authority"],
        "full_wfa_evidence_file":str(proof_path.relative_to(Path(factory_dir))).replace("\\","/"),
        "full_wfa_evidence_sha256":sha256_file(proof_path),
        "geometry":{"sl_atr":actual[0],"tp_atr":actual[1],"max_hold_bars":actual[2],"purge_bars":actual[3],"embargo_bars":actual[4]},
        "full_wfa_pass":True,
    }

def prove_pool_full_wfa_geometry(factory_dir: Path,pool: list[dict],canonical_cfg: dict)->list[dict]:
    if not pool:
        raise RuntimeError("INHERITED_V147_EMPTY_POOL")
    return [prove_candidate_full_wfa_geometry(factory_dir,c,canonical_cfg) for c in pool]

def _scrub_contract_geometry(obj: Any, path: tuple[str,...]=())->Any:
    if isinstance(obj,dict):
        out={}
        for k,v in obj.items():
            if k=="strategy_geometry":
                continue
            if k in GEOMETRY_LABEL_FIELDS and ("label" in path or path[-1:] == ("label",)):
                continue
            if k in GEOMETRY_SPLIT_FIELDS and ("split" in path or "temporal_index" in path or "methodology" in path):
                continue
            out[k]=_scrub_contract_geometry(v,path+(str(k),))
        return out
    if isinstance(obj,list): return [_scrub_contract_geometry(x,path) for x in obj]
    return obj

def contracts_equal_except_strategy_geometry(a: dict,b: dict)->bool:
    return _scrub_contract_geometry(a)==_scrub_contract_geometry(b)

def cpcv_progress_authority(factory_dir: Path)->dict:
    fd=Path(factory_dir)
    qp=_read(fd/"cpcv_qualification_progress.json",{})
    rows=[r for r in (qp.get("rows") or []) if isinstance(r,dict)] if isinstance(qp,dict) else []
    live_rows_obj=_read(fd/"cpcv_live_split_results.json",{})
    live_rows=[r for r in (live_rows_obj.get("rows") or []) if isinstance(r,dict)] if isinstance(live_rows_obj,dict) else []
    live=_read(fd/"cpcv_live.json",{})
    split_completed=int((live.get("split_completed",0) if isinstance(live,dict) else 0) or 0)
    committed=bool(rows or live_rows or split_completed>0)
    return {
        "committed":committed,"qualification_rows":len(rows),"live_split_rows":len(live_rows),
        "split_completed":split_completed,"survivors":len((qp.get("survivors") or []) if isinstance(qp,dict) else []),
    }

def archive_uncommitted_cpcv_surfaces(factory_dir: Path,reason: str)->dict:
    fd=Path(factory_dir); progress=cpcv_progress_authority(fd)
    if progress["committed"]:
        raise RuntimeError("INHERITED_V147_CPCV_PROGRESS_COMMITTED_FAIL_CLOSED: "+json.dumps(progress,sort_keys=True))
    names=["cpcv_finalist_plan.json","cpcv_qualification_progress.json","cpcv_live.json","cpcv_live_split_results.json"]
    existing=[n for n in names if (fd/n).exists()]
    if not existing:
        return {"archived":[],"progress":progress}
    hist=fd/"history"/"inherited_v147"; hist.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    moved=[]
    for n in existing:
        dst=hist/f"{stamp}_{n}"
        shutil.move(str(fd/n),str(dst)); moved.append(str(dst.relative_to(fd)).replace("\\","/"))
    return {"archived":moved,"progress":progress,"reason":str(reason)}

def provisional_cpcv_summary(rows: list[dict])->dict:
    vals=[r for r in (rows or []) if isinstance(r,dict)]
    def nums(key):
        out=[]
        for r in vals:
            try:
                v=float(r.get(key))
                if math.isfinite(v): out.append(v)
            except Exception: pass
        return out
    def median(xs):
        if not xs:return None
        ys=sorted(xs); n=len(ys); m=n//2
        return ys[m] if n%2 else (ys[m-1]+ys[m])/2.0
    pf=nums("profit_factor"); exp=nums("expectancy_r"); dd=nums("max_drawdown_r"); rec=nums("recovery_factor")
    return {
        "authority":"PROVISIONAL_COMPLETED_SPLITS_ONLY","provisional":True,"completed_split_records":len(vals),
        "median_profit_factor":median(pf),"median_expectancy_r":median(exp),
        "worst_expectancy_r":min(exp) if exp else None,"worst_max_drawdown_r":max(dd) if dd else None,
        "worst_recovery_factor":min(rec) if rec else None,
    }

def classify_recoverable_failure(job: dict,factory_dir: Path|None)->dict:
    if str((job or {}).get("status") or "")!="FAILED":
        return {"recoverable":False,"failure_class":None,"reason":"NOT_FAILED"}
    err=str((job or {}).get("error") or "")
    failure_class=next((x for x in KNOWN_RECOVERABLE_FAILURES if x in err),None)
    if not failure_class:
        return {"recoverable":False,"failure_class":None,"reason":"UNRECOGNIZED_FAILURE_CLASS"}
    if factory_dir is None or not Path(factory_dir).exists():
        return {"recoverable":False,"failure_class":failure_class,"reason":"FACTORY_EVIDENCE_MISSING"}
    fd=Path(factory_dir); pool_path=fd/"candidate_pool.json"; manifest=_read(fd/"factory_manifest.json",{})
    pool=_read(pool_path,[]) if pool_path.exists() else []
    if not pool_path.exists() or not isinstance(pool,list) or not pool or not isinstance(manifest,dict) or str(manifest.get("status") or "")!="DISCOVERY_POOL_READY":
        return {"recoverable":False,"failure_class":failure_class,"reason":"DISCOVERY_POOL_NOT_COMMITTED"}
    progress=cpcv_progress_authority(fd)
    if progress["committed"]:
        return {"recoverable":False,"failure_class":failure_class,"reason":"CPCV_PROGRESS_ALREADY_COMMITTED","progress":progress}
    snapshot=fd/"discovery_immutable.csv"
    snapshot_sha=sha256_file(snapshot) if snapshot.exists() else ""
    try:
        snapshot_geometry=extract_dataset_strategy_geometry(read_csv_auto(snapshot,usecols=["sl_atr","tp_atr","max_hold_bars"]))
        canonical=(round(float(snapshot_geometry["sl_atr"]),10),round(float(snapshot_geometry["tp_atr"]),10),int(snapshot_geometry["max_hold_bars"]),int(snapshot_geometry["max_hold_bars"]),int(snapshot_geometry["max_hold_bars"]))
    except Exception:
        return {"recoverable":False,"failure_class":failure_class,"reason":"DISCOVERY_SNAPSHOT_GEOMETRY_INVALID"}
    agreed=None
    for candidate in pool:
        wfa=candidate.get("wfa_evidence") if isinstance(candidate.get("wfa_evidence"),dict) else {}
        source_run=str(candidate.get("source_run") or "").strip(); run_dir=fd/"research_runs"/source_run; cfg_path=run_dir/"run_config.json"
        if (not bool((candidate.get("discovery_acceptance") or {}).get("passed")) or not bool(wfa.get("cv_gate_pass"))
                or not str(wfa.get("fidelity_stage") or "").startswith("FULL_WFA") or not source_run or not cfg_path.exists()):
            return {"recoverable":False,"failure_class":failure_class,"reason":"FULL_WFA_SOURCE_PROOF_MISSING"}
        try:
            _source_full_wfa_proof(run_dir,candidate)
        except Exception:
            return {"recoverable":False,"failure_class":failure_class,"reason":"FULL_WFA_SOURCE_PASS_EVIDENCE_MISSING"}
        source_cfg=_read(cfg_path,{})
        try: actual=geometry_tuple(source_cfg)
        except Exception:
            return {"recoverable":False,"failure_class":failure_class,"reason":"FULL_WFA_SOURCE_GEOMETRY_MISSING"}
        source_snapshot_sha=str(((source_cfg.get("research_window") or {}).get("authority_snapshot_sha256") or ""))
        if not snapshot_sha or source_snapshot_sha!=snapshot_sha:
            return {"recoverable":False,"failure_class":failure_class,"reason":"FULL_WFA_SOURCE_SNAPSHOT_MISMATCH"}
        if int(actual[3])!=int(actual[2]) or int(actual[4])!=int(actual[2]):
            return {"recoverable":False,"failure_class":failure_class,"reason":"FULL_WFA_TEMPORAL_GEOMETRY_NOT_CANONICAL"}
        sig=(round(actual[0],10),round(actual[1],10),int(actual[2]),int(actual[3]),int(actual[4]))
        if sig!=canonical:
            return {"recoverable":False,"failure_class":failure_class,"reason":"FULL_WFA_SOURCE_GEOMETRY_MISMATCH_CANONICAL_SNAPSHOT","expected":canonical,"actual":sig}
        if agreed is None: agreed=sig
        elif sig!=agreed:
            return {"recoverable":False,"failure_class":failure_class,"reason":"FULL_WFA_SOURCE_GEOMETRY_DISAGREEMENT"}
    return {
        "recoverable":True,"failure_class":failure_class,"reason":"SAFE_ZERO_PROGRESS_CPCV_RECOVERY",
        "factory_id":fd.name,"candidate_pool_sha256":sha256_file(pool_path),"discovery_snapshot_sha256":snapshot_sha,
        "source_wfa_geometry":agreed,"candidate_count":len(pool),"progress":progress,
    }
