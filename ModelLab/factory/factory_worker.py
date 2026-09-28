from __future__ import annotations

import argparse
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

from factory.champion_factory import run_discovery_pool, run_cpcv_qualification, run_tournament, run_monte_carlo, run_forward_championship
from factory.factory_orchestrator import run_auto_factory, run_manual_factory
from factory.factory_control import FactoryPauseRequested, FactoryStopRequested
from factory.factory_jobs import job_paths, load_job, save_job, read_candidates, atomic_write_json, write_heartbeat
from data.data_quality import audit_dataset, research_readiness, llm_data_quality_context
from host.mt5_gap_repair import discover_mt5_gap_fill_targets, matching_mt5_gap_fill_targets, run_gap_repair_cycle
from models.model_lab import load_cfg
from core.settings_store import UserSettingsStore


def _atomic_json(path: Path, obj):
    atomic_write_json(path,obj)


def _append_event(path: Path, ev: dict):
    with path.open("a",encoding="utf-8") as f:
        f.write(json.dumps(ev,default=str)+"\n")
        f.flush()
        try: os.fsync(f.fileno())
        except OSError: pass


def _api_key(config_path: str|Path) -> str:
    app_dir=MODELLAB_ROOT
    settings_root=(Path(os.environ.get("LOCALAPPDATA"))/"ComplexPolicy"/"ModelLab") if os.environ.get("LOCALAPPDATA") else (MODELLAB_ROOT/"runtime"/"user_data")
    try:
        _,key,_,_=UserSettingsStore(settings_root).load(load_cfg(config_path))
        return str(key or "")
    except Exception:
        return ""




def _prepare_auto_data_quality(root: Path, job_id: str, payload: dict, config_path: str|Path, progress, control_check) -> dict:
    """Staged Data Quality authority for AUTO/MANUAL/DISCOVERY research.

    Contract v0.11.2:
      1) local/cached audit only -- NEVER opens MT5;
      2) PASS -> Research immediately;
      3) repairable FAIL -> REPAIR stage may open MT5, run verified tester repair,
         re-audit against the same broker/feed, then continue automatically;
      4) non-repairable defects remain fail-closed without launching MT5.
    """
    progress({
        "stage":"data_quality_preflight",
        "current":1,"total":5,
        "message":"Data Quality · local audit (MT5 closed)",
    })
    report=audit_dataset(payload["dataset"],broker_reconcile=False,use_cached_broker_proof=True)
    control_check()
    ready,reasons=research_readiness(report)

    if not ready:
        hard=list(report.get("hard_reasons") or [])
        broker=dict(report.get("broker_reconciliation") or {})
        non_repairable=[
            str(r) for r in reasons
            if not str(r).startswith("BROKER_RECONCILIATION_REQUIRED")
            and not str(r).startswith("SOURCE_BACKED_MISSING_BARS:")
        ]
        if hard or non_repairable:
            progress({
                "stage":"data_quality_preflight",
                "current":2,"total":5,
                "message":"Data Quality BLOCKED · "+" · ".join(reasons),
                "data_quality_status":str(report.get("status") or "UNKNOWN"),
            })
            raise RuntimeError("DATA QUALITY GATE BLOCKED · " + " · ".join(reasons))

        progress({
            "stage":"data_quality_repair",
            "current":2,"total":5,
            "message":"Data Quality local audit failed · entering MT5 repair stage",
            "data_quality_status":str(report.get("status") or "UNKNOWN"),
        })
        targets=discover_mt5_gap_fill_targets()
        if broker.get("verified"):
            matched=matching_mt5_gap_fill_targets(targets,report)
            if len(matched)==1:
                target=matched[0]
            elif len(matched)>1:
                raise RuntimeError(f"DATA_QUALITY_REPAIR_TARGET_AMBIGUOUS:{len(matched)}")
            else:
                raise RuntimeError("DATA_QUALITY_REPAIR_TARGET_NOT_FOUND")
        else:
            if len(targets)!=1:
                raise RuntimeError(
                    f"DATA_QUALITY_REPAIR_TARGET_REQUIRED:{len(targets)} · "
                    "Auto Research membutuhkan tepat satu deployed Max.ex5 ketika broker proof belum tersedia."
                )
            target=targets[0]

        control_check()
        progress({
            "stage":"data_quality_repair",
            "current":3,"total":5,
            "message":"Data Quality · MT5 verify/repair running",
        })
        try:
            repaired=run_gap_repair_cycle(payload["dataset"],target=target)
        except RuntimeError as exc:
            if "Target MT5 sudah berjalan sebelum REPAIR" in str(exc):
                raise FactoryPauseRequested(
                    "DATA_QUALITY_REPAIR_WAITING_FOR_MT5_CLOSE · tutup exact target MT5 lalu RESUME RESEARCH"
                ) from exc
            raise
        report=dict(repaired.get("report") or {})
        control_check()
        ready,reasons=research_readiness(report)
        if not ready:
            raise RuntimeError("DATA QUALITY REPAIR FAILED · " + " · ".join(reasons))
        progress({
            "stage":"data_quality_repair",
            "current":4,"total":5,
            "message":"Data Quality repair VERIFIED · missing=0",
            "data_quality_status":str(report.get("status") or "UNKNOWN"),
        })

    cfg_path=Path(config_path)
    raw=json.loads(cfg_path.read_text(encoding="utf-8"))
    raw.setdefault("agent",{})["data_quality_context"]=llm_data_quality_context(report)
    raw.setdefault("agent",{})["data_quality_source_sha256"]=str(report.get("sha256") or "")
    atomic_write_json(cfg_path,raw)

    job=load_job(root,job_id) or {}
    if job:
        job["data_quality_preflight"]={
            "status":str(report.get("status") or "UNKNOWN"),
            "sha256":str(report.get("sha256") or ""),
            "warnings":list(report.get("warnings") or []),
            "completed":True,
            "mt5_opened_only_after_local_fail":True,
        }
        save_job(root,job)
    progress({
        "stage":"data_quality_preflight",
        "current":5,"total":5,
        "message":"Data Quality PASS · research plan frozen",
        "data_quality_status":str(report.get("status") or "UNKNOWN"),
    })
    return report


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--factory-root",required=True); ap.add_argument("--job-id",required=True); ap.add_argument("--resume",action="store_true"); a=ap.parse_args()
    root=Path(a.factory_root); paths=job_paths(root,a.job_id); job=load_job(root,a.job_id)
    if not job: raise SystemExit(2)
    payload=dict(job.get("payload") or {}); action=str(job.get("action") or "").upper()
    needs_dq=action in {"AUTO","MANUAL","DISCOVERY"} and bool(payload.get("run_data_quality_preflight",True))
    initial_status="DATA_QUALITY_PREFLIGHT" if needs_dq else "RUNNING"
    job["status"]=initial_status; job["pid"]=os.getpid(); job["error"]=None; job["resumed"]=bool(a.resume); save_job(root,job)
    write_heartbeat(root,a.job_id,os.getpid(),initial_status)
    current_generation=int(job.get("generation",0) or 0)
    current_cycle=int(job.get("orchestrator_cycle",0) or 0)

    def control_check():
        if paths["stop"].exists():
            raise FactoryStopRequested("STOP RESEARCH requested by operator")
        if paths["pause"].exists():
            raise FactoryPauseRequested("PAUSE RESEARCH requested by operator")

    def progress(ev):
        nonlocal job,current_generation,current_cycle
        control_check()
        ev=dict(ev or {}); ev["utc"]=datetime.now(timezone.utc).isoformat()
        if ev.get("factory_id"):
            job["factory_id"]=str(ev.get("factory_id"))
        if ev.get("orchestrator_cycle") is not None:
            try:
                new_cycle=int(ev.get("orchestrator_cycle"))
                if new_cycle!=current_cycle:
                    current_cycle=new_cycle; current_generation=0; job["qualified"]=0; job["generation"]=0
                    job["pending_pool_eligible"]=0; job["remaining_pool_slots"]=int(job.get("target",12) or 12)
                    job["projected_pool"]=0; job["pool_target_reached"]=False; job["pool_projection_authority"]=None
                job["orchestrator_cycle"]=current_cycle
            except Exception:
                pass
        if ev.get("stage")=="factory_discovery":
            try: current_generation=int(ev.get("current",0))+1
            except Exception: pass
            # A new generation starts from the last atomically committed Pool. Pending
            # eligibility is recomputed by Supervisor at the next safe round boundary.
            job["pending_pool_eligible"]=0
            job["remaining_pool_slots"]=max(0,int(job.get("target",12) or 12)-int(job.get("qualified",0) or 0))
            job["projected_pool"]=int(job.get("qualified",0) or 0)
            job["pool_target_reached"]=False
            job["pool_projection_authority"]=None
        if ev.get("stage")=="pool_projection":
            job["pending_pool_eligible"]=int(ev.get("pending_eligible",0) or 0)
            job["remaining_pool_slots"]=int(ev.get("remaining_slots",0) or 0)
            job["projected_pool"]=int(ev.get("projected_pool",job.get("qualified",0)) or 0)
            job["pool_target_reached"]=bool(ev.get("target_reached",False))
            job["pool_projection_authority"]=str(ev.get("projection_authority") or "") or None
        if ev.get("stage")=="factory_generation_done":
            current_generation=int(ev.get("current",current_generation) or current_generation)
            job["qualified"]=int(ev.get("qualified",job.get("qualified",0)) or 0)
            job["target"]=int(ev.get("target",job.get("target",12)) or 12)
            job["total_experiments"]=int(ev.get("total_experiments",job.get("total_experiments",0)) or 0)
            # Atomic pool commit has now absorbed the pending finalists.
            job["pending_pool_eligible"]=0
            job["remaining_pool_slots"]=max(0,int(job.get("target",12) or 12)-int(job.get("qualified",0) or 0))
            job["projected_pool"]=int(job.get("qualified",0) or 0)
            job["pool_target_reached"]=int(job.get("qualified",0) or 0)>=int(job.get("target",12) or 12)
            job["pool_projection_authority"]="ATOMIC_POOL_COMMIT"
        rr=ev.get("result_row")
        if isinstance(rr,dict):
            rows=read_candidates(root,a.job_id)
            row=dict(rr); row["Generation"]=current_generation or job.get("generation") or 1
            if action in {"AUTO","MANUAL"}: row["Factory Cycle"]=current_cycle or 1
            rows.append(row); _atomic_json(paths["candidates"],rows)
        job["generation"]=current_generation
        job["last_event"]=ev
        save_job(root,job); write_heartbeat(root,a.job_id,os.getpid(),str(job.get("status") or "RUNNING")); _append_event(paths["events"],ev)

    def mark_research_running():
        nonlocal job
        job=load_job(root,a.job_id) or job
        job["status"]="RUNNING"; job["pid"]=os.getpid(); job["error"]=None
        save_job(root,job); write_heartbeat(root,a.job_id,os.getpid(),"RUNNING")

    def verify_recovery_pool_immutability():
        rc=job.get("recovery_contract") if isinstance(job.get("recovery_contract"),dict) else {}
        expected=str(rc.get("candidate_pool_sha256") or "")
        fid=str(rc.get("factory_id") or "")
        if not expected or not fid: return
        q=root/fid/"candidate_pool.json"
        if not q.exists(): raise RuntimeError("RECOVERY_CANDIDATE_POOL_MISSING")
        import hashlib
        actual=hashlib.sha256(q.read_bytes()).hexdigest()
        if actual!=expected: raise RuntimeError("RECOVERY_CANDIDATE_POOL_MUTATED")

    def verify_recovery_route_authority():
        rc=job.get("recovery_contract") if isinstance(job.get("recovery_contract"),dict) else {}
        if not rc: return
        if str(rc.get("restart_stage") or "")!="CPCV": raise RuntimeError("RECOVERY_RESTART_STAGE_INVALID")
        fid=str(rc.get("factory_id") or "")
        if action=="AUTO":
            state_path=root/"_orchestrators"/f"{a.job_id}.json"
            try: state=json.loads(state_path.read_text(encoding="utf-8"))
            except Exception as exc: raise RuntimeError("RECOVERY_ORCHESTRATOR_STATE_MISSING") from exc
            if str(state.get("current_factory_id") or "")!=fid: raise RuntimeError("RECOVERY_ORCHESTRATOR_FACTORY_ID_MISMATCH")
            if str(state.get("stage") or "").upper()!="CPCV" or str(state.get("manifest_status") or "")!="DISCOVERY_POOL_READY":
                raise RuntimeError("RECOVERY_ORCHESTRATOR_STAGE_MISMATCH")

    try:
        control_check(); verify_recovery_pool_immutability(); verify_recovery_route_authority()
        config_path=payload["config_path"]
        recovery=job.get("recovery_contract") if isinstance(job.get("recovery_contract"),dict) else {}
        skip_recovery_dq=bool(recovery.get("skip_data_quality_preflight"))
        if action=="AUTO":
            if bool(payload.get("run_data_quality_preflight",True)) and not skip_recovery_dq:
                _prepare_auto_data_quality(root,a.job_id,payload,config_path,progress,control_check)
                mark_research_running()
            result=run_auto_factory(
                root,payload["dataset"],config_path,payload["discovery_from"],payload["discovery_to"],
                payload["tournament_from"],payload["tournament_to"],payload["fresh_from"],payload["fresh_to"],
                progress=progress,llm_api_key=_api_key(config_path),orchestrator_id=a.job_id,resume=bool(a.resume),
                max_cycles=int(payload.get("orchestrator_max_cycles",0) or 0),
            )
        elif action=="MANUAL":
            if bool(payload.get("run_data_quality_preflight",True)):
                _prepare_auto_data_quality(root,a.job_id,payload,config_path,progress,control_check)
                mark_research_running()
            result=run_manual_factory(
                root,payload["dataset"],config_path,payload["discovery_from"],payload["discovery_to"],
                payload["tournament_from"],payload["tournament_to"],payload["fresh_from"],payload["fresh_to"],
                progress=progress,orchestrator_id=a.job_id,resume=bool(a.resume),
            )
        elif action=="DISCOVERY":
            if bool(payload.get("run_data_quality_preflight",True)):
                _prepare_auto_data_quality(root,a.job_id,payload,config_path,progress,control_check)
                mark_research_running()
            result=run_discovery_pool(
                payload["dataset"],config_path,root,payload["discovery_from"],payload["discovery_to"],
                payload["tournament_from"],payload["tournament_to"],payload["fresh_from"],payload["fresh_to"],
                progress=progress,llm_api_key=_api_key(config_path),factory_id=payload.get("factory_id"),resume=bool(a.resume),
            )
        elif action=="CPCV":
            result=run_cpcv_qualification(payload["factory_dir"],config_path,progress=progress,llm_api_key=_api_key(config_path))
        elif action=="TOURNAMENT":
            result=run_tournament(payload["factory_dir"],payload["dataset"],config_path,progress=progress,llm_api_key=_api_key(config_path))
        elif action=="MONTE_CARLO":
            result=run_monte_carlo(payload["factory_dir"],config_path,progress=progress,llm_api_key=_api_key(config_path))
        elif action in {"FORWARD","FRESH"}:
            result=run_forward_championship(payload["factory_dir"],payload["dataset"],config_path,progress=progress,llm_api_key=_api_key(config_path))
        else:
            raise ValueError("Unknown factory action: "+action)
        verify_recovery_pool_immutability()
        job=load_job(root,a.job_id) or job
        result_status=str((result or {}).get("status") or "") if isinstance(result,dict) else ""
        if result_status in {"WAITING_FOR_SCIENTIST_REVIEW","WAITING_FOR_NEW_FORWARD_DATA","FORWARD_INSUFFICIENT_SAMPLE"}:
            # Waiting states are resumable, not successful terminal jobs. Scientist
            # review resumes from sealed failure evidence; Forward waits resume the
            # same Factory after fresh data arrives.
            job["status"]="PAUSED"; job["pause_reason"]=result_status; job["paused_utc"]=datetime.now(timezone.utc).isoformat()
        else:
            job["status"]="COMPLETED"
        job["pid"]=None; job["result"]=result; job["error"]=None
        if job.get("recovery_contract"):
            job["recovery_state"]="RECOVERY_PAUSED" if job["status"]=="PAUSED" else "RECOVERY_COMPLETED"
        if isinstance(result,dict):
            job["qualified"]=int(result.get("qualified",job.get("qualified",0)) or job.get("qualified",0))
            if result.get("target") is not None: job["target"]=int(result.get("target"))
        save_job(root,job); write_heartbeat(root,a.job_id,os.getpid(),str(job["status"]))
        return 0
    except FactoryPauseRequested as e:
        job=load_job(root,a.job_id) or job; job["status"]="PAUSED"; job["pid"]=None; job["error"]=None; job["pause_reason"]=str(e); job["paused_utc"]=datetime.now(timezone.utc).isoformat(); save_job(root,job); write_heartbeat(root,a.job_id,os.getpid(),"PAUSED"); return 4
    except FactoryStopRequested as e:
        job=load_job(root,a.job_id) or job; job["status"]="STOPPED"; job["pid"]=None; job["error"]=str(e); job["stopped_utc"]=datetime.now(timezone.utc).isoformat(); save_job(root,job); write_heartbeat(root,a.job_id,os.getpid(),"STOPPED"); return 3
    except BaseException as e:
        job=load_job(root,a.job_id) or job
        detail=str(e).strip(); current_error=(f"{type(e).__name__}: {detail}" if detail else type(e).__name__); current_tb=traceback.format_exc()
        job["status"]="FAILED"; job["pid"]=None; job["error"]=current_error; job["traceback"]=current_tb
        if job.get("recovery_contract"): job["recovery_state"]="RECOVERY_FAILED"
        save_job(root,job); write_heartbeat(root,a.job_id,os.getpid(),"FAILED"); return 1

if __name__=="__main__":
    raise SystemExit(main())
