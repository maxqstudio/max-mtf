from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import os
import re
import tempfile
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scientist.knowledge.scientist_knowledge import load_knowledge, compact_context, sync_status
from scientist.python.scientist_python_runtime import (
    analysis_capability_instruction,
    authorized_analysis_inputs,
    parse_python_analysis_request,
    python_analysis_evidence_for_llm,
    run_scientist_python_analysis,
    scientist_python_health,
)

from host.provider_catalog import (
    chat_completion,
    stream_chat_completion,
    extract_chat_text,
    extract_token_usage,
    estimate_api_cost_usd,
    fallback_error_category,
    normalize_base_url,
)

CHAT_SCHEMA = "MAX_SCIENTIST_CHAT_V2_THREAD"
CONTEXT_SCHEMA = "MAX_SCIENTIST_CHAT_CONTEXT_V1"
MAX_HISTORY_MESSAGES = 80
MAX_REQUEST_HISTORY_MESSAGES = 16
MAX_REQUEST_HISTORY_CHARS = 28000
MAX_CONTEXT_CHARS = 60000

# Deliberately no imports from factory_control/champion_factory/factory_jobs. This module
# has no Factory/control execution surface. Its only optional execution capability is the
# shared guarded Scientist Python analytical runtime, which cannot mutate Factory authority.


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else deepcopy(default)


def _read_jsonl_tail(path: Path, limit: int = 18) -> list[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()[-max(1, int(limit)):]
    except Exception:
        return []
    out: list[dict] = []
    for line in lines:
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def _compact_rows(rows: Any, limit: int = 16) -> list[dict]:
    if not isinstance(rows, list):
        return []
    keep = (
        "candidate_id", "pool_id", "family", "status", "pass", "accepted", "rank",
        "first_failed_gate", "failed_gates", "overall_expectancy_r", "median_expectancy_r", "worst_expectancy_r",
        "profit_factor", "median_profit_factor", "max_drawdown_r", "median_max_drawdown_r",
        "recovery_factor", "sharpe", "psr", "dsr", "cvar", "daily_cvar_r", "trades",
        "owner_size_priority", "size_parameters", "actual_params", "score",
    )
    out: list[dict] = []
    for row in rows[: max(1, int(limit))]:
        if not isinstance(row, dict):
            continue
        clean = {k: deepcopy(row.get(k)) for k in keep if k in row}
        if not clean:
            # Keep only a shallow, bounded fallback rather than dumping arbitrary evidence.
            clean = {str(k): deepcopy(v) for k, v in list(row.items())[:18]}
        out.append(clean)
    return out


def _source(sources: list[dict], source_id: str, path: Path, note: str) -> None:
    if not Path(path).exists():
        return
    sources.append({"id": source_id, "file": Path(path).name, "note": note})


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _strict_json(path: Path) -> Any:
    path=Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"SCIENTIST_CHAT_EVIDENCE_MISSING: {path.name}")
    except Exception as exc:
        raise RuntimeError(f"SCIENTIST_CHAT_EVIDENCE_CORRUPT: {path.name}: {type(exc).__name__}") from exc


def _verify_read_only_stage_seal(fd: Path, manifest: dict, stage: str, meta_key: str, required_artifact: str) -> dict:
    """Verify immutable downstream evidence without importing execution authority."""
    meta=manifest.get(meta_key) if isinstance(manifest.get(meta_key),dict) else {}
    if not meta:
        raise RuntimeError(f"SCIENTIST_CHAT_{stage}_MANIFEST_AUTHORITY_MISSING")
    contract=meta.get("stage_contract") if isinstance(meta.get("stage_contract"),dict) else None
    claimed_contract_hash=str(meta.get("stage_contract_hash") or "")
    claimed_seal_hash=str(meta.get("terminal_seal_hash") or "")
    seal_name=str(meta.get("terminal_seal_file") or f"{stage.lower()}_terminal_seal.json")
    if not contract or not claimed_contract_hash or not claimed_seal_hash:
        raise RuntimeError(f"SCIENTIST_CHAT_{stage}_SEAL_BINDING_MISSING")
    if _stable_hash(contract) != claimed_contract_hash:
        raise RuntimeError(f"SCIENTIST_CHAT_{stage}_MANIFEST_CONTRACT_DRIFT")
    seal=_strict_json(fd/seal_name)
    if not isinstance(seal,dict) or str(seal.get("stage") or "").upper()!=stage.upper():
        raise RuntimeError(f"SCIENTIST_CHAT_{stage}_TERMINAL_SEAL_INVALID")
    check=deepcopy(seal); seal_hash=str(check.pop("seal_hash","") or "")
    if not seal_hash or _stable_hash(check)!=seal_hash:
        raise RuntimeError(f"SCIENTIST_CHAT_{stage}_TERMINAL_SEAL_HASH_MISMATCH")
    if seal_hash != claimed_seal_hash:
        raise RuntimeError(f"SCIENTIST_CHAT_{stage}_SEAL_NOT_BOUND_TO_MANIFEST")
    if str(seal.get("contract_hash") or "") != claimed_contract_hash:
        raise RuntimeError(f"SCIENTIST_CHAT_{stage}_CONTRACT_DRIFT")
    artifacts=seal.get("artifacts") if isinstance(seal.get("artifacts"),dict) else {}
    if required_artifact not in artifacts:
        raise RuntimeError(f"SCIENTIST_CHAT_{stage}_ARTIFACT_NOT_SEALED: {required_artifact}")
    for name,expected_hash in artifacts.items():
        q=fd/str(name)
        if not q.exists() or _sha_file(q)!=str(expected_hash):
            raise RuntimeError(f"SCIENTIST_CHAT_{stage}_ARTIFACT_TAMPER: {name}")
    return seal


def _latest_generation_rows(factory_dir: Path) -> tuple[list[dict], str | None]:
    rd = Path(factory_dir) / "research_runs"
    if not rd.exists():
        return [], None
    candidates = sorted([p for p in rd.iterdir() if p.is_dir() and (p / "cv_leaderboard.json").exists()], key=lambda p: p.name)
    if not candidates:
        return [], None
    latest = candidates[-1]
    rows = _read_json(latest / "cv_leaderboard.json", [])
    return _compact_rows(rows, 18), latest.name




_SENSITIVE_SETTING_TOKENS = ("api_key", "apikey", "secret", "password", "token", "credential")

def _safe_setting_value(value: Any) -> Any:
    """Return a JSON-safe research-setting value with secret-like fields removed."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return deepcopy(value)
    if isinstance(value, list):
        return [_safe_setting_value(v) for v in value]
    if isinstance(value, tuple):
        return [_safe_setting_value(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            sk = str(key)
            lk = sk.lower()
            if any(tok in lk for tok in _SENSITIVE_SETTING_TOKENS):
                continue
            out[sk] = _safe_setting_value(val)
        return out
    return str(value)

def build_research_settings_snapshot(cfg: dict | None) -> dict:
    """Expose research configuration to Scientist Chat as read-only advisory context.

    The snapshot deliberately excludes credentials and execution endpoints.  It
    distinguishes editable/current Owner configuration from the frozen Factory
    research_plan that is added separately by build_read_only_context().
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    agent = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    llm = agent.get("llm") if isinstance(agent.get("llm"), dict) else {}
    arch = cfg.get("research_architecture") if isinstance(cfg.get("research_architecture"), dict) else {}
    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    allowed = [str(x) for x in (arch.get("allowed_families") or []) if str(x)]
    model_cfg = {}
    for family in allowed:
        if family in models:
            model_cfg[family] = _safe_setting_value(models.get(family))
    # Preserve baseline/support settings that are scientifically relevant even
    # when they are not listed in allowed_families.
    for family in ("gru_patience", "hybrid_oof_inner_folds", "hybrid_note", "adaptive_note"):
        if family in models:
            model_cfg[family] = _safe_setting_value(models.get(family))

    autonomous_stack = []
    for entry in llm.get("stack") or []:
        if not isinstance(entry, dict):
            continue
        autonomous_stack.append({
            "provider": entry.get("provider"),
            "model": entry.get("model"),
            "enabled": bool(entry.get("enabled", True)),
        })

    return {
        "schema": "MAX_RESEARCH_SETTINGS_SNAPSHOT_V1",
        "authority": {
            "read_only": True,
            "can_modify_settings": False,
            "purpose": "Scientist Chat may inspect and recommend settings; Owner remains the only settings authority.",
            "active_factory_uses_frozen_research_plan": True,
        },
        "owner_current_config": {
            "seed": _safe_setting_value(cfg.get("seed")),
            "cpu_threads": _safe_setting_value(cfg.get("cpu_threads")),
            "label": _safe_setting_value(cfg.get("label") or {}),
            "split": _safe_setting_value(cfg.get("split") or {}),
            "acceptance": _safe_setting_value(cfg.get("acceptance") or {}),
            "gate_kpis": _safe_setting_value(cfg.get("gate_kpis") or {}),
            "strategy_optimizer_kpi": _safe_setting_value(((cfg.get("strategy_optimizer") or {}).get("kpi") or {})),
            "score_policy": _safe_setting_value(cfg.get("score_policy") or {}),
            "trade_sample_policy": _safe_setting_value(cfg.get("trade_sample_policy") or {}),
            "champion_factory": _safe_setting_value(cfg.get("champion_factory") or {}),
            "compute": _safe_setting_value(cfg.get("compute") or {}),
            "research_architecture": _safe_setting_value(arch),
            "agent_research": {
                "max_experiments": _safe_setting_value(agent.get("max_experiments")),
                "round_size": _safe_setting_value(agent.get("round_size")),
                "max_rounds": _safe_setting_value(agent.get("max_rounds")),
                "patience_rounds": _safe_setting_value(agent.get("patience_rounds")),
                "min_improvement": _safe_setting_value(agent.get("min_improvement")),
                "min_experiments_before_stop": _safe_setting_value(agent.get("min_experiments_before_stop")),
                "search": _safe_setting_value(agent.get("search") or {}),
                "policy_discovery": _safe_setting_value(agent.get("policy_discovery") or {}),
                "window_discovery": _safe_setting_value(agent.get("window_discovery") or {}),
                "research_memory": _safe_setting_value(agent.get("research_memory") or {}),
                "fidelity_ladder": _safe_setting_value(agent.get("fidelity_ladder") or {}),
                "experiment_blocks": _safe_setting_value(agent.get("experiment_blocks") or {}),
                "promotion": _safe_setting_value(agent.get("promotion") or {}),
            },
            "model_family_config": model_cfg,
            "autonomous_scientist_llm": {
                "enabled": bool(llm.get("enabled", False)),
                "scientist_scope": llm.get("scientist_scope"),
                "max_proposals_per_round": llm.get("max_proposals_per_round"),
                "hypothesis_kinds": _safe_setting_value(llm.get("hypothesis_kinds") or []),
                "fallback_on": _safe_setting_value(llm.get("fallback_on") or []),
                "model_health_enabled": bool(llm.get("model_health_enabled", False)),
                "stack": autonomous_stack,
            },
        },
    }

def build_read_only_context(
    factory_dir: str | Path | None,
    *,
    scope: str = "AUTO",
    live_job: dict | None = None,
    live_candidates: list[dict] | None = None,
    research_settings: dict | None = None,
    live_hardware: dict | None = None,
    live_compute_plan: dict | None = None,
) -> dict:
    """Build an evidence snapshot safe for discussion-only chat.

    The active locked/fresh Forward evidence is deliberately excluded. The chat sees the
    same research-side evidence class as the running Scientist, not unseen holdout data.
    """
    scope = str(scope or "AUTO").upper()
    fd = Path(factory_dir) if factory_dir else None
    sources: list[dict] = []
    ctx: dict[str, Any] = {
        "schema": CONTEXT_SCHEMA,
        "mode": "READ_ONLY_DISCUSSION",
        "scope": scope,
        "created_utc": utcnow(),
        "authority": {
            "can_execute": False,
            "can_modify_research": False,
            "can_modify_settings": False,
            "can_promote": False,
            "tools": [],
            "locked_or_fresh_forward_evidence_exposed": False,
        },
        "sources": sources,
    }
    # Max-native static capability/workflow knowledge is always available to Chat.
    # It describes what Max already supports and its immutable governance boundaries;
    # it is not evidence that a particular live run has reached/passed a stage.
    knowledge = load_knowledge()
    if isinstance(knowledge, dict) and knowledge.get("schema"):
        ctx["max_knowledge"] = compact_context(knowledge)
        ksync = sync_status(knowledge)
        ctx["max_knowledge_sync"] = {"in_sync": bool(ksync.get("in_sync")), "changed_count": len(ksync.get("changed") or [])}
        sources.append({
            "id": "MAXKB",
            "file": "SCIENTIST_KNOWLEDGE_BASE.json",
            "note": "Static Max capability/workflow/novelty knowledge; use it to avoid duplicate recommendations, not as live stage evidence",
        })
    else:
        ctx["max_knowledge"] = {"status": "UNAVAILABLE"}
        ctx["max_knowledge_sync"] = {"in_sync": False, "changed_count": None}

    include_settings = scope in {"AUTO", "CURRENT FACTORY", "RESEARCH SETTINGS", "FULL FACTORY"}
    if include_settings and isinstance(research_settings, dict) and research_settings:
        ctx["research_settings"] = deepcopy(research_settings)
        sources.append({
            "id": "SETTINGS",
            "file": "loaded research configuration",
            "note": "Sanitized current Owner research settings; advisory/read-only in Scientist Chat",
        })

    # Current-host hardware truth must be available even before the first Factory exists.
    # Owner configuration describes what is allowed/requested; it is not evidence that a
    # GPU/runtime is actually present.  Keep live host truth separate from any frozen
    # Factory hardware snapshot so Scientist recommendations never confuse the two.
    if isinstance(live_hardware, dict) and live_hardware:
        cpu = live_hardware.get("cpu") or {}
        mem = live_hardware.get("memory") or {}
        nvidia = live_hardware.get("nvidia") or {}
        torch = live_hardware.get("torch") or {}
        devices=[]
        for row in list(nvidia.get("devices") or [])[:4]:
            if not isinstance(row,dict):
                continue
            devices.append({
                "name": row.get("name"),
                "memory_total_gib": row.get("memory_total_gib"),
                "memory_free_gib": row.get("memory_free_gib"),
            })
        ctx["live_hardware"] = {
            "schema": "MAX_SCIENTIST_LIVE_HARDWARE_V1",
            "authority": "DETECTED_CURRENT_HOST",
            "status": live_hardware.get("status") or "AVAILABLE",
            "error_class": live_hardware.get("error_class"),
            "captured_utc": live_hardware.get("captured_utc"),
            "profile_hash": live_hardware.get("profile_hash"),
            "os": {
                "system": (live_hardware.get("os") or {}).get("system"),
                "release": (live_hardware.get("os") or {}).get("release"),
            },
            "cpu": {
                "name": cpu.get("name"),
                "physical_cores": cpu.get("physical_cores"),
                "logical_threads": cpu.get("logical_threads"),
                "planning_cores": cpu.get("planning_cores"),
                "core_count_source": cpu.get("core_count_source"),
                "architecture": cpu.get("architecture"),
            },
            "memory": {
                "total_gib": mem.get("total_gib"),
                "available_gib": mem.get("available_gib"),
                "source": mem.get("source"),
            },
            "nvidia": {"detected": bool(nvidia.get("detected")), "devices": devices},
            "torch": {
                "installed": bool(torch.get("installed")),
                "torch_version": torch.get("torch_version"),
                "cuda_available": bool(torch.get("cuda_available")),
                "cuda_version": torch.get("cuda_version"),
            },
        }
        sources.append({
            "id": "LIVE_HW",
            "file": "current host hardware probe",
            "note": "Current-host detected hardware truth; use this instead of inferring hardware from allowed compute settings",
        })

    if isinstance(live_compute_plan, dict) and live_compute_plan:
        caps=live_compute_plan.get("capabilities") or {}
        torch_cap=caps.get("torch") or {}
        opencl_cap=caps.get("opencl") or {}
        vulkan_cap=caps.get("vulkan") or {}
        xgb_cap=caps.get("xgboost_cuda") or {}
        lgb_cap=caps.get("lightgbm_gpu") or {}
        ctx["live_compute_plan"] = {
            "schema": "MAX_SCIENTIST_LIVE_COMPUTE_V1",
            "authority": "RESOLVED_CURRENT_HOST_PLUS_OWNER_CONFIG",
            "status": live_compute_plan.get("status") or "AVAILABLE",
            "error_class": live_compute_plan.get("error_class"),
            "mode": live_compute_plan.get("mode"),
            "fallback_cpu": bool(live_compute_plan.get("fallback_cpu", True)),
            "temporal_dl": deepcopy(live_compute_plan.get("temporal_dl") or {}),
            "xgboost": deepcopy(live_compute_plan.get("xgboost") or {}),
            "lightgbm": deepcopy(live_compute_plan.get("lightgbm") or {}),
            "random_forest": deepcopy(live_compute_plan.get("random_forest") or {}),
            "vulkan": deepcopy(live_compute_plan.get("vulkan") or {}),
            "notes": deepcopy(live_compute_plan.get("notes") or []),
            "capabilities": {
                "torch_accelerator": torch_cap.get("accelerator"),
                "torch_device": torch_cap.get("torch_device"),
                "xgboost_cuda_usable": bool(xgb_cap.get("usable")),
                "lightgbm_gpu_usable": bool(lgb_cap.get("usable")),
                "opencl_device_evidence": bool(opencl_cap.get("device_evidence")),
                "vulkan_detected": bool(vulkan_cap.get("detected")),
                "cpu_usable": bool((caps.get("cpu") or {}).get("usable", True)),
            },
        }
        sources.append({
            "id": "LIVE_COMPUTE",
            "file": "resolved current-host compute plan",
            "note": "Effective training backends resolved from detected runtime capabilities plus Owner compute policy",
        })

    if not fd or not fd.exists():
        ctx["factory"] = {"status": "NO_FACTORY_CONTEXT"}
        if live_job:
            ctx["live_runtime"] = _compact_live_job(live_job)
        return ctx

    manifest = _read_json(fd / "factory_manifest.json", {})
    _source(sources, "FACTORY", fd / "factory_manifest.json", "Factory identity and committed stage/status")
    ctx["factory"] = {
        "factory_id": fd.name,
        "status": manifest.get("status"),
        "stage": manifest.get("stage"),
        "next_required": manifest.get("next_required"),
        "qualified": manifest.get("qualified") or manifest.get("pool_size"),
        "target": manifest.get("target"),
        "total_experiments": manifest.get("total_experiments"),
        "max_total_experiments": manifest.get("max_total_experiments"),
        "research_contract_hash": manifest.get("research_contract_hash"),
    }
    if live_job:
        ctx["live_runtime"] = _compact_live_job(live_job)
    if live_candidates:
        ctx["live_candidates"] = _compact_rows(live_candidates, 12)
        sources.append({"id": "LIVE", "file": "background job snapshot", "note": "Current non-authoritative UI runtime snapshot"})

    include_all = scope in {"AUTO", "CURRENT FACTORY", "FULL FACTORY"}
    if include_all or scope in {"CURRENT GENERATION", "MODEL & CANDIDATES", "RESEARCH SETTINGS"}:
        plan = _read_json(fd / "research_plan.json", {})
        if plan:
            ctx["research_plan"] = {
                "active_families": deepcopy(plan.get("active_families") or []),
                "topology_priority": deepcopy(plan.get("topology_priority") or {}),
                "family_size_priorities": deepcopy(plan.get("family_size_priorities") or {}),
                "parameter_envelopes": deepcopy(plan.get("parameter_envelopes") or {}),
                "resource_capacity": deepcopy(plan.get("resource_capacity") or {}),
            }
            _source(sources, "PLAN", fd / "research_plan.json", "Frozen deterministic research plan")
        rows, run_id = _latest_generation_rows(fd)
        if rows:
            ctx["latest_generation"] = {"run_id": run_id, "candidates": rows}
            sources.append({"id": "WFA", "file": f"research_runs/{run_id}/cv_leaderboard.json", "note": "Latest committed WFA leaderboard"})
        trials = _read_jsonl_tail(fd / "all_trials.jsonl", 18)
        if trials:
            ctx["recent_trials"] = _compact_rows(trials, 18)
            _source(sources, "TRIALS", fd / "all_trials.jsonl", "Recent committed Discovery trial ledger")

    if include_all or scope == "DATA QUALITY":
        dq = _read_json(fd / "dataset_quality_context.json", {})
        if dq:
            ctx["data_quality"] = dq
            _source(sources, "DATA", fd / "dataset_quality_context.json", "Deterministic data-quality snapshot")
        cap = _read_json(fd / "dataset_capacity_profile.json", {})
        if cap:
            ctx["dataset_capacity"] = cap
            _source(sources, "CAPACITY", fd / "dataset_capacity_profile.json", "Dataset-capacity profile")
        hw = _read_json(fd / "hardware_profile.json", {})
        if hw:
            # Hardware evidence is already compact and contains no credentials.
            ctx["hardware"] = hw
            _source(sources, "HW", fd / "hardware_profile.json", "Frozen hardware profile")

    if include_all or scope in {"MODEL & CANDIDATES", "CURRENT GENERATION"}:
        pool = _read_json(fd / "candidate_pool.json", [])
        if pool:
            ctx["candidate_pool"] = _compact_rows(pool, 18)
            _source(sources, "POOL", fd / "candidate_pool.json", "Committed WFA-qualified candidate pool")
        topo = _read_json(fd / "failure_topology.json", {})
        if topo:
            ctx["failure_topology"] = topo
            _source(sources, "FAIL", fd / "failure_topology.json", "Deterministic Discovery/WFA failure topology")
        cpcv_path=fd / "cpcv_qualification_evidence.json"
        if cpcv_path.exists():
            _verify_read_only_stage_seal(fd,manifest,"CPCV","cpcv","cpcv_qualification_evidence.json")
            cpcv = _strict_json(cpcv_path)
            if not isinstance(cpcv,dict):
                raise RuntimeError("SCIENTIST_CHAT_CPCV_EVIDENCE_INVALID")
            ctx["cpcv"] = {
                "candidates_evaluated": cpcv.get("candidates_evaluated"),
                "survivor_count": cpcv.get("survivor_count"),
                "rows": _compact_rows(cpcv.get("rows") or [], 12),
            }
            _source(sources, "CPCV", cpcv_path, "Sealed CPCV finalist evidence")
        tournament_path=fd / "tournament_leaderboard.json"
        if tournament_path.exists():
            _verify_read_only_stage_seal(fd,manifest,"TOURNAMENT","tournament","tournament_leaderboard.json")
            tournament = _strict_json(tournament_path)
            if not isinstance(tournament,list):
                raise RuntimeError("SCIENTIST_CHAT_TOURNAMENT_EVIDENCE_INVALID")
            ctx["tournament"] = _compact_rows(tournament, 12)
            _source(sources, "TOUR", tournament_path, "Sealed Tournament leaderboard")
        mc_path=fd / "monte_carlo_evidence.json"
        if mc_path.exists():
            _verify_read_only_stage_seal(fd,manifest,"MONTE_CARLO","monte_carlo","monte_carlo_evidence.json")
            mc = _strict_json(mc_path)
            if not isinstance(mc,dict):
                raise RuntimeError("SCIENTIST_CHAT_MONTE_CARLO_EVIDENCE_INVALID")
            ctx["monte_carlo"] = {"simulation_count": mc.get("simulation_count"), "rows": _compact_rows(mc.get("rows") or [], 12)}
            _source(sources, "MC", mc_path, "Sealed Monte Carlo evidence")

    if include_all or scope == "SCIENTIST MEMORY":
        journals = _read_json(fd / "stage_scientist_journal.json", [])
        if isinstance(journals, list) and journals:
            ctx["scientist_journal"] = deepcopy(journals[-8:])
            _source(sources, "SCI", fd / "stage_scientist_journal.json", "Latest committed Scientist stage reports")
        director = _read_json(fd / "research_director_journal.json", [])
        if isinstance(director, list) and director:
            ctx["research_director"] = deepcopy(director[-6:])
            _source(sources, "DIR", fd / "research_director_journal.json", "Latest committed Research Director reports")
        memory = _read_json(fd / "research_memory.json", {})
        if memory:
            # Bound memory size by selecting only scientifically useful summaries.
            ctx["research_memory"] = {
                "failure_topology": deepcopy(memory.get("failure_topology") or {}),
                "family_statistics": deepcopy(memory.get("family_statistics") or memory.get("family_stats") or {}),
                "next_discovery_plan": deepcopy(memory.get("next_discovery_plan") or {}),
                "hypothesis_lifecycle": deepcopy((memory.get("hypothesis_lifecycle") or [])[-12:]),
                "stage_feedback": deepcopy((memory.get("stage_feedback") or [])[-10:]),
            }
            _source(sources, "MEM", fd / "research_memory.json", "Bounded research memory")

    ctx["excluded"] = [
        "raw training CSV rows",
        "API credentials",
        "execution/control endpoints",
        "locked/fresh Forward evidence not available to the running Scientist",
    ]
    return ctx


def _compact_live_job(job: dict) -> dict:
    if not isinstance(job, dict):
        return {}
    ev = job.get("last_event") if isinstance(job.get("last_event"), dict) else {}
    return {
        "job_id": job.get("job_id"),
        "action": job.get("action"),
        "status": job.get("status"),
        "factory_id": job.get("factory_id") or ev.get("factory_id"),
        "generation": ev.get("factory_generation") or ev.get("generation"),
        "stage": ev.get("stage"),
        "message": ev.get("message"),
        "updated_utc": job.get("updated_utc") or ev.get("created_utc") or ev.get("timestamp"),
    }


def available_chat_models(llm_cfg: dict, connected_models: list[str] | None = None) -> list[str]:
    out: list[str] = []
    for model in connected_models or []:
        m = str(model or "").strip()
        if m and m not in out:
            out.append(m)
    for e in llm_cfg.get("stack") or []:
        if isinstance(e, dict) and e.get("enabled", True):
            m = str(e.get("model") or "").strip()
            if m and m not in out:
                out.append(m)
    m = str(llm_cfg.get("model") or "").strip()
    if m and m not in out:
        out.append(m)
    return out


def available_chat_fallback_models(llm_cfg: dict) -> list[str]:
    """Return the explicit MANUAL Scientist Chat fallback route.

    This is intentionally separate from ``llm_cfg["stack"]``.  The latter is
    autonomous Scientist/Director research routing authority and must never be
    borrowed silently by a manually selected chat model.
    """
    out: list[str] = []
    for raw in llm_cfg.get("chat_fallback_stack") or []:
        if isinstance(raw, dict):
            if not raw.get("enabled", True):
                continue
            model = str(raw.get("model") or "").strip()
        else:
            model = str(raw or "").strip()
        if model and model not in out:
            out.append(model)
    return out


def _normalized_route_entry(llm_cfg: dict, raw: dict | None, model: str) -> dict:
    raw=raw if isinstance(raw,dict) else {}
    model=str(raw.get("model") or model or "").strip()
    provider=str(raw.get("provider") or llm_cfg.get("provider") or "custom").strip() or "custom"
    base_url=normalize_base_url(str(raw.get("base_url") or raw.get("endpoint") or llm_cfg.get("base_url") or llm_cfg.get("endpoint") or ""))
    api_key_env=str(raw.get("api_key_env") or llm_cfg.get("api_key_env") or "COMPLEXPOLICY_LLM_API_KEY")
    route={"provider":provider,"base_url":base_url,"model":model,"api_key_env":api_key_env}
    route["route_id"]="|".join((provider.lower(),model,base_url.rstrip("/").lower(),api_key_env))
    return route


def _route_entry(llm_cfg: dict, model: str) -> dict:
    model = str(model or "").strip()
    for e in llm_cfg.get("stack") or []:
        if isinstance(e, dict) and str(e.get("model") or "").strip() == model:
            return _normalized_route_entry(llm_cfg,e,model)
    return _normalized_route_entry(llm_cfg,{},model)


def _chat_fallback_route_entries(llm_cfg: dict) -> list[dict]:
    """Return exact configured Chat fallback routes; never collapse to model name."""
    out=[]; seen=set()
    for raw in llm_cfg.get("chat_fallback_stack") or []:
        if isinstance(raw,dict):
            if not raw.get("enabled",True):
                continue
            entry=_normalized_route_entry(llm_cfg,raw,str(raw.get("model") or ""))
        else:
            entry=_normalized_route_entry(llm_cfg,{},str(raw or ""))
        if not entry.get("model") or entry["route_id"] in seen:
            continue
        seen.add(entry["route_id"]); out.append(entry)
    return out


def _api_key_for(entry: dict, default_api_key: str) -> str:
    env_name = str(entry.get("api_key_env") or "COMPLEXPOLICY_LLM_API_KEY")
    return (default_api_key or os.environ.get(env_name) or "").strip()


def chat_model_profile(llm_cfg: dict, model: str) -> dict:
    """Return the persisted per-model Scientist Chat profile.

    Profiles are advisory/runtime controls for Chat only. They never modify the
    autonomous Research Scientist stack or deterministic Factory authority.
    """
    profiles=llm_cfg.get("chat_model_profiles") if isinstance(llm_cfg.get("chat_model_profiles"),dict) else {}
    raw=profiles.get(str(model)) if isinstance(profiles,dict) and isinstance(profiles.get(str(model)),dict) else {}
    depth=str(raw.get("analysis_depth","DEEP") or "DEEP").upper()
    if depth not in {"QUICK","BALANCED","DEEP"}: depth="DEEP"
    defaults={
        "QUICK":{"context_chars":18000,"history_messages":6,"history_chars":8000,"max_output_tokens":4096},
        "BALANCED":{"context_chars":36000,"history_messages":10,"history_chars":16000,"max_output_tokens":8192},
        "DEEP":{"context_chars":60000,"history_messages":16,"history_chars":28000,"max_output_tokens":12288},
    }[depth]
    def _ival(key,default,lo,hi):
        try: v=int(raw.get(key,default) or default)
        except Exception: v=int(default)
        return max(lo,min(hi,v))
    try: temp=float(raw.get("temperature",llm_cfg.get("chat_temperature",0.20)) or 0.20)
    except Exception: temp=0.20
    return {
        "analysis_depth":depth,
        "temperature":max(0.0,min(1.5,temp)),
        "timeout_sec":_ival("timeout_sec",int(llm_cfg.get("timeout_sec",60) or 60),10,180),
        "max_output_tokens":_ival("max_output_tokens",defaults["max_output_tokens"],256,32768),
        "context_chars":_ival("context_chars",defaults["context_chars"],4000,120000),
        "history_messages":_ival("history_messages",defaults["history_messages"],0,32),
        "history_chars":_ival("history_chars",defaults["history_chars"],0,60000),
        "streaming":bool(raw.get("streaming",True)),
        "stream_fallback_to_buffered":bool(raw.get("stream_fallback_to_buffered",True)),
    }


def _compatible_kwargs(callable_obj, kwargs: dict) -> dict:
    """Adapt legacy local adapters before invocation; never retry after provider code ran."""
    try:
        sig=inspect.signature(callable_obj)
    except (TypeError,ValueError):
        return dict(kwargs)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return dict(kwargs)
    return {k:v for k,v in kwargs.items() if k in sig.parameters}


def _buffered_chat_call(entry: dict, api_key: str, messages: list[dict], profile: dict) -> dict:
    kwargs=_compatible_kwargs(chat_completion,{
        "temperature":float(profile["temperature"]),
        "timeout":int(profile["timeout_sec"]),
        "max_tokens":int(profile["max_output_tokens"]),
    })
    return chat_completion(entry["base_url"],entry["model"],_api_key_for(entry,api_key),messages,**kwargs)


def _stream_chat_call(entry: dict, api_key: str, messages: list[dict], profile: dict, on_delta) -> dict:
    kwargs=_compatible_kwargs(stream_chat_completion,{
        "temperature":float(profile["temperature"]),
        "timeout":int(profile["timeout_sec"]),
        "max_tokens":int(profile["max_output_tokens"]),
        "on_delta":on_delta,
    })
    return stream_chat_completion(entry["base_url"],entry["model"],_api_key_for(entry,api_key),messages,**kwargs)


def _is_preanswer_stream_capability_failure(exc: BaseException, *, saw_visible_delta: bool) -> bool:
    return (not saw_visible_delta) and str(getattr(exc,"category","") or "").upper() in {"STREAM_UNSUPPORTED","STREAM_CAPABILITY"}


def _process_step(phase: str) -> str:
    return {
        "BUILDING_CONTEXT":"Reading research evidence",
        "CALLING_MODEL":"Calling selected Scientist model",
        "WAITING_FIRST_TOKEN":"Waiting for first response token",
        "STREAMING":"Writing analysis",
        "BUFFERED_RESPONSE":"Finalizing buffered response",
        "PYTHON_ANALYSIS":"Running bounded Python analysis",
        "COMPLETED":"Analysis complete",
    }.get(str(phase or "").upper(),str(phase or "Scientist working").replace("_"," ").title())


def _chat_system_prompt() -> str:
    return (
        "You are Max Scientist Chat, a READ-ONLY quantitative research discussion room. "
        "You may explain, critique, compare, diagnose, and recommend ideas from the supplied evidence. "
        "You have NO Factory/control execution authority and NO ability to start/pause/stop/abort research, change settings, "
        "admit candidates, write arbitrary files, call MT5, compile models, promote a Champion, or alter risk/research authority. "
        "Your only optional execution support is the host-governed Scientist Python analytical capability described separately; it is ANALYTICAL_EVIDENCE_ONLY and never deterministic authority. "
        "Never claim that you performed an action. If the user asks you to execute or change something, explain the proposed change only. "
        "Treat deterministic evidence as authority and clearly distinguish evidence from inference. "
        "Never invent a cause, anomaly, warning detail, metric, stage result, or next-step fact that is absent from CURRENT READ-ONLY RESEARCH CONTEXT. "
        "If context gives a status such as VALID_WITH_WARNINGS but does not contain the warning reasons, explicitly say that the warning details are not available in the supplied context. "
        "Do not give hypothetical causes/examples unless the user explicitly asks for hypotheses; label any such content as hypothesis, not evidence. "
        "Do not infer locked/fresh Forward results that are absent from the supplied context. "
        "Never reveal chain-of-thought, hidden reasoning, scratchpad, or tags such as <think>, <thought>, <analysis>, or <reasoning>. "
        "You may inspect research_settings and recommend better settings when the user asks. Distinguish CURRENT OWNER CONFIG from the FROZEN ACTIVE research_plan. "
        "When LIVE_HW and LIVE_COMPUTE are present, they are the current-host hardware/runtime authority: use them directly, do not ask the Owner to repeat hardware specs already supplied, and do not infer a GPU merely because CUDA/ROCm/Vulkan/OpenCL are allowed in settings. "
        "Distinguish detected hardware/runtime capability from configured allowances, and distinguish both from any frozen Factory hardware/resource plan. "
        "For an active Factory, never imply that changing current UI/config mutates the frozen plan; state whether a recommendation applies only to the next Factory. "
        "KPI authority for ONNX Factory Research is PER GATE: Discovery, CPCV, Tournament, Monte Carlo, and Fresh Forward each own independent thresholds; Champion is a deterministic promotion/integrity/runtime contract, not a sixth statistical market gate. "
        "Max MTF v2.0 is a separate project forked from closed single-TF v1.4.5. At bootstrap Strategy Champion=null and Model Champion=null; BASELINE-MTF-V2 is active but is not a Champion. MTF-1 data foundation is implemented: M5 is the sole canonical OHLCV value authority; M15/H1/H4 are rebuilt from M5 using native MT5 higher-TF boundaries and parity only; alignment is closed-bar causal in UTC; future M5 directional use and market-bar forward fill are forbidden. MTF research/strategy activation remains disabled until later phases. The active EA is EA_v2_00/baseline/Max_MTF.mq5 and deployment must target a verified MT5 terminal data root, never raw C:\\. Strategy Optimizer is a separate upstream MT5 EA parameter-search tool before Research. Its KPI and H1 trade-frequency baseline are not Research KPI. Use research_settings.strategy_optimizer_kpi as the live Optimizer KPI authority; do not substitute Research gate thresholds. Its EA authority is the active package Max MTF v2.0 baseline EA and Max must never substitute an unrelated terminal EA. During search MT5 genetic fitness is Custom max from Max OnTester arithmetic Mean R, so Result=Mean R. Weighted R = sum(net P/L)/sum(initial risk) is transported per pass through MT5 optimization frames and is a separate frozen Python hard gate; Recovery Factor remains an independent hard gate sourced from the dedicated MT5 Recovery Factor statistic. v0.8.9 disables MT5 optimization-cache reuse for this frame-dependent evidence; an XML row without Weighted-R frame evidence is never Champion-eligible, and a native-gate-passing unresolved contender blocks promotion until revalidated. v0.9.0 established transactional EA↔Max_MTF.set parity for direct Champion commit. v0.11.0 supersedes automatic Strategy promotion: an eligible Optimizer winner becomes a human-readable Strategy Challenger EA + fixed .set + KPI/setup metadata, terminal state STRATEGY_CHALLENGER_FOUND, while current Max_MTF.mq5/Max_MTF.set/Python strategy authority remain unchanged. Only explicit Owner PROMOTE TO STRATEGY CHAMPION may atomically replace canonical Max_MTF.mq5, canonical Max_MTF.set, compile/deploy and Python geometry authority; on success the former Champion becomes a new uniquely coded Strategy Challenger, and on failure the old Champion authority is restored. In v0.9.1, Data Quality source-backed gap repair must not reuse canonical Champion Max_MTF.set implicitly because that preset disables training output; Max creates a dedicated Max_MTF_GapRepair.set from the Champion preset, forces Max_MTF_Training.csv writing ON, requires the exact verified MT5 terminal to be closed before startup /config launch, and considers repair complete only after a fresh broker audit proves missing=0. v0.11.2 stages Data Quality before Research: AUDIT and the initial Auto Research preflight are local/exact-SHA-cache only and must not initialize/open MT5; if that stage PASSes, Research starts directly. Only a repairable FAIL enters REPAIR / VERIFY WITH MT5, which may open the selected terminal, preserve UTF-16/UTF-8 Max_MTF.set encoding while creating Max_MTF_GapRepair.set, run the verified writer, re-audit missing=0, and cache broker proof only for the exact repaired CSV SHA. v0.9.1 also exposes generic Champion/Shadow ONNX model-family identity for all deployable tree/temporal families; Max_MTF_Champion_Trades.csv is actual MT5 deal audit only, while Max_MTF_Shadow_Trades.csv contains non-executing Challenger entry candidates explicitly marked executed=0. These audit CSVs never own PASS/FAIL, sizing, strategy geometry, or optimizer fitness and are disabled in native optimization/gap-repair presets. v0.10.0 separates Research Challenger from Production Champion: eligible research outputs receive unique human-readable family+UTC Challenger filenames without hashes, are listed with KPI evidence on the Champion page, may be copied to MT5 for Owner-selected Shadow by filename without Python changing EA inputs, and require explicit Owner promotion after all deterministic promotion gates PASS. The Owner manually runs the training-data backtest and explicitly STARTs Research; never claim Optimizer automatically backtests, generates the dataset, or starts Research. Optimizer rounds are atomic/resumable: START/RESUME process compatible existing evidence first and Resume never reruns the checkpointed MT5 round. After a parsed round with no eligible winner, Max automatically refines and launches the next native MT5 round while the frozen maximum-round budget remains; there is no manual Continue authority. Scientist may propose only that automatic next round's bounded ranges: OFF=DETERMINISTIC_ONLY, actual LLM proposal=SCIENTIST_PROPOSAL with deterministic accept/reject evidence, and unavailable/failed provider/model/call=DETERMINISTIC_FALLBACK with an explicit reason. If existing evidence already yields a winner, never call Scientist and never launch another optimization round; register the winner as a Strategy Challenger, leave the current Champion untouched, then STOP. If max rounds are exhausted without a winner, stop at NO_CHAMPION_MAX_ROUNDS. MT5 report filenames are not scientific identity authority; canonical runtime filenames are Max_MTF.xml and Max_MTF.set, while internal EA+symbol+timeframe+date-range identity plus per-round fingerprint/checkpoint owns evidence. Owner-selected optimization parameters are frozen per run, and Scientist may never activate a frozen parameter. Strategy Optimizer form settings persist across navigation/reload/app restart via durable shadow-state; active jobs continue using only their frozen request. After explicit Strategy Challenger promotion, the promoted Max_MTF.mq5 SL_ATR/TP_ATR/MaxHoldBars become the one execution-geometry authority shared by Max EA and Model Research: CP32 rows must carry exactly that geometry, Python labels inherit it, mixed/stale datasets fail closed, and Scientist/Feature-Label Audit may not mutate SL/TP/Horizon. Adaptive lot/risk remains EA/system-layer authority and is not a model feature or training target. "
        "When the Owner asks for KPI advice, answer per relevant gate instead of inventing one global KPI profile. Use the live gate_kpis in research_settings as the current Research authority, but do not confuse enabled=true or migrated legacy values with a scientific recommendation. Read max_knowledge.kpi_scientist_policy before recommending KPI placement or thresholds. "
        "Discovery is early screening plus full chronological WFA and should preserve candidate diversity; do not recommend enabling every correlated risk metric by default. CPCV owns purged-combinatorial robustness, worst-path/distribution evidence and PBO when canonical cross-strategy computation exists. PBO NOT_COMPUTABLE is distinct from an Owner decision to disable the concept; never invent pseudo-PBO from one candidate. "
        "Tournament is NOT Fresh/OOS data: it is frozen hard eligibility plus deterministic ranking after CPCV; ranking cannot rescue a hard-gate failure and there is no Top-K elimination in the current contract. Monte Carlo owns resampling/path-tail robustness such as P05/P95, probability of loss/ruin and survival; do not present PSR/DSR as Monte-Carlo-native metrics. "
        "PSR requires an explicit benchmark and adequate sample. DSR requires defensible canonical trial-universe/effective-trials accounting; do not compute it from only the small survivor pool and do not assume a migrated enabled flag proves validity. Sharpe/Sortino/Calmar/Ulcer/CVaR may be diagnostics or predeclared gates, but do not mechanically enable them at every stage. "
        "Fresh Forward is the untouched final generalization gate and must never be relaxed after observing failure. The Owner production policy reference is Expectancy >=0.50R, PF >=1.50, RF >=3.00, Max DD <10%, with Research H1 sample baseline 8 trades/month AUTO-scaled; if live config uses a different unit such as max_drawdown_r, flag the unit/schema mismatch instead of silently equating percent and R. Champion adds no sixth statistical market test. "
        "For Strategy Optimizer, one Max round launches one native MT5 optimization. MT5 owns genetic population/job/task scheduling across tester agents; Tasks/Passed values in MT5 are native passes inside that round, not extra Max rounds. The raw Cartesian search-space size is not the genetic task count. "
        "Recommendations must respect deterministic hard gates, CPCV seed authority, locked/fresh Forward separation, and Capacity Governor. Never recommend lowering scientific KPI gates merely to manufacture survivors. "
        "When recommending settings, prefer a compact Current → Suggested → Why → Trade-off/Effect format, using a Markdown table when several settings are compared. "
        "Act as the Owner's quantitative research Scientist: deeply audit settings, model capacity, KPI hierarchy, failure topology, robustness evidence and trade-offs before recommending changes. "
        "Do not merely agree with the Owner; identify scientific risks and distinguish screening gates from final Champion gates. "
        "Before recommending any new capability or workflow change, inspect max_knowledge and perform a Max novelty check. "
        "For any model-training discussion, max_knowledge.model_training_method_contract is the canonical methodology authority: internal temporal early-stop validation is horizon-purged, MoE top-k gates retain differentiable soft magnitude, load balancing couples soft routing probability with hard dispatch, MoE health is authoritative per block from the restored best checkpoint, experts are latent rather than regime-supervised, and temporal-to-tree stacking is purged OOF only. "
        "Max knowledge is a static capability/contract map, not proof of current run results; live evidence and frozen/current settings remain separate authorities. "
        "If Max already has the capability, classify it as EXISTING and do not propose building it again; explain how the existing control can be used or configured. "
        "If the core capability exists but a scientifically distinct gap remains, classify it as EXTENSION and name the existing capability before the gap. "
        "If no code feature is needed and the idea can be tested with existing controls, classify it as EXPERIMENT. "
        "You may recommend ideas outside the current Max contract; classify them as NEW or OUTSIDE_CURRENT_CONTRACT and explain the integration/validation burden. "
        "If a suggestion would violate deterministic validation, chronology, capacity, locked/fresh separation, or other hard authority, classify it as CONFLICT and give a compliant alternative. "
        "For substantive recommendations, explicitly distinguish SUPPORTED evidence from HYPOTHESIS or SPECULATIVE reasoning. "
        "Answer with conclusions and evidence only. Use clean Markdown naturally: short headings, bullets, numbered steps, code blocks, and valid GFM Markdown tables when they improve clarity. "
        "Every Markdown table must have a header row, separator row, and equal column counts. "
        "Keep answers concise but technically useful. When citing evidence, use the supplied source IDs like [SETTINGS], [PLAN], [WFA], [FAIL]."
    )


def _sanitize_response_text(text: str) -> str:
    """Strip hidden-reasoning wrappers if a provider emits them despite prompt policy.

    This is a display-safety boundary, not a scientific transformation.  It only
    removes explicit private-reasoning containers; the user-facing conclusion is
    preserved verbatim otherwise.
    """
    out=str(text or "")
    tags=("think","thought","analysis","reasoning")
    for tag in tags:
        out=re.sub(rf"(?is)<{tag}\b[^>]*>.*?</{tag}\s*>", "", out)
        out=re.sub(rf"(?is)&lt;{tag}\b[^&]*&gt;.*?&lt;/{tag}\s*&gt;", "", out)
        out=re.sub(rf"(?is)```{tag}\s*\n.*?```", "", out)
    # Fail safe for an unterminated explicit reasoning tag: never display the
    # trailing private scratchpad if the provider forgot the closing tag.
    out=re.sub(r"(?is)<(?:think|thought|analysis|reasoning)\b[^>]*>.*$", "", out)
    return out.strip()


def discuss(
    llm_cfg: dict,
    *,
    selected_model: str,
    api_key: str,
    history: list[dict],
    user_prompt: str,
    context: dict,
    allow_fallback: bool = False,
    progress_callback=None,
) -> dict:
    """Run one read-only Scientist discussion with exactly-once-safe provider routing."""
    selected_model = str(selected_model or "").strip()
    if not selected_model:
        raise ValueError("Scientist Chat model belum dipilih")
    if not str(user_prompt or "").strip():
        raise ValueError("Pertanyaan kosong")
    primary = _route_entry(llm_cfg, selected_model)
    if not primary.get("base_url"):
        raise ValueError("LLM base URL belum dikonfigurasi")

    process_started=utcnow(); process_steps=[]
    def _progress(phase: str, **extra):
        label=_process_step(phase)
        if not process_steps or process_steps[-1].get("phase")!=str(phase):
            process_steps.append({"phase":str(phase),"label":label,"utc":utcnow()})
        if progress_callback:
            payload={"phase":str(phase),"label":label,"process_steps":deepcopy(process_steps)}
            payload.update(extra)
            progress_callback(payload)

    route=[primary]
    if allow_fallback:
        seen={str(primary.get("route_id") or "")}
        for entry in _chat_fallback_route_entries(llm_cfg):
            rid=str(entry.get("route_id") or "")
            if not rid or rid in seen:
                continue
            seen.add(rid); route.append(entry)

    # Internal/failed persistence is diagnostics, not conversation. It must never
    # become an invisible prompt to a later model.
    visible_history=[]
    for msg in history or []:
        if not isinstance(msg,dict) or bool(msg.get("error")):
            continue
        if str(msg.get("visibility") or "visible").lower() not in {"visible","conversation"}:
            continue
        role=str(msg.get("role") or "")
        content=str(msg.get("content") or "").strip()
        if role in {"user","assistant"} and content:
            visible_history.append({"role":role,"content":content})

    context_text=json.dumps(context,ensure_ascii=False,separators=(",",":"),default=str)
    python_authorized=authorized_analysis_inputs(context)
    python_health=scientist_python_health()
    shared_python_analysis=None

    def _messages_for(profile: dict) -> list[dict]:
        max_history_messages=int(profile["history_messages"]); max_history_chars=int(profile["history_chars"])
        prior_rev=[]; used_chars=0
        for msg in reversed(visible_history):
            if len(prior_rev)>=max_history_messages:
                break
            remaining=max_history_chars-used_chars
            if remaining<=0:
                break
            content=str(msg.get("content") or "")
            clipped=content[-min(len(content),remaining,7000):]
            prior_rev.append({"role":msg["role"],"content":clipped}); used_chars+=len(clipped)
        prior=list(reversed(prior_rev))
        depth_note={
            "QUICK":"Prefer direct diagnosis; inspect only the strongest evidence needed to answer.",
            "BALANCED":"Audit relevant evidence and explain the main trade-offs before recommending changes.",
            "DEEP":"Perform a deep scientific audit of relevant settings/evidence, test alternative explanations, and state trade-offs and uncertainty before recommending changes.",
        }[profile["analysis_depth"]]
        system_prompt=_chat_system_prompt()+"\nSCIENTIST ANALYSIS DEPTH: "+profile["analysis_depth"]+". "+depth_note
        msgs=[
            {"role":"system","content":system_prompt},
            {"role":"system","content":"CURRENT READ-ONLY RESEARCH CONTEXT:\n"+context_text[:int(profile["context_chars"])]},
        ]
        if shared_python_analysis is None:
            msgs.append({"role":"system","content":analysis_capability_instruction(python_authorized,python_health)})
        else:
            msgs.append({"role":"system","content":
                "A single Scientist Python attempt has already occurred in this turn. No second Python request is allowed. "
                "Use the following ANALYTICAL_EVIDENCE_ONLY if EXECUTED; otherwise continue REASONING_ONLY and do not fabricate Python-derived numbers.\n"
                +json.dumps(python_analysis_evidence_for_llm(shared_python_analysis),ensure_ascii=False,separators=(",",":"),default=str)})
        return [*msgs,*prior,{"role":"user","content":str(user_prompt).strip()[:12000]}]

    def _route_key(entry: dict) -> str:
        env_name=str(entry.get("api_key_env") or "COMPLEXPOLICY_LLM_API_KEY")
        if str(entry.get("route_id") or "")==str(primary.get("route_id") or "") or env_name==str(primary.get("api_key_env") or ""):
            return (str(api_key or "") or os.environ.get(env_name) or "").strip()
        return str(os.environ.get(env_name) or "").strip()

    _progress("BUILDING_CONTEXT")
    attempts=[]; last_exc=None
    requested_profile=chat_model_profile(llm_cfg,selected_model)
    safe_route_fallback_categories={"QUOTA_OR_RATE_LIMIT","PROVIDER_5XX","MODEL_UNAVAILABLE","PROVIDER_UNREACHABLE"}

    for idx,entry in enumerate(route):
        profile=chat_model_profile(llm_cfg,str(entry.get("model") or ""))
        messages=_messages_for(profile)
        route_api_key=_route_key(entry)
        try:
            if not entry.get("base_url"):
                raise ValueError(f"Scientist Chat fallback route base URL missing: {entry.get('model')}")
            _progress("CALLING_MODEL",model=entry["model"],provider=str(entry.get("provider") or "custom"))
            body=None; streamed=False; partial=[]; saw_visible_delta=[False]
            if bool(profile.get("streaming",True)):
                _progress("WAITING_FIRST_TOKEN",model=entry["model"])
                first=[True]
                def _on_delta(chunk):
                    text=str(chunk or "")
                    if text:
                        saw_visible_delta[0]=True
                    if first[0]:
                        first[0]=False; _progress("STREAMING",model=entry["model"],partial_text="")
                    partial.append(text)
                    _joined="".join(partial)
                    visible=_sanitize_response_text(_joined)
                    if '"python_analysis"' in _joined[:1200]:
                        visible="Running bounded Python analysis…"
                    _progress("STREAMING",model=entry["model"],partial_text=visible)
                try:
                    body=_stream_chat_call(entry,route_api_key,messages,profile,_on_delta)
                    streamed=True
                except Exception as stream_exc:
                    # A second same-route request is allowed only when the provider
                    # explicitly reports a pre-answer stream-capability mismatch.
                    if (not bool(profile.get("stream_fallback_to_buffered",True))
                        or not _is_preanswer_stream_capability_failure(stream_exc,saw_visible_delta=saw_visible_delta[0])):
                        raise
                    _progress("BUFFERED_RESPONSE",model=entry["model"],note="stream capability unavailable; same route buffered")
                    body=_buffered_chat_call(entry,route_api_key,messages,profile)
            else:
                _progress("BUFFERED_RESPONSE",model=entry["model"])
                body=_buffered_chat_call(entry,route_api_key,messages,profile)

            text=_sanitize_response_text(extract_chat_text(body))
            if not text:
                raise RuntimeError("Scientist provider returned an empty visible response")

            py_request=parse_python_analysis_request(text) if shared_python_analysis is None else None
            if py_request is not None:
                _progress("PYTHON_ANALYSIS",model=entry["model"],partial_text="Running bounded Python analysis…")
                shared_python_analysis=run_scientist_python_analysis(py_request,python_authorized)
                py_evidence=python_analysis_evidence_for_llm(shared_python_analysis)
                followup_messages=list(messages)+[
                    {"role":"assistant","content":text},
                    {"role":"system","content":
                        "HOST SCIENTIST PYTHON RESULT. This is ANALYTICAL_EVIDENCE_ONLY and cannot override deterministic MAX. "
                        "If execution_status is not EXECUTED, continue REASONING_ONLY and never claim Python-derived numbers. No second Python request is allowed.\n"
                        +json.dumps(py_evidence,ensure_ascii=False,separators=(",",":"),default=str)},
                    {"role":"user","content":"Answer the original question now. Do not return another python_analysis request."},
                ]
                _progress("BUFFERED_RESPONSE",model=entry["model"],note="interpreting bounded Python analysis")
                body=_buffered_chat_call(entry,route_api_key,followup_messages,profile)
                messages=followup_messages
                streamed=False
                text=_sanitize_response_text(extract_chat_text(body))
                if not text:
                    raise RuntimeError("Scientist provider returned an empty post-analysis response")

            usage=extract_token_usage(body,messages=messages,output_text=text)
            provider=str(entry.get("provider") or "custom")
            pricing_map=llm_cfg.get("pricing_usd_per_1m") if isinstance(llm_cfg.get("pricing_usd_per_1m"),dict) else {}
            pricing=pricing_map.get(f"{provider}|{entry['model']}") if isinstance(pricing_map.get(f"{provider}|{entry['model']}"),dict) else {}
            cost=estimate_api_cost_usd(usage,pricing)
            attempts.append({"priority":idx+1,"provider":provider,"model":entry["model"],"route_id":entry.get("route_id"),"status":"PASS","streamed":bool(streamed)})
            _progress("COMPLETED",model=entry["model"],partial_text=text)
            answering_route={k:entry.get(k) for k in ("route_id","provider","model","base_url","api_key_env")}
            return {
                "schema":CHAT_SCHEMA,
                "content":text,
                "requested_model":selected_model,
                "answered_by":entry["model"],
                "provider":provider,
                "answering_route":answering_route,
                "fallback_used":idx>0,
                "attempts":attempts,
                "usage":usage,
                "cost":cost,
                "context_sources":deepcopy(context.get("sources") or []),
                "created_utc":utcnow(),
                "analysis_mode":str((shared_python_analysis or {}).get("analysis_mode") or "REASONING_ONLY"),
                "python_analysis":python_analysis_evidence_for_llm(shared_python_analysis) if isinstance(shared_python_analysis,dict) else None,
                "process":{"started_utc":process_started,"completed_utc":utcnow(),"steps":deepcopy(process_steps),"analysis_depth":profile["analysis_depth"],"streamed":bool(streamed)},
                "chat_profile":{k:profile[k] for k in ("analysis_depth","temperature","timeout_sec","max_output_tokens","context_chars","history_messages","history_chars","streaming")},
                "requested_chat_profile":{k:requested_profile[k] for k in ("analysis_depth","temperature","timeout_sec","max_output_tokens","context_chars","history_messages","history_chars","streaming")},
            }
        except Exception as exc:
            last_exc=exc
            category=fallback_error_category(exc)
            attempts.append({
                "priority":idx+1,"provider":str(entry.get("provider") or "custom"),"model":entry.get("model"),"route_id":entry.get("route_id"),
                "status":"FAIL","category":category or "NON_FALLBACK_ERROR","error":str(exc)[:500],
            })
            # Timeout is exactly-once ambiguous after request initiation; unlike the
            # autonomous Scientist, manual Chat does not automatically create a second
            # provider request after TIMEOUT.
            if (not allow_fallback) or category not in safe_route_fallback_categories:
                break
    if last_exc is not None:
        err=RuntimeError(str(last_exc)); setattr(err,"attempts",attempts); raise err
    raise RuntimeError("Scientist Chat route unavailable")


class ScientistChatStore:
    """Persistent Chat history with atomic thread-generation authority."""
    def __init__(self, root: str | Path):
        self.root=Path(root)
        self._local_lock=threading.RLock()

    @staticmethod
    def _safe_id(factory_id: str | None) -> str:
        raw=str(factory_id or "NO_FACTORY")
        return re.sub(r"[^A-Za-z0-9_.-]+","_",raw)[:180] or "NO_FACTORY"

    @staticmethod
    def _new_thread_id() -> str:
        return "THREAD_"+uuid.uuid4().hex.upper()

    def path_for(self, factory_id: str | None) -> Path:
        return self.root/f"{self._safe_id(factory_id)}.json"

    @contextlib.contextmanager
    def _locked(self, factory_id: str | None):
        path=self.path_for(factory_id); path.parent.mkdir(parents=True,exist_ok=True)
        lock_path=Path(str(path)+".lock")
        with self._local_lock:
            f=open(lock_path,"a+b")
            try:
                f.seek(0,os.SEEK_END)
                if f.tell()==0:
                    f.write(b"0"); f.flush()
                f.seek(0)
                if os.name=="nt":
                    import msvcrt
                    msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(),fcntl.LOCK_EX)
                yield
            finally:
                try:
                    if os.name=="nt":
                        import msvcrt
                        f.seek(0); msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(f.fileno(),fcntl.LOCK_UN)
                finally:
                    f.close()

    def _payload_unlocked(self, factory_id: str | None) -> dict:
        path=self.path_for(factory_id)
        if not path.exists():
            return {"schema":CHAT_SCHEMA,"factory_id":str(factory_id or "NO_FACTORY"),"messages":[]}
        try:
            obj=json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"SCIENTIST_CHAT_STORE_CORRUPT: {path.name}: {type(exc).__name__}") from exc
        if not isinstance(obj,dict) or not isinstance(obj.get("messages",[]),list):
            raise RuntimeError(f"SCIENTIST_CHAT_STORE_CORRUPT: {path.name}: invalid payload")
        return obj

    def _write_unlocked(self, factory_id: str | None, messages: list[dict], thread_id: str) -> Path:
        path=self.path_for(factory_id); path.parent.mkdir(parents=True,exist_ok=True)
        payload={
            "schema":CHAT_SCHEMA,"factory_id":str(factory_id or "NO_FACTORY"),
            "thread_id":str(thread_id or self._new_thread_id()),"updated_utc":utcnow(),
            "messages":[deepcopy(x) for x in (messages or []) if isinstance(x,dict)][-MAX_HISTORY_MESSAGES:],
        }
        fd,tmp_name=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as out:
                json.dump(payload,out,ensure_ascii=False,indent=2,default=str); out.flush()
                try: os.fsync(out.fileno())
                except OSError: pass
            os.replace(tmp_name,path)
        finally:
            try:
                if os.path.exists(tmp_name): os.unlink(tmp_name)
            except OSError: pass
        return path

    def current_thread_id(self, factory_id: str | None) -> str:
        with self._locked(factory_id):
            obj=self._payload_unlocked(factory_id)
            thread_id=str(obj.get("thread_id") or "").strip()
            if thread_id:
                return thread_id
            thread_id=self._new_thread_id()
            rows=obj.get("messages") if isinstance(obj,dict) else []
            self._write_unlocked(factory_id,[x for x in (rows or []) if isinstance(x,dict)],thread_id)
            return thread_id

    def load(self, factory_id: str | None) -> list[dict]:
        with self._locked(factory_id):
            obj=self._payload_unlocked(factory_id)
            rows=obj.get("messages") if isinstance(obj,dict) else []
            return [deepcopy(x) for x in (rows or []) if isinstance(x,dict)][-MAX_HISTORY_MESSAGES:]

    def save(self, factory_id: str | None, messages: list[dict], *, thread_id: str | None = None) -> Path:
        with self._locked(factory_id):
            obj=self._payload_unlocked(factory_id)
            current=str(obj.get("thread_id") or "").strip()
            if not current:
                current=self._new_thread_id()
            requested=str(thread_id or "").strip()
            if requested and requested!=current:
                raise RuntimeError("STALE_SCIENTIST_CHAT_THREAD")
            return self._write_unlocked(factory_id,messages,current)

    def clear(self, factory_id: str | None) -> Path:
        # One lock covers read-generation boundary + atomic replace. A stale saver
        # can only run before this clear (then clear wins) or after it (then fails).
        with self._locked(factory_id):
            self._payload_unlocked(factory_id)  # surface corruption; never disguise as empty history
            return self._write_unlocked(factory_id,[],self._new_thread_id())

