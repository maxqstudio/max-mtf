from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from host.compute_backend import resolve_compute_plan
from host.hardware_profile import collect_hardware_profile, summarize_hardware_profile
from research.research_architect import capability_catalog, recommended_parameter_envelopes, compile_research_plan, apply_research_plan, apply_strategy_parameter_envelopes
from models.capacity_governor import (
    build_dataset_capacity_profile, recommended_capacity_envelopes, summarize_capacity_evidence,
    summarize_capacity_evidence_by_family, cumulative_committed_full_wfa_capacity_rows,
    CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY,
)
from models.model_registry import configured_family_size_priorities, registry_for_scientist, is_hybrid_family, family_spec, hybrid_parts, effective_bounds
from core.contract import CONTRACT_ID, FEATURES
from data.dataset_integrity import build_research_window_snapshot, read_csv_auto, fresh_readiness
from factory.factory_jobs import atomic_write_json
from research.evaluation import (
    metrics_from_trades, regime_diagnostics, stress_diagnostics, temporal_stability,
    trade_outcomes, trading_metrics,
)
from research.kpi import shadow_acceptance, walk_forward_acceptance, monte_carlo_acceptance, fresh_forward_acceptance
from data.labels import build_labels
from models.model_lab import feature_matrix, load_cfg
from models.models import CandidateSpec, make_model, fit_model, predict_model_proba, spec_fingerprint, experiment_fingerprint, candidate_runtime_contract, model_training_diagnostics, candidate_capacity_contract
from research.sample_policy import auto_trade_sample
from research.risk_kpi import gate_rows as risk_gate_rows, dsr_trial_count, psr_benchmark
from research.gate_kpi import gate_profile, risk_cfg_for_gate, gate_profiles_snapshot
from factory.supervisor_agent import run_supervisor_agent
from research.cpcv import candidate_cpcv
from research.pbo import compute_cpcv_pbo, group_expectancy_from_seed_rows
from factory.factory_control import FactoryControlSignal
from research.research_checkpoint import commit_checkpoint, load_checkpoint, clean_partial_temps
from data.feature_label_audit import run_feature_label_audit
from research.guided_research import run_guided_research
from scientist.core.scientist import LLMScientist
from research.research_engine_v3 import read_jsonl, write_jsonl, failure_topology, SCHEMA as RESEARCH_ENGINE_SCHEMA
from research.research_feedback import cpcv_failure_topology, generic_stage_topology, dataset_header_context, feedback_memory_item
from research.creativity_governor import adaptive_creativity_profile
from research.experiment_blocks import resolve_decisive_hypotheses
from research.structured_research_memory import refresh_structured_memory
from research.learning_policy import recommend_learning_actions
from scientist.skills.max_scientist_skills import skill_guidance
from research.future_learning_foundation import foundation_snapshot
from research.research_control import research_mode as control_research_mode, provenance as research_control_provenance, bind_manual_capacity_authority
from research.policy_discovery import policy_actions, policy_trading_metrics, policy_temporal_stability, policy_regime_diagnostics, policy_stress_diagnostics, write_policy_csv, POLICY_SCHEMA
from core.temporal_index import contract_from_cfg
from data.data_quality import audit_dataset, research_readiness
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry
from core.inherited_v147 import (canonical_candidate_cfg, strip_strategy_geometry_from_label, prove_pool_full_wfa_geometry,
    contracts_equal_except_strategy_geometry, cpcv_progress_authority, archive_uncommitted_cpcv_surfaces)

ProgressCallback = Callable[[dict], None]
SCHEMA = "CP_CHAMPION_FACTORY_V3"
GLOBAL_MEMORY_SCHEMA = "CP_GLOBAL_RESEARCH_MEMORY_V2"
RESEARCH_KERNEL_SCHEMA = "CP_RESEARCH_KERNEL_V2_TEMPORAL_INDEXED"


def _emit(cb, stage, current, total, message, **extra):
    if cb:
        cb({"stage": stage, "current": current, "total": total, "message": message, **extra})


def _write(path: Path, obj):
    atomic_write_json(path, obj)



def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _stable_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _critical_scientific_contract(cfg: dict) -> dict:
    """Freeze only authorities that may change scientific outcomes/replay."""
    return {
        "label": deepcopy(cfg.get("label") or {}),
        "split": deepcopy(cfg.get("split") or {}),
        "deployment": deepcopy(cfg.get("deployment") or {}),
        "acceptance": deepcopy(cfg.get("acceptance") or {}),
        "gate_kpis": gate_profiles_snapshot(cfg),
        "trade_sample_policy": deepcopy(cfg.get("trade_sample_policy") or {}),
        "feature_research": deepcopy(cfg.get("feature_research") or {}),
        "seed": int(cfg.get("seed",42) or 42),
        "research_mode": control_research_mode(cfg),
        "champion_factory": {k:deepcopy(v) for k,v in (cfg.get("champion_factory") or {}).items() if k not in {"fresh_to"}},
    }


def _assert_temporal_leakage_guard(cfg: dict, *, require_embargo: bool = False) -> dict:
    t=contract_from_cfg(cfg)
    if int(t.purge_bars) < int(t.label_horizon_bars):
        raise RuntimeError(f"DATA_FLOW_TEMPORAL_LEAKAGE_GUARD: purge_bars={t.purge_bars} < label_horizon_bars={t.label_horizon_bars}")
    if require_embargo and int(t.embargo_bars) < int(t.label_horizon_bars):
        raise RuntimeError(f"CPCV_TEMPORAL_LEAKAGE_GUARD: embargo_bars={t.embargo_bars} < label_horizon_bars={t.label_horizon_bars}")
    return t.__dict__


def _assert_data_quality_authority(master: Path, cfg: dict) -> dict:
    agent=cfg.get("agent") or {}
    ctx=agent.get("data_quality_context") if isinstance(agent.get("data_quality_context"),dict) else {}
    expected=str(agent.get("data_quality_source_sha256") or "")
    actual=_sha(master)
    continuity=ctx.get("continuity") if isinstance(ctx.get("continuity"),dict) else {}
    status=str(ctx.get("quality_status") or "")
    reasons=[]
    if not expected: reasons.append("DQ_SOURCE_SHA_MISSING")
    elif expected != actual: reasons.append("DQ_SOURCE_SHA_DRIFT")
    if status not in {"VALID","VALID_WITH_WARNINGS"}: reasons.append("DQ_STATUS_NOT_READY")
    if not bool(continuity.get("broker_verified")): reasons.append("DQ_BROKER_NOT_VERIFIED")
    if int(continuity.get("source_backed_missing",0) or 0)>0: reasons.append("DQ_SOURCE_BACKED_MISSING")
    if int(continuity.get("dataset_only",0) or 0)>0: reasons.append("DQ_DATASET_ONLY_ROWS")
    if reasons:
        raise RuntimeError("DATA_QUALITY_AUTHORITY_REQUIRED: "+",".join(reasons))
    return {"source_sha256":actual,"quality_status":status,"continuity":deepcopy(continuity)}


def _stage_seal(fd: Path, stage: str, *, contract: dict, files: list[str]) -> dict:
    artifacts={}
    for name in files:
        q=fd/name
        if not q.exists():
            raise RuntimeError(f"{stage} seal missing artifact: {name}")
        artifacts[name]=_sha(q)
    payload={"schema":"MAX_STAGE_SEAL_V1","stage":str(stage).upper(),"contract":deepcopy(contract),"contract_hash":_stable_hash(contract),"artifacts":artifacts}
    payload["seal_hash"]=_stable_hash(payload)
    _write(fd/f"{str(stage).lower()}_terminal_seal.json",payload)
    return payload


def _verify_stage_seal(fd: Path, stage: str, expected: dict | None = None) -> dict:
    path=fd/f"{str(stage).lower()}_terminal_seal.json"
    seal=_read(path,{})
    if not seal or str(seal.get("stage") or "").upper()!=str(stage).upper():
        raise RuntimeError(f"{stage} terminal seal missing")
    check=deepcopy(seal); claimed=check.pop("seal_hash",None)
    if not claimed or _stable_hash(check)!=claimed:
        raise RuntimeError(f"{stage} terminal seal hash mismatch")
    for name,h in (seal.get("artifacts") or {}).items():
        q=fd/name
        if not q.exists() or _sha(q)!=str(h):
            raise RuntimeError(f"{stage} artifact tamper: {name}")
    if expected is not None and _stable_hash(expected)!=str(seal.get("contract_hash") or ""):
        raise RuntimeError(f"{stage} contract drift")
    return seal


def verify_champion_terminal_authority(factory_dir) -> dict:
    """Validate production Champion authority before any orchestration consumer trusts it."""
    fd=Path(factory_dir); fm=_read(fd/"factory_manifest.json",{})
    if str(fm.get("status") or "") not in {"FACTORY_WINNER", "CHAMPION"}:
        raise RuntimeError("Factory-winner terminal authority requested for non-winner Factory")
    seal=_verify_stage_seal(fd,"CHAMPION")
    claimed=str(fm.get("champion_terminal_seal_hash") or "")
    if not claimed or claimed != str(seal.get("seal_hash") or ""):
        raise RuntimeError("Champion terminal seal is not bound to factory_manifest")
    champion=_read(fd/"champion.json",{})
    if not champion or str(champion.get("pool_id") or "") != str(fm.get("champion") or ""):
        raise RuntimeError("Champion identity drift between artifact and factory_manifest")
    return {"manifest":fm,"champion":champion,"seal":seal}


def _candidate_identity(c: dict) -> dict:
    return {k:deepcopy(c.get(k)) for k in ("pool_id","family","name","params","fingerprint","spec_fingerprint","trained_candidate_id","training_seed","take_threshold","decision_policy","policy_fingerprint","research_overrides","experiment_block_id","hypothesis_id")}


def _assert_same_candidate(source: dict, candidate: dict, stage: str) -> None:
    a=_candidate_identity(source); b=_candidate_identity(candidate)
    # Optional keys must agree when source carries them; no downstream mutation allowed.
    for k,v in a.items():
        if v is None: continue
        if b.get(k)!=v:
            raise RuntimeError(f"{stage} candidate identity drift: {k}")


def _strategy_metrics(proba, df, cfg: dict, threshold: float, policy: dict | None = None) -> dict:
    return policy_trading_metrics(proba,df,cfg,policy) if policy else trading_metrics(proba,df,cfg,threshold)


def _strategy_outcomes(proba, df, cfg: dict, threshold: float, policy: dict | None = None):
    if not policy:
        return trade_outcomes(proba,df,cfg,threshold)
    act=policy_actions(proba,df,cfg,policy)
    lr=df["long_r"].to_numpy(float); sr=df["short_r"].to_numpy(float)
    r=np.where(act>0,lr,np.where(act<0,sr,0.0))
    return act,r


def _factory_id():
    return datetime.now(timezone.utc).strftime("FACTORY_%Y%m%d_%H%M%S_%f_UTC")


def _dataset_identity(csv_path: Path) -> dict:
    x = read_csv_auto(csv_path, usecols=["symbol", "period", "signal_time"])
    if x.empty:
        raise ValueError("Dataset kosong")
    if x[["symbol", "period"]].drop_duplicates().shape[0] != 1:
        raise ValueError("Factory membutuhkan tepat satu symbol/timeframe")
    ts = pd.to_datetime(x["signal_time"], errors="coerce")
    return {
        "symbol": str(x["symbol"].iloc[0]), "period": int(x["period"].iloc[0]),
        "start": str(ts.min()), "end": str(ts.max()), "rows": int(len(x)),
    }


def _merge_factory_trial_ledger(factory_dir: Path, source_run: Path, generation: int) -> dict:
    """Merge one Supervisor run ledger into append-stable Factory research history."""
    target=factory_dir/"all_trials.jsonl"
    existing=read_jsonl(target)
    incoming=read_jsonl(source_run/"all_trials.jsonl")
    by_key={}
    for r in existing:
        key=(str(r.get("source_run") or r.get("run_id") or ""),str(r.get("trial_stage") or ""),str(r.get("original_name") or r.get("name") or ""),int(r.get("round",0) or 0))
        by_key[key]=r
    for r in incoming:
        x=deepcopy(r); x["factory_generation"]=int(generation); x["source_run"]=source_run.name
        key=(source_run.name,str(x.get("trial_stage") or ""),str(x.get("original_name") or x.get("name") or ""),int(x.get("round",0) or 0))
        by_key[key]=x
    merged=sorted(by_key.values(),key=lambda r:(int(r.get("factory_generation",0) or 0),int(r.get("round",0) or 0),str(r.get("trial_stage") or ""),str(r.get("original_name") or r.get("name") or "")))
    write_jsonl(target,merged)
    full=[r for r in merged if str(r.get("trial_stage"))=="FULL_WFA"]
    screen=[r for r in merged if str(r.get("trial_stage"))=="CHEAP_SCREEN"]
    summary={"schema":"CP_FACTORY_ALL_TRIAL_SUMMARY_V1","research_engine_schema":RESEARCH_ENGINE_SCHEMA,"ledger_records":len(merged),"screen_records":len(screen),"full_wfa_records":len(full),"generations":max([int(r.get("factory_generation",0) or 0) for r in merged],default=0),"updated_utc":datetime.now(timezone.utc).isoformat()}
    _write(factory_dir/"all_trial_summary.json",summary)
    return summary


def _pool_memory(pool_rows: list[dict], leaderboards: list[dict]) -> dict:
    all_rows = []
    for block in leaderboards:
        all_rows.extend(block.get("rows") or [])
    all_rows.sort(key=lambda r: (bool(r.get("cv_gate_pass")), float(r.get("selection_score", -1e99))), reverse=True)
    fail = {}
    for r in all_rows:
        g = str(r.get("cv_first_failed_gate") or "PASS")
        fail[g] = fail.get(g, 0) + 1
    elites = []
    for r in all_rows[:12]:
        if not r.get("family") or not isinstance(r.get("params"), dict):
            continue
        elites.append({
            "run_id": r.get("run_id"), "name": r.get("name"), "family": r.get("family"), "params": r.get("params"),
            "cv_gate_pass": bool(r.get("cv_gate_pass")), "selection_score": float(r.get("selection_score", -1e99)),
            "first_failed_gate": r.get("cv_first_failed_gate"), "trades": int(r.get("total_validation_trades", 0) or 0),
            "pf": float(r.get("median_profit_factor", 0) or 0), "expectancy_r": float(r.get("median_expectancy_r", 0) or 0),
            "worst_expectancy_r": float(r.get("worst_expectancy_r", 0) or 0),
            "worst_dd_r": float(r.get("worst_fold_max_drawdown_r", 0) or 0),
            "training_memory_months": int((r.get("params") or {}).get("training_memory_months", 0) or 0),
        })
    return {
        "schema": "CP_RESEARCH_MEMORY_V1", "elites": elites, "failure_gate_counts": fail,
        "experiment_count": len(all_rows), "qualified_pool_count": len(pool_rows),
        "learning_summary": {
            "best_family": elites[0]["family"] if elites else None,
            "dominant_failure_gate": max(fail, key=fail.get) if fail else None,
        },
    }


def _merge_learning_memory(old: dict, new: dict) -> dict:
    elites = list(old.get("elites") or []) + list(new.get("elites") or [])
    uniq = {}
    for e in elites:
        if not e.get("family") or not isinstance(e.get("params"), dict):
            continue
        fp = spec_fingerprint(CandidateSpec(str(e["family"]), str(e.get("name") or "memory"), dict(e["params"])))
        prev = uniq.get(fp)
        if prev is None or (bool(e.get("cv_gate_pass")), float(e.get("selection_score", -1e99))) > (bool(prev.get("cv_gate_pass")), float(prev.get("selection_score", -1e99))):
            uniq[fp] = e
    ranked = sorted(uniq.values(), key=lambda e: (bool(e.get("cv_gate_pass")), float(e.get("selection_score", -1e99))), reverse=True)[:16]
    fail = dict(old.get("failure_gate_counts") or {})
    for k, v in (new.get("failure_gate_counts") or {}).items():
        fail[str(k)] = int(fail.get(str(k), 0)) + int(v or 0)
    out={
        "schema": "CP_RESEARCH_MEMORY_V1", "elites": ranked, "failure_gate_counts": fail,
        "experiment_count": int(old.get("experiment_count", 0) or 0) + int(new.get("experiment_count", 0) or 0),
        "qualified_pool_count": int(new.get("qualified_pool_count", 0) or 0),
        "learning_summary": {
            "best_family": ranked[0].get("family") if ranked else None,
            "dominant_failure_gate": max(fail, key=fail.get) if fail else None,
        },
    }
    # Research-cycle metadata is not a qualification authority, but it must survive
    # generations so Experiment Blocks and the Director can use committed lessons.
    out["failure_topology"]=deepcopy(new.get("failure_topology") or old.get("failure_topology") or {})
    out["stage_feedback"]=list((old.get("stage_feedback") or []) + (new.get("stage_feedback") or []))[-16:]
    by_h={}
    for h in list(old.get("hypothesis_lifecycle") or [])+list(new.get("hypothesis_lifecycle") or []):
        if not isinstance(h,dict): continue
        key=str(h.get("hypothesis_id") or _stable_hash({"kind":h.get("kind"),"title":h.get("title"),"payload":h.get("payload")}))
        by_h[key]=deepcopy(h)
    out["hypothesis_lifecycle"]=list(by_h.values())[-256:]
    if new.get("next_discovery_plan") or old.get("next_discovery_plan"):
        out["next_discovery_plan"]=deepcopy(new.get("next_discovery_plan") or old.get("next_discovery_plan") or {})
    out=refresh_structured_memory(out,out.get("hypothesis_lifecycle") or [])
    return out


def _research_contract(snapshot: Path, cfg: dict, identity: dict, source_master_sha256: str | None = None) -> tuple[str, dict]:
    payload = {
        "contract_schema":"CP_RESEARCH_CONTRACT_R5_EXACT_DATASET",
        "discovery_snapshot_sha256": _sha(snapshot),
        "source_master_sha256": str(source_master_sha256 or ""),
        "symbol": identity.get("symbol"), "period": identity.get("period"),
        "feature_contract": CONTRACT_ID,
        "scientific_contract": _critical_scientific_contract(cfg),
        "research_kernel_schema": RESEARCH_KERNEL_SCHEMA,
    }
    return _stable_hash(payload), payload


def _global_memory_path(root: Path) -> Path:
    return root / "_global_research_memory.json"


def _load_global_contract(root: Path, contract_hash: str) -> tuple[dict, dict]:
    path=_global_memory_path(root)
    if path.exists():
        try:
            gm=json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Global Research Memory corrupt: {path.name}: {exc}") from exc
        if not isinstance(gm,dict) or gm.get("schema") != GLOBAL_MEMORY_SCHEMA or not isinstance(gm.get("contracts"), dict):
            raise RuntimeError(f"Global Research Memory schema invalid: {path.name}")
    else:
        gm={"schema": GLOBAL_MEMORY_SCHEMA, "contracts": {}}
    rec = dict((gm.get("contracts") or {}).get(contract_hash) or {})
    rec.setdefault("tested_experiment_fingerprints", rec.get("tested_fingerprints", []))
    rec.setdefault("learning_memory", {})
    rec.setdefault("factories", [])
    rec.setdefault("feedback_exposures", {})
    rec.setdefault("stage_feedback", [])
    return gm, rec


def _save_global_contract(root: Path, gm: dict, contract_hash: str, rec: dict):
    gm = dict(gm); contracts = dict(gm.get("contracts") or {}); contracts[contract_hash] = rec
    gm["schema"] = GLOBAL_MEMORY_SCHEMA; gm["contracts"] = contracts
    _write(_global_memory_path(root), gm)

def _record_downstream_failure(fd: Path, stage: str, summary: dict):
    """Seal raw downstream evidence while permitting bounded NEXT-cycle summaries.

    The current cycle may never tune against raw CPCV/Tournament/Monte-Carlo/Forward
    rows.  R5 adds a separate exact-contract feedback channel containing only a
    committed Scientist summary/topology for the *next* Discovery cycle.  Fresh
    Forward remains report-only for the same snapshot.
    """
    fm=_read(fd / "factory_manifest.json",{})
    contract_hash=str(fm.get("research_contract_hash") or "")
    if not contract_hash:
        return
    root=fd.parent
    gm,rec=_load_global_contract(root,contract_hash)
    vault=dict(rec.get("evaluation_vault") or {"schema":"CP_EVALUATION_VAULT_V2","failures":[]})
    failures=list(vault.get("failures") or [])
    stage_u=str(stage).upper()
    next_cycle_allowed=stage_u in {"CPCV","TOURNAMENT","MONTE_CARLO"}
    item={
        "factory_id":fd.name,"stage":stage_u,"summary":summary,
        "recorded_utc":datetime.now(timezone.utc).isoformat(),
        "same_cycle_research_feedback_allowed":False,
        "next_cycle_summary_feedback_allowed":bool(next_cycle_allowed),
        "feedback_channel":"research_feedback.json" if next_cycle_allowed else None,
    }
    failures.append(item)
    vault["schema"]="CP_EVALUATION_VAULT_V2"
    vault["failures"]=failures[-48:]
    vault["last_failure_stage"]=stage_u
    vault["same_cycle_research_feedback_allowed"]=False
    vault["next_cycle_summary_feedback_allowed"]=bool(next_cycle_allowed)
    vault["raw_evidence_sealed"]=True
    rec["evaluation_vault"]=vault
    rec["updated_utc"]=datetime.now(timezone.utc).isoformat()
    _save_global_contract(root,gm,contract_hash,rec)
    _write(fd / "evaluation_vault.json", vault)


def _llm_header_context(fd: Path, contract_hash: str) -> dict:
    """Read only the CSV header for LLM context; never expose dataset rows."""
    snap=fd/"discovery_immutable.csv"
    cols=[]
    try:
        cols=list(pd.read_csv(snap,sep=None,engine="python",nrows=0).columns)
    except Exception:
        cols=list(FEATURES)
    return dataset_header_context(cols,feature_contract=CONTRACT_ID,feature_count=len(FEATURES),research_contract_hash=contract_hash)


def _actionable_learning(entry: dict) -> tuple[bool, str | None]:
    """Require a plan that is guaranteed to mutate the *next Discovery* deterministically."""
    plan=entry.get("next_discovery_plan") if isinstance(entry.get("next_discovery_plan"),dict) else {}
    if not str(plan.get("objective") or "").strip():
        return False,"NEXT_DISCOVERY_PLAN_MISSING_OBJECTIVE"
    if not list(plan.get("change") or []):
        return False,"NEXT_DISCOVERY_PLAN_MISSING_CHANGE"
    if not str(plan.get("falsification") or "").strip():
        return False,"NEXT_DISCOVERY_PLAN_MISSING_FALSIFICATION"
    meaningful=[]
    for h in (entry.get("hypotheses") or []):
        if not isinstance(h,dict) or not bool(h.get("executable",False)): continue
        kind=str(h.get("kind") or "").upper(); payload=h.get("payload") if isinstance(h.get("payload"),dict) else {}
        if kind=="MODEL_ARCHITECTURE" and (payload.get("variable_keys_by_family") or payload.get("parameter_ranges_by_family")):
            meaningful.append(h)
        elif kind=="TRAINING_MEMORY" and list(payload.get("months") or []):
            meaningful.append(h)
        elif kind=="SELECTIVITY_POLICY" and list(payload.get("take_thresholds") or []):
            meaningful.append(h)
        elif kind=="HYBRID_ABLATION" and list(payload.get("pairs") or payload.get("families") or []):
            meaningful.append(h)
        elif kind=="SEED_STABILITY" and list(payload.get("families") or []):
            meaningful.append(h)
    if not meaningful:
        return False,"NEXT_DISCOVERY_PLAN_HAS_NO_WIRED_EXECUTABLE_HYPOTHESIS"
    return True,None


_LLM_RETRYABLE_CATEGORIES={"QUOTA_OR_RATE_LIMIT","QUOTA_EXHAUSTED","RATE_LIMIT","TIMEOUT","PROVIDER_5XX","PROVIDER_UNREACHABLE","MODEL_UNAVAILABLE","DAILY_QUOTA_EXHAUSTED","RATE_LIMITED","COOLDOWN"}

def _llm_stack_exhausted(provenance: dict | None) -> bool:
    attempts=list((provenance or {}).get("attempts") or [])
    if not attempts:
        return False
    saw=False
    for a in attempts:
        status=str(a.get("status") or "").upper()
        if status=="PASS":
            return False
        if status=="SKIP":
            saw=True; continue
        if status=="FAIL" and str(a.get("category") or "").upper() in _LLM_RETRYABLE_CATEGORIES:
            saw=True; continue
        return False
    return saw

def _deterministic_failure_plan(stage: str, topology: dict) -> dict:
    dominant=str((topology or {}).get("dominant_first_failed_gate") or (topology or {}).get("dominant_failure_group") or "UNKNOWN")
    return {
        "schema":"MAX_DETERMINISTIC_FAILURE_LEARNING_V1",
        "mode":"DETERMINISTIC_FALLBACK",
        "stage":str(stage).upper(),
        "dominant_failure_gate":dominant,
        "directive":"Continue deterministic Discovery inside frozen Owner/model/capacity authority using committed failure topology; do not fabricate Scientist hypotheses.",
    }

def _stage_scientist_and_feedback(fd: Path, cfg: dict, stage: str, status: str, topology: dict, rows: list[dict], *, llm_api_key: str|None=None, learning_allowed: bool=False, contract_hash_override: str|None=None) -> dict:
    """Commit a stage Scientist report and, when permitted, a bounded next-cycle lesson.

    Deterministic evidence remains the sole PASS/FAIL authority.  A failed downstream
    stage may restart Discovery only after a usable LLM Scientist plan has been
    committed under the exact research-contract hash.  API/configuration failures do
    not consume the feedback exposure budget and cannot cause a blind restart.
    """
    if control_research_mode(cfg) == "MANUAL":
        stage_u=str(stage).upper()
        entry={
            "schema":"CP_STAGE_SCIENTIST_REPORT_V1","stage":stage_u,"status":status,
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "summary":f"{stage_u} {status} · MANUAL RESEARCH · Scientist disabled by contract",
            "report":{},"scientific_method":{},"strategy":{},"hypotheses":[],"next_discovery_plan":{},
            "llm_provenance":{"execution_mode":"DISABLED_MANUAL_RESEARCH","attempts":[]},
            "same_cycle_research_feedback_allowed":False,"next_cycle_summary_feedback_requested":False,
            "scientist_ready":False,"feedback_exposure":0,"feedback_limit":None,"feedback_budget_remaining":None,
            "feedback_exhausted":False,"learning_ready":False,"learning_source":"NONE_MANUAL_RESEARCH",
            "stop_research":False,"error":None,
        }
        journal=_read(fd/"stage_scientist_journal.json",[])
        if not isinstance(journal,list): journal=[]
        journal.append(entry); _write(fd/"stage_scientist_journal.json",journal[-96:])
        return entry
    fm=_read(fd/"factory_manifest.json",{})
    contract_hash=str(contract_hash_override or fm.get("research_contract_hash") or "")
    root=fd.parent
    gm,rec=_load_global_contract(root,contract_hash) if contract_hash else ({"schema":GLOBAL_MEMORY_SCHEMA,"contracts":{}},{})
    exposures=dict(rec.get("feedback_exposures") or {})
    stage_u=str(stage).upper()
    failed=("NO_SURVIVOR" in str(status) or "FAIL" in str(status) or str(status)=="INSUFFICIENT_QUALIFIED_POOL")
    requested_learning=bool(learning_allowed and failed and contract_hash)
    current_exposure=int(exposures.get(stage_u,0) or 0)
    limits=(((cfg.get("champion_factory") or {}).get("research_feedback") or {}).get("max_exposures") or {})
    limit=int(limits.get(stage_u,0) or 0)
    budget_available=bool(not requested_learning or limit<=0 or current_exposure < limit)
    use_learning=bool(requested_learning and budget_available)
    proposed_exposure=current_exposure+(1 if use_learning else 0)
    llmcfg=dict((cfg.get("agent") or {}).get("llm") or {})
    response={} ; error=None
    deterministic_only=bool(llmcfg.get("factory_session_deterministic_only",False))
    scientist=LLMScientist(llmcfg,api_key=llm_api_key) if bool(llmcfg.get("enabled",False)) and not deterministic_only else None
    scientist_ready=bool(scientist is not None and scientist.ready)
    _factory_context={
        "hardware_profile":_read(fd/"hardware_profile.json",{}),
        "research_plan":_read(fd/"research_plan.json",{}),
        "compute_plan":_read(fd/"compute_plan.json",{}),
        "dataset_capacity_profile":_read(fd/"dataset_capacity_profile.json",{}),
        "data_quality_profile":_read(fd/"dataset_quality_context.json",{}),
    }
    _seed_policy=deepcopy((((cfg.get("champion_factory") or {}).get("cpcv_stage") or {}).get("seed_confirmation") or {}))
    _stage_evidence={"status":status,"evaluated":len(rows)}
    if stage_u=="DATA":
        _stage_evidence["data_quality_profile"]=deepcopy(_factory_context.get("data_quality_profile") or {})
    context={
        "status":status,"dataset":_llm_header_context(fd,contract_hash),"stage_evidence":_stage_evidence,
        "failure_topology":topology,"candidate_summaries":list((topology or {}).get("candidate_rows") or [])[:16],
        "research_memory":deepcopy(rec.get("learning_memory") or {}),"feedback_exposure":proposed_exposure,
        "factory_context":_factory_context,"seed_policy":_seed_policy,
        "creativity_profile":adaptive_creativity_profile(cfg,failure_topology=topology,stale_rounds=0),
    }
    deterministic_fallback=False
    if scientist_ready:
        try:
            response=scientist.stage_review(stage_u,context,cfg,learning_allowed=use_learning)
        except Exception as exc:
            error=str(exc)
            prov=deepcopy(getattr(scientist,"last_call_provenance",{}))
            if _llm_stack_exhausted(prov):
                deterministic_fallback=True
                response={
                    "summary":f"{stage_u} {status} · LLM stack exhausted · deterministic research continues",
                    "next_discovery_plan":_deterministic_failure_plan(stage_u,topology) if requested_learning and budget_available else {},
                    "llm_provenance":prov,
                }
                error=None
    elif scientist is None or not scientist_ready:
        deterministic_fallback=True
        _why="factory-session deterministic-only" if deterministic_only else "LLM unavailable"
        response={
            "summary":f"{stage_u} {status} · {_why} · deterministic research continues",
            "next_discovery_plan":_deterministic_failure_plan(stage_u,topology) if requested_learning and budget_available else {},
            "llm_provenance":{"execution_mode":"DETERMINISTIC_FALLBACK","attempts":[]},
        }

    _subjects=list((topology or {}).get("candidate_rows") or [])
    _subject=deepcopy(_subjects[0]) if stage_u=="CPCV_CANDIDATE" and len(_subjects)==1 else {}
    entry={
        "schema":"CP_STAGE_SCIENTIST_REPORT_V1","stage":stage_u,"status":status,"created_utc":datetime.now(timezone.utc).isoformat(),
        "subject":_subject,
        "summary":str(response.get("summary") or (f"{stage_u} {status} · deterministic evidence committed")),
        "report":deepcopy(response.get("report") or {}),"scientific_method":deepcopy(response.get("scientific_method") or {}),"strategy":deepcopy(response.get("strategy") or {}),
        "hypotheses":deepcopy(response.get("hypotheses") or []),"next_discovery_plan":deepcopy(response.get("next_discovery_plan") or {}),
        "llm_provenance":deepcopy(response.get("llm_provenance") or {}),
        "same_cycle_research_feedback_allowed":False,"next_cycle_summary_feedback_requested":requested_learning,
        "scientist_ready":scientist_ready,"feedback_exposure":current_exposure,"feedback_limit":limit or None,
        "feedback_budget_remaining":None if limit<=0 else max(0,limit-current_exposure),
        "feedback_exhausted":bool(requested_learning and not budget_available),"learning_ready":False,
        "learning_source":"DETERMINISTIC_FALLBACK" if deterministic_fallback else "LLM_SCIENTIST",
        "stop_research":False,"stop_research_advisory":bool(response.get("stop_research_advisory",response.get("stop_research",False))),"error":error,
    }
    if use_learning and error is None:
        if deterministic_fallback:
            entry["learning_ready"]=True
        else:
            ok,why=_actionable_learning(entry)
            if ok:
                entry["learning_ready"]=True
            else:
                entry["error"]=why

    # Exposure is consumed only by a committed actionable lesson, never by an API or
    # schema failure.  This makes retry/resume scientifically and operationally sane.
    if entry["learning_ready"]:
        committed_exposure=current_exposure+1
        entry["feedback_exposure"]=committed_exposure
        entry["feedback_budget_remaining"]=None if limit<=0 else max(0,limit-committed_exposure)
    else:
        committed_exposure=current_exposure

    journal=_read(fd/"stage_scientist_journal.json",[])
    if not isinstance(journal,list): journal=[]
    journal.append(entry); _write(fd/"stage_scientist_journal.json",journal[-96:])
    if contract_hash and entry["learning_ready"]:
        exposures[stage_u]=committed_exposure; rec["feedback_exposures"]=exposures
        item=feedback_memory_item(fd.name,stage_u,status,topology,entry,committed_exposure,contract_hash)
        sf=list(rec.get("stage_feedback") or []); sf.append(item); rec["stage_feedback"]=sf[-32:]
        lm=deepcopy(rec.get("learning_memory") or {})
        lm["failure_topology"]=deepcopy(topology); lm["stage_feedback"]=sf[-16:]; lm["next_discovery_plan"]=deepcopy(entry.get("next_discovery_plan") or {})
        hs=list(lm.get("hypothesis_lifecycle") or [])
        for h in entry.get("hypotheses") or []:
            if not isinstance(h,dict): continue
            x=deepcopy(h); x.setdefault("status","PROPOSED"); x["source"]="STAGE_SCIENTIST"; x["source_stage"]=stage_u; x["source_factory"]=fd.name; x["source_status"]=status
            x["source_failure_topology"]={k:deepcopy((topology or {}).get(k)) for k in ("dominant_first_failed_gate","dominant_failure_group","first_failed_gate_counts","all_failed_gate_counts","worst_split_combination") if (topology or {}).get(k) is not None}
            hid=str(x.get("hypothesis_id") or _stable_hash({"kind":x.get("kind"),"title":x.get("title"),"payload":x.get("payload")}))
            x["hypothesis_id"]=hid; hs=[q for q in hs if str((q or {}).get("hypothesis_id"))!=hid]; hs.append(x)
        lm["hypothesis_lifecycle"]=hs[-256:]; lm=refresh_structured_memory(lm,lm["hypothesis_lifecycle"]); rec["learning_memory"]=lm; rec["updated_utc"]=datetime.now(timezone.utc).isoformat()
        _save_global_contract(root,gm,contract_hash,rec)
        _write(fd/"research_feedback.json",{
            "schema":"CP_RESEARCH_FEEDBACK_V1","latest":item,"exposures":exposures,
            "feedback_exhausted":False,"learning_ready":True,
        })
    return entry


def _resolve_committed_hypotheses(fd: Path, stage: str, status: str, rows: list[dict]) -> list[dict]:
    """Resolve proxy-supported hypotheses with their actual downstream authority."""
    fm=_read(fd/"factory_manifest.json",{})
    contract_hash=str(fm.get("research_contract_hash") or "")
    if not contract_hash:
        return []
    root=fd.parent; gm,rec=_load_global_contract(root,contract_hash)
    lm=deepcopy(rec.get("learning_memory") or {})
    hs=list(lm.get("hypothesis_lifecycle") or [])
    updated,decisions=resolve_decisive_hypotheses(hs,rows,stage,status)
    if not decisions:
        return []
    lm["hypothesis_lifecycle"]=updated[-256:]
    lm=refresh_structured_memory(lm,lm["hypothesis_lifecycle"])
    rec["learning_memory"]=lm; rec["updated_utc"]=datetime.now(timezone.utc).isoformat()
    _save_global_contract(root,gm,contract_hash,rec)
    local=_read(fd/"research_memory.json",{})
    if isinstance(local,dict):
        local["hypothesis_lifecycle"]=deepcopy(updated[-256:]); local=refresh_structured_memory(local,local["hypothesis_lifecycle"]); _write(fd/"research_memory.json",local)
    payload={"schema":"CP_HYPOTHESIS_DECISIVE_OUTCOMES_V1","stage":str(stage).upper(),"stage_status":status,"decisions":decisions,"created_utc":datetime.now(timezone.utc).isoformat()}
    _write(fd/f"hypothesis_decisive_outcomes_{str(stage).lower()}.json",payload)
    hist=_read(fd/"hypothesis_decisive_outcomes.json",{"schema":"CP_HYPOTHESIS_DECISIVE_OUTCOMES_HISTORY_V1","entries":[]})
    entries=list(hist.get("entries") or []) if isinstance(hist,dict) else []
    entries.append(payload)
    _write(fd/"hypothesis_decisive_outcomes.json",{"schema":"CP_HYPOTHESIS_DECISIVE_OUTCOMES_HISTORY_V1","entries":entries[-32:],"latest":payload})
    return decisions


def retry_failure_scientist_learning(factory_dir, config_path, *, llm_api_key: str|None=None) -> dict:
    """Retry only the Scientist post-mortem from already committed failure evidence.

    No model is refit and no validation stage is re-opened.  Used by orchestrator RESUME
    after an API/configuration failure left the Factory waiting for mandatory learning.
    """
    fd=Path(factory_dir); cfg=load_cfg(config_path); fm=_read(fd/"factory_manifest.json",{})
    status=str(fm.get("status") or ""); stage=str(fm.get("stage") or "").upper()
    if status=="INSUFFICIENT_QUALIFIED_POOL":
        stage="POOL"
        dcontract=fm.get("discovery_stage_contract") if isinstance(fm.get("discovery_stage_contract"),dict) else None
        if not dcontract: raise RuntimeError("Scientist retry fail-closed: Discovery stage contract missing")
        _verify_stage_seal(fd,"DISCOVERY",expected=dcontract)
        if dcontract.get("scientific_contract") != _critical_scientific_contract(cfg):
            raise RuntimeError("Scientist retry fail-closed: scientific config drift after Discovery failure")
        rows=_read(fd/"candidate_pool.json",[]); topo=_read(fd/"failure_topology.json",{})
    elif status=="CPCV_NO_SURVIVOR":
        stage="CPCV"
        meta=fm.get("cpcv") if isinstance(fm.get("cpcv"),dict) else {}; contract=meta.get("stage_contract") if isinstance(meta.get("stage_contract"),dict) else None
        if not contract: raise RuntimeError("Scientist retry fail-closed: CPCV stage contract missing")
        _verify_stage_seal(fd,"CPCV",expected=contract)
        if contract.get("scientific_contract") != _critical_scientific_contract(cfg):
            raise RuntimeError("Scientist retry fail-closed: scientific config drift after CPCV failure")
        ev=_read(fd/"cpcv_qualification_evidence.json",{}); rows=list(ev.get("rows") or []); topo=_read(fd/"cpcv_failure_topology.json",{})
    elif status=="TOURNAMENT_NO_SURVIVOR":
        stage="TOURNAMENT"
        meta=fm.get("tournament") if isinstance(fm.get("tournament"),dict) else {}; contract=meta.get("stage_contract") if isinstance(meta.get("stage_contract"),dict) else None
        if not contract: raise RuntimeError("Scientist retry fail-closed: Tournament stage contract missing")
        _verify_stage_seal(fd,"TOURNAMENT",expected=contract)
        if contract.get("scientific_contract") != _critical_scientific_contract(cfg):
            raise RuntimeError("Scientist retry fail-closed: scientific config drift after Tournament failure")
        rows=_read(fd/"tournament_leaderboard.json",[]); topo=_read(fd/"tournament_failure_topology.json",{})
    elif status=="MONTE_CARLO_NO_SURVIVOR":
        stage="MONTE_CARLO"
        meta=fm.get("monte_carlo") if isinstance(fm.get("monte_carlo"),dict) else {}; contract=meta.get("stage_contract") if isinstance(meta.get("stage_contract"),dict) else None
        if not contract: raise RuntimeError("Scientist retry fail-closed: Monte Carlo stage contract missing")
        _verify_stage_seal(fd,"MONTE_CARLO",expected=contract)
        if contract.get("scientific_contract") != _critical_scientific_contract(cfg):
            raise RuntimeError("Scientist retry fail-closed: scientific config drift after Monte Carlo failure")
        ev=_read(fd/"monte_carlo_evidence.json",{}); rows=list(ev.get("rows") or []); topo=_read(fd/"monte_carlo_failure_topology.json",{})
    else:
        raise RuntimeError(f"Scientist failure-learning retry tidak berlaku untuk status {status!r}")
    entry=_stage_scientist_and_feedback(fd,cfg,stage,status,topo,rows,llm_api_key=llm_api_key,learning_allowed=True)
    exhausted=bool(entry.get("feedback_exhausted")); ready=bool(entry.get("learning_ready"))
    fm.update({
        "stage_scientist_journal":"stage_scientist_journal.json",
        "research_learning_ready":ready,
        "research_feedback_exhausted":exhausted,
        "research_restart_required":bool(ready and not exhausted),
        "next_required":("STOP_RESEARCH_FEEDBACK_BUDGET" if exhausted else ("START_NEW_DISCOVERY_WITH_"+stage+"_LEARNING" if ready else "WAIT_SCIENTIST_REVIEW")),
    })
    _write(fd/"factory_manifest.json",fm)
    return {"status":status,"stage":stage,"learning_ready":ready,"feedback_exhausted":exhausted,"scientist":entry,"manifest":fm}

def _candidate_cfg(base_cfg: dict, candidate: dict) -> dict:
    # v2.0.1 inherited v1.4.7 contract: candidate research overrides retain only
    # candidate-specific research knobs. Strategy geometry is always replayed from the
    # canonical dataset/Strategy authority resolved on the base config.
    return canonical_candidate_cfg(base_cfg,candidate)

def _guided_cycle(source_run: Path, snapshot: Path, config_path: Path, research_root: Path, progress=None) -> dict:
    """Restore legacy Feature+Label Audit -> Guided Research inside Discovery."""
    audit=run_feature_label_audit(source_run,snapshot,config_path=config_path,out_dir=research_root,progress=progress)
    guided=run_guided_research(audit["run"],snapshot,config_path=config_path,out_dir=research_root,progress=progress)
    return {"audit":audit,"guided":guided}


def _candidate_param_distance(a: dict, b: dict, cfg: dict | None = None) -> float:
    if str(a.get("family"))!=str(b.get("family")): return 1.0
    try:
        from models.model_registry import effective_bounds, get_bounds
        bounds=(effective_bounds(cfg or {},str(a.get("family"))) if cfg is not None else (get_bounds().get(str(a.get("family"))) or {}))
    except Exception: bounds={}
    pa=a.get("params") or {}; pb=b.get("params") or {}; vals=[]
    for k in sorted(set(pa)&set(pb)):
        try:
            av=float(pa[k]); bv=float(pb[k]); lo,hi,_=bounds.get(k,(min(av,bv),max(av,bv) if av!=bv else av+1.0,float)); span=max(1e-12,float(hi)-float(lo)); vals.append(min(1.0,abs(av-bv)/span))
        except Exception:
            vals.append(0.0 if pa.get(k)==pb.get(k) else 1.0)
    return float(sum(vals)/len(vals)) if vals else 0.0


def _select_pool_passes(passed: list[dict], existing_pool: list[dict], slots: int, weight: float=0.15, cfg: dict | None = None) -> list[dict]:
    """Select only WFA PASS rows; use bounded diversity as a tie/allocation term."""
    candidates=[r for r in passed if isinstance(r,dict)]; chosen=[]; slots=max(0,int(slots))
    if not candidates or slots<=0: return []
    scores=[float(r.get("selection_score",-1e99)) for r in candidates]; lo=min(scores); hi=max(scores); span=max(1e-12,hi-lo); w=max(0.0,min(0.30,float(weight)))
    while candidates and len(chosen)<slots:
        best=None; best_key=None
        anchors=list(existing_pool)+chosen
        for r in candidates:
            q=(float(r.get("selection_score",lo))-lo)/span if hi>lo else 1.0
            div=min((_candidate_param_distance(r,x,cfg) for x in anchors),default=1.0)
            merit=(1.0-w)*q+w*div
            key=(merit,float(r.get("selection_score",-1e99)),str(r.get("name") or ""))
            if best_key is None or key>best_key: best=r; best_key=key; best=(dict(r)); best["pool_diversity_score"]=float(div); best["pool_allocation_score"]=float(merit)
        original_name=str(best.get("name")); chosen.append(best); candidates=[r for r in candidates if str(r.get("name"))!=original_name]
    return chosen


def run_discovery_pool(master_csv, config_path, factory_root, discovery_from, discovery_to,
                       tournament_from=None, tournament_to=None, fresh_from=None, fresh_to=None,
                       progress: ProgressCallback = None, llm_api_key: str | None = None,
                       factory_id: str | None = None, resume: bool = False) -> dict:
    """Build the qualified Discovery pool with atomic crash-resume checkpoints.

    Commit boundaries are intentionally coarse enough to be deterministic and safe:
    immutable source/preflight, completed Supervisor generation, WFA-qualified pool
    commit, and completed Guided/Research-Memory generation. CPCV is a separate finalist stage. Work after the last
    committed boundary is disposable and is replayed after pause/crash/reboot.
    """
    master = Path(master_csv); root = Path(factory_root); root.mkdir(parents=True, exist_ok=True)
    cfg = load_cfg(config_path); fc = cfg.get("champion_factory", {})
    dq_authority=_assert_data_quality_authority(master,cfg)
    # Inherited v1.4.7: resolve Strategy/dataset geometry before ANY Discovery or
    # downstream scientific contract is frozen. This removes stale 1.8/2.7/24 label
    # copies from research config and rebuilds purge/embargo from max_hold_bars.
    _authority_raw=read_csv_auto(master,usecols=["sl_atr","tp_atr","max_hold_bars"])
    if _authority_raw.empty:
        raise RuntimeError("STRATEGY_GEOMETRY_AUTHORITY_DATASET_EMPTY")
    cfg,_canonical_strategy_geometry=synchronize_cfg_with_dataset_geometry(cfg,_authority_raw)
    fc = cfg.get("champion_factory", {})
    temporal_authority=_assert_temporal_leakage_guard(cfg)
    research_mode=control_research_mode(cfg); manual_mode=(research_mode=="MANUAL")
    manual_contract=(fc.get("manual_research") or {}) if isinstance(fc.get("manual_research"),dict) else {}
    manual_candidates=[x for x in (manual_contract.get("candidates") or []) if isinstance(x,dict)]
    data_quality_context=deepcopy((cfg.get("agent") or {}).get("data_quality_context") or {})
    tournament_from = tournament_from or fc.get("tournament_from"); tournament_to = tournament_to or fc.get("tournament_to")
    fresh_from = fresh_from or fc.get("fresh_from"); fresh_to = fresh_to or fc.get("fresh_to")
    ds = pd.Timestamp(discovery_from); de = pd.Timestamp(discovery_to); ts = pd.Timestamp(tournament_from); te = pd.Timestamp(tournament_to); fs = pd.Timestamp(fresh_from); fe = pd.Timestamp(fresh_to)
    if not (ds <= de < ts <= te < fs <= fe):
        raise ValueError(f"Chronological factory split invalid/overlapping: Discovery {ds.date()}→{de.date()}, Tournament {ts.date()}→{te.date()}, Forward {fs.date()}→{fe.date()}")
    if manual_mode:
        if not manual_candidates:
            raise ValueError("MANUAL RESEARCH fail-closed: no exact Owner candidates configured")
        target=len(manual_candidates); max_gen=1; max_total=len(manual_candidates); batch_budget=len(manual_candidates)
        manual_min_survivors=max(1,min(target,int(manual_contract.get("minimum_wfa_survivors",1) or 1)))
    else:
        configured_target=int(fc.get("target_pool",12) or 12)
        if configured_target != 12:
            raise RuntimeError(f"DISCOVERY_AUTO_POOL_AUTHORITY: target_pool must be exactly 12, got {configured_target}")
        target = 12; max_gen = int(fc.get("max_generations", 8)); max_total = int(fc.get("max_total_experiments", 216)); batch_budget = int(fc.get("discovery_batch_experiments", 36))
        manual_min_survivors=1
    discovery_stage_contract={
        "schema":"MAX_DISCOVERY_STAGE_CONTRACT_V1",
        "research_mode":research_mode,
        "scientific_contract":_critical_scientific_contract(cfg),
        "data_quality":dq_authority,
        "temporal_index":temporal_authority,
        "windows":{"discovery":[str(discovery_from),str(discovery_to)],"tournament":[str(tournament_from),str(tournament_to)],"fresh":[str(fresh_from),str(fresh_to)]},
        "target_pool":int(target),
        "manual_candidate_contract":deepcopy(manual_candidates) if manual_mode else None,
    }
    discovery_stage_contract_hash=_stable_hash(discovery_stage_contract)
    run = root / (str(factory_id) if factory_id else _factory_id())
    checkpoint_path = run / "discovery_checkpoint.json"
    resumed = bool(resume and run.exists())

    if resumed:
        cp = load_checkpoint(checkpoint_path)
        snap = run / "discovery_immutable.csv"
        if not cp:
            raise RuntimeError(
                "Resume ditolak: checkpoint lama/tidak valid tidak boleh dipromosikan ke Research Kernel V2. "
                "Pertahankan Factory lama sebagai evidence read-only dan START Factory baru pada v0.7.2 R1."
            )
        clean_partial_temps(run)
        for _name,_key in (("tournament_immutable.csv","frozen_tournament_sha256"),("forward_refit_history.csv","frozen_refit_history_sha256")):
            _q=run/_name
            if _q.exists(): discovery_stage_contract[_key]=_sha(_q)
        discovery_stage_contract_hash=_stable_hash(discovery_stage_contract)
        if str(cp.get("discovery_stage_contract_hash") or "") != discovery_stage_contract_hash:
            raise RuntimeError("Resume ditolak: Discovery scientific/window/seed/mode contract berubah")
        snap = run / "discovery_immutable.csv"
        if not snap.exists():
            raise RuntimeError("Resume ditolak: immutable Discovery snapshot hilang")
        rw = dict(cp.get("research_window") or {})
        if rw.get("snapshot_csv_sha256") and _sha(snap) != str(rw.get("snapshot_csv_sha256")):
            raise RuntimeError("Resume ditolak: immutable Discovery snapshot hash berubah")
        ident = dict(cp.get("identity") or _dataset_identity(snap))
        contract_hash = str(cp.get("research_contract_hash") or "")
        contract_payload = dict(cp.get("research_contract") or {})
        if contract_payload.get("scientific_contract") != _critical_scientific_contract(cfg):
            raise RuntimeError("Resume ditolak: scientific config changed since Discovery checkpoint")
        if not contract_hash:
            contract_hash, contract_payload = _research_contract(snap, cfg, ident, _sha(master))
        if str(contract_payload.get("research_kernel_schema") or "") != RESEARCH_KERNEL_SCHEMA:
            raise RuntimeError(
                "Resume ditolak: Factory dibuat dengan research-kernel semantics lama. "
                "v0.7.2 R1 wajib memulai Factory baru agar evidence lama dan baru tidak tercampur."
            )
        expected_master=str(contract_payload.get("source_master_sha256") or "")
        if not expected_master:
            raise RuntimeError("Resume ditolak: Factory tidak memiliki exact-dataset R5 source-master contract. START Factory R5 baru.")
        if _sha(master) != expected_master:
            raise RuntimeError("Resume ditolak: source master dataset berubah sejak Factory dibuat. R5 fail-closed agar learning tidak menyeberang dataset revision.")
        for _name,_key in (("tournament_immutable.csv","frozen_tournament_sha256"),("forward_refit_history.csv","frozen_refit_history_sha256")):
            _q=run/_name; _expected=(cp.get("discovery_stage_contract") or {}).get(_key)
            if not _q.exists() or not _expected or _sha(_q)!=str(_expected):
                raise RuntimeError(f"Resume ditolak: frozen downstream authority drift: {_name}")
        historical_seen = set(str(x) for x in (cp.get("historical_seen") or []))
        pool = list(cp.get("pool") or []); pool_fp = set(str(x) for x in (cp.get("pool_fp") or []))
        tested_current = set(str(x) for x in (cp.get("tested_current") or []))
        generation_runs = list(cp.get("generation_runs") or [])
        leaderboards=[]
        for _generation_index,_rid in enumerate(generation_runs,start=1):
            _rows=_read(run/"research_runs"/str(_rid)/"cv_leaderboard.json",[])
            if isinstance(_rows,list):
                for _r in _rows:
                    if isinstance(_r,dict): _r["run_id"]=str(_rid)
                leaderboards.append({"generation":int(_generation_index),"run_id":str(_rid),"rows":_rows})
        total_exp = int(cp.get("total_exp", 0) or 0); memory = dict(cp.get("memory") or {})
        guided_override = dict(cp.get("guided_override") or {}); guided_cycles = list(cp.get("guided_cycles") or [])
        director_state = dict(cp.get("director_state") or {})
        director_journal = _read(run / "research_director_journal.json", [])
        if not isinstance(director_journal,list): director_journal=[]
        next_generation = int(cp.get("next_generation", 1) or 1)
        _emit(progress,"factory_resume",next_generation-1,max_gen,f"RESUME dari atomic checkpoint #{cp.get('_checkpoint_sequence')} · generation {next_generation} · pool {len(pool)}/{target}")
    else:
        run.mkdir(parents=True, exist_ok=False)
        snap = run / "discovery_immutable.csv"; rw = build_research_window_snapshot(master, discovery_from, discovery_to, snap)
        ident = _dataset_identity(snap)
        contract_hash, contract_payload = _research_contract(snap, cfg, ident, _sha(master))
        # Freeze downstream historical authorities before any Discovery result exists.
        tournament_snap=run/"tournament_immutable.csv"
        tournament_rw=build_research_window_snapshot(master,tournament_from,tournament_to,tournament_snap)
        refit_hist=run/"forward_refit_history.csv"
        refit_rw=build_research_window_snapshot(master,discovery_from,tournament_to,refit_hist)
        discovery_stage_contract["frozen_tournament_sha256"]=_sha(tournament_snap)
        discovery_stage_contract["frozen_refit_history_sha256"]=_sha(refit_hist)
        discovery_stage_contract_hash=_stable_hash(discovery_stage_contract)
        gm0, grec0 = _load_global_contract(root, contract_hash)
        historical_seen = set(str(x) for x in (grec0.get("tested_experiment_fingerprints") or []))
        pool=[]; pool_fp=set(); tested_current=set(); leaderboards=[]; generation_runs=[]; total_exp=0
        memory=dict(grec0.get("learning_memory") or {}); guided_override={}; guided_cycles=[]
        director_state={}; director_journal=[]; next_generation=1

    gm, grec = _load_global_contract(root, contract_hash)
    global_learning = dict(grec.get("learning_memory") or {})
    llm_dataset_ctx=_llm_header_context(run,contract_hash)
    if manual_mode:
        # Owner manual experiments are auditable evidence but do not seed/contaminate
        # autonomous Discovery memory unless a future explicit import contract is added.
        historical_seen=set(); memory={}; global_learning={}
    elif not memory:
        memory = global_learning

    # R7 hardware authority: a new Factory captures a deterministic machine profile
    # before the Research Director selects model families. Resume keeps the original
    # research plan/profile so evidence semantics cannot silently change mid-Factory.
    if resumed and (run/"hardware_profile.json").exists():
        hardware_profile=_read(run/"hardware_profile.json",{})
        current_runtime_profile=collect_hardware_profile()
        if current_runtime_profile.get("profile_hash") != hardware_profile.get("profile_hash"):
            _write(run/"hardware_profile_runtime_current.json",current_runtime_profile)
    else:
        hardware_profile=collect_hardware_profile()
        _write(run/"hardware_profile.json",hardware_profile)
    capacity_profile=build_dataset_capacity_profile(ident,cfg,feature_count=len(FEATURES),sequence_hint=int((cfg.get("research_architecture") or {}).get("sequence_capacity_hint",128) or 128))
    # v1.3.1: compute authority must be resolved before Scientist/Architect capacity planning.
    plan = resolve_compute_plan(cfg); cfg["resolved_compute"] = plan; _write(run / "compute_plan.json", plan)
    _write(run/"dataset_capacity_profile.json",capacity_profile)
    if data_quality_context:
        _write(run/"dataset_quality_context.json",data_quality_context)
    capacity_guidance=recommended_capacity_envelopes(capacity_profile,hardware_profile)
    hardware_caps=capability_catalog(hardware_profile,cfg)
    hardware_envelopes=recommended_parameter_envelopes(hardware_profile,capacity_profile,plan)
    _write(run/"hardware_capabilities.json",hardware_caps)
    _write(run/"capacity_guidance.json",capacity_guidance)

    persisted_plan=deepcopy(director_state.get("research_plan") or _read(run/"research_plan.json",{}) or (((cfg.get("agent") or {}).get("research_plan") or {}) if manual_mode else {}))
    if persisted_plan and manual_mode:
        cfg.setdefault("agent",{})["research_plan"]=deepcopy(persisted_plan)
        cfg,_manual_capacity_rows=bind_manual_capacity_authority(cfg,manual_candidates,hardware_profile,capacity_profile)
        persisted_plan=deepcopy((cfg.get("agent") or {}).get("research_plan") or {})
        _write(run/"manual_capacity_admission.json",{
            "schema":"MAX_MANUAL_DYNAMIC_CAPACITY_ADMISSION_V1",
            "authority":"SAME_LEGAL_RESOURCE_SCIENTIFIC_CAPACITY_AS_AUTO_AND_SCIENTIST",
            "candidates":_manual_capacity_rows,
        })
    if persisted_plan:
        director_state["research_plan"]=persisted_plan
        apply_research_plan(cfg,persisted_plan)

    # Factory-level Research Director. It receives Discovery-side evidence only and
    # creates a persistent directive for the next generation. Deterministic research
    # remains executable when the LLM is unavailable.
    llmcfg=dict((cfg.get("agent") or {}).get("llm") or {})
    director=None
    director_enabled=(not manual_mode) and bool(llmcfg.get("enabled",False))
    if director_enabled:
        director=LLMScientist(llmcfg,api_key=llm_api_key)
        if not director.ready:
            raise RuntimeError("LLM route preflight fail-closed: LLM enabled but provider/model stack is invalid or empty")
        else:
            # START RESEARCH route preflight: actual lightweight call follows the ordered
            # stack. Retryable exhaustion advances through every fallback; only after the
            # last model is unavailable does Max enter deterministic mode. Auth/config
            # errors remain fail-closed and are never disguised as quota exhaustion.
            try:
                route_probe=director.test()
                _write(run/"llm_route_preflight.json",{"schema":"MAX_LLM_ROUTE_PREFLIGHT_V1","status":"READY","probe":route_probe,"provenance":deepcopy(getattr(director,"last_call_provenance",{}))})
            except Exception as exc:
                prov=deepcopy(getattr(director,"last_call_provenance",{}))
                if _llm_stack_exhausted(prov):
                    _write(run/"llm_route_preflight.json",{"schema":"MAX_LLM_ROUTE_PREFLIGHT_V1","status":"ALL_LLM_EXHAUSTED_DETERMINISTIC","error":str(exc),"provenance":prov})
                    # Latch deterministic-only mode for this Factory invocation.  Every
                    # downstream Scientist/Supervisor call sees the same runtime cfg and
                    # must not retry routes already proven exhausted at START RESEARCH.
                    cfg.setdefault("agent",{}).setdefault("llm",{})["factory_session_deterministic_only"]=True
                    cfg["agent"]["llm"]["factory_session_deterministic_only_reason"]="START_PREFLIGHT_ALL_LLM_EXHAUSTED"
                    llmcfg["factory_session_deterministic_only"]=True
                    director_enabled=False
                    director=None
                else:
                    _write(run/"llm_route_preflight.json",{"schema":"MAX_LLM_ROUTE_PREFLIGHT_V1","status":"FAIL_CLOSED","error":str(exc),"provenance":prov})
                    raise RuntimeError("LLM route preflight fail-closed: "+str(exc)) from exc

    # DATA stage Scientist report is a schema/header review only. It is committed once
    # per Factory and receives no raw CSV rows. Resume reuses the existing report.
    _data_reports=[e for e in _read(run/"stage_scientist_journal.json",[]) if isinstance(e,dict) and str(e.get("stage") or "").upper()=="DATA"]
    if not _data_reports:
        data_topology={"schema":"CP_DATA_STAGE_SUMMARY_V2","stage":"DATA","integrity_status":"READY","feature_contract":CONTRACT_ID,"feature_count":len(FEATURES),"data_quality":deepcopy(data_quality_context)}
        data_scientist=_stage_scientist_and_feedback(run,cfg,"DATA","DATA_READY",data_topology,[],llm_api_key=llm_api_key,learning_allowed=False,contract_hash_override=contract_hash)
        _emit(progress,"scientist",0,1,f"LLM Scientist · Data: {data_scientist.get('summary') or 'DATA_READY'}",factory_id=run.name,scientist_update=data_scientist)

    def _director_entry(phase: str, generation: int, response: dict | None = None, error: str | None = None) -> dict:
        response=dict(response or {})
        now=datetime.now(timezone.utc).isoformat()
        return {
            "report_id":f"{run.name}:{str(phase).upper()}:{int(generation)}:{len(director_journal)+1}",
            "source":"FACTORY_RESEARCH_DIRECTOR",
            "factory_id":run.name,"factory_generation":int(generation),"round":0,
            "phase":str(phase).upper(),"created_utc":now,"enabled":bool(director_enabled),
            "summary":str(response.get("summary") or ""),"report":dict(response.get("report") or {}),
            "strategy":dict(response.get("strategy") or {}),"hypotheses":list(response.get("hypotheses") or []),
            "llm_provenance":deepcopy(response.get("llm_provenance") or {}),
            "stop_research":bool(response.get("stop_research",False)),"error":str(error) if error else None,
        }

    def _attach_compiled_director_authority(entry: dict, plan_for_entry: dict) -> dict:
        """Attach the exact deterministic bounds that may execute after an LLM directive."""
        entry=dict(entry or {}); plan_for_entry=deepcopy(plan_for_entry or {})
        local_cfg=deepcopy(cfg); apply_research_plan(local_cfg,plan_for_entry)
        bounds={}
        for fam in list(plan_for_entry.get("active_families") or []):
            row=effective_bounds(local_cfg,str(fam))
            bounds[str(fam)]={k:[v[0],v[1]] for k,v in row.items()}
        entry["compiled_authority"]={
            "schema":"MAX_DIRECTOR_COMPILED_AUTHORITY_V1",
            "parameter_bounds":bounds,
            "family_size_priorities":deepcopy(plan_for_entry.get("family_size_priorities") or configured_family_size_priorities(local_cfg)),
            "topology_priority":deepcopy(plan_for_entry.get("topology_priority") or {}),
            "resource_capacity":deepcopy(plan_for_entry.get("resource_capacity") or {}),
            "authority":"DETERMINISTIC_PLAN_OVERRIDES_LLM_NUMERIC_NARRATIVE",
        }
        rr=dict(entry.get("report") or {}); rr["parameter_authority"]="DETERMINISTIC_COMPILED_EFFECTIVE_BOUNDS"; entry["report"]=rr
        return entry

    def _commit_director(entry: dict):
        director_journal.append(entry)
        _write(run / "research_director_journal.json", director_journal)
        _emit(progress,"research_director",int(entry.get("factory_generation",0)),max_gen,
              f"Research Director · {entry.get('phase')} · " + (entry.get("summary") or ("ERROR: "+str(entry.get("error"))) if entry.get("error") else "directive committed"),
              factory_id=run.name,factory_generation=int(entry.get("factory_generation",0)),director_phase=entry.get("phase"),scientist_update=entry)

    def _existing_director_entry(phase: str, generation: int) -> dict | None:
        phase=str(phase).upper(); generation=int(generation)
        for e in reversed(director_journal):
            if not isinstance(e,dict):
                continue
            if str(e.get("phase") or "").upper()==phase and int(e.get("factory_generation",-1) or -1)==generation:
                return e
        return None

    def _checkpoint(phase: str, **extra):
        payload={
            "schema":"CP_DISCOVERY_RESUME_V1","factory_id":run.name,"phase":str(phase),
            "research_window":rw,"identity":ident,"research_contract_hash":contract_hash,"research_contract":contract_payload,
            "discovery_stage_contract":deepcopy(discovery_stage_contract),"discovery_stage_contract_hash":discovery_stage_contract_hash,
            "historical_seen":sorted(historical_seen),"pool":pool,"pool_fp":sorted(pool_fp),"tested_current":sorted(tested_current),
            "generation_runs":generation_runs,"total_exp":int(total_exp),"memory":memory,
            "guided_override":guided_override,"guided_cycles":guided_cycles,"director_state":director_state,"next_generation":int(next_generation),
            "target":target,"max_generations":max_gen,"max_total_experiments":max_total,"updated_utc":datetime.now(timezone.utc).isoformat(),
        }
        payload.update(extra)
        commit_checkpoint(checkpoint_path,payload)

    if not resumed:
        _checkpoint("SNAPSHOT_COMMITTED")

    if director_enabled and director is not None and not bool(director_state.get("preflight_committed")):
        existing=_existing_director_entry("PREFLIGHT",0)
        if existing and not existing.get("error"):
            research_plan=deepcopy(director_state.get("research_plan") or _read(run/"research_plan.json",{})) or compile_research_plan(existing.get("strategy") or {},hardware_profile,cfg,capacity_profile)
            director_state["research_plan"]=research_plan; apply_research_plan(cfg,research_plan); _write(run/"research_plan.json",research_plan)
            director_state["next_directive"]={"phase":"PREFLIGHT","source_generation":0,"summary":existing.get("summary"),"strategy":existing.get("strategy") or {},"hypotheses":existing.get("hypotheses") or [],"research_plan":research_plan}
            director_state["preflight_committed"]=True; director_state["last_error"]=None
            _emit(progress,"research_director",0,max_gen,"Research Director pre-flight journal reused",factory_id=run.name,factory_generation=0,director_phase="PREFLIGHT_REUSE",scientist_update=existing)
        else:
            try:
                resp=director.factory_preflight({
                    "factory_id":run.name,"factory_generation":0,"dataset":llm_dataset_ctx,
                    "data_quality_profile":deepcopy(data_quality_context),
                    "research_memory":memory,"remaining_budget":max_total-total_exp,
                    "generation_summary":{},"guided_summary":{},"scientific_agenda":[],
                    "hardware_profile":summarize_hardware_profile(hardware_profile),
                    "hardware_capabilities":hardware_caps,
                    "recommended_parameter_envelopes":hardware_envelopes,
                    "dataset_capacity_profile":capacity_profile,
                    "capacity_guidance":capacity_guidance,
                    "model_registry":registry_for_scientist(),
                    "creativity_profile":adaptive_creativity_profile(cfg,failure_topology=(memory.get("failure_topology") or {}),stale_rounds=0),
                    "learning_policy":recommend_learning_actions(memory,memory.get("failure_topology") or {},limit=5),
                    "scientist_skills":skill_guidance({"failure_topology":memory.get("failure_topology") or {},"top_results":memory.get("elites") or []},max_skills=9),
                    "future_learning_foundation":foundation_snapshot(cfg),
                },cfg)
                entry=_director_entry("PREFLIGHT",0,resp)
                research_plan=compile_research_plan(entry.get("strategy") or {},hardware_profile,cfg,capacity_profile)
                director_state["research_plan"]=research_plan; apply_research_plan(cfg,research_plan); _write(run/"research_plan.json",research_plan)
                entry=_attach_compiled_director_authority(entry,research_plan)
                director_state["next_directive"]={"phase":"PREFLIGHT","source_generation":0,"summary":entry.get("summary"),"strategy":entry.get("strategy") or {},"hypotheses":entry.get("hypotheses") or [],"research_plan":research_plan}
                director_state["preflight_committed"]=True; director_state["last_error"]=None
                _commit_director(entry)
            except Exception as exc:
                prov=deepcopy(getattr(director,"last_call_provenance",{})) if director is not None else {}
                if _llm_stack_exhausted(prov):
                    entry=_director_entry("PREFLIGHT",0,{
                        "summary":"LLM stack exhausted · deterministic Research Director fallback",
                        "report":{"condition":"ALL_LLM_EXHAUSTED","interpretation":"All configured LLM routes are temporarily unavailable; deterministic research authority remains active.","next_action":"Compile deterministic research plan inside frozen Owner/capacity authority.","confidence":1.0},
                        "llm_provenance":prov,
                    }); _commit_director(entry)
                    research_plan=compile_research_plan({},hardware_profile,cfg,capacity_profile)
                    director_state["research_plan"]=research_plan; apply_research_plan(cfg,research_plan); _write(run/"research_plan.json",research_plan)
                    director_state["preflight_committed"]=True; director_state["last_error"]=None; director_state.setdefault("next_directive",{})
                    director_enabled=False; director=None
                else:
                    entry=_director_entry("PREFLIGHT",0,error=str(exc)); _commit_director(entry)
                    raise RuntimeError("Research Director pre-flight fail-closed: "+str(exc)) from exc
        _checkpoint("DIRECTOR_PREFLIGHT_COMMITTED")
    elif director_enabled and director_state.get("preflight_committed"):
        _emit(progress,"research_director",0,max_gen,"Research Director pre-flight checkpoint reused",factory_id=run.name,factory_generation=0,director_phase="PREFLIGHT_REUSE")

    if not director_state.get("research_plan"):
        research_plan=compile_research_plan({},hardware_profile,cfg,capacity_profile)
        director_state["research_plan"]=research_plan; apply_research_plan(cfg,research_plan); _write(run/"research_plan.json",research_plan)
    else:
        apply_research_plan(cfg,director_state["research_plan"])

    # compute plan already frozen before Research Architect compilation.

    from models.model_registry import enabled_families
    from models.onnx_export import preflight_export_stack
    deploy_families = tuple(enabled_families(cfg)); preflight_path = run / "factory_onnx_preflight.json"
    _rp=director_state.get("research_plan") or {}
    _source=str(_rp.get("selection_source") or "LEGACY_CONFIG")
    # Historical R6 manifests used DEFAULT / MANUAL_ENABLED provenance. R7 preserves those values as accepted legacy evidence; new adaptive cycles use SCIENTIST or DETERMINISTIC_FALLBACK.
    active_family_provenance=[{"family":f,"provenance":_source} for f in deploy_families]
    existing_pf=_read(preflight_path,{}) if preflight_path.exists() else {}
    if existing_pf.get("status")=="PASS":
        _emit(progress,"onnx_preflight_reuse",1,1,"Factory ONNX preflight checkpoint reused · PASS")
    else:
        _emit(progress, "compute", 1, 1, "Compute AUTO resolved", compute_plan=plan)
        _emit(progress, "onnx_preflight", 0, max(1, len(deploy_families)), "Factory ONNX preflight · one-time gate")
        def _pf_cb(ev):
            fam = str(ev.get("family") or "model"); cur = int(ev.get("current", 0) or 0); total = max(1, int(ev.get("total", 1) or 1)); phase = str(ev.get("phase") or "start"); status = str(ev.get("status") or "")
            msg = f"ONNX preflight {fam} · {cur}/{total}" if phase == "start" else f"ONNX preflight {fam} · {status} · {cur}/{total}"
            _emit(progress, "onnx_preflight", cur, total, msg, family=fam, phase=phase, status=status)
        pf = preflight_export_stack(families=deploy_families, n_features=32, tolerance=float(cfg["acceptance"].get("max_onnx_abs_error", 1e-4)), progress=_pf_cb)
        _write(preflight_path, pf)
        if pf.get("status") != "PASS":
            failed = [str(x.get("family")) + ": " + str(x.get("error") or "unknown") for x in pf.get("families", []) if x.get("status") != "PASS"]
            raise RuntimeError("Factory ONNX preflight FAIL: " + ("; ".join(failed) or "unknown converter failure"))
        _checkpoint("PREFLIGHT_COMMITTED")

    base_seed = int(cfg.get("seed", 42))
    for gen in range(next_generation, max_gen + 1):
        if len(pool) >= target or total_exp >= max_total:
            break
        gcfg = deepcopy(cfg)
        if isinstance(guided_override.get("label"),dict):
            _label=deepcopy(gcfg.get("label") or {}); _label.update(strip_strategy_geometry_from_label(guided_override["label"])); gcfg["label"]=_label
        if isinstance(guided_override.get("feature_research"),dict): gcfg["feature_research"]=deepcopy(guided_override["feature_research"])
        ac = gcfg.setdefault("agent", {})
        ac["skip_locked_test"] = True; ac["discovery_full_oof_only"] = True; ac["disable_pass_early_stop"] = True
        ac["factory_generation"] = int(gen)
        ac["factory_pool_remaining_slots"] = max(0,int(target-len(pool)))
        ac["factory_committed_pool_size"] = int(len(pool))
        ac["research_contract_hash"] = str(contract_hash)
        directive=deepcopy(director_state.get("next_directive") or {})
        if directive:
            ac["factory_director"]=directive
            # Closed-loop capacity tuning: the Research Director may tighten/widen the
            # next generation's parameter envelope without changing the family universe.
            _rp=deepcopy(ac.get("research_plan") or {})
            _rp=apply_strategy_parameter_envelopes(_rp,directive.get("strategy") or {})
            if _rp:
                ac["research_plan"]=_rp
        ac["max_experiments"] = min(batch_budget, max_total - total_exp); ac["onnx_preflight_authority"] = str(preflight_path)
        ac["exclude_experiment_fingerprints"] = sorted(historical_seen | tested_current)
        ac["factory_context"]={
            "hardware_profile":summarize_hardware_profile(hardware_profile),
            "dataset_capacity_profile":deepcopy(capacity_profile),
            "capacity_guidance":deepcopy(capacity_guidance),
            "research_plan":deepcopy(ac.get("research_plan") or director_state.get("research_plan") or {}),
            "compute_plan":deepcopy(plan),
            "owner_topology_priority":deepcopy((gcfg.get("research_architecture") or {}).get("hybrid_priority",0.50)),
            "owner_family_size_priorities":deepcopy(configured_family_size_priorities(gcfg)),
            "cpcv_seed_policy":deepcopy(((fc.get("cpcv_stage") or {}).get("seed_confirmation") or {})),
            "authority":"FACTORY_CONTEXT_R6_FAMILY_SIZE_PRIORITY"
        }
        gcfg["seed"] = base_seed + (gen - 1) * 104729; gcfg["research_window"] = rw
        if memory: ac["generation_memory"] = memory
        gp = run / f"generation_{gen:02d}_config.json"; _write(gp, gcfg)
        def _gen_progress(ev):
            if progress:
                x=dict(ev or {}); x.setdefault("factory_id",run.name); x.setdefault("factory_generation",gen); progress(x)
        skipped = len(historical_seen | tested_current)
        _checkpoint("GENERATION_READY",current_generation=gen)
        _emit(progress, "factory_discovery", gen - 1, max_gen, f"Discovery generation {gen} · pool {len(pool)}/{target} · prior fingerprints {skipped}")

        # Supervisor result is one atomic unit. Discovery v0.7.3 stops at WFA/OOF.
        # CPCV is deliberately deferred until the WFA-qualified pool is frozen, so expensive
        # combinatorial fits cannot block every research generation.
        cp_now=load_checkpoint(checkpoint_path) or {}
        reuse_supervisor = int(cp_now.get("current_generation",0) or 0)==gen and str(cp_now.get("phase")) in {"SUPERVISOR_COMMITTED","POOL_COMMITTED","GUIDED_RUNNING"} and isinstance(cp_now.get("current_leaderboard"),list)
        if reuse_supervisor:
            lb=list(cp_now.get("current_leaderboard") or []); rd=run/"research_runs"/str(cp_now.get("current_run")); pool_before=int(cp_now.get("pool_before",len(pool)) or len(pool))
            _emit(progress,"factory_resume",len(pool),target,f"Resume generation {gen} dari WFA pool checkpoint · pool {len(pool)}/{target}")
        else:
            _checkpoint("SUPERVISOR_RUNNING",current_generation=gen)
            res = run_supervisor_agent(snap, gp, run / "research_runs", progress=_gen_progress, llm_api_key=llm_api_key)
            rd = Path(res["run"]); lb = _read(rd / "cv_leaderboard.json", [])
            if rd.name not in generation_runs: generation_runs.append(rd.name)
            for r in lb:
                if isinstance(r, dict):
                    r["run_id"] = rd.name
                    if r.get("family") and isinstance(r.get("params"), dict):
                        spec0=CandidateSpec(str(r["family"]), str(r.get("name") or "tested"), dict(r["params"]))
                        tested_current.add(str(r.get("experiment_fingerprint") or experiment_fingerprint(spec0,gcfg)))
            leaderboards.append({"generation":int(gen),"run_id": rd.name, "rows": lb})
            manifest = _read(rd / "model_manifest.json", {})
            _policy=manifest.get("decision_policy") if isinstance(manifest.get("decision_policy"),dict) else None
            _cvsel=manifest.get("cv_selection") if isinstance(manifest.get("cv_selection"),dict) else None
            _cvacc=manifest.get("cv_acceptance") if isinstance(manifest.get("cv_acceptance"),dict) else None
            if _policy and _cvsel and bool((_cvacc or {}).get("passed")):
                _pr=deepcopy(_cvsel)
                _pr.update({"family":manifest.get("model_family"),"name":manifest.get("model_name"),"params":deepcopy(manifest.get("hyperparameters") or {}),
                            "fidelity_stage":"FULL_WFA_POLICY","cv_gate_pass":True,"cv_gate_reasons":[],"cv_first_failed_gate":None,
                            "decision_policy":deepcopy(_policy),"policy_fingerprint":_stable_hash(_policy)})
                _specp=CandidateSpec(str(_pr["family"]),str(_pr["name"]),dict(_pr["params"]))
                _pr.setdefault("experiment_fingerprint",experiment_fingerprint(_specp,gcfg)); _pr.setdefault("training_seed",int(gcfg.get("seed",42) or 42))
                _pr.setdefault("trained_candidate_id",manifest.get("trained_candidate_id") or _stable_hash({"spec":spec_fingerprint(_specp),"seed":_pr["training_seed"],"policy":_pr["policy_fingerprint"],"contract":contract_hash}))
                lb=[r for r in lb if not (str((r or {}).get("name"))==str(_pr.get("name")) and str((r or {}).get("family"))==str(_pr.get("family")))] + [_pr]
            total_exp += int((manifest.get("agent") or {}).get("experiments_completed", len(lb)))
            pool_before=len(pool)
            _checkpoint("SUPERVISOR_COMMITTED",current_generation=gen,current_run=rd.name,current_leaderboard=lb,pool_before=pool_before)

        _merge_factory_trial_ledger(run,rd,gen)
        # Full-WFA failure topology is a research diagnostic; it cannot grant PASS.
        _factory_full_rows=[]
        for _b in leaderboards:
            _factory_full_rows.extend([_r for _r in (_b.get("rows") or []) if isinstance(_r,dict)])
        _write(run/"failure_topology.json",failure_topology(_factory_full_rows,authority="FACTORY_FULL_WFA"))

        passed = [r for r in lb if bool(r.get("cv_gate_pass")) and str(r.get("fidelity_stage") or "FULL_WFA").startswith("FULL_WFA") and bool(walk_forward_acceptance(r,gcfg).get("passed"))]
        passed.sort(key=lambda r: float(r.get("selection_score", -1e99)), reverse=True)
        # Filter exact research-experiment duplicates BEFORE diversity allocation. If a
        # duplicate consumes an allocation slot and is skipped only afterwards, another
        # valid WFA PASS can be stranded and the Pool may remain under-filled.
        eligible_passed=[]
        for r in passed:
            if not (r.get("family") and isinstance(r.get("params"),dict)): continue
            _spec=CandidateSpec(str(r["family"]),str(r.get("name") or "tested"),dict(r["params"]))
            _fp=str(r.get("experiment_fingerprint") or experiment_fingerprint(_spec,gcfg))
            if _fp in pool_fp or _fp in historical_seen: continue
            eligible_passed.append(r)
        div_weight=float(fc.get("pool_diversity_weight",0.15) or 0.15)
        allocated=(eligible_passed[:max(0,target-len(pool))] if manual_mode else _select_pool_passes(eligible_passed,pool,target-len(pool),div_weight,gcfg))
        for r in allocated:
            if len(pool)>=target: break
            spec = CandidateSpec(str(r["family"]), str(r["name"]), dict(r["params"]))
            fp = str(r.get("experiment_fingerprint") or experiment_fingerprint(spec,gcfg))
            if fp in pool_fp or fp in historical_seen:
                continue
            pool_fp.add(fp)
            pool.append({
                "pool_id": f"CAND_{len(pool)+1:02d}", "source_run": rd.name, "family": spec.family, "name": spec.name,
                "params": spec.params, "fingerprint": fp, "spec_fingerprint": spec_fingerprint(spec),
                "trained_candidate_id":r.get("trained_candidate_id"),"training_seed":r.get("training_seed"),
                "decision_policy":deepcopy(r.get("decision_policy") or {}) or None,"policy_fingerprint":r.get("policy_fingerprint"),
                "experiment_block_id":r.get("experiment_block_id"),"hypothesis_id":r.get("hypothesis_id"),
                "pool_diversity_score":r.get("pool_diversity_score"),"pool_allocation_score":r.get("pool_allocation_score"),
                "take_threshold": float(r.get("take_threshold", 0.65)),
                "research_overrides": {"label":strip_strategy_geometry_from_label(gcfg.get("label") or {}),"feature_research":deepcopy(gcfg.get("feature_research") or {})},
                "wfa_evidence":deepcopy(r),
                "discovery_acceptance": {"passed":True,"authority":"FULL_WFA_ONLY","first_failed_gate":None},
                "cpcv_status":"WAITING",
                "discovery_metrics": {k: r.get(k) for k in (
                    "selection_score", "total_validation_trades", "auto_min_validation_trades", "median_profit_factor",
                    "overall_expectancy_r", "median_expectancy_r", "worst_expectancy_r", "median_max_drawdown_r", "worst_fold_max_drawdown_r",
                    "median_recovery_factor", "worst_fold_recovery_factor", "positive_fold_ratio")},
            })
            _write(run/"candidate_pool.json",pool)

        new_qualified=len(pool)-pool_before
        _checkpoint("POOL_COMMITTED",current_generation=gen,current_run=rd.name,current_leaderboard=lb,pool_before=pool_before)
        if (not manual_mode) and len(pool) < target and new_qualified == 0:
            try:
                _checkpoint("GUIDED_RUNNING",current_generation=gen,current_run=rd.name,current_leaderboard=lb,pool_before=pool_before)
                cycle=_guided_cycle(rd,snap,gp,run / "research_runs",progress=_gen_progress)
                g=cycle.get("guided") or {}; guided_cycles.append({"generation":gen,"audit_run":Path(cycle["audit"]["run"]).name,"guided_run":Path(g.get("run","")).name,"status":g.get("status")})
                if g.get("status")=="GUIDED_RESEARCH_READY":
                    rc=g.get("recommended_config") or {}
                    guided_override={"label":deepcopy(rc.get("label") or gcfg.get("label") or {}),"feature_research":deepcopy(rc.get("feature_research") or gcfg.get("feature_research") or {})}
                    _emit(progress,"guided_learning",gen,max_gen,"Guided Research PASS · next generation memakai learned label/feature contract",guided_run=g.get("run"))
                else:
                    _emit(progress,"guided_learning",gen,max_gen,"Guided Research tidak menemukan hypothesis PASS · lanjut Research Memory/Scientist")
            except FactoryControlSignal:
                raise
            except Exception as exc:
                guided_cycles.append({"generation":gen,"status":"GUIDED_ERROR","error":str(exc)})
                _emit(progress,"guided_learning",gen,max_gen,f"Guided cycle gagal; deterministic Research Memory tetap lanjut: {exc}")

        local_memory = _pool_memory(pool, leaderboards)
        local_memory["failure_topology"]=_read(run/"failure_topology.json",{})
        _hl=_read(rd/"hypothesis_lifecycle.json",[])
        if isinstance(_hl,list): local_memory["hypothesis_lifecycle"]=deepcopy(_hl)
        if guided_cycles: local_memory["guided_cycles"]=deepcopy(guided_cycles[-8:])
        memory = _merge_learning_memory(global_learning, local_memory)
        _write(run / "research_memory.json", memory); _write(run / "candidate_pool.json", pool)
        if not manual_mode:
            grec["tested_experiment_fingerprints"] = sorted(historical_seen | tested_current); grec["learning_memory"] = memory; grec["updated_utc"] = datetime.now(timezone.utc).isoformat()
            if run.name not in grec["factories"]: grec["factories"].append(run.name)
            _save_global_contract(root, gm, contract_hash, grec)
            _rp_evidence=deepcopy(director_state.get("research_plan") or _read(run/"research_plan.json",{}))
            _active_families=list((_rp_evidence or {}).get("active_families") or []) if isinstance(_rp_evidence,dict) else []
            # Dynamic capacity learns from cumulative *committed* Full-WFA evidence
            # inside this exact Factory lineage.  The collector excludes CHEAP_SCREEN
            # and provisional/non-WFA rows, and deduplicates resume/evidence mirrors by
            # authoritative experiment_fingerprint where available.
            _capacity_rows=cumulative_committed_full_wfa_capacity_rows(leaderboards)
            _capacity_evidence_by_family=summarize_capacity_evidence_by_family(
                _capacity_rows,_active_families,authority=CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY
            )
            _capacity_evidence=summarize_capacity_evidence(
                _capacity_rows,authority=CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY
            )
            if isinstance(_rp_evidence,dict) and _rp_evidence:
                _rp_evidence["capacity_evidence"]=_capacity_evidence
                _rp_evidence["capacity_evidence_by_family"]=_capacity_evidence_by_family
                director_state["research_plan"]=_rp_evidence
                apply_research_plan(cfg,_rp_evidence)
                _write(run/"research_plan.json",_rp_evidence)
                _write(run/f"capacity_evidence_generation_{gen:02d}.json",{
                    "authority":CUMULATIVE_COMMITTED_FULL_WFA_AUTHORITY,
                    "committed_full_wfa_observation_count":len(_capacity_rows),
                    "global_index":_capacity_evidence,
                    "capacity_evidence_by_family":_capacity_evidence_by_family,
                })

        if director_enabled and director is not None:
            existing=_existing_director_entry("GENERATION_REVIEW",gen)
            if existing and not existing.get("error"):
                director_state["next_directive"]={"phase":"GENERATION_REVIEW","source_generation":gen,"summary":existing.get("summary"),"strategy":existing.get("strategy") or {},"hypotheses":existing.get("hypotheses") or []}
                director_state["last_error"]=None
                _emit(progress,"research_director",gen,max_gen,f"Research Director generation {gen} journal reused",factory_id=run.name,factory_generation=gen,director_phase="GENERATION_REVIEW_REUSE",scientist_update=existing)
            else:
                try:
                    agenda=_read(rd / "scientific_agenda.json",[])
                    if not isinstance(agenda,list): agenda=[]
                    top_rows=[]
                    for _r in lb[:8]:
                        if not isinstance(_r,dict): continue
                        top_rows.append({k:_r.get(k) for k in ("name","family","cv_gate_pass","cv_first_failed_gate","selection_score","median_profit_factor","overall_expectancy_r","median_expectancy_r","worst_expectancy_r","worst_fold_max_drawdown_r","total_validation_trades","parameter_count","median_effective_train_rows","training_memory_months")})
                    resp=director.factory_generation_review({
                        "factory_id":run.name,"factory_generation":gen,"dataset":llm_dataset_ctx,"research_memory":memory,
                        "remaining_budget":max(0,max_total-total_exp),"scientific_agenda":agenda,
                        "guided_summary":guided_cycles[-1] if guided_cycles else {},
                        "generation_summary":{
                            "experiments":len(lb),"wfa_passed":len(passed),"wfa_pool_added":new_qualified,
                            "pool_qualified":len(pool),"pool_target":target,"top_results":top_rows,
                            "cpcv_stage":"DEFERRED_UNTIL_WFA_POOL_READY","failure_gate_counts":local_memory.get("failure_gate_counts") or {},
                            "failure_topology":_read(run/"failure_topology.json",{}),
                            "all_trial_summary":_read(run/"all_trial_summary.json",{}),
                        },
                        "hardware_profile":summarize_hardware_profile(hardware_profile),
                        "hardware_capabilities":hardware_caps,
                        "recommended_parameter_envelopes":hardware_envelopes,
                        "dataset_capacity_profile":capacity_profile,
                        "capacity_guidance":capacity_guidance,
                        "creativity_profile":adaptive_creativity_profile(gcfg,board=lb,failure_topology=_read(run/"failure_topology.json",{}),stale_rounds=0),
                        "learning_policy":recommend_learning_actions(memory,_read(run/"failure_topology.json",{}),limit=5),
                        "scientist_skills":skill_guidance({"failure_topology":_read(run/"failure_topology.json",{}),"top_results":top_rows},max_skills=9),
                        "future_learning_foundation":foundation_snapshot(gcfg),
                    },gcfg)
                    entry=_director_entry("GENERATION_REVIEW",gen,resp)
                    _next_plan=apply_strategy_parameter_envelopes(deepcopy(director_state.get("research_plan") or _read(run/"research_plan.json",{})),entry.get("strategy") or {})
                    entry=_attach_compiled_director_authority(entry,_next_plan)
                    _commit_director(entry)
                    director_state["next_directive"]={"phase":"GENERATION_REVIEW","source_generation":gen,"summary":entry.get("summary"),"strategy":entry.get("strategy") or {},"hypotheses":entry.get("hypotheses") or []}
                    director_state["last_error"]=None
                except Exception as exc:
                    prov=deepcopy(getattr(director,"last_call_provenance",{})) if director is not None else {}
                    if _llm_stack_exhausted(prov):
                        entry=_director_entry("GENERATION_REVIEW",gen,{
                            "summary":f"Generation {gen} · LLM stack exhausted · deterministic research continues",
                            "report":{"condition":"ALL_LLM_EXHAUSTED","interpretation":"No configured LLM route remained available at this safe generation boundary.","next_action":"Continue deterministic Discovery from committed evidence.","confidence":1.0},
                            "llm_provenance":prov,
                        }); _commit_director(entry)
                        director_state["last_error"]=None
                        cfg.setdefault("agent",{}).setdefault("llm",{})["factory_session_deterministic_only"]=True
                        cfg["agent"]["llm"]["factory_session_deterministic_only_reason"]="GENERATION_REVIEW_ALL_LLM_EXHAUSTED"
                        director_enabled=False; director=None
                    else:
                        entry=_director_entry("GENERATION_REVIEW",gen,error=str(exc)); _commit_director(entry)
                        director_state["last_error"]=str(exc)
                        raise RuntimeError("Research Director generation review fail-closed: "+str(exc)) from exc

        _write(run / "discovery_progress.json", {"schema": SCHEMA, "generation": gen, "qualified": len(pool), "target": target, "qualification_authority":"WFA_OOF_ONLY", "cpcv_stage":"DEFERRED", "total_experiments": total_exp, "max_total_experiments": max_total, "generation_runs": generation_runs, "historical_fingerprints_skipped": len(historical_seen), "research_director_reports": len(director_journal)})
        next_generation=gen+1
        _checkpoint("GENERATION_COMMITTED")
        _emit(progress, "factory_generation_done", gen, max_gen, f"Generation {gen} selesai · WFA pool {len(pool)}/{target} · experiments {total_exp}/{max_total}", qualified=len(pool), target=target, total_experiments=total_exp, max_total_experiments=max_total)

    pool = pool[:target]
    ready = (len(pool) >= manual_min_survivors) if manual_mode else (len(pool) == target)
    status = "DISCOVERY_POOL_READY" if ready else ("MANUAL_WFA_NO_SURVIVOR" if manual_mode else "INSUFFICIENT_QUALIFIED_POOL")
    forward_mode = str(fc.get("fresh_to_mode") or "AUTO_NEWEST").upper()
    forward_contract = {"from": str(fresh_from), "to": "AUTO_NEWEST" if forward_mode == "AUTO_NEWEST" else str(fresh_to), "initial_to": str(fresh_to), "mode": forward_mode}
    manifest = {
        "schema": SCHEMA, "factory_id": run.name, "status": status, "stage": "DISCOVERY",
        "research_control":research_control_provenance(research_mode),
        "research_mode":research_mode,
        "source_master": str(master), "source_master_sha256": _sha(master),
        "research_contract_hash": contract_hash, "research_contract": contract_payload, "research_kernel_schema": RESEARCH_KERNEL_SCHEMA,
        "discovery_stage_contract":deepcopy(discovery_stage_contract),"discovery_stage_contract_hash":discovery_stage_contract_hash,
        "global_memory": {"historical_fingerprints_skipped": len(historical_seen), "global_memory_file": "../_global_research_memory.json"},
        "compute_plan_file": "compute_plan.json", "checkpoint_file":"discovery_checkpoint.json", "checkpoint_policy":"LAST_COMMITTED_ATOMIC",
        "active_family_provenance":active_family_provenance,
        "research_director":{"enabled":bool(director_enabled),"journal_file":"research_director_journal.json","reports":len(director_journal),"preflight_committed":bool(director_state.get("preflight_committed"))},
        "research_engine":{"schema":RESEARCH_ENGINE_SCHEMA,"fidelity_ladder":("DISABLED_OWNER_EXACT" if manual_mode else "CHEAP_SCREEN_TO_FULL_WFA"),"failure_topology_file":"failure_topology.json","all_trial_ledger_file":"all_trials.jsonl","qualification_authority":"FULL_WFA_ONLY","deterministic_discovery_used":False if manual_mode else True},
        "discovery": {"from": str(discovery_from), "to": str(discovery_to), "snapshot": "discovery_immutable.csv", "snapshot_sha256": _sha(snap), "identity": ident, "method": "WFA_OOF_POOL__CPCV_DEFERRED_FINALIST_STAGE", "qualification_authority":"WFA_OOF", "guided_cycles": guided_cycles},
        "tournament_contract": {"from": str(tournament_from), "to": str(tournament_to),"snapshot":"tournament_immutable.csv","snapshot_sha256":_sha(run/"tournament_immutable.csv")},
        "forward_contract": {**forward_contract,"refit_history":"forward_refit_history.csv","refit_history_sha256":_sha(run/"forward_refit_history.csv")},
        "candidate_pool_file": "candidate_pool.json", "qualified_candidates": len(pool), "target_candidates": target,
        "manual_research":({"requested_candidates":target,"minimum_wfa_survivors":manual_min_survivors,"candidate_names":[str(x.get("name") or x.get("family")) for x in manual_candidates],"llm_used":False,"deterministic_discovery_used":False,"validation_authority":"DETERMINISTIC"} if manual_mode else None),
        "total_experiments": total_exp, "max_total_experiments": max_total, "generation_runs": generation_runs,
        "cpcv_opened": False, "cpcv_survivors_file": None, "tournament_opened": False, "monte_carlo_opened": False, "forward_opened": False, "forward_checks": [], "next_required":("RUN_CPCV_QUALIFICATION" if ready else ("MANUAL_TERMINAL_WFA_FAIL" if manual_mode else "CONTINUE_DISCOVERY")),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    # Do not publish a terminal Discovery manifest until its immutable artifacts are
    # sealed. A power loss between manifest publication and seal creation would leave
    # an unrecoverable DISCOVERY_POOL_READY state that CPCV must reject.
    _write(run / "candidate_pool.json", pool)
    discovery_seal=_stage_seal(run,"DISCOVERY",contract=discovery_stage_contract,files=["candidate_pool.json","discovery_immutable.csv","tournament_immutable.csv","forward_refit_history.csv"])
    manifest["discovery_terminal_seal"]="discovery_terminal_seal.json"; manifest["discovery_terminal_seal_hash"]=discovery_seal["seal_hash"]
    pool_topology={"schema":"CP_POOL_STAGE_SUMMARY_V1","stage":"POOL","evaluated":len(pool),"passed":len(pool),"failed":0,"dominant_failure_group":None,
                   "candidate_rows":[{"pool_id":c.get("pool_id"),"family":c.get("family"),"name":c.get("name"),"status":"QUALIFIED","selection_score":(c.get("discovery_metrics") or {}).get("selection_score")} for c in pool]}
    pool_scientist=_stage_scientist_and_feedback(run,cfg,"POOL",status,pool_topology,pool,llm_api_key=llm_api_key,learning_allowed=((not ready) and (not manual_mode)),contract_hash_override=contract_hash)
    manifest["stage_scientist_journal"]="stage_scientist_journal.json"
    if (not ready) and (not manual_mode):
        manifest["research_learning_ready"]=bool(pool_scientist.get("learning_ready"))
        manifest["research_feedback_exhausted"]=bool(pool_scientist.get("feedback_exhausted"))
        manifest["research_restart_required"]=bool(pool_scientist.get("learning_ready")) and not bool(pool_scientist.get("feedback_exhausted"))
        manifest["next_required"]=("STOP_RESEARCH_FEEDBACK_BUDGET" if pool_scientist.get("feedback_exhausted") else ("START_NEW_DISCOVERY_WITH_POOL_LEARNING" if pool_scientist.get("learning_ready") else "WAIT_SCIENTIST_REVIEW"))
    _write(run/"factory_manifest.json",manifest)
    next_generation=max_gen+1; _checkpoint("DISCOVERY_COMPLETED",final_status=status)
    _emit(progress, "factory_done", 1, 1, f"{status} · {len(pool)}/{target} qualified",scientist_update=pool_scientist)
    return {"factory": str(run), "status": status, "qualified": len(pool), "target": target, "manifest": manifest,"scientist":pool_scientist}

def _fit_candidate(spec: CandidateSpec, train_df: pd.DataFrame, cfg: dict):
    from models.model_lab import apply_candidate_memory
    td, mem = apply_candidate_memory(train_df, spec, cfg)
    X = feature_matrix(td, cfg); y = td["label"].to_numpy(np.int64)
    model=make_model(spec,cfg); fit_model(model,spec.family,X,y,sample_weight=(td["supervised_weight"].to_numpy(float) if "supervised_weight" in td.columns else None),cfg=cfg)
    return model, td, X, mem


def _tournament_acceptance(metrics: dict, cfg: dict, sample: dict, yearly: dict) -> dict:
    p = gate_profile(cfg, "tournament")
    gates = {
        "MIN_TRADES": int(metrics.get("trades", 0)) >= int(sample["minimum_trades"]),
        "MAX_DD": float(metrics.get("max_drawdown_r", 999999)) <= float(p.get("max_drawdown_r", 12.0)),
        "MIN_RECOVERY": float(metrics.get("recovery_factor", -999)) >= float(p.get("min_recovery_factor", 2.0)),
        "MIN_PF": float(metrics.get("profit_factor", 0)) >= float(p.get("min_profit_factor", 1.35)),
        "MIN_EXPECTANCY": float(metrics.get("expectancy_r", -999)) >= float(p.get("min_expectancy_r", 0.15)),
        "EVERY_YEAR_NONNEGATIVE": (all(float(v.get("expectancy_r", -999)) >= 0.0 for v in yearly.values()) if yearly else False) if bool(p.get("require_every_year_nonnegative", True)) else True,
        "POSITIVE_MONTHS": float(metrics.get("positive_month_ratio", 0)) >= float(p.get("min_positive_month_ratio", 0.55)),
        "POSITIVE_QUARTERS": float(metrics.get("positive_quarter_ratio", 0)) >= float(p.get("min_positive_quarter_ratio", 0.60)),
        "REGIME_CONCENTRATION": float(metrics.get("regime_concentration", 1)) <= float(p.get("max_dominant_positive_regime_share", 0.75)),
        "TOP10_WIN_SHARE": float(metrics.get("top10_win_profit_share", 1)) <= float(p.get("max_top10_win_profit_share", 0.55)),
        "STRESS_X1_50": float(metrics.get("stress_x1_50_expectancy_r", -999)) >= float(p.get("stress_x1_50_min_expectancy_r", 0.05)),
    }
    rows = [
        {"name":"MIN_TRADES","actual":int(metrics.get("trades",0)),"operator":">=","threshold":int(sample["minimum_trades"]),"passed":bool(gates["MIN_TRADES"])},
        {"name":"MAX_DD","actual":float(metrics.get("max_drawdown_r",999999)),"operator":"<=","threshold":float(p.get("max_drawdown_r",12.0)),"passed":bool(gates["MAX_DD"])},
        {"name":"MIN_RECOVERY","actual":float(metrics.get("recovery_factor",-999)),"operator":">=","threshold":float(p.get("min_recovery_factor",2.0)),"passed":bool(gates["MIN_RECOVERY"])},
        {"name":"MIN_PF","actual":float(metrics.get("profit_factor",0)),"operator":">=","threshold":float(p.get("min_profit_factor",1.35)),"passed":bool(gates["MIN_PF"])},
        {"name":"MIN_EXPECTANCY","actual":float(metrics.get("expectancy_r",-999)),"operator":">=","threshold":float(p.get("min_expectancy_r",0.15)),"passed":bool(gates["MIN_EXPECTANCY"])},
        {"name":"EVERY_YEAR_NONNEGATIVE","actual":min([float(v.get("expectancy_r",-999)) for v in yearly.values()], default=None),"operator":">=","threshold":0.0,"passed":bool(gates["EVERY_YEAR_NONNEGATIVE"])},
        {"name":"POSITIVE_MONTHS","actual":float(metrics.get("positive_month_ratio",0)),"operator":">=","threshold":float(p.get("min_positive_month_ratio",0.55)),"passed":bool(gates["POSITIVE_MONTHS"])},
        {"name":"POSITIVE_QUARTERS","actual":float(metrics.get("positive_quarter_ratio",0)),"operator":">=","threshold":float(p.get("min_positive_quarter_ratio",0.60)),"passed":bool(gates["POSITIVE_QUARTERS"])},
        {"name":"REGIME_CONCENTRATION","actual":float(metrics.get("regime_concentration",1)),"operator":"<=","threshold":float(p.get("max_dominant_positive_regime_share",0.75)),"passed":bool(gates["REGIME_CONCENTRATION"])},
        {"name":"TOP10_WIN_SHARE","actual":float(metrics.get("top10_win_profit_share",1)),"operator":"<=","threshold":float(p.get("max_top10_win_profit_share",0.55)),"passed":bool(gates["TOP10_WIN_SHARE"])},
        {"name":"STRESS_X1_50","actual":float(metrics.get("stress_x1_50_expectancy_r",-999)),"operator":">=","threshold":float(p.get("stress_x1_50_min_expectancy_r",0.05)),"passed":bool(gates["STRESS_X1_50"])},
    ]
    risk_rows=risk_gate_rows(metrics,risk_cfg_for_gate(cfg,"tournament"),mode="point",prefix="TOURNAMENT",group="risk_adjusted")
    for row in risk_rows:
        gates[row["name"]]=bool(row["passed"])
        rows.append(row)
    failed = [k for k, v in gates.items() if not v]
    return {"schema":"MAX_GATE_KPI_PROFILES_V1","profile":str(p.get("profile_version","TOURNAMENT_KPI_V1")),"passed": not failed, "first_failed_gate": failed[0] if failed else None, "reasons": failed, "gates": gates, "gate_rows": rows, "risk_kpi_gates": risk_rows, "sample": sample}



def _requires_cpcv_seed_confirmation(family: str) -> bool:
    fam=str(family or "")
    if (family_spec(fam) or {}).get("role")=="temporal":
        return True
    if is_hybrid_family(fam):
        parts=hybrid_parts(fam)
        return bool(parts and (family_spec(parts[0]) or {}).get("role")=="temporal")
    return False


def _cpcv_seed_list(cfg: dict, family: str) -> list[int]:
    """Canonical seed discipline: temporal/hybrid = 42→11→77; deterministic tree = configured base seed."""
    if _requires_cpcv_seed_confirmation(family):
        return [42,11,77]
    return [int((cfg or {}).get("seed",42) or 42)]


def _aggregate_seed_cpcv(seed_rows: list[dict], planned_seeds: list[int] | None = None) -> dict:
    if not seed_rows:
        raise RuntimeError("CPCV seed confirmation produced no evidence")
    planned=[int(x) for x in (planned_seeds or [r.get("seed") for r in seed_rows])]
    completed=[int(x.get("seed")) for x in seed_rows]
    per_seed_pass=[bool((x.get("evidence") or {}).get("passed")) for x in seed_rows]
    complete=(completed==planned)
    passed=bool(complete and all(per_seed_pass))
    first_fail=next((x for x in seed_rows if not bool((x.get("evidence") or {}).get("passed"))),None)
    summaries=[(x.get("evidence") or {}).get("summary") or {} for x in seed_rows]
    keys=set().union(*(d.keys() for d in summaries)) if summaries else set(); summary={}
    for k in keys:
        vals=[]
        for d in summaries:
            v=d.get(k)
            if isinstance(v,(int,float)) and math.isfinite(float(v)): vals.append(float(v))
        if not vals: continue
        lk=str(k).lower()
        if "worst_expectancy" in lk or "worst_recovery" in lk: summary[k]=float(min(vals))
        elif "worst" in lk and ("drawdown" in lk or "ulcer" in lk): summary[k]=float(max(vals))
        else: summary[k]=float(np.median(vals))
    summary.update({"seed_count_completed":len(seed_rows),"seed_pass_count":sum(per_seed_pass),"seed_ids":completed})
    pbo_groups=group_expectancy_from_seed_rows(seed_rows,groups=int((seed_rows[0].get("evidence") or {}).get("groups",6) or 6))
    reasons=[]; first_failed_gate=None
    if first_fail:
        ev=first_fail.get("evidence") or {}; seed=int(first_fail.get("seed")); fg=ev.get("first_failed_gate") or "CPCV_FAIL"
        first_failed_gate=f"SEED_{seed}::{fg}"; reasons=[f"SEED_{seed}::{r}" for r in (ev.get("reasons") or [fg])]
    elif not complete:
        first_failed_gate="CPCV_SEED_STABILITY"; reasons=[f"CPCV_SEED_STABILITY:{len(completed)}/{len(planned)}"]
    base=deepcopy(seed_rows[0].get("evidence") or {})
    # Every economic/risk gate is AND across completed seeds; missing planned seeds make stability fail.
    gate_maps=[(x.get("evidence") or {}).get("gates") or {} for x in seed_rows]
    gate_names=sorted(set().union(*(g.keys() for g in gate_maps if isinstance(g,dict))))
    gates={name:all(bool(g.get(name,False)) for g in gate_maps if isinstance(g,dict)) for name in gate_names}
    gates["CPCV_SEED_STABILITY"]=passed
    return {
        "schema":"CP_CPCV_SEED_CONFIRMATION_V2","passed":passed,"first_failed_gate":first_failed_gate,"reasons":reasons,
        "summary":summary,"combinations":int(base.get("combinations",0) or 0),
        "groups":base.get("groups"),"test_groups":base.get("test_groups"),"purge_bars":base.get("purge_bars"),"embargo_bars":base.get("embargo_bars"),
        "take_threshold":base.get("take_threshold"),"policy_schema":base.get("policy_schema"),"decision_policy":deepcopy(base.get("decision_policy")),
        "seed_confirmation":{"required":len(planned)>1,"planned_seeds":planned,"planned_seed_count":len(planned),"completed_seed_count":len(seed_rows),
            "policy":"PROGRESSIVE_ALL_FIXED_SEEDS_MUST_PASS","seed_results":[{"seed":int(x.get("seed")),"passed":bool((x.get("evidence") or {}).get("passed")),"first_failed_gate":(x.get("evidence") or {}).get("first_failed_gate"),"summary":deepcopy((x.get("evidence") or {}).get("summary") or {}),"combinations":int((x.get("evidence") or {}).get("combinations",0) or 0)} for x in seed_rows]},
        "methodology_audit":{"schema":"CP_CPCV_SEED_METHODOLOGY_AUDIT_V2","same_splits_across_seeds":True,"same_take_threshold_across_seeds":True,"same_candidate_params_across_seeds":True,"only_training_seed_changes":True,"base_methodology":deepcopy(base.get("methodology_audit") or {})},
        "gates":gates,"paths":deepcopy(base.get("paths") or []),"terminology":base.get("terminology","COMBINATORIAL_PURGED_SPLITS"),
        "pbo_group_expectancy_r":pbo_groups,
    }


def run_cpcv_qualification(factory_dir, config_path, progress: ProgressCallback = None, llm_api_key: str | None = None) -> dict:
    """Mandatory canonical CPCV over the immutable Discovery Pool.

    Authority: exact 6 groups / 2 test groups / 15 legal purged+embargoed splits.
    Temporal/hybrid candidates require progressive 42→11→77 and all fixed seeds PASS.
    The frozen Discovery Pool is never mutated by this stage.
    """
    fd=Path(factory_dir); fm=_read(fd/"factory_manifest.json",{}); cfg=load_cfg(config_path)
    pool=_read(fd/"candidate_pool.json",[])
    if fm.get("status") != "DISCOVERY_POOL_READY" or not pool:
        raise RuntimeError("CPCV fail-closed: frozen WFA-qualified Discovery pool belum READY")
    if bool(fm.get("cpcv_opened")):
        raise RuntimeError("CPCV qualification sudah terminal untuk Factory ini")
    draw=read_csv_auto(fd/"discovery_immutable.csv")
    if draw.empty: raise RuntimeError("CPCV Discovery snapshot kosong")
    # Re-resolve canonical geometry from the immutable Discovery dataset. This makes a
    # safe v1.4.5/v1.4.6 -> v1.4.7 inherited recovery independent of stale runtime cfg.
    cfg,_canonical_strategy_geometry=synchronize_cfg_with_dataset_geometry(cfg,draw)
    temporal_authority=_assert_temporal_leakage_guard(cfg,require_embargo=True)
    dcontract=fm.get("discovery_stage_contract") if isinstance(fm.get("discovery_stage_contract"),dict) else None
    if not dcontract:
        raise RuntimeError("CPCV fail-closed: Discovery stage contract missing")
    current_scientific=_critical_scientific_contract(cfg)
    if dcontract.get("scientific_contract") != current_scientific:
        if not contracts_equal_except_strategy_geometry(dcontract.get("scientific_contract") or {},current_scientific):
            raise RuntimeError("CPCV fail-closed: scientific config drift after Discovery")
        progress_authority=cpcv_progress_authority(fd)
        if progress_authority.get("committed"):
            raise RuntimeError("INHERITED_V147_CPCV_PROGRESS_COMMITTED_FAIL_CLOSED: cannot migrate stale Discovery geometry contract")
        proofs=prove_pool_full_wfa_geometry(fd,pool,cfg)
        old_contract=deepcopy(dcontract); old_seal=_read(fd/"discovery_terminal_seal.json",{})
        dcontract=deepcopy(dcontract); dcontract["scientific_contract"]=current_scientific; dcontract["temporal_index"]=temporal_authority
        dcontract["inherited_v147_geometry_handoff"]={"authority":"SOURCE_FULL_WFA_RUN_CONFIG_PROOF","candidate_count":len(proofs),"candidate_pool_sha256":_sha(fd/"candidate_pool.json")}
        discovery_seal=_stage_seal(fd,"DISCOVERY",contract=dcontract,files=["candidate_pool.json","discovery_immutable.csv","tournament_immutable.csv","forward_refit_history.csv"])
        fm["discovery_stage_contract"]=dcontract; fm["discovery_stage_contract_hash"]=_stable_hash(dcontract)
        fm["discovery_terminal_seal_hash"]=discovery_seal["seal_hash"]
        migration={"schema":"MAX_MTF_V201_INHERITED_V147_GEOMETRY_HANDOFF_V1","status":"MIGRATED_WITH_SOURCE_WFA_PROOF","candidate_pool_sha256":_sha(fd/"candidate_pool.json"),"before_contract":old_contract,"before_seal":old_seal,"after_contract":dcontract,"after_seal_hash":discovery_seal["seal_hash"],"candidate_source_proofs":proofs,"cpcv_progress_authority":progress_authority,"created_utc":datetime.now(timezone.utc).isoformat()}
        _write(fd/"inherited_v147_strategy_geometry_handoff.json",migration); fm["inherited_v147_strategy_geometry_handoff_file"]="inherited_v147_strategy_geometry_handoff.json"; _write(fd/"factory_manifest.json",fm)
    else:
        discovery_seal=_verify_stage_seal(fd,"DISCOVERY",expected=dcontract)
    # CPCV is mandatory and methodologically fixed by Owner contract.
    split=cfg.get("split") or {}; fc=cfg.get("champion_factory") or {}; ccfg_stage=fc.get("cpcv_stage") or {}
    if not bool(split.get("cpcv_enabled",True)) or not bool(ccfg_stage.get("enabled",True)):
        raise RuntimeError("CPCV_MANDATORY_EXACT: CPCV cannot be disabled")
    if (int(split.get("cpcv_groups",6)),int(split.get("cpcv_test_groups",2)),int(split.get("cpcv_max_combinations",15))) != (6,2,15):
        raise RuntimeError("CPCV_MANDATORY_EXACT: expected 6 groups / 2 test groups / 15 combinations")
    temporal_contract=temporal_authority
    target_survivors=max(1,int(ccfg_stage.get("target_survivors",3)))
    min_survivors=max(1,int(ccfg_stage.get("minimum_survivors_to_tournament",1)))
    batch=max(1,int(ccfg_stage.get("finalist_batch_size",3)))
    cpcv_profile=gate_profile(cfg,"cpcv")
    pbo_enabled=bool(cpcv_profile.get("pbo_enabled",False))
    pbo_min_candidates=max(4,int(cpcv_profile.get("pbo_min_candidates",4) or 4))
    pbo_max=float(cpcv_profile.get("pbo_max",0.20))
    max_finalists=max(1,min(len(pool),int(ccfg_stage.get("max_finalists",len(pool)) or len(pool))))
    stage_contract={
        "schema":"MAX_CPCV_STAGE_CONTRACT_V1",
        "upstream_discovery_seal_hash":discovery_seal.get("seal_hash"),
        "scientific_contract":_critical_scientific_contract(cfg),
        "methodology":{"groups":6,"test_groups":2,"combinations":15,"purge_bars":int(temporal_contract["purge_bars"]),"embargo_bars":int(temporal_contract["embargo_bars"]),"label_horizon_bars":int(temporal_contract["label_horizon_bars"])},
        "temporal_seed_policy":{"temporal_or_hybrid":[42,11,77],"tree":"CONFIGURED_BASE_SEED","all_required_pass":True},
        "pbo_policy":{"enabled":pbo_enabled,"max":pbo_max,"minimum_candidates":pbo_min_candidates,"matrix":"CANDIDATE_X_6_CPCV_GROUP_MEDIAN_OOS_EXPECTANCY"},
        "target_survivors":target_survivors,"minimum_survivors_to_tournament":min_survivors,"max_finalists":max_finalists,
        "candidate_pool_sha256":_sha(fd/"candidate_pool.json"),
        "discovery_snapshot_sha256":_sha(fd/"discovery_immutable.csv"),
    }
    stage_hash=_stable_hash(stage_contract)

    plan_path=fd/"cpcv_finalist_plan.json"; plan=_read(plan_path,{})
    if plan and str(plan.get("stage_contract_hash") or "") != stage_hash:
        archive_uncommitted_cpcv_surfaces(fd,"STALE_PRE_V147_CPCV_PLAN_STAGE_CONTRACT")
        plan={}
    if not plan:
        ranked=sorted(pool,key=lambda c:float((c.get("discovery_metrics") or {}).get("selection_score",-1e99)),reverse=True)
        finalists=[str(c.get("pool_id")) for c in ranked[:max_finalists]]
        plan={"schema":"CP_CPCV_FINALIST_PLAN_V3","stage_contract_hash":stage_hash,"ranking_authority":"WFA_OOF_SELECTION_SCORE_ONLY","target_survivors":target_survivors,
              "minimum_survivors_to_tournament":min_survivors,"finalist_batch_size":batch,"max_finalists":max_finalists,
              "terminology":"COMBINATORIAL_PURGED_SPLITS","finalist_pool_ids":finalists,"created_utc":datetime.now(timezone.utc).isoformat()}
        _write(plan_path,plan)
    finalists=list(plan.get("finalist_pool_ids") or [])
    by_id={str(c.get("pool_id")):c for c in pool}

    progress_path=fd/"cpcv_qualification_progress.json"; state=_read(progress_path,{})
    if state and str(state.get("stage_contract_hash") or "") != stage_hash:
        pa=cpcv_progress_authority(fd)
        if pa.get("committed"):
            raise RuntimeError("INHERITED_V147_CPCV_PROGRESS_COMMITTED_FAIL_CLOSED: progress belongs to another contract")
        archive_uncommitted_cpcv_surfaces(fd,"STALE_PRE_V147_CPCV_PROGRESS_STAGE_CONTRACT")
        _write(plan_path,plan)
        state={}
    rows=list(state.get("rows") or []); survivors=list(state.get("survivors") or [])
    done={str(r.get("pool_id")) for r in rows}
    # Resume rows must remain exact prefixes of immutable source candidates.
    for row in rows:
        src=by_id.get(str(row.get("pool_id")))
        if src is None: raise RuntimeError("CPCV resume rejected: candidate missing from immutable Pool")
        _assert_same_candidate(src,row,"CPCV_RESUME")
        planned=_cpcv_seed_list(_candidate_cfg(cfg,src),str(src.get("family")))
        completed=list(((row.get("evidence") or {}).get("seed_confirmation") or {}).get("seed_results") or [])
        got=[int(x.get("seed")) for x in completed if isinstance(x,dict) and x.get("seed") is not None]
        if got and got != planned[:len(got)]:
            raise RuntimeError("CPCV resume rejected: non-canonical seed prefix")

    if _sha(fd/"candidate_pool.json") != stage_contract["candidate_pool_sha256"] or _sha(fd/"discovery_immutable.csv") != stage_contract["discovery_snapshot_sha256"]:
        raise RuntimeError("CPCV input authority drift")

    for i,pool_id in enumerate(finalists,1):
        if len(survivors)>=target_survivors and (not pbo_enabled or len(rows)>=pbo_min_candidates): break
        if pool_id in done: continue
        c=by_id.get(pool_id)
        if not c: raise RuntimeError(f"CPCV finalist hilang dari frozen pool: {pool_id}")
        # Independent Full-WFA revalidation from evidence frozen in candidate_pool.json.
        wfa=c.get("wfa_evidence") if isinstance(c.get("wfa_evidence"),dict) else {}
        if not bool((c.get("discovery_acceptance") or {}).get("passed")) or not bool(wfa.get("cv_gate_pass")):
            raise RuntimeError(f"CPCV source {pool_id} is not Full-WFA PASS")
        ccfg=_candidate_cfg(cfg,c)
        if not bool(walk_forward_acceptance(wfa,ccfg).get("passed")):
            raise RuntimeError(f"CPCV source {pool_id} no longer satisfies frozen Full-WFA acceptance")
        _write(fd/"cpcv_live.json",{"schema":"CP_CPCV_LIVE_V2","status":"RUNNING","pool_id":pool_id,"rank":i,"candidate":c.get("name"),"family":c.get("family"),"split_completed":0,"split_total":15,"survivors":len(survivors),"target_survivors":target_survivors,"updated_utc":datetime.now(timezone.utc).isoformat()})
        _write(fd/"cpcv_live_split_results.json",{"schema":"CP_CPCV_LIVE_SPLITS_V2","pool_id":pool_id,"candidate":c.get("name"),"family":c.get("family"),"rows":[],"updated_utc":datetime.now(timezone.utc).isoformat()})
        _emit(progress,"cpcv_finalist",len(rows),len(finalists),f"CPCV finalist {i}/{len(finalists)} · {pool_id} · survivors {len(survivors)}/{target_survivors}",pool_id=pool_id,finalist_rank=i,survivors=len(survivors),target_survivors=target_survivors)
        cdf=build_labels(draw,ccfg); spec=CandidateSpec(str(c["family"]),str(c["name"]),dict(c["params"]))
        if cdf.empty: raise RuntimeError(f"CPCV candidate {pool_id} labeled dataset kosong")
        policy=deepcopy(c.get("decision_policy") or {}) or None
        if policy and str(policy.get("schema") or POLICY_SCHEMA) != POLICY_SCHEMA:
            raise RuntimeError(f"CPCV {pool_id}: unsupported policy schema")
        seeds=_cpcv_seed_list(ccfg,spec.family); seed_rows=[]
        def _live_cpcv(event):
            x=dict(event or {})
            split_completed=int(x.get("split_completed",x.get("current",0)) or 0); split_total=int(x.get("split_total",x.get("total",15)) or 15)
            live={"schema":"CP_CPCV_LIVE_V2","status":"RUNNING","pool_id":pool_id,"rank":i,"candidate":c.get("name"),"family":c.get("family"),
                  "split_completed":split_completed,"split_no":x.get("split_no"),"split_total":split_total,"test_groups":x.get("test_groups"),"phase":x.get("phase"),"message":x.get("message"),
                  "training_seed":x.get("training_seed"),"seed_index":x.get("seed_index"),"seed_total":x.get("seed_total"),
                  "profit_factor":x.get("profit_factor"),"expectancy_r":x.get("expectancy_r"),"max_drawdown_r":x.get("max_drawdown_r"),"recovery_factor":x.get("recovery_factor"),"trades":x.get("trades"),
                  "survivors":len(survivors),"target_survivors":target_survivors,"updated_utc":datetime.now(timezone.utc).isoformat()}
            _write(fd/"cpcv_live.json",live)
            if str(x.get("phase") or "")=="split_done":
                lp=fd/"cpcv_live_split_results.json"
                ls=_read(lp,{"schema":"CP_CPCV_LIVE_SPLITS_V2","pool_id":pool_id,"candidate":c.get("name"),"family":c.get("family"),"rows":[]})
                seed_key=int(x.get("training_seed",0) or 0); split_key=int(x.get("split_no",0) or 0)
                lrows=[r for r in (ls.get("rows") or []) if (int((r or {}).get("training_seed",0) or 0),int((r or {}).get("split",0) or 0))!=(seed_key,split_key)]
                lrows.append({"training_seed":seed_key,"seed_index":x.get("seed_index"),"seed_total":x.get("seed_total"),"split":split_key,"test_groups":list(x.get("test_groups") or []),"profit_factor":x.get("profit_factor"),"expectancy_r":x.get("expectancy_r"),"max_drawdown_r":x.get("max_drawdown_r"),"recovery_factor":x.get("recovery_factor"),"trades":x.get("trades"),"completed_utc":datetime.now(timezone.utc).isoformat()})
                ls.update({"rows":sorted(lrows,key=lambda r:(int(r.get("seed_index",0) or 0),int(r.get("split",0) or 0))),"updated_utc":datetime.now(timezone.utc).isoformat()})
                _write(lp,ls)
            if progress: progress(x)
        for seed_idx,seed in enumerate(seeds,1):
            seed_cfg=deepcopy(ccfg); seed_cfg["seed"]=int(seed)
            def _seed_live(event,_seed=seed,_seed_idx=seed_idx):
                x=dict(event or {}); x["training_seed"]=int(_seed); x["seed_index"]=_seed_idx; x["seed_total"]=len(seeds)
                if x.get("message"): x["message"]=f"Seed {_seed} [{_seed_idx}/{len(seeds)}] · {x['message']}"
                _live_cpcv(x)
            sev=candidate_cpcv(spec,cdf,seed_cfg,float(c.get("take_threshold",0.65)),progress=_seed_live,decision_policy=policy)
            if int(sev.get("combinations",0) or 0)!=15:
                raise RuntimeError(f"CPCV {pool_id}: non-canonical split count")
            seed_rows.append({"seed":int(seed),"evidence":sev})
            if not bool(sev.get("passed")): break
        ev=_aggregate_seed_cpcv(seed_rows,seeds)
        row={**_candidate_identity(c),"rank":i,"passed":bool(ev.get("passed")),"first_failed_gate":ev.get("first_failed_gate"),"reasons":list(ev.get("reasons") or []),"summary":dict(ev.get("summary") or {}),"evidence":ev}
        rows.append(row); done.add(pool_id)
        if row["passed"]:
            frozen=deepcopy(_candidate_identity(c)); frozen["cpcv"]={k:deepcopy(ev.get(k)) for k in ("schema","passed","first_failed_gate","reasons","summary","groups","test_groups","purge_bars","embargo_bars","combinations","seed_confirmation","policy_schema","decision_policy")}; frozen["cpcv_frozen_utc"]=datetime.now(timezone.utc).isoformat(); survivors.append(frozen)
        _write(progress_path,{"schema":"CP_CPCV_QUALIFICATION_PROGRESS_V3","stage_contract_hash":stage_hash,"rows":rows,"survivors":survivors,"tested":len(rows),"pass":len(survivors),"fail":sum(not bool(r.get("passed")) for r in rows),"updated_utc":datetime.now(timezone.utc).isoformat()})
        topo=cpcv_failure_topology(rows,cfg); _write(fd/"cpcv_failure_topology.json",topo)
        if i % batch == 0 and len(survivors)>=target_survivors and (not pbo_enabled or len(rows)>=pbo_min_candidates): break

    pbo=compute_cpcv_pbo(rows,groups=6,min_candidates=pbo_min_candidates)
    pbo_gate={"enabled":pbo_enabled,"threshold_max":pbo_max,**pbo}
    if pbo_enabled:
        pbo_gate["passed"]=bool(pbo.get("status")=="COMPUTED" and float(pbo.get("pbo",1.0))<=pbo_max)
        if not pbo_gate["passed"]:
            survivors=[]
    else:
        pbo_gate["passed"]=None

    topo=cpcv_failure_topology(rows,cfg); _write(fd/"cpcv_failure_topology.json",topo)
    evidence={"schema":"CP_CPCV_QUALIFICATION_V4","authority":"MANDATORY_EXACT_6C2_15_AFTER_FROZEN_FULL_WFA_POOL","stage_contract":stage_contract,"stage_contract_hash":stage_hash,"terminology":"COMBINATORIAL_PURGED_SPLITS","plan":plan,"candidates_evaluated":len(rows),"survivor_count":len(survivors),"pbo":pbo_gate,"rows":rows}
    _write(fd/"cpcv_qualification_evidence.json",evidence)
    audits=[]
    for r in rows:
        a=((r.get("evidence") or {}).get("methodology_audit") or {})
        if a: audits.append({"pool_id":r.get("pool_id"),"family":r.get("family"),"name":r.get("name"),"passed":r.get("passed"),"audit":a})
    _write(fd/"cpcv_methodology_audit.json",{"schema":"CP_CPCV_FACTORY_METHODOLOGY_AUDIT_V3","authority_changed":bool(pbo_enabled),"pass_fail_authority":"MANDATORY_EXACT_CPCV_PLUS_OPTIONAL_CROSS_STRATEGY_PBO","candidate_count":len(audits),"pbo":pbo_gate,"candidates":audits,"created_utc":datetime.now(timezone.utc).isoformat()})
    if len(survivors)>=min_survivors:
        status="CPCV_SURVIVORS_READY"; _write(fd/"cpcv_survivors.json",survivors)
    else:
        status="CPCV_NO_SURVIVOR"; _record_downstream_failure(fd,"CPCV",{"finalists_evaluated":len(rows),"survivors":0,"failure_topology":topo,"pbo":pbo_gate})
    seal_files=["cpcv_qualification_evidence.json","cpcv_methodology_audit.json","cpcv_finalist_plan.json"] + (["cpcv_survivors.json"] if survivors else [])
    seal=_stage_seal(fd,"CPCV",contract=stage_contract,files=seal_files)
    decisive_outcomes=_resolve_committed_hypotheses(fd,"CPCV",status,rows)
    scientist_entry=_stage_scientist_and_feedback(fd,cfg,"CPCV",status,topo,rows,llm_api_key=llm_api_key,learning_allowed=(status=="CPCV_NO_SURVIVOR"))
    fm.update({"status":status,"stage":"CPCV","cpcv_opened":True,"cpcv":{"method":"MANDATORY_EXACT_6C2_15","terminology":"COMBINATORIAL_PURGED_SPLITS","target_survivors":target_survivors,
               "minimum_survivors_to_tournament":min_survivors,"max_finalists":max_finalists,"evaluated":len(rows),"survivors":len(survivors),"pbo":pbo_gate,"plan_file":"cpcv_finalist_plan.json","evidence_file":"cpcv_qualification_evidence.json","failure_topology_file":"cpcv_failure_topology.json","methodology_audit_file":"cpcv_methodology_audit.json","stage_contract":stage_contract,"stage_contract_hash":stage_hash,"terminal_seal_file":"cpcv_terminal_seal.json","terminal_seal_hash":seal.get("seal_hash"),"hypothesis_decisive_outcomes":len(decisive_outcomes)},
               "cpcv_survivors_file":"cpcv_survivors.json" if survivors else None,"stage_scientist_journal":"stage_scientist_journal.json",
               "research_learning_ready":bool(scientist_entry.get("learning_ready")) if status=="CPCV_NO_SURVIVOR" else False,
               "research_feedback_exhausted":bool(scientist_entry.get("feedback_exhausted")),
               "research_restart_required":status=="CPCV_NO_SURVIVOR" and bool(scientist_entry.get("learning_ready")) and not bool(scientist_entry.get("feedback_exhausted")),
               "next_required":"RUN_TOURNAMENT" if status=="CPCV_SURVIVORS_READY" else ("STOP_RESEARCH_FEEDBACK_BUDGET" if scientist_entry.get("feedback_exhausted") else ("START_NEW_DISCOVERY_WITH_CPCV_LEARNING" if scientist_entry.get("learning_ready") else "WAIT_SCIENTIST_REVIEW"))})
    _write(fd/"factory_manifest.json",fm)
    _emit(progress,"factory_done",1,1,f"{status} · CPCV survivors {len(survivors)}/{len(rows)} finalists evaluated",scientist_update=scientist_entry)
    return {"factory":str(fd),"status":status,"survivors":len(survivors),"evaluated":len(rows),"manifest":fm,"scientist":scientist_entry}

def run_tournament(factory_dir, master_csv, config_path, tournament_from=None, tournament_to=None, progress: ProgressCallback = None, llm_api_key: str | None = None) -> dict:
    fd=Path(factory_dir); fm=_read(fd/"factory_manifest.json",{}); pool=_read(fd/"cpcv_survivors.json",[]); cfg=load_cfg(config_path)
    if fm.get("status") != "CPCV_SURVIVORS_READY" or not pool:
        raise RuntimeError("Tournament fail-closed: CPCV finalist survivors belum READY")
    cpcv_meta=fm.get("cpcv") if isinstance(fm.get("cpcv"),dict) else {}
    cpcv_contract=cpcv_meta.get("stage_contract") if isinstance(cpcv_meta.get("stage_contract"),dict) else None
    if not cpcv_contract: raise RuntimeError("Tournament fail-closed: CPCV stage contract missing")
    cpcv_seal=_verify_stage_seal(fd,"CPCV",expected=cpcv_contract)
    dcontract=fm.get("discovery_stage_contract") or {}
    if dcontract.get("scientific_contract") != _critical_scientific_contract(cfg):
        raise RuntimeError("Tournament fail-closed: scientific config drift")
    tc=fm.get("tournament_contract") or {}; tournament_from=tc.get("from") or tournament_from; tournament_to=tc.get("to") or tournament_to
    if not tournament_from or not tournament_to: raise RuntimeError("Tournament contract tidak ditemukan")
    if fm.get("tournament_opened"): raise RuntimeError("Tournament sudah pernah dibuka untuk factory ini")
    tour=fd/str(tc.get("snapshot") or "tournament_immutable.csv")
    expected_tour=str(tc.get("snapshot_sha256") or dcontract.get("frozen_tournament_sha256") or "")
    if not tour.exists() or not expected_tour or _sha(tour)!=expected_tour:
        raise RuntimeError("Tournament fail-closed: frozen Tournament snapshot drift")
    # master is no longer an input authority for Tournament; the pre-frozen snapshot is.
    plan=resolve_compute_plan(cfg); cfg["resolved_compute"]=plan; _write(fd/"tournament_compute_plan.json",plan)
    disc=fd/"discovery_immutable.csv"; draw=read_csv_auto(disc); traw=read_csv_auto(tour)
    if draw.empty or traw.empty: raise RuntimeError("Discovery/Tournament dataset kosong")
    ident=_dataset_identity(tour); sample=auto_trade_sample(ident["period"],tournament_from,tournament_to,cfg,"TOURNAMENT")
    cpcv_ev=_read(fd/"cpcv_qualification_evidence.json",{}); source_rows={str(r.get("pool_id")):r for r in (cpcv_ev.get("rows") or []) if isinstance(r,dict) and bool(r.get("passed"))}
    stage_contract={"schema":"MAX_TOURNAMENT_STAGE_CONTRACT_V1","upstream_cpcv_seal_hash":cpcv_seal.get("seal_hash"),"scientific_contract":_critical_scientific_contract(cfg),"tournament_snapshot_sha256":expected_tour,"discovery_snapshot_sha256":_sha(disc),"survivor_ids":[str(c.get("pool_id")) for c in pool]}
    rows=[]; trade_map={}
    for i,c in enumerate(pool,1):
        src=source_rows.get(str(c.get("pool_id")))
        if src is None: raise RuntimeError(f"Tournament candidate {c.get('pool_id')} missing from CPCV PASS evidence")
        _assert_same_candidate(src,c,"TOURNAMENT_INPUT")
        _emit(progress,"factory_tournament",i-1,len(pool),f"Tournament {i}/{len(pool)} · {c['pool_id']} · {c['family']}")
        ccfg=_candidate_cfg(cfg,c); ccfg["resolved_compute"]=plan
        dtrain=build_labels(draw,ccfg); tdf=build_labels(traw,ccfg)
        if dtrain.empty or tdf.empty: raise RuntimeError(f"Candidate {c['pool_id']} labeled dataset kosong")
        spec=CandidateSpec(c["family"],c["name"],dict(c["params"])); model,td,Xhist,mem=_fit_candidate(spec,dtrain,ccfg)
        Xt=feature_matrix(tdf,ccfg); p=np.asarray(predict_model_proba(model,spec.family,Xhist,Xt),float)
        threshold=float(c.get("take_threshold",0.65)); policy=deepcopy(c.get("decision_policy") or {}) or None
        act,r=_strategy_outcomes(p,tdf,ccfg,threshold,policy); take=(act!=0); trades=np.asarray(r[take],float)
        timestamps=tdf.loc[take,"signal_time"].to_numpy() if "signal_time" in tdf.columns else None
        evaluation_start=evaluation_end=None
        if "signal_time" in tdf.columns and len(tdf):
            ets=pd.to_datetime(tdf["signal_time"],errors="coerce").dropna()
            if len(ets): evaluation_start=ets.min(); evaluation_end=ets.max()
        tr=metrics_from_trades(trades,n_rows=len(tdf),take_threshold=(float(policy.get("take_threshold",threshold)) if policy else threshold),timestamps=timestamps,multiple_testing_trials=dsr_trial_count(ccfg),benchmark_sharpe=psr_benchmark(ccfg),evaluation_start=evaluation_start,evaluation_end=evaluation_end)
        if policy:
            temp=policy_temporal_stability(p,tdf,ccfg,policy); reg=policy_regime_diagnostics(p,tdf,ccfg,policy); stress=policy_stress_diagnostics(p,tdf,ccfg,policy)
        else:
            temp=temporal_stability(p,tdf,ccfg,threshold); reg=regime_diagnostics(p,tdf,ccfg,threshold); stress=stress_diagnostics(p,tdf,ccfg,threshold)
        yearly={}; years=pd.to_datetime(tdf["signal_time"],errors="coerce").dt.year.to_numpy()
        for y in sorted(set(int(x) for x in years if not pd.isna(x))):
            mask=np.where(years==y)[0]
            yearly[str(y)]=_strategy_metrics(p[mask],tdf.iloc[mask],ccfg,threshold,policy) if len(mask) else {}
        enriched=dict(tr); enriched.update({"positive_month_ratio":float(temp.get("positive_month_ratio",0)),"positive_quarter_ratio":float(temp.get("positive_quarter_ratio",0)),"regime_concentration":float(reg.get("dominant_positive_regime_share",1)),"stress_x1_50_expectancy_r":float((((stress.get("spread") or {}).get("spread_x1.50") or {}).get("expectancy_r",-999))),"auto_min_trades":int(sample["minimum_trades"])})
        acc=_tournament_acceptance(enriched,ccfg,sample,yearly)
        worst_year=min((float(v.get("expectancy_r",-999)) for v in yearly.values()),default=-999)
        rank=[1 if acc["passed"] else 0,worst_year,float(enriched.get("recovery_factor",-999)),float(enriched.get("expectancy_r",-999)),float(enriched.get("profit_factor",0)),-float(enriched.get("max_drawdown_r",999999))]
        row={**_candidate_identity(c),"training_memory":mem,"model_training_diagnostics":model_training_diagnostics(model),"metrics":enriched,"yearly":yearly,"acceptance":acc,"rank_key":rank}
        rows.append(row); trade_map[str(c["pool_id"])]=[float(x) for x in trades.tolist()]
    rows.sort(key=lambda r:tuple(r["rank_key"]),reverse=True); _write(fd/"tournament_leaderboard.json",rows); _write(fd/"tournament_trade_returns.json",trade_map)
    survivors=[r for r in rows if bool((r.get("acceptance") or {}).get("passed"))]
    if survivors:
        status="TOURNAMENT_SURVIVORS_READY"; frozen=[]
        for r in survivors:
            z={**_candidate_identity(r),"metrics":deepcopy(r.get("metrics")),"yearly":deepcopy(r.get("yearly")),"acceptance":deepcopy(r.get("acceptance")),"frozen_utc":datetime.now(timezone.utc).isoformat(),"tournament_snapshot_sha256":expected_tour}; frozen.append(z)
        _write(fd/"tournament_survivors.json",frozen)
    else:
        status="TOURNAMENT_NO_SURVIVOR"; _record_downstream_failure(fd,"TOURNAMENT",{"candidates":len(pool),"survivors":0,"first_failed_gates":[(r.get("acceptance") or {}).get("first_failed_gate") for r in rows]})
    topology=generic_stage_topology("TOURNAMENT",rows); _write(fd/"tournament_failure_topology.json",topology)
    seal_files=["tournament_leaderboard.json","tournament_trade_returns.json","tournament_failure_topology.json"]+(["tournament_survivors.json"] if survivors else [])
    seal=_stage_seal(fd,"TOURNAMENT",contract=stage_contract,files=seal_files)
    decisive_outcomes=_resolve_committed_hypotheses(fd,"TOURNAMENT",status,rows)
    scientist_entry=_stage_scientist_and_feedback(fd,cfg,"TOURNAMENT",status,topology,rows,llm_api_key=llm_api_key,learning_allowed=(status=="TOURNAMENT_NO_SURVIVOR"))
    fm.update({"status":status,"stage":"TOURNAMENT","tournament_opened":True,"tournament":{"from":str(tournament_from),"to":str(tournament_to),"snapshot":tour.name,"snapshot_sha256":expected_tour,"auto_trade_sample":sample,"survivor_count":len(survivors),"failure_topology_file":"tournament_failure_topology.json","stage_contract":stage_contract,"stage_contract_hash":_stable_hash(stage_contract),"terminal_seal_file":"tournament_terminal_seal.json","terminal_seal_hash":seal.get("seal_hash"),"hypothesis_decisive_outcomes":len(decisive_outcomes)},"tournament_survivors_file":"tournament_survivors.json" if survivors else None,"monte_carlo_opened":False,"research_learning_ready":bool(scientist_entry.get("learning_ready")) if status=="TOURNAMENT_NO_SURVIVOR" else False,"research_feedback_exhausted":bool(scientist_entry.get("feedback_exhausted")),"research_restart_required":status=="TOURNAMENT_NO_SURVIVOR" and bool(scientist_entry.get("learning_ready")) and not bool(scientist_entry.get("feedback_exhausted")),"next_required":(("STOP_RESEARCH_FEEDBACK_BUDGET" if scientist_entry.get("feedback_exhausted") else ("START_NEW_DISCOVERY_WITH_TOURNAMENT_LEARNING" if scientist_entry.get("learning_ready") else "WAIT_SCIENTIST_REVIEW")) if status=="TOURNAMENT_NO_SURVIVOR" else "RUN_MONTE_CARLO")})
    _write(fd/"factory_manifest.json",fm); _emit(progress,"factory_done",1,1,f"{status} · survivors {len(survivors)}/{len(pool)}",scientist_update=scientist_entry)
    return {"factory":str(fd),"status":status,"survivors":len(survivors),"manifest":fm,"scientist":scientist_entry}

def _mc_distribution(trades: np.ndarray, simulations: int, seed: int, chunk: int = 2000, ruin_floor_r: float = -20.0) -> dict:
    trades = np.asarray(trades, dtype=np.float64)
    if trades.ndim != 1 or not np.isfinite(trades).all():
        raise ValueError("Monte Carlo trade-return vector contains non-finite/corrupt values")
    n = len(trades)
    if n < 2:
        raise ValueError("Monte Carlo membutuhkan minimal 2 closed trades")
    rng = np.random.default_rng(int(seed)); pfs=[]; exps=[]; dds=[]; recs=[]; totals=[]; min_curves=[]
    left = int(simulations)
    while left > 0:
        k = min(int(chunk), left); idx = rng.integers(0, n, size=(k, n)); sims = trades[idx]
        pos = np.where(sims > 0, sims, 0.0).sum(axis=1); neg = -np.where(sims < 0, sims, 0.0).sum(axis=1)
        pf = np.divide(pos, neg, out=np.where(pos > 0, np.full(k, 999.0), np.zeros(k)), where=neg > 1e-12)
        exp = sims.mean(axis=1); total = sims.sum(axis=1); curve = np.cumsum(sims, axis=1); peak = np.maximum.accumulate(np.concatenate([np.zeros((k, 1)), curve], axis=1), axis=1)[:, 1:]
        dd = np.max(peak - curve, axis=1); rec = np.divide(total, dd, out=np.where(total > 0, np.full(k, 999.0), np.zeros(k)), where=dd > 1e-12)
        pfs.append(pf); exps.append(exp); dds.append(dd); recs.append(rec); totals.append(total); min_curves.append(np.min(curve,axis=1)); left -= k
    pf=np.concatenate(pfs); exp=np.concatenate(exps); dd=np.concatenate(dds); rec=np.concatenate(recs); total=np.concatenate(totals); min_curve=np.concatenate(min_curves)
    qlo=0.05; qhi=0.95
    robust = {"trades": int(n), "profit_factor": float(np.quantile(pf, qlo)), "expectancy_r": float(np.quantile(exp, qlo)), "max_drawdown_r": float(np.quantile(dd, qhi)), "recovery_factor": float(np.quantile(rec, qlo)), "total_r": float(np.quantile(total, qlo))}
    summary = {
        "method": "IID_BOOTSTRAP_WITH_REPLACEMENT", "simulations": int(simulations), "seed": int(seed), "trade_count": int(n),
        "robust_quantile": {"lower": qlo, "upper": qhi}, "robust_metrics": robust,
        "probabilities": {"loss": float(np.mean(total <= 0.0)), "ruin": float(np.mean(min_curve <= float(ruin_floor_r))), "survival": float(1.0 - np.mean(min_curve <= float(ruin_floor_r))), "ruin_floor_r": float(ruin_floor_r)},
        "distribution": {
            "profit_factor": {"p05": float(np.quantile(pf,.05)), "p50": float(np.quantile(pf,.50)), "p95": float(np.quantile(pf,.95))},
            "expectancy_r": {"p05": float(np.quantile(exp,.05)), "p50": float(np.quantile(exp,.50)), "p95": float(np.quantile(exp,.95))},
            "max_drawdown_r": {"p05": float(np.quantile(dd,.05)), "p50": float(np.quantile(dd,.50)), "p95": float(np.quantile(dd,.95))},
            "recovery_factor": {"p05": float(np.quantile(rec,.05)), "p50": float(np.quantile(rec,.50)), "p95": float(np.quantile(rec,.95))},
        },
    }
    return summary


def run_monte_carlo(factory_dir, config_path, progress: ProgressCallback = None, llm_api_key: str | None = None) -> dict:
    fd=Path(factory_dir); fm=_read(fd/"factory_manifest.json",{}); cfg=load_cfg(config_path)
    survivors=_read(fd/"tournament_survivors.json",[]); trades=_read(fd/"tournament_trade_returns.json",{})
    if fm.get("status") != "TOURNAMENT_SURVIVORS_READY" or not survivors:
        raise RuntimeError("Monte Carlo fail-closed: Tournament survivors belum READY")
    if fm.get("monte_carlo_opened"): raise RuntimeError("Monte Carlo sudah pernah dibuka untuk factory ini")
    tmeta=fm.get("tournament") if isinstance(fm.get("tournament"),dict) else {}; tcontract=tmeta.get("stage_contract") if isinstance(tmeta.get("stage_contract"),dict) else None
    if not tcontract: raise RuntimeError("Monte Carlo fail-closed: Tournament stage contract missing")
    tseal=_verify_stage_seal(fd,"TOURNAMENT",expected=tcontract)
    dcontract=fm.get("discovery_stage_contract") or {}
    if dcontract.get("scientific_contract") != _critical_scientific_contract(cfg): raise RuntimeError("Monte Carlo fail-closed: scientific config drift")
    expected_ids=[str(c.get("pool_id")) for c in survivors]
    if set(str(k) for k in trades.keys()) != set(expected_ids):
        raise RuntimeError("Monte Carlo fail-closed: survivor/trade-return set mismatch")
    leaderboard={str(r.get("pool_id")):r for r in _read(fd/"tournament_leaderboard.json",[]) if isinstance(r,dict) and bool((r.get("acceptance") or {}).get("passed"))}
    fc=cfg.get("champion_factory") or {}; simulations=int(fc.get("monte_carlo_simulations",10000))
    if simulations < 100: raise ValueError("Monte Carlo simulations minimal 100")
    base_seed=int(cfg.get("seed",42) or 42); sample=((fm.get("tournament") or {}).get("auto_trade_sample") or {})
    stage_contract={"schema":"MAX_MONTE_CARLO_STAGE_CONTRACT_V1","upstream_tournament_seal_hash":tseal.get("seal_hash"),"scientific_contract":_critical_scientific_contract(cfg),"simulations":simulations,"base_seed":base_seed,"method":"IID_BOOTSTRAP_WITH_REPLACEMENT","survivor_ids":expected_ids,"trade_returns_sha256":_sha(fd/"tournament_trade_returns.json")}
    rows=[]; passed=[]
    for i,c in enumerate(survivors,1):
        src=leaderboard.get(str(c.get("pool_id")))
        if src is None: raise RuntimeError(f"Monte Carlo source {c.get('pool_id')} missing from Tournament PASS leaderboard")
        _assert_same_candidate(src,c,"MONTE_CARLO_INPUT")
        arr=np.asarray(trades.get(str(c["pool_id"])),dtype=float)
        if arr.ndim!=1 or len(arr)<2 or not np.isfinite(arr).all(): raise RuntimeError(f"Monte Carlo corrupt trade-return vector: {c['pool_id']}")
        expected_trades=int((c.get("metrics") or {}).get("trades",-1) or -1)
        if expected_trades != len(arr): raise RuntimeError(f"Monte Carlo trade count mismatch for {c['pool_id']}: {len(arr)} != {expected_trades}")
        _emit(progress,"monte_carlo",i-1,len(survivors),f"Monte Carlo {i}/{len(survivors)} · {c['pool_id']} · {simulations:,} simulations")
        seed=base_seed+int(hashlib.sha256(str(c.get("fingerprint")).encode()).hexdigest()[:8],16)
        mc_profile=gate_profile(cfg,"monte_carlo")
        mc=_mc_distribution(arr,simulations,seed,ruin_floor_r=float(mc_profile.get("ruin_floor_r",-20.0))); robust=dict(mc["robust_metrics"]); robust["auto_min_trades"]=int(sample.get("minimum_trades",0) or 0)
        acc=monte_carlo_acceptance(mc,cfg)
        row={**_candidate_identity(c),"tournament_metrics":deepcopy(c.get("metrics")),"monte_carlo":mc,"acceptance":acc}
        rows.append(row)
        if acc.get("passed"): passed.append(row)
        _emit(progress,"monte_carlo",i,len(survivors),f"{c['pool_id']} · {'PASS' if acc.get('passed') else 'FAIL'} · PF p05 {robust['profit_factor']:.3f} · Exp p05 {robust['expectancy_r']:+.4f}R · DD p95 {robust['max_drawdown_r']:.2f}R")
    evidence={"schema":"CP_MONTE_CARLO_V2","stage_contract":stage_contract,"stage_contract_hash":_stable_hash(stage_contract),"simulation_count":simulations,"kpi_authority":"MAX_GATE_KPI_PROFILES_V1::MONTE_CARLO_KPI_V1","rows":rows}
    _write(fd/"monte_carlo_evidence.json",evidence)
    if passed:
        status="MONTE_CARLO_SURVIVORS_READY"; _write(fd/"monte_carlo_survivors.json",passed)
    else:
        status="MONTE_CARLO_NO_SURVIVOR"; _record_downstream_failure(fd,"MONTE_CARLO",{"survivors_in":len(survivors),"survivors_out":0,"simulations":simulations,"first_failed_gates":[(r.get("acceptance") or {}).get("first_failed_gate") for r in rows]})
    topology=generic_stage_topology("MONTE_CARLO",rows); _write(fd/"monte_carlo_failure_topology.json",topology)
    seal_files=["monte_carlo_evidence.json","monte_carlo_failure_topology.json"]+(["monte_carlo_survivors.json"] if passed else [])
    seal=_stage_seal(fd,"MONTE_CARLO",contract=stage_contract,files=seal_files)
    decisive_outcomes=_resolve_committed_hypotheses(fd,"MONTE_CARLO",status,rows)
    scientist_entry=_stage_scientist_and_feedback(fd,cfg,"MONTE_CARLO",status,topology,rows,llm_api_key=llm_api_key,learning_allowed=(status=="MONTE_CARLO_NO_SURVIVOR"))
    fm.update({"status":status,"stage":"MONTE_CARLO","monte_carlo_opened":True,"monte_carlo":{"simulations":simulations,"survivors_in":len(survivors),"survivors_out":len(passed),"evidence_file":"monte_carlo_evidence.json","failure_topology_file":"monte_carlo_failure_topology.json","stage_contract":stage_contract,"stage_contract_hash":_stable_hash(stage_contract),"terminal_seal_file":"monte_carlo_terminal_seal.json","terminal_seal_hash":seal.get("seal_hash"),"hypothesis_decisive_outcomes":len(decisive_outcomes)},"monte_carlo_survivors_file":"monte_carlo_survivors.json" if passed else None,"forward_opened":False,"research_learning_ready":bool(scientist_entry.get("learning_ready")) if status=="MONTE_CARLO_NO_SURVIVOR" else False,"research_feedback_exhausted":bool(scientist_entry.get("feedback_exhausted")),"research_restart_required":status=="MONTE_CARLO_NO_SURVIVOR" and bool(scientist_entry.get("learning_ready")) and not bool(scientist_entry.get("feedback_exhausted")),"next_required":(("STOP_RESEARCH_FEEDBACK_BUDGET" if scientist_entry.get("feedback_exhausted") else ("START_NEW_DISCOVERY_WITH_MONTE_CARLO_LEARNING" if scientist_entry.get("learning_ready") else "WAIT_SCIENTIST_REVIEW")) if status=="MONTE_CARLO_NO_SURVIVOR" else "RUN_FORWARD_CHAMPIONSHIP")})
    _write(fd/"factory_manifest.json",fm); _emit(progress,"factory_done",1,1,f"{status} · survivors {len(passed)}/{len(survivors)}",scientist_update=scientist_entry)
    return {"factory":str(fd),"status":status,"survivors":len(passed),"simulations":simulations,"manifest":fm,"scientist":scientist_entry}

def _resolve_forward_to(master: Path, contract: dict, requested=None) -> str:
    mode=str(contract.get("mode") or ("AUTO_NEWEST" if str(contract.get("to"))=="AUTO_NEWEST" else "FIXED")).upper()
    if mode=="AUTO_NEWEST":
        raw=read_csv_auto(master,usecols=["signal_time"]); newest=pd.to_datetime(raw["signal_time"],errors="coerce").max()
        if pd.isna(newest): raise RuntimeError("Forward tidak dapat menentukan newest signal_time")
        return str(newest.date())
    return str(contract.get("to") or requested)


def _e2e_forward_local_data_quality(master: Path, cfg: dict) -> dict | None:
    """Return deterministic local DQ evidence for the isolated Golden E2E lane only.

    Production research must never enter this path.  The E2E lane uses a synthetic
    CP32 dataset that deliberately has no broker authority; requiring MT5 broker
    reconciliation there would test the broker instead of the Research workflow.
    """
    e2e=dict((cfg.get("champion_factory") or {}).get("e2e_workflow_test") or {})
    if not bool(e2e.get("enabled")):
        return None
    if str(e2e.get("profile") or "") != "E2E_WORKFLOW_TEST_V1":
        raise RuntimeError("E2E_FORWARD_DQ_CONTRACT_INVALID: unexpected profile")
    if bool(e2e.get("production_evidence", False)):
        raise RuntimeError("E2E_FORWARD_DQ_CONTRACT_INVALID: production_evidence must be false")
    ctx=dict((cfg.get("agent") or {}).get("data_quality_context") or {})
    if ctx.get("e2e_only") is not True or str(ctx.get("authority") or "") != "SYNTHETIC_GOLDEN_CP32_WORKFLOW_ONLY_NOT_PRODUCTION_EVIDENCE":
        raise RuntimeError("E2E_FORWARD_DQ_CONTRACT_INVALID: E2E data-quality authority missing")
    if master.name != "CP32_E2E_GOLDEN.csv":
        raise RuntimeError("E2E_FORWARD_DQ_CONTRACT_INVALID: unexpected dataset filename")

    report=audit_dataset(master,broker_reconcile=False,use_cached_broker_proof=False)
    identity=dict(report.get("identity") or {})
    if str(identity.get("symbol") or "") != "E2E_XAUUSD":
        raise RuntimeError("E2E_FORWARD_DQ_CONTRACT_INVALID: unexpected synthetic symbol")
    reasons=[str(x) for x in (report.get("hard_reasons") or [])]
    observed=dict(report.get("observed_discontinuities") or {})
    if int(observed.get("count",0) or 0) != 0:
        reasons.append(f"E2E_OBSERVED_DISCONTINUITIES:{int(observed.get('count',0) or 0)}")
    if reasons:
        raise RuntimeError("FORWARD_DATA_QUALITY_BLOCKED: "+",".join(reasons))
    report["e2e_workflow_local_proof"]={
        "status":"PASS",
        "profile":"E2E_WORKFLOW_TEST_V1",
        "broker_reconciliation_required":False,
        "production_evidence":False,
        "authority":"LOCAL_SYNTHETIC_GOLDEN_CP32_ONLY",
    }
    return report


def run_forward_championship(factory_dir, master_csv, config_path, fresh_from=None, fresh_to=None, progress: ProgressCallback = None, llm_api_key: str | None = None) -> dict:
    fd=Path(factory_dir); fm=_read(fd/"factory_manifest.json",{}); cfg=load_cfg(config_path); candidates=_read(fd/"monte_carlo_survivors.json",[])
    allowed={"MONTE_CARLO_SURVIVORS_READY","FORWARD_INSUFFICIENT_SAMPLE"}
    if fm.get("status") not in allowed or not candidates:
        raise RuntimeError("Forward Championship fail-closed: Monte Carlo survivors belum READY atau championship sudah terminal")
    mcmeta=fm.get("monte_carlo") if isinstance(fm.get("monte_carlo"),dict) else {}; mccontract=mcmeta.get("stage_contract") if isinstance(mcmeta.get("stage_contract"),dict) else None
    if not mccontract: raise RuntimeError("Forward fail-closed: Monte Carlo stage contract missing")
    mcseal=_verify_stage_seal(fd,"MONTE_CARLO",expected=mccontract)
    dcontract=fm.get("discovery_stage_contract") or {}
    if dcontract.get("scientific_contract") != _critical_scientific_contract(cfg): raise RuntimeError("Forward fail-closed: scientific config drift")
    contract=fm.get("forward_contract") or {}
    declared_from=str(contract.get("from") or "")
    expected_from=str(((dcontract.get("windows") or {}).get("fresh") or [declared_from])[0])
    if not declared_from or declared_from != expected_from:
        raise RuntimeError("Forward fail-closed: predeclared Fresh boundary drift")
    if fresh_from is not None and str(fresh_from) != declared_from:
        raise RuntimeError("Forward fail-closed: caller attempted to move predeclared fresh_from")
    fresh_from=declared_from; master=Path(master_csv)
    hist=fd/str(contract.get("refit_history") or "forward_refit_history.csv")
    expected_hist=str(contract.get("refit_history_sha256") or dcontract.get("frozen_refit_history_sha256") or "")
    if not hist.exists() or not expected_hist or _sha(hist)!=expected_hist:
        raise RuntimeError("Forward fail-closed: frozen pre-Forward refit history drift")
    # Revalidate all committed checks before extending the locked OOS window.
    checks=list(fm.get("forward_checks") or [])
    for prev in checks:
        pc=prev.get("stage_contract") if isinstance(prev.get("stage_contract"),dict) else None
        if not pc: raise RuntimeError("Forward prior-check contract missing")
        _verify_stage_seal(fd,f"FORWARD_CHECK_{int(prev.get('check')):03d}",expected=pc)
    n=len(checks)+1
    # No new rows is a nonterminal maturity state, not an invalid range.
    times=read_csv_auto(master,usecols=["signal_time"]); newest=pd.to_datetime(times["signal_time"],errors="coerce").max()
    if pd.isna(newest): raise RuntimeError("Forward tidak dapat menentukan newest signal_time")
    if newest.date() < pd.Timestamp(fresh_from).date():
        fresh_to=str(newest.date()); raw_new=False
    else:
        fresh_to=_resolve_forward_to(master,contract,fresh_to); raw_new=True
    if checks and raw_new:
        prev_to=checks[-1].get("evaluated_to")
        if prev_to and pd.Timestamp(fresh_to)<=pd.Timestamp(prev_to):
            raise RuntimeError(f"Forward belum memiliki data baru setelah check terakhir {prev_to}")
    # Production Fresh data keeps exact physical/broker authority.  The isolated
    # synthetic Golden E2E lane uses deterministic local DQ evidence only; it must
    # never launch MT5 or masquerade as production broker proof.
    dq_report=None
    if raw_new:
        dq_report=_e2e_forward_local_data_quality(master,cfg)
        if dq_report is None:
            dq_report=audit_dataset(master,broker_reconcile=True); ready,reasons=research_readiness(dq_report)
            if not ready: raise RuntimeError("FORWARD_DATA_QUALITY_BLOCKED: "+",".join(reasons))
        did=dq_report.get("identity") or {}; baseid=((fm.get("discovery") or {}).get("identity") or {})
        if str(did.get("symbol"))!=str(baseid.get("symbol")) or int(did.get("period") or -1)!=int(baseid.get("period") or -2):
            raise RuntimeError("FORWARD_DATASET_IDENTITY_DRIFT")
    dq_file=f"forward_data_quality_{n:03d}.json"
    if dq_report is not None: _write(fd/dq_file,dq_report)
    plan=resolve_compute_plan(cfg); cfg["resolved_compute"]=plan; _write(fd/"forward_compute_plan.json",plan)
    forward=fd/f"forward_immutable_{n:03d}.csv"
    if raw_new:
        build_research_window_snapshot(master,fresh_from,fresh_to,forward)
        fraw=read_csv_auto(forward)
    else:
        fraw=pd.DataFrame()
    hraw=read_csv_auto(hist)
    if hraw.empty: raise RuntimeError("Forward refit-history dataset kosong")
    # Append-only OOS: every previously committed snapshot must be an exact row prefix.
    if checks and raw_new:
        prev=fd/str(checks[-1].get("snapshot")); praw=read_csv_auto(prev)
        if len(fraw)<len(praw) or list(fraw.columns)!=list(praw.columns) or not fraw.iloc[:len(praw)].reset_index(drop=True).equals(praw.reset_index(drop=True)):
            raise RuntimeError("FORWARD_APPEND_ONLY_VIOLATION: historical Fresh evidence changed/backfilled")
    # Determine maturity before fitting/scoring.
    rows=[]; fitted={}; all_sufficient=False; passed=[]
    source_mc={str(r.get("pool_id")):r for r in (_read(fd/"monte_carlo_evidence.json",{}).get("rows") or []) if isinstance(r,dict) and bool((r.get("acceptance") or {}).get("passed"))}
    if raw_new and not fraw.empty:
        ident=_dataset_identity(forward); sample=auto_trade_sample(ident["period"],fresh_from,fresh_to,cfg,"FRESH")
        for i,c in enumerate(candidates,1):
            src=source_mc.get(str(c.get("pool_id")))
            if src is None: raise RuntimeError(f"Forward source {c.get('pool_id')} missing from MC PASS evidence")
            _assert_same_candidate(src,c,"FORWARD_INPUT")
            _emit(progress,"forward_championship",i-1,len(candidates),f"Forward {i}/{len(candidates)} · {c['pool_id']} · {c['family']}")
            ccfg=_candidate_cfg(cfg,c); ccfg["resolved_compute"]=plan
            hdf=build_labels(hraw,ccfg); fdf=build_labels(fraw,ccfg)
            if hdf.empty: raise RuntimeError(f"Forward candidate {c['pool_id']} refit history labeled dataset kosong")
            if fdf.empty:
                continue
            spec=CandidateSpec(c["family"],c["name"],dict(c["params"])); model,td,Xhist,mem=_fit_candidate(spec,hdf,ccfg); Xf=feature_matrix(fdf,ccfg); proba=np.asarray(predict_model_proba(model,spec.family,Xhist,Xf),float)
            threshold=float(c.get("take_threshold",0.65)); policy=deepcopy(c.get("decision_policy") or {}) or None
            metrics=_strategy_metrics(proba,fdf,ccfg,threshold,policy); metrics["auto_min_trades"]=int(sample["minimum_trades"]); metrics["recovery_factor"]=float(metrics.get("recovery_factor",0.0))
            fitted[str(c["pool_id"])]={"model":model,"spec":spec,"Xhist":Xhist,"Xf":Xf,"cfg":ccfg,"history_sha256":expected_hist}
            sufficient=int(metrics.get("trades",0) or 0)>=int(sample["minimum_trades"])
            acc=fresh_forward_acceptance(metrics,ccfg) if sufficient else {"schema":"MAX_GATE_KPI_PROFILES_V1","profile":"FRESH_FORWARD_KPI_V1","stage":"FRESH_FORWARD","passed":False,"first_failed_gate":"FRESH_MIN_TRADES","reasons":["FRESH_MIN_TRADES"],"sample_state":"INSUFFICIENT_SAMPLE","gates":[]}
            rank=[1 if acc.get("passed") else 0,float(metrics.get("recovery_factor",-999)),float(metrics.get("expectancy_r",-999)),float(metrics.get("profit_factor",0)),-float(metrics.get("max_drawdown_r",999999))]
            rows.append({**_candidate_identity(c),"training_memory":mem,"model_training_diagnostics":model_training_diagnostics(model),"metrics":metrics,"acceptance":acc,"rank_key":rank})
        all_sufficient=bool(rows) and all(int((r.get("metrics") or {}).get("trades",0) or 0)>=int(sample["minimum_trades"]) for r in rows) and len(rows)==len(candidates)
        rows.sort(key=lambda r:tuple(r["rank_key"]),reverse=True); passed=[r for r in rows if bool((r.get("acceptance") or {}).get("passed"))]
    else:
        sample={"minimum_trades":0,"state":"NO_FRESH_ROWS"}
    terminal=False; champion=None; champion_seal=None
    if not raw_new or not all_sufficient:
        status="FORWARD_INSUFFICIENT_SAMPLE"
    elif passed:
        status="FACTORY_WINNER"; terminal=True; w=passed[0]; champion={**_candidate_identity(w),"metrics":deepcopy(w.get("metrics")),"acceptance":deepcopy(w.get("acceptance"))}
        champion["selected_utc"]=datetime.now(timezone.utc).isoformat(); champion["forward_snapshot_sha256"]=_sha(forward); champion["refit_history_sha256"]=expected_hist
        runtime_dir=fd/"champion_runtime"; runtime_dir.mkdir(exist_ok=True); fit=fitted.get(str(w.get("pool_id")))
        if fit is None: raise RuntimeError("Champion ONNX export failed: fitted winner object missing")
        try:
            from models.onnx_export import export_tabular, verify_onnx, export_hybrid, verify_hybrid_onnx, verify_onnx_with_context
            model=fit["model"]; spec=fit["spec"]; Xhist=fit["Xhist"]; Xf=fit["Xf"]
            if is_hybrid_family(spec.family):
                paths=export_hybrid(model,runtime_dir,prefix="champion",n_features=32); parity=verify_hybrid_onnx(paths,model,Xhist,Xf,max_rows=1000,n_features=32)
                artifacts={"temporal_onnx":str(Path(paths["temporal"]).name),"policy_model_onnx":str(Path(paths["policy"]).name),"temporal_sha256":_sha(Path(paths["temporal"])),"policy_model_sha256":_sha(Path(paths["policy"]))}
            else:
                op=export_tabular(model,spec.family,runtime_dir/"champion.onnx",32); parity=verify_onnx_with_context(op,model,Xhist,Xf,max_rows=1000,n_features=32) if (family_spec(spec.family) or {}).get("role")=="temporal" else verify_onnx(op,model,Xf,max_rows=1000,n_features=32)
                artifacts={"onnx":str(Path(op).name),"onnx_sha256":_sha(Path(op))}
            max_err=float(parity.get("max_abs_error",999)); tol=float((cfg.get("acceptance") or {}).get("max_onnx_abs_error",1e-4))
            if max_err>tol: raise RuntimeError(f"Champion ONNX parity {max_err} > {tol}")
            policy=deepcopy(w.get("decision_policy") or {}) or None
            if policy:
                pol_path=write_policy_csv(runtime_dir/"decision_policy.csv",policy); artifacts["decision_policy"]="decision_policy.csv"; artifacts["decision_policy_sha256"]=_sha(pol_path)
            runtime={"schema":"CP_CHAMPION_RUNTIME_V2","family":spec.family,"candidate_identity":_candidate_identity(w),"feature_contract":CONTRACT_ID,"feature_count":len(FEATURES),"feature_order":list(FEATURES),"class_order":["SELL","SKIP","BUY"],"refit_history_sha256":expected_hist,"forward_snapshot_sha256":_sha(forward),"runtime_contract":candidate_runtime_contract(spec,32),"parity":parity,"artifacts":artifacts,"generator":"onnx_export.py","generated_utc":datetime.now(timezone.utc).isoformat()}
            _write(runtime_dir/"runtime_manifest.json",runtime); champion["runtime_manifest"]="champion_runtime/runtime_manifest.json"; champion["onnx_parity"]=parity
            promotion_profile=gate_profile(cfg,"champion_promotion")
            promotion_checks={
                "ALL_UPSTREAM_PASS": bool((w.get("acceptance") or {}).get("passed")) and bool(mcseal.get("seal_hash")),
                "ARTIFACT_INTEGRITY": bool(mcseal.get("seal_hash")) and bool(expected_hist) and _sha(hist)==expected_hist,
                "NO_POST_FORWARD_TUNING": dcontract.get("scientific_contract") == _critical_scientific_contract(cfg),
                "ONNX_EXPORT": bool(artifacts),
                "ONNX_PARITY": max_err <= tol,
            }
            required={
                "ALL_UPSTREAM_PASS":bool(promotion_profile.get("require_all_upstream_pass",True)),
                "ARTIFACT_INTEGRITY":bool(promotion_profile.get("require_artifact_integrity",True)),
                "NO_POST_FORWARD_TUNING":bool(promotion_profile.get("require_no_post_forward_tuning",True)),
                "ONNX_EXPORT":bool(promotion_profile.get("require_onnx_export",True)),
                "ONNX_PARITY":bool(promotion_profile.get("require_onnx_parity",True)),
            }
            promotion_failed=[name for name,req in required.items() if req and not promotion_checks.get(name,False)]
            champion["promotion"]={"schema":"MAX_GATE_KPI_PROFILES_V1","profile":str(promotion_profile.get("profile_version","CHAMPION_PROMOTION_V1")),"checks":promotion_checks,"required":required,"passed":not promotion_failed,"first_failed_gate":promotion_failed[0] if promotion_failed else None}
            if promotion_failed: raise RuntimeError("Champion promotion blocked: "+promotion_failed[0])
            _write(fd/"champion.json",champion)
            champion_files=["champion.json","champion_runtime/runtime_manifest.json"]
            for k,v in artifacts.items():
                if k.endswith("sha256"): continue
                champion_files.append("champion_runtime/"+str(v))
            champion_contract={"schema":"MAX_CHAMPION_STAGE_CONTRACT_V1","winner_identity":_candidate_identity(w),"refit_history_sha256":expected_hist,"forward_snapshot_sha256":_sha(forward),"feature_contract":CONTRACT_ID,"feature_order":list(FEATURES),"class_order":["SELL","SKIP","BUY"],"max_onnx_abs_error":tol}
            champion_seal=_stage_seal(fd,"CHAMPION",contract=champion_contract,files=champion_files)
        except Exception as exc:
            status="FACTORY_WINNER_RUNTIME_BLOCKED"; champion["runtime_error"]=str(exc); champion["runtime_manifest"]=None; _write(fd/"champion.json",champion)
    else:
        status="NO_CHAMPION_FORWARD_FAIL"; terminal=True; _record_downstream_failure(fd,"FORWARD_CHAMPIONSHIP",{"survivors":len(candidates),"passed":0,"evaluated_to":str(fresh_to),"first_failed_gates":[(r.get("acceptance") or {}).get("first_failed_gate") for r in rows]})
    leaderboard_file=f"forward_leaderboard_{n:03d}.json"; _write(fd/leaderboard_file,rows)
    ev_name=f"forward_evidence_{n:03d}.json"
    previous_hash=(checks[-1].get("terminal_seal_hash") if checks else None)
    stage_contract={"schema":"MAX_FORWARD_CHECK_CONTRACT_V1","check":n,"upstream_monte_carlo_seal_hash":mcseal.get("seal_hash"),"previous_check_seal_hash":previous_hash,"scientific_contract":_critical_scientific_contract(cfg),"fresh_from":fresh_from,"evaluated_to":str(fresh_to),"refit_history_sha256":expected_hist,"snapshot_sha256":(_sha(forward) if forward.exists() else None),"data_quality_sha256":(_sha(fd/dq_file) if (fd/dq_file).exists() else None)}
    evidence={"schema":SCHEMA,"status":status,"stage_contract":stage_contract,"stage_contract_hash":_stable_hash(stage_contract),"forward":{"from":str(fresh_from),"to":str(fresh_to),"snapshot":forward.name if forward.exists() else None,"snapshot_sha256":_sha(forward) if forward.exists() else None,"auto_trade_sample":sample,"all_survivors_sample_sufficient":all_sufficient,"leaderboard_file":leaderboard_file},"champion":champion,"terminal":terminal}
    _write(fd/ev_name,evidence)
    seal_files=[ev_name,leaderboard_file]+([forward.name] if forward.exists() else [])+([dq_file] if (fd/dq_file).exists() else [])
    fseal=_stage_seal(fd,f"FORWARD_CHECK_{n:03d}",contract=stage_contract,files=seal_files)
    checks.append({"check":n,"evaluated_to":str(fresh_to),"snapshot":forward.name if forward.exists() else None,"snapshot_sha256":_sha(forward) if forward.exists() else None,"evidence_file":ev_name,"leaderboard_file":leaderboard_file,"status":status,"survivors":len(candidates),"passed":len(passed),"minimum_trades":int(sample.get("minimum_trades",0) or 0),"terminal":terminal,"stage_contract":stage_contract,"terminal_seal_file":f"forward_check_{n:03d}_terminal_seal.json","terminal_seal_hash":fseal.get("seal_hash")})
    topology=generic_stage_topology("FORWARD",rows); _write(fd/"forward_failure_topology.json",topology)
    scientist_entry=_stage_scientist_and_feedback(fd,cfg,"CHAMPION" if status=="FACTORY_WINNER" else "FORWARD",status,topology,rows,llm_api_key=llm_api_key,learning_allowed=False)
    next_required=("REGISTER_MODEL_CHALLENGER" if status=="FACTORY_WINNER" else ("REPAIR_ONNX_RUNTIME" if status=="FACTORY_WINNER_RUNTIME_BLOCKED" else ("WAIT_NEW_FORWARD_DATA" if status=="FORWARD_INSUFFICIENT_SAMPLE" else "TERMINAL_FORWARD_FAIL")))
    fm.update({"status":status,"stage":"FORWARD_CHAMPIONSHIP","forward_opened":bool(terminal),"forward_checks":checks,"forward_evidence_file":ev_name,"champion_file":"champion.json" if champion else None,"champion":champion.get("pool_id") if champion else None,"stage_scientist_journal":"stage_scientist_journal.json","research_restart_required":False,"next_required":next_required})
    if champion_seal:
        fm["champion_terminal_seal"]="champion_terminal_seal.json"
        fm["champion_terminal_seal_hash"]=champion_seal.get("seal_hash")
    _write(fd/"factory_manifest.json",fm); _emit(progress,"factory_done",1,1,status,scientist_update=scientist_entry)
    return {"factory":str(fd),"status":status,"champion":champion,"survivors":len(candidates),"manifest":fm,"scientist":scientist_entry}


# Backward-compatible name for Scientist/legacy callers; v0.7.1 authority is Forward Championship.
def run_fresh(factory_dir, master_csv, config_path, fresh_from=None, fresh_to=None, progress: ProgressCallback = None) -> dict:
    return run_forward_championship(factory_dir, master_csv, config_path, fresh_from, fresh_to, progress)
