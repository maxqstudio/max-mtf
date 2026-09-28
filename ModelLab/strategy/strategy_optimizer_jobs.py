from __future__ import annotations
import json, os, signal, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from core.project_paths import MODELLAB_ROOT
from strategy.strategy_optimizer import RUNS_ROOT, EVIDENCE_ROOT, validate_request, discover_bootstrap_optimization_reports, optimizer_metrics_sidecar_for_report, parse_optimizer_metrics_csv
from factory.factory_jobs import atomic_write_json

ACTIVE={"QUEUED","PROCESSING_EXISTING_EVIDENCE","COMPILING_EA","PREPARING_MT5","MT5_OPTIMIZING","PARSING_RESULTS","SCIENTIST_REFINING","RESUMING","ROUND_COMPLETE_NO_CHAMPION"}
TERMINAL={"STRATEGY_CHALLENGER_FOUND","CHAMPION_FOUND","NO_CHAMPION_MAX_ROUNDS","FAILED","STOPPED"}
RECOVERABLE={"WAITING_FOR_REPORT","FAILED"}


def _now(): return datetime.now(timezone.utc).isoformat()
def _job_dir(job_id:str)->Path: return RUNS_ROOT/job_id
def _path(job_id:str)->Path: return _job_dir(job_id)/"status.json"
def _process_path(job_id:str)->Path: return _job_dir(job_id)/"worker_process.json"
def _atomic(path:Path,obj:dict):
    atomic_write_json(Path(path),obj)

def _write_status(st:dict)->dict:
    jid=str(st["job_id"]); st["updated_utc"]=_now()
    _atomic(_path(jid),st); _atomic(EVIDENCE_ROOT/jid/"status.json",st)
    return st

def load_job(job_id:str)->dict|None:
    p=_path(job_id)
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None

def latest_job()->dict|None:
    if not RUNS_ROOT.exists(): return None
    rows=[]
    for p in RUNS_ROOT.glob("*/status.json"):
        try: rows.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception: pass
    return max(rows,key=lambda x:str(x.get("updated_utc") or "")) if rows else None

def _spawn_worker(job_id:str, *, resume:bool=False, report:str|None=None)->dict:
    status=load_job(job_id)
    if not status: raise FileNotFoundError(job_id)
    evidence=EVIDENCE_ROOT/job_id; evidence.mkdir(parents=True,exist_ok=True)
    creationflags=0
    if os.name=="nt": creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)|getattr(subprocess,"DETACHED_PROCESS",0)
    out=(evidence/"worker_stdout.log").open("a",encoding="utf-8")
    err=(evidence/"worker_stderr.log").open("a",encoding="utf-8")
    cmd=[sys.executable,"-m","strategy.strategy_optimizer_worker","--job-id",job_id]
    if resume: cmd.append("--resume")
    if report: cmd += ["--report",str(report)]
    try:
        proc=subprocess.Popen(cmd,cwd=str(MODELLAB_ROOT),creationflags=creationflags,stdout=out,stderr=err)
    finally:
        out.close(); err.close()
    # After spawn, the worker owns status.json. Persist launcher/process ownership in a
    # separate sidecar so the parent never races or overwrites worker state on Windows.
    _atomic(_process_path(job_id),{
        "schema":"MAX_STRATEGY_OPTIMIZER_PROCESS_OWNER_V1",
        "job_id":job_id,"pid":int(proc.pid),"spawned_utc":_now(),
        "resume":bool(resume),
        "worker_command_mode":("RESUME_EXISTING_EVIDENCE_THEN_AUTO_CONTINUE_IF_NEEDED" if resume else "START_AUTO_OPTIMIZER"),
    })
    view=dict(status); view["worker_pid"]=int(proc.pid)
    return view


def resume_job(job_id:str, report_path:str|None=None)->dict:
    """Resume the checkpointed round without rerunning it; auto-continue later rounds only when no Champion exists."""
    st=load_job(job_id)
    if not st: raise FileNotFoundError(job_id)
    status=str(st.get("status") or "")
    if status not in RECOVERABLE|{"FAILED"}:
        raise RuntimeError(f"Strategy Optimizer job is not resumable: {status}")
    if status=="FAILED":
        msg=str(st.get("message") or "").lower()
        # v0.8.2 could fail while atomically replacing status.json on Windows even
        # though the MT5 report already existed. Those failures are evidence-resumable:
        # Resume must parse the checkpoint/report, never relaunch the same native round.
        resumable_failure=any(x in msg for x in ("xml","report","status.json","winerror 5","winerror 32","access is denied"))
        round_no=max(1,int(st.get("round") or 1))
        checkpoint=(_job_dir(job_id)/f"round_{round_no}_state.json").exists()
        if not resumable_failure and not checkpoint:
            raise RuntimeError("FAILED job has no resumable MT5 evidence/checkpoint; START a new frozen Optimizer request")
    st["status"]="RESUMING"; st["message"]="Resuming checkpointed MT5 evidence; completed round is never rerun, and no-winner evidence auto-continues within the frozen round budget"; st["resume_requested_utc"]=_now()
    _write_status(st)
    return _spawn_worker(job_id,resume=True,report=report_path)


def start_job(request:dict)->dict:
    """Start a new frozen Optimizer request.

    Scientifically complete external/manual XML+Weighted-R-sidecar evidence is consumed first.
    XML-only legacy evidence is not v0.8.5 Champion-compatible. Prior MAX-generated round XML is
    never cross-job bootstrap evidence. An eligible winner is registered as a Strategy Challenger and stops immediately; otherwise the
    Optimizer automatically refines and continues until Champion or max_rounds.
    """
    req=validate_request(request)
    current=latest_job()
    if current and str(current.get("status")) in ACTIVE:
        raise RuntimeError(f"Strategy Optimizer already active: {current.get('job_id')}")
    job_id=datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:8]
    d=_job_dir(job_id); d.mkdir(parents=True,exist_ok=False)
    evidence=EVIDENCE_ROOT/job_id; evidence.mkdir(parents=True,exist_ok=False)
    request_text=json.dumps(req,indent=2); (d/"request.json").write_text(request_text,encoding="utf-8"); (evidence/"request.json").write_text(request_text,encoding="utf-8")
    hits=discover_bootstrap_optimization_reports(req)
    existing=hits[0] if hits else None
    existing_metrics=None
    existing_nonce=0
    if existing is not None:
        existing_metrics=optimizer_metrics_sidecar_for_report(existing)
        parsed_metrics=parse_optimizer_metrics_csv(existing_metrics)
        nonces={int(v["run_nonce"]) for v in parsed_metrics.values()}
        if len(nonces)!=1:
            raise RuntimeError(f"Bootstrap optimizer sidecar must contain exactly one run nonce: {existing_metrics}")
        existing_nonce=next(iter(nonces))
    status={
        "schema":"MAX_STRATEGY_OPTIMIZER_JOB_V4","job_id":job_id,
        "status":"PROCESSING_EXISTING_EVIDENCE" if existing else "QUEUED",
        "created_utc":_now(),"updated_utc":_now(),"request":req,"frozen_config":req,
        "round":1 if existing else 0,
        "message":("Compatible MT5 XML found; processing it first, then auto-continuing only if no Champion exists" if existing else "Queued MT5 Round 1"),
        "evidence_dir":str(evidence),"first_failed_gate":None,
        "state_transitions":[{"from":"IDLE","to":"PROCESSING_EXISTING_EVIDENCE" if existing else "QUEUED","utc":_now(),"reason":"START AUTO OPTIMIZER"}],
    }
    _atomic(d/"status.json",status); _atomic(evidence/"status.json",status); (EVIDENCE_ROOT/"LATEST.txt").write_text(str(evidence),encoding="utf-8")
    if existing:
        rs={
            "schema":"MAX_STRATEGY_OPTIMIZER_ROUND_STATE_V2","round":1,"phase":"MT5_COMPLETE",
            "search_space":req["search_space"],"set_path":"","ini_path":"","report_override":str(existing),
            "optimize_params":req.get("optimize_params") or [],"updated_utc":_now(),
            "optimizer_metrics_path":str(existing_metrics),"optimizer_metrics_file":existing_metrics.name,
            "optimizer_run_nonce":int(existing_nonce),
        }
        _atomic(d/"round_1_state.json",rs); _atomic(evidence/"round_01"/"round_state.json",rs)
        return _spawn_worker(job_id,resume=True,report=str(existing))
    return _spawn_worker(job_id)


def cancel_job(job_id:str)->dict:
    st=load_job(job_id)
    if not st: raise FileNotFoundError(job_id)
    if str(st.get("status")) in TERMINAL: return st
    pid=int(st.get("worker_pid") or 0)
    try:
        owner=json.loads(_process_path(job_id).read_text(encoding="utf-8"))
        pid=int(owner.get("pid") or pid or 0)
    except Exception:
        pass
    if pid>0:
        try:
            if os.name=="nt": subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],capture_output=True,timeout=10)
            else: os.kill(pid,signal.SIGTERM)
        except Exception: pass
    st["status"]="STOPPED"; st["message"]="Stopped by Owner"; st["stopped_utc"]=_now()
    return _write_status(st)
