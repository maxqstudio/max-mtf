from __future__ import annotations
import json
import os
import shutil
import hashlib
import math
import random
from datetime import datetime, timezone
from copy import deepcopy
from pathlib import Path
from core.project_paths import MODELLAB_ROOT
from factory.challenger_registry import register_eligible_challenger
from typing import Callable, Optional

import joblib
import numpy as np
import pandas as pd

from core.contract import FEATURES, CONTRACT_ID
from research.evaluation import classification_metrics, trading_metrics
from research.kpi import build_locked_test_kpi, locked_test_acceptance, walk_forward_acceptance
from data.labels import build_labels
from strategy.strategy_geometry import synchronize_cfg_with_dataset_geometry
from data.dataset_integrity import fresh_readiness
from models.model_lab import (
    load_cfg, load_training_csv, split_locked_test, research_region, candidate_cv, feature_matrix, apply_candidate_memory,
    acceptance, sha256_file, _emit,
)
from models.models import CandidateSpec, experiment_fingerprint, trained_candidate_id, candidate_input_shape, candidate_runtime_contract, generate_initial_population, make_model, fit_model, spec_fingerprint, predict_model_proba, validate_candidate, strict_scientist_candidate_admission, candidate_capacity_contract
from models.model_registry import is_hybrid_family, family_spec, enabled_families
from research.research_planner import plan_next_candidates, family_stats
from models.topology_allocation import configured_hybrid_priority, effective_hybrid_priority, allocation_counts, enforce_item_allocation
from scientist.core.scientist import LLMScientist
from research.research_memory import seed_candidates_from_memory
from research.scientific_hypotheses import apply_policy_agenda
from research.policy_discovery import discover_policy, build_policy_locked_test_kpi, write_policy_csv, policy_trading_metrics, policy_actions
from research.experiment_blocks import reconcile_hypotheses, choose_active_hypothesis, compile_experiment_block, evaluate_block
from research.research_feedback import dataset_header_context
from research.creativity_governor import adaptive_creativity_profile, llm_research_influence
from models.model_registry import effective_bounds, configured_family_size_priorities
from research.learning_policy import recommend_learning_actions
from scientist.skills.max_scientist_skills import skill_guidance
from research.future_learning_foundation import foundation_snapshot
from research.research_engine_v3 import (
    gate_failure_margins, failure_topology, cheap_screen_spec, cheap_screen_cfg,
    select_full_wfa_promotions, trial_record, write_jsonl, SCHEMA as RESEARCH_ENGINE_SCHEMA,
)

ProgressCallback = Optional[Callable[[dict], None]]


_LLM_RETRYABLE_CATEGORIES={"QUOTA_OR_RATE_LIMIT","QUOTA_EXHAUSTED","RATE_LIMIT","TIMEOUT","PROVIDER_5XX","PROVIDER_UNREACHABLE","MODEL_UNAVAILABLE","DAILY_QUOTA_EXHAUSTED","RATE_LIMITED","COOLDOWN"}

def _llm_stack_exhausted(provenance: dict | None) -> bool:
    attempts=list((provenance or {}).get("attempts") or [])
    if not attempts:
        return False
    saw=False
    for row in attempts:
        status=str((row or {}).get("status") or "").upper()
        if status=="PASS":
            return False
        if status=="SKIP":
            saw=True; continue
        if status=="FAIL" and str((row or {}).get("category") or "").upper() in _LLM_RETRYABLE_CATEGORIES:
            saw=True; continue
        return False
    return saw


def _write_json(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _jsonable_spec(s: CandidateSpec) -> dict:
    return {"family": s.family, "name": s.name, "params": s.params}


def _scientist_execution_provenance(source_spec: CandidateSpec, executable_spec: CandidateSpec, *, experiment_block: dict|None=None) -> dict:
    """Bind Scientist intent to the exact candidate that is actually queued.

    Normal Scientist proposals must execute exactly as admitted. A hypothesis-directed
    experiment block is a separate deterministic intervention authority; when it changes
    parameters, the resulting trial must never be attributed as an exact LLM proposal.
    """
    src={"family":source_spec.family,"name":source_spec.name,"params":deepcopy(source_spec.params)}
    exe={"family":executable_spec.family,"name":executable_spec.name,"params":deepcopy(executable_spec.params)}
    block=experiment_block if isinstance(experiment_block,dict) else {}
    transformed=(src["family"]!=exe["family"] or src["params"]!=exe["params"])
    if block:
        authority="DETERMINISTIC_EXPERIMENT_BLOCK"
        exact_llm_execution=not transformed
        attribution="LLM_PROPOSAL_EXACT" if exact_llm_execution else "EXPERIMENT_BLOCK_INTERVENTION_NOT_LLM_EXACT"
    else:
        authority="STRICT_SCIENTIST_ADMISSION"
        if transformed:
            raise RuntimeError("SCIENTIST_EXECUTABLE_IDENTITY_DRIFT")
        exact_llm_execution=True
        attribution="LLM_PROPOSAL_EXACT"
    return {
        "schema":"MAX_MTF_SCIENTIST_EXECUTION_PROVENANCE_V1",
        "source_requested_candidate":src,
        "executable_candidate":exe,
        "execution_authority":authority,
        "experiment_block_id":str(block.get("block_id") or "") or None,
        "experiment_block_kind":str(block.get("kind") or "") or None,
        "parameters_transformed":bool(transformed),
        "exact_llm_proposal_executed":bool(exact_llm_execution),
        "scientific_attribution":attribution,
    }


def _register_spec(spec: CandidateSpec, specs_by_name: dict[str, CandidateSpec]) -> CandidateSpec:
    if spec.name not in specs_by_name:
        specs_by_name[spec.name] = spec
        return spec
    # LLMs are quite capable of naming five different experiments "best_xgb".
    # Governance prefers identifiers that actually identify something.
    suffix = abs(hash(spec_fingerprint(spec))) % 1000000
    spec = CandidateSpec(spec.family, f"{spec.name}_{suffix:06d}", dict(spec.params))
    specs_by_name[spec.name] = spec
    return spec


def _dataset_context(raw: pd.DataFrame, labeled: pd.DataFrame) -> dict:
    counts=labeled["label"].value_counts().to_dict()
    return {
        "rows_raw": int(len(raw)),
        "rows_labeled": int(len(labeled)),
        "symbol": str(raw["symbol"].iloc[0]),
        "period": int(raw["period"].iloc[0]),
        "start": str(raw["signal_time"].min()),
        "end": str(raw["signal_time"].max()),
        "classes": {"SELL":int(counts.get(0,0)),"SKIP":int(counts.get(1,0)),"BUY":int(counts.get(2,0))},
        "feature_contract": CONTRACT_ID,
        "feature_count": len(FEATURES),
    }



def _supervisor_initial_strategy(dataset_ctx: dict, generation_memory: dict, cfg: dict, externally_excluded_count: int) -> tuple[dict, int, dict]:
    """Build a reproducible memory-aware initial plan before round 1.

    A new Factory must not blindly replay the same registry seed plan.  The plan is
    derived only from legal Discovery information: source profile, Global/Generation
    Research Memory, prior experiment fingerprints, and operator creativity knobs.
    """
    ac = cfg.get("agent", {}) or {}
    search = ac.get("search", {}) or {}
    llm = ac.get("llm", {}) or {}
    memory = generation_memory or {}
    classes = dataset_ctx.get("classes", {}) or {}
    total_cls = max(1, sum(int(v or 0) for v in classes.values()))
    skip_ratio = float(classes.get("SKIP", 0) or 0) / total_cls
    creativity_profile=adaptive_creativity_profile(cfg,failure_topology=(generation_memory or {}).get("failure_topology") or {},stale_rounds=0)
    explore = max(float(search.get("exploration_ratio", 0.45)), float(creativity_profile.get("target_exploration_ratio",0.45)))
    # A strongly imbalanced/abstention-heavy source deserves a little more breadth.
    if skip_ratio >= 0.70:
        explore += 0.08
    # Raw downstream evidence is sealed. R5 may receive only a committed exact-contract
    # Scientist summary/hypothesis from a prior closed cycle; never raw evaluator rows.
    explore = max(0.15, min(0.85, explore))

    priorities = {}
    for rank, elite in enumerate(memory.get("elites") or []):
        fam = str(elite.get("family") or "")
        if fam:
            priorities[fam] = max(priorities.get(fam, 0.0), max(0.45, 1.65 - 0.12 * rank))
    strategy = {
        "exploration_ratio": explore,
        "family_priorities": priorities,
        "focus": "memory_aware_initial_plan",
    }
    months=[]
    for elite in memory.get("elites") or []:
        try:
            m=int((elite.get("params") or {}).get("training_memory_months"))
            if m>0 and m not in months: months.append(m)
        except Exception:
            pass
    if months:
        strategy["preferred_training_memory_months"] = months[:6]

    seed_payload = {
        "dataset": {k: dataset_ctx.get(k) for k in ("symbol","period","start","end","rows_raw","rows_labeled","classes")},
        "memory_summary": memory.get("learning_summary") or {},
        "evaluation_feedback": "RAW_SEALED; EXACT_CONTRACT_STAGE_SUMMARY_MAY_BE_PRESENT",
        "external_fingerprints": int(externally_excluded_count),
        "creativity": {
            "base_exploration": float(search.get("exploration_ratio",0.45)),
            "crossover": float(search.get("crossover_ratio",0.30)),
            "llm_research_influence": llm_research_influence(cfg),
            "scientific_creativity": float(creativity_profile.get("owner_creativity",0.50)),
            "adaptive_profile": creativity_profile,
            "scientist_proposals": int(llm.get("max_proposals_per_round",5)),
        },
    }
    digest = hashlib.sha256(json.dumps(seed_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    seed_offset = int(digest[:12], 16) % 1000003
    plan = {
        "phase":"SUPERVISOR_INITIAL_PLAN",
        "reason":"source_profile_plus_global_memory_plus_creativity",
        "strategy":strategy,
        "seed_offset":seed_offset,
        "source_skip_ratio":skip_ratio,
        "external_fingerprints_excluded":int(externally_excluded_count),
        "memory_elites":len(memory.get("elites") or []),
        "downstream_feedback_items":len(memory.get("stage_feedback") or []),
        "evaluation_feedback":"RAW_SEALED; EXACT_CONTRACT_STAGE_SUMMARY_MAY_BE_PRESENT",
        "creativity":seed_payload["creativity"],
    }
    return strategy, seed_offset, plan


def _period_label(period: int|float|str) -> str:
    try: p=int(float(period))
    except Exception: return str(period or "?")
    mapping={1:"M1",2:"M2",3:"M3",4:"M4",5:"M5",6:"M6",10:"M10",12:"M12",15:"M15",20:"M20",30:"M30",16385:"H1",16386:"H2",16387:"H3",16388:"H4",16390:"H6",16392:"H8",16396:"H12",16408:"D1",32769:"W1",49153:"MN1",60:"H1",120:"H2",180:"H3",240:"H4",360:"H6",480:"H8",720:"H12",1440:"D1",10080:"W1",43200:"MN1"}
    return mapping.get(p, f"P{p}")


def _dataset_provenance(raw: pd.DataFrame, csv_path: str|Path, csv_hash: str|None=None) -> dict:
    period=int(raw["period"].iloc[0]); symbol=str(raw["symbol"].iloc[0])
    return {
        "symbol":symbol,
        "period":period,
        "timeframe":_period_label(period),
        "source_csv_name":Path(csv_path).name,
        "source_csv_sha256":str(csv_hash or sha256_file(csv_path)),
        "source_rows":int(len(raw)),
        "source_start":str(pd.to_datetime(raw["signal_time"],errors="coerce").min()),
        "source_end":str(pd.to_datetime(raw["signal_time"],errors="coerce").max()),
        "identity_schema":"DATASET_ID_V2",
    }


def _legacy_holdout_key(csv_hash: str, cfg: dict) -> str:
    payload={"source_csv_sha256":csv_hash,"contract":CONTRACT_ID,"label":cfg.get("label"),"split":cfg.get("split")}
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _run_identity_from_disk(path: Path, run_id: str) -> dict|None:
    run=path.parent.parent/"runs"/str(run_id)
    mp=run/"model_manifest.json"
    if mp.exists():
        try:
            m=_load_json(mp); dp=m.get("dataset_provenance") or {}
            if dp.get("period") is not None:
                return {"symbol":str(dp.get("symbol")),"period":int(dp.get("period")),"timeframe":str(dp.get("timeframe") or _period_label(dp.get("period")))}
        except Exception: pass
    lp=run/"labeled_dataset.csv"
    if lp.exists():
        try:
            d=pd.read_csv(lp,usecols=["symbol","period"],nrows=1)
            if not d.empty:
                period=int(d["period"].iloc[0]); return {"symbol":str(d["symbol"].iloc[0]),"period":period,"timeframe":_period_label(period)}
        except Exception: pass
    return None

def _safe_top_rows(board: list[dict]) -> list[dict]:
    # PASS/failure evidence is essential context. R3 omitted these fields, allowing
    # the Scientist to describe a high-scoring all-FAIL frontier as "optimal".
    keys=("name","family","cv_gate_pass","cv_first_failed_gate","cv_gate_reasons","selection_score","overall_expectancy_r","median_expectancy_r","worst_expectancy_r","expectancy_std_r","median_profit_factor","profit_factor_std","median_max_drawdown_r","worst_fold_max_drawdown_r","median_recovery_factor","worst_fold_recovery_factor","positive_fold_ratio","total_validation_trades","median_win_rate","median_payoff_ratio","median_sharpe_ratio","median_sortino_ratio","median_calmar_mar_ratio","median_probabilistic_sharpe_ratio","median_deflated_sharpe_ratio","median_ulcer_index_r","median_daily_cvar95_r","median_cvar95_r","median_positive_month_ratio","median_positive_quarter_ratio","median_regime_concentration","median_stress_x1_25_expectancy_r","median_stress_x1_50_expectancy_r","median_threshold_plateau","mean_balanced_accuracy","mean_macro_f1","mean_log_loss","mean_brier_score","mean_expected_calibration_error","take_threshold")
    return [{k:r.get(k) for k in keys} for r in board[:10]]


def _holdout_registry_path(out_dir: str|Path) -> Path:
    return Path(out_dir).resolve().parent / "governance" / "holdout_registry.json"


def _holdout_key(csv_hash: str, cfg: dict, dataset_ctx: dict|None=None) -> str:
    ctx=dataset_ctx or {}
    payload={
        "schema":"HOLDOUT_ID_V2",
        "source_csv_sha256":csv_hash,
        "symbol":ctx.get("symbol"),"period":ctx.get("period"),"start":ctx.get("start") or ctx.get("source_start"),"end":ctx.get("end") or ctx.get("source_end"),
        "contract":CONTRACT_ID,"label":cfg.get("label"),"split":cfg.get("split")}
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_holdouts(path: Path) -> dict:
    if not path.exists(): return {"schema":"HOLDOUT_REGISTRY_V2","holdouts":{}}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {"schema":"HOLDOUT_REGISTRY_V2","holdouts":{}}


def _lookup_prior_holdout(path: Path, csv_hash: str, cfg: dict, dataset_ctx: dict) -> tuple[str,dict|None,str|None]:
    """Return (new_key, prior, note). Legacy collisions are ignored only when timeframe identity proves they differ."""
    reg=_load_holdouts(path); holds=reg.get("holdouts",{})
    new_key=_holdout_key(csv_hash,cfg,dataset_ctx)
    if new_key in holds:
        return new_key,dict(holds[new_key]),None
    legacy_key=_legacy_holdout_key(csv_hash,cfg)
    legacy=holds.get(legacy_key)
    if not legacy:
        return new_key,None,None
    prior_id=str(legacy.get("run_id") or "")
    prior_ident=_run_identity_from_disk(path,prior_id) if prior_id else None
    cur_symbol=str(dataset_ctx.get("symbol")); cur_period=int(dataset_ctx.get("period"))
    if prior_ident and (str(prior_ident.get("symbol"))!=cur_symbol or int(prior_ident.get("period"))!=cur_period):
        return new_key,None,f"LEGACY_REGISTRY_COLLISION_IGNORED:{prior_id}:{prior_ident.get('timeframe')}!=${_period_label(cur_period)}".replace('$','')
    prior=dict(legacy); prior["legacy_registry_entry"]=True; prior["identity_verified"]=bool(prior_ident)
    return new_key,prior,(None if prior_ident else "LEGACY_SOURCE_IDENTITY_UNAVAILABLE")


def _register_holdout_open(path: Path, key: str, run_id: str, csv_hash: str, dataset_ctx: dict|None=None):
    reg=_load_holdouts(path); reg["schema"]="HOLDOUT_REGISTRY_V2"
    ctx=dataset_ctx or {}
    reg.setdefault("holdouts",{})[key]={"run_id":run_id,"source_csv_sha256":csv_hash,"symbol":ctx.get("symbol"),"period":ctx.get("period"),"timeframe":ctx.get("timeframe") or _period_label(ctx.get("period")),"opened_utc":datetime.now(timezone.utc).isoformat(),"identity_schema":"HOLDOUT_ID_V2"}
    path.parent.mkdir(parents=True,exist_ok=True); _write_json(path,reg)

def _finalize(winner_spec: CandidateSpec, winner_row: dict, pre: pd.DataFrame, test: pd.DataFrame, cfg: dict, out: Path, source_csv: str, progress=None, policy: dict|None=None):
    policy_name = " + CP_POLICY_V1" if policy else ""
    eval_cfg=deepcopy(cfg)
    auto_sample=None
    if not test.empty:
        try:
            from research.sample_policy import auto_trade_sample
            stage=str(cfg.get("evaluation_stage","LOCKED")).upper()
            auto_sample=auto_trade_sample(int(test["period"].iloc[0]),pd.to_datetime(test["signal_time"],errors="coerce").min(),pd.to_datetime(test["signal_time"],errors="coerce").max(),cfg,"FRESH" if stage=="FRESH" else "LOCKED")
            if auto_sample.get("minimum_trades") is not None:
                eval_cfg.setdefault("acceptance",{})["min_test_trades"]=int(auto_sample["minimum_trades"])
        except Exception:
            auto_sample=None
    _emit(progress,"winner",0,1,f"Locked test dibuka sekali untuk {winner_spec.name}{policy_name}…",winner=winner_spec.name)
    pre_fit,memory_info=apply_candidate_memory(pre,winner_spec,cfg)
    Xpre=feature_matrix(pre_fit,cfg); ypre=pre_fit["label"].to_numpy(np.int64)
    Xtest=feature_matrix(test,cfg); ytest=test["label"].to_numpy(np.int64)
    winner=make_model(winner_spec,cfg)
    fit_model(winner,winner_spec.family,Xpre,ypre,sample_weight=(pre_fit["supervised_weight"].to_numpy(float) if "supervised_weight" in pre_fit.columns else None),cfg=cfg)
    if list(getattr(winner,"classes_",[])) != [0,1,2]:
        raise RuntimeError(f"Winner did not train all three classes: {getattr(winner,'classes_',None)}")
    ptest=np.asarray(predict_model_proba(winner,winner_spec.family,Xpre,Xtest),float)
    class_test=classification_metrics(ptest,ytest,sample_weight=(test["supervised_weight"].to_numpy(float) if "supervised_weight" in test.columns else None))
    if policy:
        trade_test=policy_trading_metrics(ptest,test,eval_cfg,policy)
    else:
        trade_test=trading_metrics(ptest,test,eval_cfg,float(winner_row["take_threshold"]))
    joblib.dump(winner,out/"winner_model.joblib")

    _emit(progress,"onnx",0,1,"Export ONNX + native parity…")
    from models.onnx_export import export_tabular, verify_onnx, export_hybrid, verify_hybrid_onnx
    temporal_onnx_path=None
    if is_hybrid_family(winner_spec.family):
        hybrid_paths=export_hybrid(winner,out,prefix="challenger",n_features=len(FEATURES))
        temporal_onnx_path=hybrid_paths["temporal"]
        onnx_path=hybrid_paths["policy"]
        parity=verify_hybrid_onnx(hybrid_paths,winner,Xpre,Xtest,max_rows=1000,n_features=len(FEATURES))
    else:
        onnx_path=export_tabular(winner,winner_spec.family,out/"challenger.onnx",len(FEATURES))
        # Temporal standalone parity uses the same causal pre-test context as MT5.
        if (family_spec(winner_spec.family) or {}).get("role")=="temporal":
            from models.onnx_export import verify_onnx_with_context
            parity=verify_onnx_with_context(onnx_path,winner,Xpre,Xtest,max_rows=1000,n_features=len(FEATURES))
        else:
            parity=verify_onnx(onnx_path,winner,Xtest,max_rows=1000)
    if policy:
        kpi_report=build_policy_locked_test_kpi(ptest,ytest,test,eval_cfg,policy,parity)
        policy_path=write_policy_csv(out/"challenger_policy.csv",policy)
    else:
        kpi_report=build_locked_test_kpi(ptest,ytest,test,eval_cfg,float(winner_row["take_threshold"]),parity)
        policy_path=None
    kpi_acceptance=locked_test_acceptance(kpi_report,eval_cfg)
    if auto_sample and auto_sample.get("minimum_trades") is not None:
        trade_test["auto_min_trades"]=int(auto_sample["minimum_trades"])
        kpi_report["auto_trade_sample"]=auto_sample
    _write_json(out/"kpi_report.json",kpi_report)
    _write_json(out/"kpi_acceptance.json",kpi_acceptance)
    passed=bool(kpi_acceptance["passed"]); reasons=list(kpi_acceptance["reasons"])

    pred=test[["signal_time","decision_bar_time","close","long_r","short_r","label"]].copy()
    pred["p_sell"]=ptest[:,0]; pred["p_skip"]=ptest[:,1]; pred["p_buy"]=ptest[:,2]
    if policy:
        pred["policy_action"]=policy_actions(ptest,test,cfg,policy)
    pred.to_csv(out/"locked_test_predictions.csv",index=False)
    return {
        "passed":passed,"reasons":reasons,"class_test":class_test,"trade_test":trade_test,
        "parity":parity,"onnx_path":onnx_path,"temporal_onnx_path":temporal_onnx_path,"policy_path":policy_path,"policy":policy,
        "runtime_contract":candidate_runtime_contract(winner_spec,len(FEATURES)),
        "kpi_report":kpi_report,"kpi_acceptance":kpi_acceptance,"effective_train_rows":int(len(pre_fit)),"training_memory":memory_info,"auto_trade_sample":auto_sample,
    }

def run_supervisor_agent(csv_path, config_path="config.json", out_dir="runs", progress: ProgressCallback=None, llm_api_key: str|None=None):
    csv_path=str(csv_path); cfg=load_cfg(config_path); _learning_foundation=foundation_snapshot(cfg); ac=cfg.get("agent",{})
    max_exp=max(1,int(ac.get("max_experiments",36)))
    round_size=max(1,int(ac.get("round_size",6)))
    max_rounds=max(1,int(ac.get("max_rounds",6)))
    patience=max(1,int(ac.get("patience_rounds",2)))
    min_improve=float(ac.get("min_improvement",0.01))
    min_before_stop=max(1,int(ac.get("min_experiments_before_stop",12)))

    run_id=datetime.now(timezone.utc).strftime("AGENT_%Y%m%d_%H%M%S_UTC")
    out=Path(out_dir)/run_id; out.mkdir(parents=True,exist_ok=True)
    _write_json(out/"run_config.json",cfg)

    from models.model_registry import enabled_families
    deploy_families = tuple(enabled_families(cfg))
    preflight_authority = str(ac.get("onnx_preflight_authority") or "").strip()
    if preflight_authority:
        try:
            authority = Path(preflight_authority)
            pf = json.loads(authority.read_text(encoding="utf-8"))
            if pf.get("status") != "PASS":
                raise RuntimeError("factory ONNX preflight authority is not PASS")
            shutil.copy2(authority, out/"onnx_preflight.json")
            _emit(progress,"onnx_preflight_reuse",1,1,"ONNX preflight authority reused · PASS")
        except Exception as e:
            raise RuntimeError("ONNX preflight authority invalid. Detail: " + str(e)) from e
    else:
        _emit(progress,"onnx_preflight",0,max(1,len(deploy_families)),"Preflight ONNX converter · one-time gate…")
        try:
            from models.onnx_export import preflight_export_stack
            def _pf_cb(ev):
                fam=str(ev.get("family") or "model")
                cur=int(ev.get("current",0) or 0); total=max(1,int(ev.get("total",1) or 1))
                phase=str(ev.get("phase") or "start")
                status=str(ev.get("status") or "")
                msg=f"ONNX preflight {fam} · {cur}/{total}" if phase=="start" else f"ONNX preflight {fam} · {status} · {cur}/{total}"
                _emit(progress,"onnx_preflight",cur,total,msg,family=fam,phase=phase,status=status)
            pf = preflight_export_stack(families=deploy_families, n_features=len(FEATURES), tolerance=float(cfg["acceptance"].get("max_onnx_abs_error",1e-4)), progress=_pf_cb)
            _write_json(out/"onnx_preflight.json", pf)
            if pf.get("status") != "PASS":
                failed = [f.get("family")+": "+f.get("error", "unknown") for f in pf.get("families",[]) if f.get("status") != "PASS"]
                raise RuntimeError("; ".join(failed) or "unknown converter failure")
        except Exception as e:
            raise RuntimeError(
                "ONNX converter preflight gagal sebelum research dimulai. "
                "Evidence disimpan di onnx_preflight.json bila preflight sempat berjalan. Detail: " + str(e)
            ) from e

    _emit(progress,"load",0,1,"Supervisor membaca dataset CP32…")
    raw=load_training_csv(csv_path)
    cfg, strategy_geometry = synchronize_cfg_with_dataset_geometry(cfg, raw)
    source_window_path=out/"source_window.csv"
    shutil.copy2(csv_path,source_window_path)
    research_window=dict(cfg.get("research_window") or {})
    research_window.update({
        "schema": research_window.get("schema") or "CP_RESEARCH_WINDOW_V1",
        "authority_snapshot_file": "source_window.csv",
        "authority_snapshot_sha256": sha256_file(source_window_path),
        "authority_snapshot_rows": int(len(raw)),
        "source_raw_end": str(pd.to_datetime(raw["signal_time"],errors="coerce").max()),
    })
    cfg["research_window"]=research_window
    _write_json(out/"run_config.json",cfg)
    _write_json(out/"source_window_manifest.json",research_window)
    _emit(progress,"label",0,1,f"Membangun labels sekali dari {len(raw):,} bar…")
    labeled=build_labels(raw,cfg)
    if len(labeled) < int(cfg["split"].get("min_train_rows",1000))+200:
        raise ValueError(f"Too few labeled rows: {len(labeled)}")
    labeled.to_csv(out/"labeled_dataset.csv",index=False)
    # One research-region authority for Supervisor, Feature/Label Audit and Guided Research.
    # Factory Discovery uses the whole immutable Discovery snapshot; legacy standalone
    # runs retain their historical internal locked split.
    pre,test,research_region_meta=research_region(labeled,cfg)
    dataset_ctx=_dataset_context(raw,labeled)
    llm_dataset_ctx=dataset_header_context(
        list(raw.columns),
        feature_contract=CONTRACT_ID,
        feature_count=len(FEATURES),
        research_contract_hash=str(ac.get("research_contract_hash") or ""),
    )
    csv_hash=sha256_file(csv_path)
    provenance=_dataset_provenance(raw,csv_path,csv_hash)
    provenance["research_region"] = research_region_meta
    provenance["strategy_geometry"] = strategy_geometry

    manual_research=ac.get("manual_research") if isinstance(ac.get("manual_research"),dict) else {}
    manual_mode=bool(manual_research.get("enabled",False))
    llmcfg=dict(ac.get("llm",{}))
    scientist=None
    scientist_enabled=(not manual_mode) and bool(llmcfg.get("enabled",False)) and not bool(llmcfg.get("factory_session_deterministic_only",False))
    if scientist_enabled:
        scientist=LLMScientist(llmcfg,api_key=llm_api_key)
        if not scientist.ready:
            scientist_enabled=False

    journal=[]; board=[]; screen_board=[]; trial_ledger=[]; specs_by_name={}; seen=set(str(x) for x in (ac.get("exclude_fingerprints") or [])); excluded_experiments=set(str(x) for x in (ac.get("exclude_experiment_fingerprints") or [])); queue=[]
    generation_memory=deepcopy(ac.get("generation_memory") or {})
    scientific_agenda=[] if manual_mode else [deepcopy(h) for h in (generation_memory.get("hypothesis_lifecycle") or []) if isinstance(h,dict) and bool(h.get("executable",True))]
    hypothesis_lifecycle=[] if manual_mode else reconcile_hypotheses([], list((generation_memory.get("hypothesis_lifecycle") or [])), source="RESEARCH_MEMORY", generation=int(ac.get("factory_generation",0) or 0))
    factory_director={} if manual_mode else (deepcopy(ac.get("factory_director") or {}) if isinstance(ac.get("factory_director"),dict) else {})
    plan_journal=[]
    if manual_mode:
        raw_manual=[x for x in (manual_research.get("candidates") or []) if isinstance(x,dict)]
        if not raw_manual:
            raise RuntimeError("MANUAL RESEARCH fail-closed: exact Owner candidate list is empty")
        seen=set(); excluded_experiments=set(); queue=[]; specs_by_name={}
        for _i,_raw in enumerate(raw_manual,1):
            _spec=validate_candidate(_raw,cfg,_i)
            if _spec is None:
                raise RuntimeError(f"MANUAL RESEARCH fail-closed: candidate #{_i} violates legal/capacity authority")
            _spec=_register_spec(_spec,specs_by_name); queue.append(_spec); seen.add(spec_fingerprint(_spec))
        initial_count=len(queue); memory_seed_count=0; externally_excluded_count=0
        experiment_block={
            "schema":"MAX_MANUAL_EXPERIMENT_BLOCK_V1","mode":"OWNER_MANUAL_EXACT",
            "block_id":f"MANUAL_{run_id}","hypothesis_id":None,"budget":len(queue),
            "authority":"OWNER_EXACT_CANDIDATE_LIST",
        }
        _write_json(out/"active_experiment_block.json",experiment_block)
        _write_json(out/"hypothesis_lifecycle.json",[])
        plan_journal.append({
            "round":1,"phase":"OWNER_MANUAL_EXACT","generated":len(queue),
            "proposal_authority":"OWNER","llm_used":False,"deterministic_discovery_used":False,
            "validation_authority":"DETERMINISTIC","candidate_names":[x.name for x in queue],
        })
        _write_json(out/"supervisor_plan.json",plan_journal)
        last_llm_strategy={}
    else:
        generation_memory=deepcopy(ac.get("generation_memory") or {})
        # Exact-contract stage Scientist hypotheses are active research instructions for
        # the new cycle (not raw downstream evidence). Keep them visible to policy agenda.
        scientific_agenda=[deepcopy(h) for h in (generation_memory.get("hypothesis_lifecycle") or []) if isinstance(h,dict) and bool(h.get("executable",True))]
        hypothesis_lifecycle=reconcile_hypotheses([], list((generation_memory.get("hypothesis_lifecycle") or [])), source="RESEARCH_MEMORY", generation=int(ac.get("factory_generation",0) or 0))
        factory_director=deepcopy(ac.get("factory_director") or {}) if isinstance(ac.get("factory_director"),dict) else {}
        for _h in (factory_director.get("hypotheses") or []):
            if isinstance(_h,dict): scientific_agenda.append(deepcopy(_h))
        hypothesis_lifecycle=reconcile_hypotheses(hypothesis_lifecycle, list(factory_director.get("hypotheses") or []), source="FACTORY_DIRECTOR", generation=int(ac.get("factory_generation",0) or 0))
        plan_journal=[]
        externally_excluded_count=len(seen)
        initial_count=min(round_size,max_exp)
        memory_seed_count=min(max(0,int(ac.get("memory_elite_recheck_count",4))),initial_count) if generation_memory else 0
        baseline_strategy, baseline_seed_offset, baseline_plan = _supervisor_initial_strategy(dataset_ctx,generation_memory,cfg,externally_excluded_count)
        director_strategy=deepcopy(factory_director.get("strategy") or {}) if isinstance(factory_director.get("strategy"),dict) else {}
        _prior_rows=list(generation_memory.get("elites") or [])
        _prior_topology=generation_memory.get("failure_topology") or {}
        _anchor=None
        if _prior_rows:
            _r=_prior_rows[0]; _anchor=CandidateSpec(str(_r.get("family")),str(_r.get("name") or "memory_anchor"),dict(_r.get("params") or {}))
        active_hypothesis=choose_active_hypothesis(hypothesis_lifecycle,_prior_topology)
        # A directed Experiment Block owns its bounded Full-WFA budget.  Control exploration
        # uses the generation budget and is not falsely reported as a 6-trial hypothesis.
        block_budget=(max(2,int(((ac.get("experiment_blocks") or {}).get("budget_per_block",6)))) if active_hypothesis else int(max_exp))
        experiment_block=compile_experiment_block(active_hypothesis,_anchor,cfg,generation=int(ac.get("factory_generation",0) or 0),block_no=1,budget=block_budget)
        if active_hypothesis:
            memory_seed_count=0
        _write_json(out/"active_experiment_block.json",experiment_block)
        _write_json(out/"hypothesis_lifecycle.json",hypothesis_lifecycle)
        initial_strategy=deepcopy(baseline_strategy)
        initial_strategy["_creativity_profile"]=deepcopy(baseline_plan.get("creativity",{}).get("adaptive_profile") or adaptive_creativity_profile(cfg,failure_topology=_prior_topology,stale_rounds=0))
        initial_strategy["_stale_rounds"]=0
        if director_strategy:
            # The Factory Research Director directs the first search plan. Deterministic
            # memory-aware baseline remains only as an anchor/fallback for omitted fields.
            for _k in ("exploration_ratio","focus","preferred_training_memory_months"):
                if _k in director_strategy: initial_strategy[_k]=deepcopy(director_strategy[_k])
            _base_pri=dict(initial_strategy.get("family_priorities") or {})
            _dir_pri=dict(director_strategy.get("family_priorities") or {})
            if _dir_pri:
                _base_pri.update(_dir_pri); initial_strategy["family_priorities"]=_base_pri
            baseline_plan["phase"]="SUPERVISOR_DIRECTED_INITIAL_PLAN"
            baseline_plan["reason"]="factory_research_director_plus_memory_anchor"
            baseline_plan["factory_director"]={
                "phase":factory_director.get("phase"),
                "source_generation":factory_director.get("source_generation"),
                "summary":factory_director.get("summary"),
                "strategy":director_strategy,
                "hypotheses_count":len(factory_director.get("hypotheses") or []),
            }
            baseline_plan["strategy"]=deepcopy(initial_strategy)
        baseline_plan.update({"round":1,"memory_rechecks":memory_seed_count,"requested":initial_count})
        memory_seeds, memory_recheck_admission = seed_candidates_from_memory(
            generation_memory,cfg,memory_seed_count,return_evidence=True
        )
        baseline_plan["memory_recheck_admission"]=deepcopy(memory_recheck_admission)
        baseline_plan["memory_exact_rechecks_admitted"]=sum(1 for x in memory_recheck_admission if x.get("admission_status")=="ACCEPTED")
        baseline_plan["memory_rechecks_rejected"]=sum(1 for x in memory_recheck_admission if x.get("admission_status")=="REJECTED")
        plan_journal.append(baseline_plan)
        for s in memory_seeds:
            fp=spec_fingerprint(s)
            if fp not in seen and experiment_fingerprint(s,cfg) not in excluded_experiments:
                s=_register_spec(s,specs_by_name); queue.append(s); seen.add(fp)
        discovery_needed=max(0,initial_count-len(queue))
        initial_cfg=deepcopy(cfg); initial_cfg["seed"]=int(cfg.get("seed",42))+int(baseline_seed_offset)
        generated_initial=[]
        if discovery_needed:
            generated_initial, initial_plan = plan_next_candidates([],{},initial_cfg,1,discovery_needed,initial_strategy,experiment_block=experiment_block)
            initial_plan.update({"phase":"SUPERVISOR_INITIAL_POPULATION","baseline_seed_offset":baseline_seed_offset,"memory_rechecks":memory_seed_count})
            plan_journal.append(initial_plan)
        for s in generated_initial:
            if len(queue)>=initial_count: break
            fp=spec_fingerprint(s)
            if fp not in seen and experiment_fingerprint(s,cfg) not in excluded_experiments:
                s=_register_spec(s,specs_by_name); queue.append(s); seen.add(fp)
        # Registry generator remains a deterministic fail-safe if the adaptive planner
        # cannot fill the requested first round after cross-Factory exclusions.
        if len(queue)<initial_count:
            fallback_cfg=deepcopy(initial_cfg); fallback_cfg["seed"]=int(initial_cfg.get("seed",42))+7919
            for _j,s in enumerate(generate_initial_population(fallback_cfg,initial_count-len(queue),round_no=1),1):
                if experiment_block:
                    from research.experiment_blocks import apply_block_to_spec
                    s=apply_block_to_spec(s,experiment_block,cfg,_j)
                if len(queue)>=initial_count: break
                fp=spec_fingerprint(s)
                if fp not in seen and experiment_fingerprint(s,cfg) not in excluded_experiments:
                    s=_register_spec(s,specs_by_name); queue.append(s); seen.add(fp)
        # Final initial-batch admission is topology-authoritative across *all* sources
        # (memory rechecks, deterministic planner, fallback). Memory cannot silently turn
        # an Owner 50/50 cycle into hybrid-only or single-only research.
        _hp=configured_hybrid_priority(cfg,legacy_none=True)
        _initial_admission=None
        if _hp is not None and queue:
            _universe=enabled_families(cfg)
            _alloc=allocation_counts(initial_count,_hp,
                single_available=any(not is_hybrid_family(f) for f in _universe),
                hybrid_available=any(is_hybrid_family(f) for f in _universe))
            _single=[x for x in queue if not is_hybrid_family(x.family)][:_alloc.get("single",0)]
            _hybrid=[x for x in queue if is_hybrid_family(x.family)][:_alloc.get("hybrid",0)]
            queue=_single+_hybrid
            _need_single=max(0,int(_alloc.get("single",0))-len(_single)); _need_hybrid=max(0,int(_alloc.get("hybrid",0))-len(_hybrid))
            if _need_single or _need_hybrid:
                _fill_cfg=deepcopy(initial_cfg); _fill_cfg["seed"]=int(_fill_cfg.get("seed",42))+15485863
                _pool=generate_initial_population(_fill_cfg,max(initial_count*4,24),round_no=1)
                for _j,s in enumerate(_pool,1):
                    if experiment_block:
                        from research.experiment_blocks import apply_block_to_spec
                        s=apply_block_to_spec(s,experiment_block,cfg,2000+_j)
                    v=validate_candidate({"family":s.family,"name":s.name,"params":s.params},cfg,2000+_j)
                    if v is None: continue
                    fp=spec_fingerprint(v); efp=experiment_fingerprint(v,cfg)
                    if fp in seen or efp in excluded_experiments: continue
                    if is_hybrid_family(v.family) and _need_hybrid>0:
                        queue.append(_register_spec(v,specs_by_name)); seen.add(fp); _need_hybrid-=1
                    elif (not is_hybrid_family(v.family)) and _need_single>0:
                        queue.append(_register_spec(v,specs_by_name)); seen.add(fp); _need_single-=1
                    if _need_single<=0 and _need_hybrid<=0: break
            _initial_admission={"configured_hybrid_priority":_hp,"target_single":int(_alloc.get("single",0)),"target_hybrid":int(_alloc.get("hybrid",0)),"actual_single":sum(not is_hybrid_family(x.family) for x in queue),"actual_hybrid":sum(is_hybrid_family(x.family) for x in queue),"authority":"OWNER_TOPOLOGY_FINAL_ADMISSION"}
        plan_journal.append({"round":1,"phase":"MEMORY_ANCHORED_DISCOVERY" if generation_memory else "DISCOVERY","generated":len(queue),"memory_rechecks":memory_seed_count,"exploration_reserve":max(0,len(queue)-memory_seed_count),"external_fingerprints_excluded":externally_excluded_count,"reason":"supervisor_baseline_plan_plus_memory_and_novel_exploration","topology_admission":_initial_admission})
        _write_json(out/"supervisor_plan.json",plan_journal)
        last_llm_strategy=deepcopy(initial_strategy if director_strategy else {})

    best_rank=(-1,-math.inf); best_score=-math.inf; stale_rounds=0; experiments=0; stop_reason="BUDGET_OR_ROUNDS"
    for round_no in range(1,max_rounds+1):
        if experiments>=max_exp: break
        if not queue and manual_mode:
            stop_reason="OWNER_MANUAL_CANDIDATES_COMPLETE"
            break
        if not queue:
            generated, plan = plan_next_candidates(board,specs_by_name,cfg,round_no,round_size,last_llm_strategy,experiment_block=experiment_block)
            plan_journal.append(plan); _write_json(out/"supervisor_plan.json",plan_journal)
            for s in generated:
                fp=spec_fingerprint(s)
                if fp not in seen:
                    s=_register_spec(s,specs_by_name); queue.append(s); seen.add(fp)
        batch=queue[:min(round_size,max_exp-experiments)]
        queue=queue[len(batch):]
        if not batch:
            stop_reason="NO_NEW_CANDIDATES"; break

        fidelity_cfg=(ac.get("fidelity_ladder") or {}) if isinstance(ac.get("fidelity_ladder"),dict) else {}
        fidelity_enabled=bool(fidelity_cfg.get("enabled",True))
        _emit(progress,"agent_round",round_no,max_rounds,f"Supervisor round {round_no}/{max_rounds}: {len(batch)} proposals · {'screen→full WFA' if fidelity_enabled else 'full WFA'}",round=round_no,experiments=experiments,budget=max_exp)
        before_rank=best_rank

        # R2 Fidelity Level 1: cheap chronological screen. This is NEVER qualification
        # authority. It only allocates CPU budget. Original specs are re-run untouched
        # at Level 2 full WFA if promoted.
        promoted_names=[]
        if fidelity_enabled:
            scfg=cheap_screen_cfg(cfg)
            current_screen=[]
            for spec in batch:
                proposal_idx=experiments+1
                sspec=cheap_screen_spec(spec,scfg)
                def _screen_fold_cb(fold_no, fold_total, meta=None):
                    meta=meta or {}; phase=meta.get("phase","fit_start"); elapsed=float(meta.get("elapsed_sec",0.0))
                    msg=(f"SCREEN {spec.name}: fold {fold_no}/{fold_total} · {elapsed:.0f}s" if phase=="fit_heartbeat"
                         else f"SCREEN {spec.name}: fold {fold_no}/{fold_total} · {phase}")
                    _emit(progress,"fidelity_screen",proposal_idx-1,max_exp,msg,candidate=spec.name,candidate_index=proposal_idx,candidate_total=max_exp,fold=fold_no,fold_total=fold_total,**meta)
                cv_s=candidate_cv(sspec,pre,scfg,fold_callback=_screen_fold_cb)
                acc_s=walk_forward_acceptance(cv_s,scfg)
                sr={"round":round_no,"experiment_block_id":experiment_block.get("block_id"),"hypothesis_id":experiment_block.get("hypothesis_id"),"family":spec.family,"name":sspec.name,"original_name":spec.name,"params":spec.params,"screen_params":sspec.params,"fidelity_stage":"CHEAP_SCREEN","experiment_fingerprint":experiment_fingerprint(spec,cfg),**cv_s}
                sr["cv_gate_pass"]=bool(acc_s["passed"]); sr["cv_gate_reasons"]=list(acc_s["reasons"]); sr["cv_first_failed_gate"]=acc_s.get("first_failed_gate"); sr["failure_margins"]=gate_failure_margins(acc_s)
                current_screen.append(sr); screen_board.append(sr)
                experiments += 1
            promoted_names=select_full_wfa_promotions(current_screen,cfg)
            promoted_set=set(promoted_names)
            for sr in current_screen:
                sr["promoted_to_full_wfa"]=str(sr.get("original_name")) in promoted_set
                orig=specs_by_name.get(str(sr.get("original_name")))
                if orig is None:
                    orig=next((x for x in batch if x.name==str(sr.get("original_name"))),None)
                if orig is not None:
                    sspec=cheap_screen_spec(orig,scfg)
                    trial_ledger.append(trial_record(run_id=run_id,round_no=round_no,stage="CHEAP_SCREEN",spec=sspec,metrics=sr,acceptance={"passed":sr["cv_gate_pass"],"first_failed_gate":sr.get("cv_first_failed_gate"),"reasons":sr.get("cv_gate_reasons"),"gates":sr["failure_margins"]["gates"]},promoted=sr["promoted_to_full_wfa"],full_spec=orig))
            pd.DataFrame(screen_board).to_json(out/"screen_leaderboard.json",orient="records",indent=2)
            write_jsonl(out/"all_trials.jsonl",trial_ledger)
            screen_topology=failure_topology(screen_board,authority="CHEAP_SCREEN_DIAGNOSTIC")
            _write_json(out/"screen_failure_topology.json",screen_topology)
            _emit(progress,"fidelity_screen",experiments,max_exp,f"Cheap screen selesai · promote {len(promoted_names)}/{len(current_screen)} ke full WFA",promoted=len(promoted_names),screened=len(current_screen))
            full_batch=[spec for spec in batch if spec.name in promoted_set]
        else:
            full_batch=batch

        if experiment_block.get("mode")=="HYPOTHESIS_DIRECTED":
            completed_block=sum(1 for r in board if str(r.get("experiment_block_id"))==str(experiment_block.get("block_id")))
            remaining_block=max(0,int(experiment_block.get("budget",0) or 0)-completed_block)
            full_batch=full_batch[:remaining_block]

        # R2 Fidelity Level 2: full WFA is the ONLY Discovery qualification authority.
        for spec in full_batch:
            idx=max(1,experiments if fidelity_enabled else experiments+1)
            def _fold_cb(fold_no, fold_total, meta=None):
                meta = meta or {}
                phase = meta.get("phase", "fit_start")
                elapsed = float(meta.get("elapsed_sec", 0.0))
                train_rows = int(meta.get("train_rows", 0))
                val_rows = int(meta.get("validation_rows", 0))
                if phase == "fit_heartbeat":
                    msg = f"FULL WFA {spec.name}: fold {fold_no}/{fold_total} · training {elapsed:.0f}s · train {train_rows:,} rows"
                elif phase == "fold_done":
                    msg = (f"FULL WFA {spec.name}: fold {fold_no}/{fold_total} selesai · {elapsed:.1f}s · "
                           f"PF {float(meta.get('preview_profit_factor',0)):.3f} · "
                           f"Exp {float(meta.get('preview_expectancy_r',0)):+.4f}R · "
                           f"trades {int(meta.get('preview_trades',0))}")
                else:
                    msg = f"FULL WFA {spec.name}: fold {fold_no}/{fold_total} mulai · train {train_rows:,} · val {val_rows:,}"
                _emit(progress,"cv",idx-1,max_exp,msg,candidate=spec.name,candidate_index=idx,candidate_total=max_exp,fold=fold_no,fold_total=fold_total,**meta)
            cv=candidate_cv(spec,pre,cfg,fold_callback=_fold_cb)
            _capacity_contract=candidate_capacity_contract(spec,cfg)
            row={"round":round_no,"experiment_block_id":experiment_block.get("block_id"),"hypothesis_id":experiment_block.get("hypothesis_id"),"family":spec.family,"name":spec.name,"params":spec.params,"fidelity_stage":"FULL_WFA","experiment_fingerprint":experiment_fingerprint(spec,cfg),**cv}
            row["capacity_contract"]=_capacity_contract
            row["parameter_count"]=_capacity_contract.get("parameter_count")
            row["owner_size_priority"]=_capacity_contract.get("owner_size_priority")
            row["training_seed"]=int(cfg.get("seed",42) or 42)
            row["trained_candidate_id"]=trained_candidate_id(spec,cfg,row.get("take_threshold"),str(ac.get("research_contract_hash") or ""))
            row_acc=walk_forward_acceptance(row,cfg)
            row["cv_gate_pass"]=bool(row_acc["passed"]); row["cv_gate_reasons"]=list(row_acc["reasons"]); row["cv_first_failed_gate"]=row_acc.get("first_failed_gate"); row["failure_margins"]=gate_failure_margins(row_acc)
            board.append(row)
            if not fidelity_enabled:
                experiments+=1
            trial_ledger.append(trial_record(run_id=run_id,round_no=round_no,stage="FULL_WFA",spec=spec,metrics=row,acceptance=row_acc,promoted=True,full_spec=spec))
            board.sort(key=lambda x:(bool(x.get("cv_gate_pass")),float(x.get("selection_score",-1e99))),reverse=True)
            best_score=float(board[0].get("selection_score",-1e99))
            best_rank=(1 if bool(board[0].get("cv_gate_pass")) else 0,best_score)
            pd.DataFrame(board).to_json(out/"cv_leaderboard.json",orient="records",indent=2)
            write_jsonl(out/"all_trials.jsonl",trial_ledger)
            topology=failure_topology(board,authority="FULL_WFA")
            _write_json(out/"failure_topology.json",topology)
            _write_json(out/"fold_forensics.json", [{"name":r.get("name"),"family":r.get("family"),"coverage_ratio":r.get("trade_coverage_ratio"),"worst_fold_by_expectancy":r.get("worst_fold_by_expectancy"),"worst_fold_by_drawdown":r.get("worst_fold_by_drawdown"),"folds":r.get("fold_diagnostics",[])} for r in board])
            closest=(row.get("failure_margins") or {}).get("closest_failed_gate") or {}
            _emit(
                progress,"cv",experiments,max_exp,
                (f"{spec.name} FULL WFA selesai · score {float(row['selection_score']):+.4f} · "
                 f"PASS {'YES' if row['cv_gate_pass'] else 'NO'} · first {row_acc.get('first_failed_gate') or '—'} · "
                 f"closest {closest.get('gate') or '—'} {float(closest.get('relative_margin'))*100:+.1f}% " if closest.get('relative_margin') is not None else
                 f"{spec.name} FULL WFA selesai · PASS {'YES' if row['cv_gate_pass'] else 'NO'} · first {row_acc.get('first_failed_gate') or '—'}"),
                candidate=spec.name,candidate_index=experiments,candidate_total=max_exp,
                candidate_score=float(row['selection_score']),best_score=float(board[0]['selection_score']),
                result_row={
                    "Exp": experiments, "Round": round_no, "Model": spec.name, "Family": spec.family,
                    "Stage":"FULL WFA", "Score": round(float(row['selection_score']),2),
                    "PASS":"YES" if bool(row.get("cv_gate_pass")) else "NO",
                    "First fail":str(row_acc.get("first_failed_gate") or ""),
                    "Fails":int(len(row_acc.get("reasons") or [])),
                    "Closest fail":str(closest.get("gate") or ""),
                    "Margin %":round(100*float(closest.get("relative_margin")),1) if closest.get("relative_margin") is not None else None,
                    "DD R":round(float(row.get("median_max_drawdown_r",999)),2),
                    "Worst DD":round(float(row.get("worst_fold_max_drawdown_r",999)),2),
                    "Recovery":round(float(row.get("median_recovery_factor",-999)),2),
                    "Worst RF":round(float(row.get("worst_fold_recovery_factor",-999)),2),
                    "PF":round(float(row['median_profit_factor']),3),
                    "Exp R":round(float(row.get('overall_expectancy_r',-999.0)),4),
                    "Overall R":round(float(row.get('overall_expectancy_r',-999.0)),4),
                    "Median R":round(float(row['median_expectancy_r']),4),
                    "Worst R":round(float(row['worst_expectancy_r']),4),
                    "Positive folds":f"{100.0*float(row.get('positive_fold_ratio',0.0)):.0f}%",
                    "Stress 1.50":round(float(row.get('median_stress_x1_50_expectancy_r',-999.0)),4),
                    "Plateau":f"{100.0*float(row.get('median_threshold_plateau',0.0)):.0f}%",
                    "Trades":int(row['total_validation_trades']), "Memory M":int(row.get("training_memory_months",0)),
                    "Coverage":f"{100.0*float(row.get('trade_coverage_ratio',0.0)):.1f}%", "Fit s":round(float(row.get('total_fit_seconds',0.0)),1),
                }
            )

        # Persist screen-only trials even if none were promoted due to future policy changes.
        write_jsonl(out/"all_trials.jsonl",trial_ledger)
        _write_json(out/"all_trial_summary.json",{
            "schema":"CP_ALL_TRIAL_SUMMARY_V1","research_engine_schema":RESEARCH_ENGINE_SCHEMA,
            "proposals_screened":len(screen_board) if fidelity_enabled else len(board),
            "full_wfa_runs":len(board),"ledger_records":len(trial_ledger),
            "fidelity_enabled":fidelity_enabled,"updated_utc":datetime.now(timezone.utc).isoformat(),
        })

        if before_rank[0] < best_rank[0]:
            improved=True
        elif before_rank[0] == best_rank[0] and math.isfinite(before_rank[1]):
            improved=(best_rank[1]-before_rank[1])>=min_improve
        else:
            improved=True
        stale_rounds=0 if improved else stale_rounds+1

        llm_note={"round":round_no,"phase":"SUPERVISOR_ROUND_REVIEW","created_utc":datetime.now(timezone.utc).isoformat(),"enabled":scientist_enabled,"summary":"","report":{},"error":None,"strategy":{},"proposals":[],"hypotheses":[],"stop_research":False}
        llm_stop=False
        if scientist_enabled and scientist is not None:
            try:
                current_plan = plan_journal[-1] if plan_journal else {}
                _wfa_pass_count=sum(1 for r in board if bool(r.get("cv_gate_pass")))
                _fail_counts={}
                for _r in board:
                    _g=str(_r.get("cv_first_failed_gate") or "UNKNOWN")
                    _fail_counts[_g]=int(_fail_counts.get(_g,0))+1
                _full_topology=failure_topology(board,authority="FULL_WFA")
                _screen_topology=failure_topology(screen_board,authority="CHEAP_SCREEN_DIAGNOSTIC") if screen_board else {}
                _creativity=adaptive_creativity_profile(cfg,board=board,failure_topology=_full_topology,stale_rounds=stale_rounds)
                _factory_ctx=deepcopy(ac.get("factory_context") or {})
                _eff_bounds={f:{k:[v[0],v[1]] for k,v in effective_bounds(cfg,f).items()} for f in enabled_families(cfg)}
                ctx={"round":round_no,"budget_remaining":max_exp-experiments,"dataset":llm_dataset_ctx,"top_results":_safe_top_rows(board),"family_stats":family_stats(board,cfg),"fold_forensics":[{"name":r.get("name"),"family":r.get("family"),"first_failed_gate":r.get("cv_first_failed_gate"),"worst_expectancy_r":r.get("worst_expectancy_r"),"worst_dd_r":r.get("worst_fold_max_drawdown_r"),"trades":r.get("total_validation_trades"),"coverage":r.get("trade_coverage_ratio"),"failure_margins":r.get("failure_margins")} for r in board[:8]],"research_memory":generation_memory,"scientific_agenda":scientific_agenda,"supervisor_plan":current_plan,"wfa_pass_count":_wfa_pass_count,"wfa_total_count":len(board),"first_failed_gate_counts":_fail_counts,"failure_topology":_full_topology,"screen_failure_topology":_screen_topology,"fidelity_ladder":{"enabled":fidelity_enabled,"proposals_screened":len(screen_board),"full_wfa_completed":len(board),"promotion_is_resource_only":True},"creativity_profile":_creativity,"effective_parameter_bounds":_eff_bounds,"family_size_priorities":configured_family_size_priorities(cfg),"factory_context":_factory_ctx,"topology_allocation":{k:current_plan.get(k) for k in ("configured_hybrid_priority","target_single_candidates","target_hybrid_candidates","single_candidates","hybrid_candidates")},"compute_allocation":deepcopy(current_plan.get("estimated_compute_allocation") or {}),"seed_policy":deepcopy(_factory_ctx.get("cpcv_seed_policy") or {})}
                
                ctx["learning_policy"]=recommend_learning_actions(generation_memory,_full_topology,limit=5)
                ctx["scientist_skills"]=skill_guidance(ctx,max_skills=9)
                ctx["future_learning_foundation"]=deepcopy(_learning_foundation)
                ctx["research_contract_hash"]=str(ac.get("research_contract_hash") or "")
                ctx["research_run_id"]=str(run_id)
                ctx["hypothesis_lifecycle"]=deepcopy(hypothesis_lifecycle)
                _max_scientist_proposals=max(0,min(int(llmcfg.get("max_proposals_per_round",5)),max_exp-experiments))
                if os.environ.get("MAX_LANGGRAPH_ACCEPTANCE_LEGACY_COMPAT")=="1":
                    resp=scientist.propose(ctx,cfg,max_n=_max_scientist_proposals)
                    resp["orchestration_backend"]="LEGACY_ACCEPTANCE_COMPAT_ONLY"
                else:
                    from max_graph.scientist_director_graph import run_agentic_scientist_round
                    resp=run_agentic_scientist_round(
                        scientist=scientist, context=ctx, cfg=cfg, out_dir=out,
                        thread_id=f"{run_id}::SCIENTIST_DIRECTOR", request_id=f"ROUND_{round_no:03d}",
                        max_n=_max_scientist_proposals,
                    )
                    resp["orchestration_backend"]="LANGGRAPH_AGENTIC_SCIENTIST"
                llm_note["summary"]=resp["summary"]; llm_note["report"]=resp.get("report",{}); llm_note["stop_research"]=False; llm_note["stop_research_advisory"]=bool(resp.get("stop_research_advisory",resp.get("stop_research",False))); llm_note["strategy"]=resp.get("strategy",{}); llm_note["hypotheses"]=resp.get("hypotheses",[]); llm_note["hypothesis_admission"]=deepcopy(resp.get("hypothesis_admission") or []); llm_note["deterministic_state"]=resp.get("deterministic_state"); llm_note["llm_provenance"]=resp.get("llm_provenance",{}); llm_note["proposal_admission"]=deepcopy(resp.get("proposal_admission") or []); llm_note["graph_candidate_admission"]=deepcopy(resp.get("graph_candidate_admission") or []); llm_note["graph_rebuild_candidate_admission"]=deepcopy(resp.get("graph_rebuild_candidate_admission") or []); llm_note["model_training_method_contract"]=deepcopy(resp.get("model_training_method_contract") or {}); llm_note["creativity_profile"]=deepcopy(_creativity); llm_note["orchestration_backend"]=resp.get("orchestration_backend"); llm_note["agentic_metadata"]=deepcopy(resp.get("agentic_metadata") or {}); llm_note["agentic_inspection"]=deepcopy(resp.get("agentic_inspection") or {}); llm_note["agentic_evidence"]=deepcopy(resp.get("agentic_evidence") or [])
                last_llm_strategy=resp.get("strategy",{})
                if not isinstance(last_llm_strategy,dict): last_llm_strategy={}
                last_llm_strategy["_creativity_profile"]=deepcopy(_creativity)
                last_llm_strategy["_stale_rounds"]=int(stale_rounds)
                for h in resp.get("hypotheses",[]):
                    key=json.dumps({"kind":h.get("kind"),"title":h.get("title"),"payload":h.get("payload")},sort_keys=True,default=str)
                    if not any(json.dumps({"kind":x.get("kind"),"title":x.get("title"),"payload":x.get("payload")},sort_keys=True,default=str)==key for x in scientific_agenda):
                        scientific_agenda.append(h)
                hypothesis_lifecycle=reconcile_hypotheses(hypothesis_lifecycle, list(resp.get("hypotheses") or []), source="SCIENTIST", generation=int(ac.get("factory_generation",0) or 0))
                _write_json(out/"scientific_agenda.json",scientific_agenda)
                _write_json(out/"hypothesis_lifecycle.json",hypothesis_lifecycle)
                _proposal_batch=list(resp["proposals"] or [])
                if str((experiment_block or {}).get("mode"))=="HYBRID_ABLATION":
                    # The deterministic paired compiler owns both ablation arms. Arbitrary
                    # LLM candidates would contaminate the controlled topology comparison.
                    _proposal_batch=[]
                    llm_note["proposal_admission"]="DETERMINISTIC_HYBRID_ABLATION_BLOCK_OWNS_PAIRED_ARMS"
                _hp=effective_hybrid_priority(cfg,resp.get("strategy") or {},legacy_none=True)
                if _hp is not None and _proposal_batch:
                    _proposal_batch,_admission_meta=enforce_item_allocation(
                        _proposal_batch,_hp,target_total=len(_proposal_batch),available_families=enabled_families(cfg)
                    )
                    llm_note["topology_admission"]=_admission_meta
                for _pi,s in enumerate(_proposal_batch,1):
                    _scientist_source_spec=s
                    if experiment_block:
                        from research.experiment_blocks import apply_block_to_spec
                        s=apply_block_to_spec(s,experiment_block,cfg,1000+_pi)
                    # Concrete Scientist proposals remain strict through the final pre-queue
                    # admission path. Deterministic experiment-block transforms are explicit
                    # separate authority and keep the historical deterministic validator.
                    if experiment_block:
                        s=validate_candidate({"family":s.family,"name":s.name,"params":s.params},cfg,1000+_pi)
                    else:
                        s, _final_admission = strict_scientist_candidate_admission({"family":s.family,"name":s.name,"params":s.params},cfg,1000+_pi)
                        llm_note.setdefault("final_queue_admission",[]).append(_final_admission)
                    if s is None: continue
                    _execution_map=_scientist_execution_provenance(_scientist_source_spec,s,experiment_block=experiment_block if experiment_block else None)
                    llm_note.setdefault("scientist_execution_provenance",[]).append(_execution_map)
                    fp=spec_fingerprint(s); efp=experiment_fingerprint(s,cfg)
                    if fp in seen or efp in excluded_experiments: continue
                    seen.add(fp); s=_register_spec(s,specs_by_name); queue.append(s); llm_note["proposals"].append(_jsonable_spec(s))
                # Scientist stop requests are advisory only; deterministic Supervisor
                # owns all execution/early-stop decisions.
                llm_stop=False
                _emit(progress,"scientist",round_no,max_rounds,f"LLM Scientist · round {round_no}: {resp['summary'] or 'laporan diterima'}",round=round_no,scientist_update=llm_note)
            except Exception as e:
                llm_note["error"]=str(e)
                _prov=deepcopy(getattr(scientist,"last_call_provenance",{})) if scientist is not None else {}
                llm_note["llm_provenance"]=_prov
                if _llm_stack_exhausted(_prov):
                    # Mid-Discovery exhaustion is latched for the remainder of this
                    # Supervisor invocation. Deterministic planning continues without
                    # hammering routes that were just proven unavailable.
                    scientist_enabled=False
                    scientist=None
                    llm_note["execution_mode"]="DETERMINISTIC_ONLY_AFTER_LLM_EXHAUSTION"
                _emit(progress,"scientist",round_no,max_rounds,f"LLM Scientist gagal, Supervisor lanjut deterministic: {e}",round=round_no,scientist_update=llm_note)
        if scientist_enabled and (llm_note.get("summary") or llm_note.get("error") or llm_note.get("proposals") or llm_note.get("hypotheses")):
            journal.append(llm_note)
            _write_json(out/"scientist_journal.json",journal)

        # Champion Factory may close a generation only at this completed-round boundary.
        # Count exact unique Full-WFA PASS experiments, never raw PASS rows. The outer
        # Factory still performs the atomic pool commit after Supervisor returns.
        remaining_slots=max(0,int(ac.get("factory_pool_remaining_slots",0) or 0))
        if remaining_slots>0:
            pending_unique={str(r.get("experiment_fingerprint") or "") for r in board
                            if bool(r.get("cv_gate_pass")) and str(r.get("experiment_fingerprint") or "")
                            and str(r.get("experiment_fingerprint") or "") not in excluded_experiments}
            committed_pool=int(ac.get("factory_committed_pool_size",0) or 0)
            pending_eligible=len(pending_unique)
            projected=committed_pool+min(pending_eligible,remaining_slots)
            target_reached=pending_eligible>=remaining_slots
            # Emit an exact, deduplicated projection at every completed round boundary so
            # the Research/Discovery UI can explain committed vs pending vs projected Pool.
            # This is telemetry only; the outer Factory remains the sole atomic pool writer.
            _emit(progress,"pool_projection",min(pending_eligible,remaining_slots),remaining_slots,
                  (f"Pool target reachable · {pending_eligible} unique pending PASS for {remaining_slots} remaining slots · finishing current round"
                   if target_reached else
                   f"Pool projection · committed {committed_pool} · unique pending {pending_eligible} · projected {projected}/{committed_pool+remaining_slots}"),
                  committed_pool=committed_pool,pending_eligible=pending_eligible,remaining_slots=remaining_slots,
                  projected_pool=projected,pool_target=committed_pool+remaining_slots,target_reached=target_reached,
                  projection_authority="EXACT_UNIQUE_FULL_WFA_PASS_AT_SAFE_ROUND_BOUNDARY")
            if target_reached:
                stop_reason="POOL_TARGET_REACHED_SAFE_ROUND_BOUNDARY"
                break

        if experiment_block.get("mode")=="HYPOTHESIS_DIRECTED":
            completed_block=sum(1 for r in board if str(r.get("experiment_block_id"))==str(experiment_block.get("block_id")))
            if completed_block>=int(experiment_block.get("budget",0) or 0):
                stop_reason="EXPERIMENT_BLOCK_BUDGET_COMPLETE"
                _emit(progress,"experiment_block",completed_block,int(experiment_block.get("budget",0) or 0),
                      f"Experiment Block {experiment_block.get('block_id')} complete · {completed_block}/{experiment_block.get('budget')} Full-WFA trials")
                break

        if manual_mode:
            stop_reason="OWNER_MANUAL_CANDIDATES_COMPLETE"
            break

        needed=min(round_size,max_exp-experiments)
        if not isinstance(last_llm_strategy,dict): last_llm_strategy={}
        _next_topology=failure_topology(board,authority="FULL_WFA")
        _next_creativity=adaptive_creativity_profile(cfg,board=board,failure_topology=_next_topology,stale_rounds=stale_rounds)
        last_llm_strategy["_creativity_profile"]=deepcopy(_next_creativity)
        last_llm_strategy["_stale_rounds"]=int(stale_rounds)
        if len(queue)<needed:
            generated, plan = plan_next_candidates(board,specs_by_name,cfg,round_no+1,needed-len(queue),last_llm_strategy,experiment_block=experiment_block)
            plan_journal.append(plan); _write_json(out/"supervisor_plan.json",plan_journal)
            for s in generated:
                fp=spec_fingerprint(s)
                if fp in seen or experiment_fingerprint(s,cfg) in excluded_experiments: continue
                seen.add(fp); s=_register_spec(s,specs_by_name); queue.append(s)

        has_cv_eligible=any(walk_forward_acceptance(r,cfg)["passed"] for r in board)
        if not has_cv_eligible and experiments>=min_before_stop and stale_rounds>=patience:
            _emit(progress,"diagnostic",experiments,max_exp,"Belum ada candidate yang lolos walk-forward KPI; Supervisor menolak early-stop dan tetap eksplorasi sampai budget/round habis.",round=round_no)
        # Champion Factory Discovery is a pool-building search, not a first-winner search.
        # Once one candidate passes, keep searching until the generation budget/rounds are
        # exhausted so the outer Factory can accumulate a diverse qualified pool.
        disable_pass_early_stop=bool(ac.get("disable_pass_early_stop",False))
        if (not disable_pass_early_stop) and experiments>=min_before_stop and stale_rounds>=patience and has_cv_eligible:
            stop_reason=f"PATIENCE_{stale_rounds}_ROUNDS"; break

    block_outcome=evaluate_block(experiment_block,board,cfg)
    _write_json(out/"experiment_block_outcome.json",block_outcome)
    if block_outcome.get("hypothesis_id"):
        for _h in hypothesis_lifecycle:
            if str(_h.get("hypothesis_id"))==str(block_outcome.get("hypothesis_id")):
                _h["status"]=block_outcome.get("status"); _h.setdefault("observations",[]).append(block_outcome)
    _write_json(out/"hypothesis_lifecycle.json",hypothesis_lifecycle)
    if not board:
        raise RuntimeError("Supervisor produced no completed experiments")
    for row in board:
        cv_gate=walk_forward_acceptance(row,cfg)
        row["cv_gate_pass"]=bool(cv_gate["passed"])
        row["cv_gate_reasons"]=list(cv_gate["reasons"])
        row["cv_first_failed_gate"]=cv_gate.get("first_failed_gate")
        row["failure_margins"]=gate_failure_margins(cv_gate)
    # PASS authority first; Composite Score ranks only within the same authority class.
    board.sort(key=lambda x:(bool(x.get("cv_gate_pass")),float(x.get("selection_score",-1e99))),reverse=True)
    pd.DataFrame(board).to_json(out/"cv_leaderboard.json",orient="records",indent=2)
    score_values=[float(r["selection_score"]) for r in board]
    top_n=score_values[:min(5,len(score_values))]
    _first_fail_counts={}
    _all_fail_counts={}
    for _r in board:
        _fg=str(_r.get("cv_first_failed_gate") or "UNKNOWN")
        if not bool(_r.get("cv_gate_pass")):
            _first_fail_counts[_fg]=int(_first_fail_counts.get(_fg,0))+1
        for _g in (_r.get("cv_gate_reasons") or []):
            _g=str(_g); _all_fail_counts[_g]=int(_all_fail_counts.get(_g,0))+1
    _near=sorted(
        [r for r in board if not bool(r.get("cv_gate_pass"))],
        key=lambda r:(len(r.get("cv_gate_reasons") or []),-float(r.get("selection_score",-1e99)))
    )[:8]
    _full_topology=failure_topology(board,authority="FULL_WFA")
    _screen_topology=failure_topology(screen_board,authority="CHEAP_SCREEN_DIAGNOSTIC") if screen_board else {}
    _write_json(out/"failure_topology.json",_full_topology)
    if screen_board: _write_json(out/"screen_failure_topology.json",_screen_topology)
    research_diag={
        "research_engine_schema":RESEARCH_ENGINE_SCHEMA,
        "research_mode":"MANUAL" if manual_mode else "AUTO",
        "proposal_authority":"OWNER" if manual_mode else "FACTORY",
        "deterministic_discovery_used":False if manual_mode else True,
        "llm_used":False if manual_mode else bool(scientist_enabled),
        "validation_authority":"DETERMINISTIC",
        "fidelity_ladder":{"enabled":bool((ac.get("fidelity_ladder") or {}).get("enabled",True)),"proposals_screened":len(screen_board),"full_wfa_completed":len(board),"screen_is_qualification_authority":False,"full_wfa_is_qualification_authority":True},
        "failure_topology":_full_topology,
        "screen_failure_topology":_screen_topology,
        "all_trial_ledger_file":"all_trials.jsonl",
        "deterministic_state":"WFA_SURVIVORS_PRESENT" if any(bool(r.get("cv_gate_pass")) for r in board) else "NO_WFA_SURVIVOR",
        "all_scores_negative": bool(score_values and max(score_values) < 0.0),
        "top_score": float(max(score_values)) if score_values else None,
        "score_span_all": float(max(score_values)-min(score_values)) if len(score_values)>1 else 0.0,
        "top5_score_span": float(max(top_n)-min(top_n)) if len(top_n)>1 else 0.0,
        "candidates_completed": len(board),
        "cv_gate_eligible_count": int(sum(1 for r in board if bool(r.get("cv_gate_pass")))),
        "first_failed_gate_counts":_first_fail_counts,
        "all_failed_gate_counts":_all_fail_counts,
        "near_miss_candidates":[{
            "name":r.get("name"),"family":r.get("family"),"failed_gate_count":len(r.get("cv_gate_reasons") or []),
            "first_failed_gate":r.get("cv_first_failed_gate"),"failed_gates":list(r.get("cv_gate_reasons") or []),
            "selection_score":r.get("selection_score"),"median_pf":r.get("median_profit_factor"),
            "median_expectancy_r":r.get("median_expectancy_r"),"worst_expectancy_r":r.get("worst_expectancy_r"),
            "worst_fold_recovery_factor":r.get("worst_fold_recovery_factor"),"worst_fold_max_drawdown_r":r.get("worst_fold_max_drawdown_r"),
        } for r in _near],
        "top_rank_cv_gate_pass": bool(board[0].get("cv_gate_pass")) if board else False,
        "top_rank_cv_gate_reasons": list(board[0].get("cv_gate_reasons") or []) if board else [],
    }
    _write_json(out/"research_diagnostics.json",research_diag)
    if research_diag["all_scores_negative"]:
        _emit(progress,"diagnostic",experiments,max_exp,"Diagnosis: semua candidate score masih negatif. Audit label/features sebelum memperbesar search budget.",diagnostic=research_diag)
    elif research_diag["top5_score_span"] < 0.01 and len(top_n)>=3:
        _emit(progress,"diagnostic",experiments,max_exp,"Diagnosis: top candidates sangat berdekatan. Periksa trade overlap/label dominance, bukan sekadar tambah hyperparameter.",diagnostic=research_diag)
    eligible_rows=[r for r in board if bool(r.get("cv_gate_pass"))]
    winner_row=eligible_rows[0] if eligible_rows else board[0]
    winner_spec=specs_by_name[winner_row["name"]]
    cv_acceptance=walk_forward_acceptance(winner_row,cfg)
    _write_json(out/"cv_acceptance.json",cv_acceptance)
    selected_policy=None
    policy_result=None
    if not cv_acceptance["passed"]:
        pcfg=ac.get("policy_discovery",{})
        signal_ok=float(winner_row.get("mean_balanced_accuracy",0.0)) >= float(pcfg.get("min_balanced_accuracy",0.36))
        if bool(pcfg.get("enabled",True)) and (signal_ok or not bool(pcfg.get("require_classification_signal",True))):
            _emit(progress,"policy_start",0,1,"Model search belum lolos KPI. Supervisor masuk bounded OOF Policy Discovery; locked test tetap sealed.",winner=winner_spec.name)
            def _policy_fold_cb(fold_no,fold_total,meta=None):
                meta=meta or {}; phase=meta.get("phase",""); elapsed=float(meta.get("elapsed_sec",0.0) or 0.0)
                _emit(progress,"policy_oof",fold_no,fold_total,f"Policy OOF · {winner_spec.name} · fold {fold_no}/{fold_total} · {phase} · {elapsed:.1f}s",fold=fold_no,fold_total=fold_total)
            policy_cfg=apply_policy_agenda(cfg,scientific_agenda)
            policy_result=discover_policy(winner_spec,pre,policy_cfg,float(winner_row.get("take_threshold",0.65)),progress=progress,fold_callback=_policy_fold_cb)
            _write_json(out/"policy_discovery.json",{k:v for k,v in policy_result.items() if k!="board"})
            _write_json(out/"policy_leaderboard.json",policy_result.get("board") or [])
            pw=policy_result.get("winner")
            if pw:
                pw=dict(pw); pw["name"]=winner_spec.name; pw["family"]=winner_spec.family; pw["round"]=winner_row.get("round")
                selected_policy=dict(pw.get("policy") or {})
                winner_row=pw
                cv_acceptance=walk_forward_acceptance(winner_row,cfg)
                _write_json(out/"cv_acceptance.json",cv_acceptance)
                research_diag["policy_discovery_attempted"]=True
                research_diag["policy_discovery_passed"]=bool(cv_acceptance.get("passed"))
                research_diag["policy_top_score"]=float(winner_row.get("selection_score",0.0))
                research_diag["policy_top_pf"]=float(winner_row.get("median_profit_factor",0.0))
                research_diag["policy_top_expectancy_r"]=float(winner_row.get("median_expectancy_r",0.0))
                _write_json(out/"research_diagnostics.json",research_diag)
                if scientist_enabled and scientist is not None:
                    try:
                        rev=scientist.policy_review({"model_frontier":_safe_top_rows(board)[:3],"policy_frontier":[{k:r.get(k) for k in ("selection_score","median_profit_factor","overall_expectancy_r","median_expectancy_r","worst_expectancy_r","positive_fold_ratio","total_validation_trades","policy")} for r in (policy_result.get("board") or [])[:5]],"policy_passed":bool(cv_acceptance.get("passed")),"next_required":"LOCKED_TEST" if cv_acceptance.get("passed") else "FEATURE_LABEL_AUDIT"})
                        note={"round":max_rounds+1,"phase":"POLICY_DISCOVERY","created_utc":datetime.now(timezone.utc).isoformat(),"enabled":True,"summary":rev.get("summary","") ,"report":rev.get("report",{}),"error":None,"strategy":{},"proposals":[],"stop_research":False,"llm_provenance":rev.get("llm_provenance",{})}
                        journal.append(note); _write_json(out/"scientist_journal.json",journal)
                        _emit(progress,"scientist",max_rounds+1,max_rounds+1,f"LLM Scientist · Policy Discovery: {note['summary'] or 'review diterima'}",scientist_update=note)
                    except Exception as e:
                        _emit(progress,"scientist",max_rounds+1,max_rounds+1,f"Scientist policy review gagal; deterministic evidence tetap authority: {e}")
        else:
            research_diag["policy_discovery_attempted"]=False
            research_diag["policy_discovery_skip_reason"]="CLASSIFICATION_SIGNAL_BELOW_THRESHOLD" if not signal_ok else "DISABLED"
            _write_json(out/"research_diagnostics.json",research_diag)

    if not cv_acceptance["passed"]:
        status="RESEARCH_REJECTED"
        next_required="FEATURE_LABEL_AUDIT" if research_diag.get("policy_discovery_attempted") else "NEW_RESEARCH_GENERATION"
        manifest={
            "run_id":run_id,"run_type":("MANUAL_VALIDATION" if manual_mode else "SUPERVISOR_AGENT"),"status":status,"supervisor_stage":"RESEARCH_REJECTED",
            "reject_reasons":cv_acceptance["reasons"],"feature_contract":CONTRACT_ID,"feature_count":len(FEATURES),"feature_order":FEATURES,"class_order":["SELL","SKIP","BUY"],
            "model_family":winner_spec.family,"model_name":winner_spec.name,"hyperparameters":winner_spec.params,"take_threshold":winner_row.get("take_threshold",selected_policy.get("take_threshold") if selected_policy else None),
            "policy_schema":selected_policy.get("schema") if selected_policy else None,"decision_policy":selected_policy,
            "deployment":cfg["deployment"],"label_policy":cfg["label"],"research_window":research_window,"cv_selection":winner_row,"cv_acceptance":cv_acceptance,
            "source_csv_sha256":csv_hash,"dataset_provenance":provenance,"symbol":provenance["symbol"],"period":provenance["period"],"timeframe":provenance["timeframe"],"source_start":provenance["source_start"],"source_end":provenance["source_end"],"source_raw_end":provenance["source_end"],"train_rows":int(len(pre)),"locked_test_rows":int(len(test)),
            "generated_utc":datetime.now(timezone.utc).isoformat(),"runtime_contract":candidate_runtime_contract(winner_spec,len(FEATURES)),
            "agent":{"experiments_completed":experiments,"experiment_budget":max_exp,"stop_reason":stop_reason,"llm_scientist_enabled":scientist_enabled,"locked_test_opened_once":False,"research_diagnostics":research_diag,"planner":("owner_manual_exact_v1" if manual_mode else "adaptive_registry_v2_learning_memory"),"research_memory_used":bool(generation_memory),"scientific_hypotheses_count":len(scientific_agenda),"supervisor_plan_file":"supervisor_plan.json","policy_discovery_file":"policy_discovery.json" if policy_result else None},
        }
        _write_json(out/"model_manifest.json",manifest)
        _write_json(out/"supervisor_state.json",{"stage":"RESEARCH_REJECTED","run_id":run_id,"candidate":winner_spec.name,"next_required":next_required,"updated_utc":datetime.now(timezone.utc).isoformat()})
        with open(out/"REPORT.md","w",encoding="utf-8") as f:
            f.write(f"# Supervisor Agent Run {run_id}\n\n**Status:** RESEARCH_REJECTED\n\n**Winner by rank:** {winner_spec.name} ({winner_spec.family})\n\n")
            f.write("Locked test was NOT opened. Model CV failed and bounded Policy Discovery did not produce a CV-eligible policy.\n\n")
            f.write(f"Next required: **{next_required}**.\n")
        _emit(progress,"done",1,1,f"RESEARCH_REJECTED · {winner_spec.name} · next {next_required} · locked test tetap sealed",run=str(out),status=status,winner=winner_spec.name)
        return {"run":str(out),"status":status,"winner":winner_spec.name,"reasons":cv_acceptance["reasons"],"manifest":manifest}

    # Guided/new-generation research can deliberately stop after OOF CV. The historical
    # locked period has already informed earlier diagnosis and therefore must not become
    # a "new" holdout merely because labels/features changed.
    if bool(ac.get("skip_locked_test", False)):
        status="NEEDS_FRESH_HOLDOUT"
        manifest={
            "run_id":run_id,"run_type":("MANUAL_VALIDATION" if manual_mode else "SUPERVISOR_AGENT"),"status":status,"supervisor_stage":"WAITING_FRESH_HOLDOUT",
            "reject_reasons":["RETIRED_HOLDOUT_SKIPPED_BY_GUIDED_RESEARCH"],"feature_contract":CONTRACT_ID,"feature_count":len(FEATURES),"feature_order":FEATURES,"class_order":["SELL","SKIP","BUY"],
            "model_family":winner_spec.family,"model_name":winner_spec.name,"hyperparameters":winner_spec.params,"take_threshold":winner_row.get("take_threshold",selected_policy.get("take_threshold") if selected_policy else None),
            "policy_schema":selected_policy.get("schema") if selected_policy else None,"decision_policy":selected_policy,
            "feature_research":deepcopy(cfg.get("feature_research",{})),"deployment":cfg["deployment"],"label_policy":cfg["label"],"research_window":research_window,"cv_selection":winner_row,"cv_acceptance":cv_acceptance,
            "source_csv_sha256":csv_hash,"dataset_provenance":provenance,"symbol":provenance["symbol"],"period":provenance["period"],"timeframe":provenance["timeframe"],"source_start":provenance["source_start"],"source_end":provenance["source_end"],"source_raw_end":provenance["source_end"],"train_rows":int(len(pre)),"locked_test_rows":0,
            "generated_utc":datetime.now(timezone.utc).isoformat(),"runtime_contract":candidate_runtime_contract(winner_spec,len(FEATURES)),
            "agent":{"experiments_completed":experiments,"experiment_budget":max_exp,"stop_reason":stop_reason,"llm_scientist_enabled":scientist_enabled,"locked_test_opened_once":False,"retired_locked_test_accessed":False,"research_diagnostics":research_diag,"planner":("owner_manual_exact_v1" if manual_mode else "adaptive_registry_v2_learning_memory"),"research_memory_used":bool(generation_memory),"scientific_hypotheses_count":len(scientific_agenda),"supervisor_plan_file":"supervisor_plan.json","skip_locked_test":True},
        }
        _write_json(out/"model_manifest.json",manifest)
        _write_json(out/"supervisor_state.json",{"stage":"WAITING_FRESH_HOLDOUT","run_id":run_id,"candidate":winner_spec.name,"next_required":"FRESH_DATA_ONLY","updated_utc":datetime.now(timezone.utc).isoformat()})
        with open(out/"REPORT.md","w",encoding="utf-8") as f:
            f.write(f"# Guided New-Generation Research {run_id}\n\n**Status:** NEEDS_FRESH_HOLDOUT\n\n")
            f.write("OOF CV PASS. Historical locked test was deliberately skipped and not accessed. Use genuinely newer data for the next validation.\n")
        _emit(progress,"done",1,1,f"NEEDS_FRESH_HOLDOUT · guided generation · retired holdout untouched",run=str(out),status=status,winner=winner_spec.name)
        return {"run":str(out),"status":status,"winner":winner_spec.name,"reasons":["RETIRED_HOLDOUT_SKIPPED_BY_GUIDED_RESEARCH"],"manifest":manifest}

    # Locked test is intentionally untouched until this exact point. Reusing the
    # same holdout after seeing its result converts it into another validation set,
    # so the Supervisor keeps a local holdout registry and refuses silent reuse.
    holdout_path=_holdout_registry_path(out_dir)
    holdout_key,prior,holdout_note=_lookup_prior_holdout(holdout_path,csv_hash,cfg,dataset_ctx)
    if prior and not bool(ac.get("allow_locked_test_reuse",False)):
        status="NEEDS_FRESH_HOLDOUT"
        manifest={
            "run_id":run_id,"run_type":("MANUAL_VALIDATION" if manual_mode else "SUPERVISOR_AGENT"),"status":status,"supervisor_stage":"WAITING_FRESH_HOLDOUT",
            "reject_reasons":["LOCKED_TEST_ALREADY_OPENED"],"feature_contract":CONTRACT_ID,"feature_count":len(FEATURES),"feature_order":FEATURES,"class_order":["SELL","SKIP","BUY"],
            "model_family":winner_spec.family,"model_name":winner_spec.name,"hyperparameters":winner_spec.params,"take_threshold":winner_row.get("take_threshold",selected_policy.get("take_threshold") if selected_policy else None),
            "policy_schema":selected_policy.get("schema") if selected_policy else None,"decision_policy":selected_policy,
            "deployment":cfg["deployment"],"label_policy":cfg["label"],"research_window":research_window,"cv_selection":winner_row,"cv_acceptance":cv_acceptance,"source_csv_sha256":csv_hash,"dataset_provenance":provenance,"symbol":provenance["symbol"],"period":provenance["period"],"timeframe":provenance["timeframe"],"source_start":provenance["source_start"],"source_end":provenance["source_end"],"source_raw_end":provenance["source_end"],"train_rows":int(len(pre)),"locked_test_rows":int(len(test)),
            "generated_utc":datetime.now(timezone.utc).isoformat(),"runtime_contract":candidate_runtime_contract(winner_spec,len(FEATURES)),"agent":{"experiments_completed":experiments,"experiment_budget":max_exp,"stop_reason":stop_reason,"llm_scientist_enabled":scientist_enabled,"locked_test_opened_once":False,"prior_holdout_run":prior.get("run_id"),"prior_holdout_identity_verified":prior.get("identity_verified",True),"holdout_registry_note":holdout_note,"research_diagnostics":research_diag,"planner":("owner_manual_exact_v1" if manual_mode else "adaptive_registry_v2_learning_memory"),"research_memory_used":bool(generation_memory),"scientific_hypotheses_count":len(scientific_agenda),"supervisor_plan_file":"supervisor_plan.json"},
        }
        _write_json(out/"model_manifest.json",manifest)
        _write_json(out/"supervisor_state.json",{"stage":"WAITING_FRESH_HOLDOUT","run_id":run_id,"candidate":winner_spec.name,"prior_holdout_run":prior.get("run_id"),"next_required":"FRESH_DATA_OR_NEW_HOLDOUT","updated_utc":datetime.now(timezone.utc).isoformat()})
        with open(out/"REPORT.md","w",encoding="utf-8") as f:
            f.write(f"# Supervisor Agent Run {run_id}\n\n**Status:** NEEDS_FRESH_HOLDOUT\n\nThe same locked-test generation was already opened by `{prior.get('run_id')}`. Supervisor refused to peek again.\n")
        _emit(progress,"done",1,1,f"NEEDS_FRESH_HOLDOUT · prior {prior.get('run_id')}",run=str(out),status=status,winner=winner_spec.name)
        return {"run":str(out),"status":status,"winner":winner_spec.name,"reasons":["LOCKED_TEST_ALREADY_OPENED"],"manifest":manifest}

    _register_holdout_open(holdout_path,holdout_key,run_id,csv_hash,provenance)
    final=_finalize(winner_spec,winner_row,pre,test,cfg,out,csv_path,progress=progress,policy=selected_policy)
    status="ELIGIBLE_CHALLENGER" if final["passed"] else "REJECTED"
    manifest={
        "run_id":run_id,"run_type":("MANUAL_VALIDATION" if manual_mode else "SUPERVISOR_AGENT"),"status":status,"supervisor_stage":("WAITING_MT5_PARITY" if final["passed"] else "RESEARCH_REJECTED"),
        "reject_reasons":final["reasons"],"feature_contract":CONTRACT_ID,"feature_count":len(FEATURES),"feature_order":FEATURES,"class_order":["SELL","SKIP","BUY"],
        "model_family":winner_spec.family,"model_name":winner_spec.name,"hyperparameters":winner_spec.params,"take_threshold":winner_row.get("take_threshold",selected_policy.get("take_threshold") if selected_policy else None),
        "policy_schema":selected_policy.get("schema") if selected_policy else None,"decision_policy":selected_policy,
        "deployment":cfg["deployment"],"label_policy":cfg["label"],"research_window":research_window,"cv_selection":winner_row,"cv_acceptance":cv_acceptance,"locked_test_classification":final["class_test"],"locked_test_trading":final["trade_test"],
        "kpi_schema":"KPI_V5_HIERARCHICAL","kpi_acceptance":final["kpi_acceptance"],"kpi_report":final["kpi_report"],"onnx_parity":final["parity"],"onnx_sha256":sha256_file(final["onnx_path"]),"temporal_onnx_sha256":sha256_file(final["temporal_onnx_path"]) if final.get("temporal_onnx_path") else None,"runtime_contract":final.get("runtime_contract"),"policy_sha256":sha256_file(final["policy_path"]) if final.get("policy_path") else None,"source_csv_sha256":csv_hash,"dataset_provenance":provenance,"symbol":provenance["symbol"],"period":provenance["period"],"timeframe":provenance["timeframe"],"source_start":provenance["source_start"],"source_end":provenance["source_end"],"source_raw_end":provenance["source_end"],"training_memory":final.get("training_memory"),"train_rows":int(final.get("effective_train_rows",len(pre))),"locked_test_rows":int(len(test)),
        "generated_utc":datetime.now(timezone.utc).isoformat(),"current_ea_input_shape":candidate_input_shape(winner_spec,len(FEATURES)),"onnx_output_shape":[1,3],
        "agent": {"experiments_completed":experiments,"experiment_budget":max_exp,"rounds_completed":max((r.get('round',0) for r in board),default=0),"stop_reason":stop_reason,"llm_scientist_enabled":scientist_enabled,"locked_test_opened_once":True,"research_diagnostics":research_diag,"planner":("owner_manual_exact_v1" if manual_mode else "adaptive_registry_v2_learning_memory"),"research_memory_used":bool(generation_memory),"scientific_hypotheses_count":len(scientific_agenda),"supervisor_plan_file":"supervisor_plan.json"},
    }
    if status=="ELIGIBLE_CHALLENGER":
        manifest=register_eligible_challenger(out,manifest,MODELLAB_ROOT)
    _write_json(out/"model_manifest.json",manifest)
    state={"stage":manifest["supervisor_stage"],"run_id":run_id,"candidate":winner_spec.name,"updated_utc":datetime.now(timezone.utc).isoformat(),"next_required":"MT5_PARITY" if final["passed"] else "NEW_RESEARCH_GENERATION"}
    _write_json(out/"supervisor_state.json",state)
    with open(out/"REPORT.md","w",encoding="utf-8") as f:
        f.write(f"# Supervisor Agent Run {run_id}\n\n**Status:** {status}\n\n**Winner:** {winner_spec.name} ({winner_spec.family})\n\n")
        f.write(f"Experiments: {experiments}/{max_exp} · Stop: {stop_reason}\n\n")
        f.write("## Walk-forward acceptance\n\n```json\n"+json.dumps(cv_acceptance,indent=2)+"\n```\n\n")
        f.write("## Locked-test KPI acceptance\n\n```json\n"+json.dumps(final["kpi_acceptance"],indent=2)+"\n```\n\n")
        f.write("## Locked test\n\n```json\n"+json.dumps(final["trade_test"],indent=2)+"\n```\n\n")
        f.write("## ONNX parity\n\n```json\n"+json.dumps(final["parity"],indent=2)+"\n```\n")
    _emit(progress,"done",1,1,f"{status} · {winner_spec.name}",run=str(out),status=status,winner=winner_spec.name)
    return {"run":str(out),"status":status,"winner":winner_spec.name,"reasons":final["reasons"],"manifest":manifest}



def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _policy_research_cfg(source_run: Path, current_config_path) -> dict:
    """Preserve source label/split/deployment, but use current acceptance and policy-search authority."""
    source_cfg_path = source_run / "run_config.json"
    source_cfg = load_cfg(source_cfg_path if source_cfg_path.exists() else current_config_path)
    current_cfg = load_cfg(current_config_path)
    cfg = deepcopy(source_cfg)
    cfg["cpu_threads"] = int(current_cfg.get("cpu_threads", cfg.get("cpu_threads", 4)))
    cfg["acceptance"] = deepcopy(current_cfg.get("acceptance", cfg.get("acceptance", {})))
    cfg["diagnostics"] = deepcopy(current_cfg.get("diagnostics", cfg.get("diagnostics", {})))
    cfg.setdefault("agent", {})["policy_discovery"] = deepcopy(
        current_cfg.get("agent", {}).get("policy_discovery", cfg.get("agent", {}).get("policy_discovery", {}))
    )
    cfg.setdefault("agent", {})["llm"] = deepcopy(
        current_cfg.get("agent", {}).get("llm", cfg.get("agent", {}).get("llm", {}))
    )
    return cfg


def _research_authority(manifest: dict) -> dict:
    """Return immutable research lineage fields without conflating fresh-input identity.

    source_csv_sha256 is retained as a compatibility alias for the immutable research
    snapshot. Fresh/master input hashes must live in fresh_input_csv_sha256.
    """
    rw = dict(manifest.get("research_window") or {})
    return {
        "sha256": str(
            manifest.get("research_source_csv_sha256")
            or rw.get("authority_snapshot_sha256")
            or manifest.get("source_csv_sha256")
            or ""
        ),
        "cutoff": str(
            manifest.get("research_source_raw_end")
            or rw.get("source_raw_end")
            or manifest.get("source_raw_end")
            or manifest.get("source_end")
            or ""
        ),
        "window": rw,
        "provenance": dict(manifest.get("dataset_provenance") or {}),
    }


def run_post_locked_policy_discovery(source_run_dir, csv_path, config_path="config.json", out_dir="runs", progress: ProgressCallback=None, llm_api_key: str|None=None):
    """Run OOF-only policy research after a historical locked-test failure.

    The already-opened locked test is never evaluated again. The model family and
    hyperparameters are frozen from the source run; only CP_POLICY_V1 selectivity
    is searched on the original upstream walk-forward region.
    """
    source_run = Path(source_run_dir)
    csv_path = str(csv_path)
    manifest_path = source_run / "model_manifest.json"
    if not manifest_path.exists():
        raise ValueError("Source run tidak memiliki model_manifest.json")
    src = _load_json(manifest_path)
    cv_acc = src.get("cv_acceptance") or {}
    if not bool(cv_acc.get("passed")):
        raise ValueError("Post-locked Policy Discovery hanya sah untuk source run yang CV-nya PASS")
    if not bool((src.get("agent") or {}).get("locked_test_opened_once")) or not (src.get("locked_test_trading") or src.get("kpi_report")):
        raise ValueError("Source run belum membuka locked test; gunakan Auto Agent biasa")
    if str(src.get("status")) == "ELIGIBLE_CHALLENGER":
        raise ValueError("Source run sudah ELIGIBLE_CHALLENGER; Policy Discovery tidak diperlukan")
    src_auth = _research_authority(src)
    expected_hash = str(src_auth.get("sha256") or src.get("source_csv_sha256") or "")
    actual_hash = sha256_file(csv_path)
    if expected_hash and actual_hash != expected_hash:
        raise ValueError("Dataset tidak sama dengan immutable research source run. Gunakan source_window.csv authority.")
    research_hash = expected_hash or actual_hash
    research_cutoff = str(src_auth.get("cutoff") or "")
    research_window = dict(src_auth.get("window") or src.get("research_window") or {})

    cfg = _policy_research_cfg(source_run, config_path)
    run_id = datetime.now(timezone.utc).strftime("POLICY_%Y%m%d_%H%M%S_UTC")
    out = Path(out_dir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "run_config.json", cfg)

    _emit(progress, "load", 0, 1, f"Membuka source run {src.get('run_id')} tanpa menyentuh locked test lama…")
    raw = load_training_csv(csv_path)
    source_raw_end = str(pd.to_datetime(raw["signal_time"], errors="coerce").max())
    if research_cutoff and pd.Timestamp(source_raw_end) != pd.Timestamp(research_cutoff):
        raise ValueError(
            f"Immutable research cutoff mismatch. Manifest={research_cutoff}; source_window.csv={source_raw_end}"
        )
    research_cutoff = source_raw_end
    provenance = _dataset_provenance(raw,csv_path,research_hash)
    src_dp = src.get("dataset_provenance") or {}
    if src_dp.get("symbol") and str(src_dp.get("symbol")) != provenance["symbol"]:
        raise ValueError("Dataset symbol berbeda dari source run")
    if src_dp.get("period") is not None and int(src_dp.get("period")) != int(provenance["period"]):
        raise ValueError(f"Dataset timeframe berbeda: source {src_dp.get('timeframe') or _period_label(src_dp.get('period'))}, input {provenance['timeframe']}")
    labeled = build_labels(raw, cfg)
    pre, _retired_locked = split_locked_test(labeled, cfg)
    # Deliberately do not calculate or inspect any metric on _retired_locked.

    spec = CandidateSpec(str(src["model_family"]), str(src["model_name"]), dict(src.get("hyperparameters") or {}))
    base_take = float(src.get("take_threshold", 0.65) or 0.65)
    _emit(progress, "policy_start", 0, 1, f"OOF Policy Discovery · frozen {spec.name} · locked lama retired")

    def _fold_cb(fold_no, fold_total, meta=None):
        meta = meta or {}
        _emit(progress, "policy_oof", fold_no, fold_total,
              f"OOF policy · fold {fold_no}/{fold_total} · {meta.get('phase','')} · {float(meta.get('elapsed_sec',0) or 0):.1f}s")

    result = discover_policy(spec, pre, cfg, base_take, progress=progress, fold_callback=_fold_cb)
    _write_json(out / "policy_discovery.json", {k: v for k, v in result.items() if k != "board"})
    _write_json(out / "policy_leaderboard.json", result.get("board") or [])
    winner = result.get("winner")
    if not winner:
        raise RuntimeError("Policy Discovery tidak menghasilkan candidate")
    winner = dict(winner)
    winner["name"] = spec.name
    winner["family"] = spec.family
    policy = dict(winner.get("policy") or {})
    cv_acceptance = walk_forward_acceptance(winner, cfg)
    _write_json(out / "cv_acceptance.json", cv_acceptance)

    passed = bool(cv_acceptance.get("passed"))
    status = "POLICY_CV_PASS_NEEDS_FRESH_HOLDOUT" if passed else "POLICY_CV_REJECTED"
    stage = "WAITING_FRESH_HOLDOUT" if passed else "POLICY_RESEARCH_REJECTED"
    if passed:
        write_policy_csv(out / "frozen_policy.csv", policy)

    journal = []
    llmcfg = dict(cfg.get("agent", {}).get("llm", {}))
    if bool(llmcfg.get("enabled", False)):
        try:
            scientist = LLMScientist(llmcfg, api_key=llm_api_key)
            if scientist.ready:
                rev = scientist.policy_review({
                    "model_frontier": [{"name": spec.name, "family": spec.family, **{k: src.get("cv_selection", {}).get(k) for k in ("selection_score","median_profit_factor","overall_expectancy_r","median_expectancy_r","worst_expectancy_r","positive_fold_ratio","total_validation_trades")}}],
                    "policy_frontier": [{k: r.get(k) for k in ("selection_score","median_profit_factor","overall_expectancy_r","median_expectancy_r","worst_expectancy_r","positive_fold_ratio","total_validation_trades","policy")} for r in (result.get("board") or [])[:5]],
                    "policy_passed": passed,
                    "next_required": "FRESH_HOLDOUT" if passed else "FEATURE_LABEL_AUDIT",
                })
                note = {"round": 1, "phase": "POST_LOCKED_POLICY_DISCOVERY", "enabled": True,
                        "summary": rev.get("summary", ""), "report": rev.get("report", {}), "error": None,
                        "strategy": {}, "proposals": [], "stop_research": False}
                journal.append(note)
                _write_json(out / "scientist_journal.json", journal)
                _emit(progress, "scientist", 1, 1, "Scientist selesai mereview OOF Policy Discovery", scientist_update=note)
        except Exception as e:
            _emit(progress, "scientist", 1, 1, f"Scientist review gagal; deterministic evidence tetap authority: {e}")

    out_manifest = {
        "run_id": run_id,
        "run_type": "POST_LOCKED_POLICY_DISCOVERY",
        "status": status,
        "supervisor_stage": stage,
        "reject_reasons": list(cv_acceptance.get("reasons") or []),
        "source_run_id": src.get("run_id"),
        "source_run_status": src.get("status"),
        "source_locked_test_retired": True,
        "retired_locked_test_accessed": False,
        "source_raw_end": research_cutoff,
        "research_source_raw_end": research_cutoff,
        "source_csv_sha256": research_hash,
        "research_source_csv_sha256": research_hash,
        "research_window": research_window,
        "dataset_provenance": provenance,
        "symbol": provenance["symbol"], "period": provenance["period"], "timeframe": provenance["timeframe"],
        "source_start": provenance["source_start"], "source_end": provenance["source_end"],
        "feature_contract": CONTRACT_ID,
        "feature_count": len(FEATURES),
        "feature_order": FEATURES,
        "class_order": ["SELL", "SKIP", "BUY"],
        "model_family": spec.family,
        "model_name": spec.name,
        "hyperparameters": spec.params,
        "take_threshold": policy.get("take_threshold", base_take),
        "policy_schema": policy.get("schema"),
        "decision_policy": policy,
        "deployment": cfg.get("deployment"),
        "label_policy": cfg.get("label"),
        "cv_selection": winner,
        "cv_acceptance": cv_acceptance,
        "train_rows": int(len(pre)),
        "locked_test_rows": 0,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "agent": {
            "experiments_completed": 0,
            "experiment_budget": 0,
            "stop_reason": "POST_LOCKED_POLICY_DISCOVERY",
            "llm_scientist_enabled": bool(journal),
            "locked_test_opened_once": False,
            "research_diagnostics": {"policy_discovery_attempted": True, "policy_discovery_passed": passed},
            "planner": "post_locked_policy_v1",
            "policy_discovery_file": "policy_discovery.json",
        },
    }
    _write_json(out / "model_manifest.json", out_manifest)
    next_required = "FRESH_HOLDOUT_FOR_FROZEN_MODEL_POLICY" if passed else "FEATURE_LABEL_AUDIT"
    _write_json(out / "supervisor_state.json", {"stage": stage, "run_id": run_id, "source_run_id": src.get("run_id"), "candidate": spec.name, "next_required": next_required, "updated_utc": datetime.now(timezone.utc).isoformat()})
    with (out / "REPORT.md").open("w", encoding="utf-8") as f:
        f.write(f"# Post-Locked OOF Policy Discovery {run_id}\n\n**Source run:** {src.get('run_id')}\n\n**Status:** {status}\n\n")
        f.write("The retired locked test was not re-opened. Policy search used only upstream OOF walk-forward evidence.\n\n")
        f.write(f"**Next required:** {next_required}\n")
    _emit(progress, "done", 1, 1, f"{status} · next {next_required}", run=str(out), status=status, winner=spec.name)
    return {"run": str(out), "status": status, "winner": spec.name, "reasons": list(cv_acceptance.get("reasons") or []), "manifest": out_manifest}



def validate_frozen_model_on_fresh_data(source_run_dir, updated_csv_path, config_path="config.json", out_dir="runs", progress: ProgressCallback=None):
    """Validate a CV-approved frozen model on truly newer same-symbol/timeframe data.

    This is the correct route for NEEDS_FRESH_HOLDOUT. It never redirects the
    operator to an older run and never re-opens the consumed historical holdout.
    """
    source_run=Path(source_run_dir); sm=_load_json(source_run/"model_manifest.json")
    if sm.get("status") != "NEEDS_FRESH_HOLDOUT":
        raise ValueError("Fresh-model validation hanya sah untuk run NEEDS_FRESH_HOLDOUT")
    if not bool((sm.get("cv_acceptance") or {}).get("passed")):
        raise ValueError("Source candidate belum PASS walk-forward hierarchy")
    source_labeled=source_run/"labeled_dataset.csv"
    if not source_labeled.exists():
        raise ValueError("Source labeled_dataset.csv tidak ditemukan; frozen training authority tidak dapat direkonstruksi")
    cfg=_policy_research_cfg(source_run,config_path)
    old_train=pd.read_csv(source_labeled)
    if old_train.empty: raise ValueError("Source labeled dataset kosong")
    research_auth=_research_authority(sm)
    research_hash=str(research_auth.get("sha256") or sm.get("source_csv_sha256") or "")
    cutoff_raw=research_auth.get("cutoff") or sm.get("source_raw_end") or sm.get("source_end")
    if cutoff_raw:
        cutoff=pd.Timestamp(str(cutoff_raw))
    else:
        cutoff=pd.to_datetime(old_train["signal_time"],errors="coerce").max()
    updated_csv_path=str(updated_csv_path); raw_new=load_training_csv(updated_csv_path); new_prov=_dataset_provenance(raw_new,updated_csv_path)
    src_dp=sm.get("dataset_provenance") or {}
    if not src_dp:
        src_dp={"symbol":str(old_train["symbol"].iloc[0]),"period":int(old_train["period"].iloc[0])}
    if str(src_dp.get("symbol")) != new_prov["symbol"] or int(src_dp.get("period")) != int(new_prov["period"]):
        raise ValueError(f"Fresh dataset identity mismatch. Source {src_dp.get('symbol')} {_period_label(src_dp.get('period'))}; input {new_prov['symbol']} {new_prov['timeframe']}")
    new_end=pd.to_datetime(raw_new["signal_time"],errors="coerce").max()
    if pd.isna(new_end) or new_end <= cutoff:
        raise ValueError(f"Dataset belum lebih baru dari source cutoff {cutoff}")
    readiness=fresh_readiness(updated_csv_path,cutoff,cfg)
    if readiness["status"] != "READY":
        raise ValueError(
            f"Fresh data belum siap [{readiness['status']}]. cutoff={cutoff}; "
            f"raw_new={readiness['raw_new_rows']}; mature={readiness['mature_raw_rows']}; "
            f"labeled={readiness['labeled_fresh_rows']}; pending_horizon={readiness['pending_horizon_rows']}; "
            f"horizon={readiness['horizon_bars']} bars; newest={readiness['newest']}"
        )
    labeled_new=build_labels(raw_new,cfg); ts_new=pd.to_datetime(labeled_new["signal_time"],errors="coerce"); fresh=labeled_new.loc[ts_new>cutoff].copy()

    spec=CandidateSpec(str(sm["model_family"]),str(sm["model_name"]),dict(sm.get("hyperparameters") or {}))
    winner_row=dict(sm.get("cv_selection") or {}); policy=dict(sm.get("decision_policy") or {}) or None
    if policy: winner_row["take_threshold"]=float(policy.get("take_threshold",winner_row.get("take_threshold",0.65)))
    updated_hash=sha256_file(updated_csv_path)
    key_raw=json.dumps({"mode":"FROZEN_MODEL_FRESH_V1","source_run":sm.get("run_id"),"updated_csv_sha256":updated_hash,"cutoff":str(cutoff),"symbol":new_prov["symbol"],"period":new_prov["period"]},sort_keys=True).encode("utf-8")
    key=hashlib.sha256(key_raw).hexdigest(); reg_path=_fresh_registry_path(out_dir); reg=_load_holdouts(reg_path)
    if key in reg.get("holdouts",{}):
        prior=reg["holdouts"][key]; raise ValueError(f"Fresh holdout ini sudah pernah dibuka oleh {prior.get('run_id')}. Gunakan data yang lebih baru.")

    run_id=datetime.now(timezone.utc).strftime("FRESH_%Y%m%d_%H%M%S_UTC"); out=Path(out_dir)/run_id; out.mkdir(parents=True,exist_ok=True)
    cfg["evaluation_stage"]="FRESH"
    _write_json(out/"run_config.json",cfg); _register_holdout_open(reg_path,key,run_id,updated_hash,new_prov)
    _emit(progress,"winner",0,1,f"Fresh holdout · {len(fresh):,} unseen {new_prov['timeframe']} rows · frozen {spec.name}")
    final=_finalize(spec,winner_row,old_train,fresh,cfg,out,updated_csv_path,progress=progress,policy=policy)
    status="ELIGIBLE_CHALLENGER" if final["passed"] else "REJECTED"
    manifest={
        "run_id":run_id,"run_type":"FRESH_MODEL_VALIDATION","status":status,"supervisor_stage":"WAITING_MT5_PARITY" if final["passed"] else "RESEARCH_REJECTED",
        "reject_reasons":final["reasons"],"source_run_id":sm.get("run_id"),"source_holdout_retired":True,"retired_locked_test_accessed":False,
        "fresh_cutoff_exclusive":str(cutoff),"fresh_data_end":str(new_end),"fresh_holdout_rows":int(len(fresh)),"fresh_readiness":readiness,
        "feature_contract":CONTRACT_ID,"feature_count":len(FEATURES),"feature_order":FEATURES,"class_order":["SELL","SKIP","BUY"],
        "model_family":spec.family,"model_name":spec.name,"hyperparameters":spec.params,"take_threshold":winner_row.get("take_threshold"),
        "policy_schema":policy.get("schema") if policy else None,"decision_policy":policy,
        "deployment":cfg.get("deployment"),"label_policy":cfg.get("label"),"research_window":sm.get("research_window") or cfg.get("research_window"),"cv_selection":winner_row,"cv_acceptance":sm.get("cv_acceptance"),
        "locked_test_classification":final["class_test"],"locked_test_trading":final["trade_test"],"kpi_schema":"KPI_V5_HIERARCHICAL",
        "kpi_acceptance":final["kpi_acceptance"],"kpi_report":final["kpi_report"],"onnx_parity":final["parity"],"onnx_sha256":sha256_file(final["onnx_path"]),"temporal_onnx_sha256":sha256_file(final["temporal_onnx_path"]) if final.get("temporal_onnx_path") else None,"runtime_contract":final.get("runtime_contract"),
        "policy_sha256":sha256_file(final["policy_path"]) if final.get("policy_path") else None,
        "source_csv_sha256":research_hash,"research_source_csv_sha256":research_hash,
        "research_source_raw_end":str(cutoff),"fresh_input_csv_sha256":updated_hash,
        "dataset_provenance":src_dp,"fresh_input_provenance":new_prov,
        "symbol":new_prov["symbol"],"period":new_prov["period"],"timeframe":new_prov["timeframe"],
        "source_start":src_dp.get("source_start",sm.get("source_start")),"source_end":str(cutoff),
        "training_memory":final.get("training_memory"),"train_rows":int(final.get("effective_train_rows",len(old_train))),"locked_test_rows":int(len(fresh)),"generated_utc":datetime.now(timezone.utc).isoformat(),"current_ea_input_shape":candidate_input_shape(spec,len(FEATURES)),"onnx_output_shape":[1,3],
        "agent":{"experiments_completed":0,"experiment_budget":0,"stop_reason":"FRESH_MODEL_VALIDATION","llm_scientist_enabled":False,"locked_test_opened_once":True,"planner":"fresh_model_v1"},
    }
    if status=="ELIGIBLE_CHALLENGER":
        manifest=register_eligible_challenger(out,manifest,MODELLAB_ROOT)
    _write_json(out/"model_manifest.json",manifest); next_required="MT5_PARITY" if final["passed"] else "FEATURE_LABEL_AUDIT_OR_NEW_HYPOTHESIS"
    _write_json(out/"supervisor_state.json",{"stage":manifest["supervisor_stage"],"run_id":run_id,"candidate":spec.name,"next_required":next_required,"updated_utc":datetime.now(timezone.utc).isoformat()})
    with (out/"REPORT.md").open("w",encoding="utf-8") as f:
        f.write(f"# Fresh Frozen-Model Validation {run_id}\n\n**Source run:** {sm.get('run_id')}\n\n**Status:** {status}\n\nFresh rows strictly after `{cutoff}`: {len(fresh):,}.\n\n**Next required:** {next_required}.\n")
    _emit(progress,"done",1,1,f"{status} · fresh frozen model",run=str(out),status=status,winner=spec.name)
    return {"run":str(out),"status":status,"winner":spec.name,"reasons":final["reasons"],"manifest":manifest}

def _fresh_registry_path(out_dir: str|Path) -> Path:
    return Path(out_dir).resolve().parent / "governance" / "fresh_holdout_registry.json"


def validate_frozen_policy_on_fresh_data(policy_run_dir, updated_csv_path, config_path="config.json", out_dir="runs", progress: ProgressCallback=None):
    """Validate a frozen model+policy on rows strictly newer than source_raw_end."""
    policy_run = Path(policy_run_dir)
    pm = _load_json(policy_run / "model_manifest.json")
    if pm.get("status") != "POLICY_CV_PASS_NEEDS_FRESH_HOLDOUT":
        raise ValueError("Run ini belum memiliki frozen policy yang PASS OOF")
    policy = dict(pm.get("decision_policy") or {})
    if not policy:
        raise ValueError("Frozen policy tidak ditemukan")
    source_run_id = str(pm.get("source_run_id") or "")
    source_run = Path(out_dir) / source_run_id
    if not source_run.exists():
        raise ValueError(f"Source training run tidak ditemukan: {source_run_id}")
    source_labeled = source_run / "labeled_dataset.csv"
    if not source_labeled.exists():
        raise ValueError("Source labeled_dataset.csv tidak ditemukan. Jangan rebuild dengan data baru karena itu mengubah training authority.")

    cfg = _policy_research_cfg(source_run, config_path)
    src_manifest = _load_json(source_run / "model_manifest.json")
    policy_auth = _research_authority(pm)
    source_auth = _research_authority(src_manifest)
    research_hash = str(policy_auth.get("sha256") or source_auth.get("sha256") or "")
    cutoff_raw = policy_auth.get("cutoff") or source_auth.get("cutoff")
    if not cutoff_raw:
        raise ValueError("Research cutoff authority tidak ditemukan; fail-closed")
    cutoff = pd.Timestamp(str(cutoff_raw))
    updated_csv_path = str(updated_csv_path)
    raw_new = load_training_csv(updated_csv_path)
    new_prov = _dataset_provenance(raw_new,updated_csv_path)
    src_dp = src_manifest.get("dataset_provenance") or {}
    if not src_dp:
        old_head=pd.read_csv(source_labeled,usecols=["symbol","period"],nrows=1); src_dp={"symbol":str(old_head["symbol"].iloc[0]),"period":int(old_head["period"].iloc[0])}
    if str(src_dp.get("symbol")) != new_prov["symbol"] or int(src_dp.get("period")) != int(new_prov["period"]):
        raise ValueError(f"Fresh dataset identity mismatch. Source {src_dp.get('symbol')} {_period_label(src_dp.get('period'))}; input {new_prov['symbol']} {new_prov['timeframe']}")
    new_end = pd.to_datetime(raw_new["signal_time"], errors="coerce").max()
    if pd.isna(new_end) or new_end <= cutoff:
        raise ValueError(f"Dataset belum lebih baru dari source cutoff {cutoff}")
    readiness = fresh_readiness(updated_csv_path, cutoff, cfg)
    if readiness["status"] != "READY":
        raise ValueError(
            f"Fresh data belum siap [{readiness['status']}]. cutoff={cutoff}; "
            f"raw_new={readiness['raw_new_rows']}; mature={readiness['mature_raw_rows']}; "
            f"labeled={readiness['labeled_fresh_rows']}; pending_horizon={readiness['pending_horizon_rows']}; "
            f"horizon={readiness['horizon_bars']} bars; newest={readiness['newest']}"
        )
    labeled_new = build_labels(raw_new, cfg)
    ts_new = pd.to_datetime(labeled_new["signal_time"], errors="coerce")
    fresh = labeled_new.loc[ts_new > cutoff].copy()

    old_train = pd.read_csv(source_labeled)
    if old_train.empty:
        raise ValueError("Source training rows kosong")
    # The old locked test is retired and may now join training, but fresh rows never do.
    spec = CandidateSpec(str(pm["model_family"]), str(pm["model_name"]), dict(pm.get("hyperparameters") or {}))
    winner_row = dict(pm.get("cv_selection") or {})
    winner_row["take_threshold"] = float(policy.get("take_threshold", winner_row.get("take_threshold", 0.65)))

    updated_hash = sha256_file(updated_csv_path)
    key_raw = json.dumps({"policy_run": pm.get("run_id"), "updated_csv_sha256": updated_hash, "cutoff": str(cutoff)}, sort_keys=True).encode("utf-8")
    key = hashlib.sha256(key_raw).hexdigest()
    reg_path = _fresh_registry_path(out_dir)
    reg = _load_holdouts(reg_path)
    if key in reg.get("holdouts", {}):
        prior = reg["holdouts"][key]
        raise ValueError(f"Fresh holdout ini sudah pernah dibuka oleh {prior.get('run_id')}. Gunakan data yang lebih baru.")

    run_id = datetime.now(timezone.utc).strftime("FRESH_%Y%m%d_%H%M%S_UTC")
    out = Path(out_dir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    cfg["evaluation_stage"]="FRESH"
    _write_json(out / "run_config.json", cfg)
    _register_holdout_open(reg_path, key, run_id, updated_hash)
    _emit(progress, "winner", 0, 1, f"Fresh holdout · {len(fresh):,} unseen {new_prov['timeframe']} rows · frozen model+policy")
    final = _finalize(spec, winner_row, old_train, fresh, cfg, out, updated_csv_path, progress=progress, policy=policy)
    status = "ELIGIBLE_CHALLENGER" if final["passed"] else "REJECTED"
    manifest = {
        "run_id": run_id,
        "run_type": "FRESH_HOLDOUT_VALIDATION",
        "status": status,
        "supervisor_stage": "WAITING_MT5_PARITY" if final["passed"] else "RESEARCH_REJECTED",
        "reject_reasons": final["reasons"],
        "source_run_id": source_run_id,
        "policy_run_id": pm.get("run_id"),
        "fresh_cutoff_exclusive": str(cutoff),
        "fresh_data_end": str(new_end),
        "fresh_holdout_rows": int(len(fresh)),
        "fresh_readiness": readiness,
        "research_window": pm.get("research_window") or src_manifest.get("research_window") or cfg.get("research_window"),
        "feature_contract": CONTRACT_ID,
        "feature_count": len(FEATURES),
        "feature_order": FEATURES,
        "class_order": ["SELL", "SKIP", "BUY"],
        "model_family": spec.family,
        "model_name": spec.name,
        "hyperparameters": spec.params,
        "take_threshold": policy.get("take_threshold"),
        "policy_schema": policy.get("schema"),
        "decision_policy": policy,
        "deployment": cfg.get("deployment"),
        "label_policy": cfg.get("label"),
        "cv_selection": winner_row,
        "cv_acceptance": pm.get("cv_acceptance"),
        "locked_test_classification": final["class_test"],
        "locked_test_trading": final["trade_test"],
        "kpi_schema": "KPI_V5_HIERARCHICAL",
        "kpi_acceptance": final["kpi_acceptance"],
        "kpi_report": final["kpi_report"],
        "onnx_parity": final["parity"],
        "onnx_sha256": sha256_file(final["onnx_path"]),
        "temporal_onnx_sha256": sha256_file(final["temporal_onnx_path"]) if final.get("temporal_onnx_path") else None,
        "runtime_contract": final.get("runtime_contract"),
        "policy_sha256": sha256_file(final["policy_path"]) if final.get("policy_path") else None,
        "source_csv_sha256": research_hash, "research_source_csv_sha256": research_hash,
        "research_source_raw_end": str(cutoff), "fresh_input_csv_sha256": updated_hash,
        "dataset_provenance": src_dp, "fresh_input_provenance": new_prov,
        "symbol": new_prov["symbol"], "period": new_prov["period"], "timeframe": new_prov["timeframe"],
        "source_start": src_dp.get("source_start", src_manifest.get("source_start")), "source_end": str(cutoff),
        "training_memory": final.get("training_memory"),
        "train_rows": int(final.get("effective_train_rows",len(old_train))),
        "locked_test_rows": int(len(fresh)),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "current_ea_input_shape": candidate_input_shape(spec,len(FEATURES)),
        "onnx_output_shape": [1, 3],
        "agent": {"experiments_completed": 0, "experiment_budget": 0, "stop_reason": "FRESH_HOLDOUT_VALIDATION", "llm_scientist_enabled": False, "locked_test_opened_once": True, "planner": "fresh_holdout_v1"},
    }
    if status == "ELIGIBLE_CHALLENGER":
        manifest = register_eligible_challenger(out, manifest, MODELLAB_ROOT)
    _write_json(out / "model_manifest.json", manifest)
    next_required = "MT5_PARITY" if final["passed"] else "FEATURE_LABEL_AUDIT_OR_NEW_HYPOTHESIS"
    _write_json(out / "supervisor_state.json", {"stage": manifest["supervisor_stage"], "run_id": run_id, "candidate": spec.name, "next_required": next_required, "updated_utc": datetime.now(timezone.utc).isoformat()})
    with (out / "REPORT.md").open("w", encoding="utf-8") as f:
        f.write(f"# Fresh Holdout Validation {run_id}\n\n**Status:** {status}\n\n**Policy run:** {pm.get('run_id')}\n\n")
        f.write(f"Fresh rows strictly after `{cutoff}`: {len(fresh):,}.\n\n**Next required:** {next_required}.\n")
    _emit(progress, "done", 1, 1, f"{status} · fresh holdout", run=str(out), status=status, winner=spec.name)
    return {"run": str(out), "status": status, "winner": spec.name, "reasons": final["reasons"], "manifest": manifest}
