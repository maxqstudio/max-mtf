from __future__ import annotations

import json
import os
import contextlib
import signal
import subprocess
import sys
import time
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.inherited_v147 import classify_recoverable_failure

ACTIVE_STATUSES={"QUEUED","DATA_QUALITY_PREFLIGHT","RUNNING","PAUSE_REQUESTED","STOP_REQUESTED","STOP_FAILED"}
RESUMABLE_STATUSES={"PAUSED","INTERRUPTED","STOPPED"}
TERMINAL_STATUSES={"PASS","FAILED","STOPPED","ABORTED","COMPLETED"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, obj) -> None:
    """Windows-safe atomic JSON writer with same-volume temp + fsync + retry."""
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp_name=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=str(path.parent))
    tmp=Path(tmp_name)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="") as f:
            json.dump(obj,f,indent=2,default=str)
            f.flush()
            try: os.fsync(f.fileno())
            except OSError: pass
        last=None
        for attempt in range(24):
            try:
                os.replace(tmp,path)
                return
            except PermissionError as e:
                last=e
            except OSError as e:
                if getattr(e,"winerror",None) not in (5,32):
                    raise
                last=e
            time.sleep(min(0.025*(attempt+1),0.30))
        if last is not None:
            raise last
        raise RuntimeError(f"atomic replace gagal: {path}")
    finally:
        try:
            if tmp.exists(): tmp.unlink()
        except OSError:
            pass


def _atomic_write_json(path: Path, obj) -> None:
    atomic_write_json(path,obj)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def job_root(factory_root: str|Path) -> Path:
    p=Path(factory_root)/"_jobs"
    p.mkdir(parents=True,exist_ok=True)
    return p


@contextlib.contextmanager
def _job_registry_lock(factory_root: str|Path):
    """Cross-process mutex for job create/resume authority.

    The single-active-job contract must be atomic: check + state transition + spawn
    happen while this OS-backed lock is held. The OS releases the lock if the
    launcher crashes, so no stale lockfile ownership is trusted.
    """
    lock_path=job_root(factory_root)/".registry.lock"
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    f=open(lock_path,"a+b")
    try:
        if os.name=="nt":
            import msvcrt
            f.seek(0,os.SEEK_END)
            if f.tell()==0:
                f.write(b"0"); f.flush()
            f.seek(0)
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


def job_paths(factory_root: str|Path, job_id: str) -> dict[str,Path]:
    root=job_root(factory_root)
    return {
        "job":root/f"{job_id}.json",
        "events":root/f"{job_id}.events.jsonl",
        "candidates":root/f"{job_id}.candidates.json",
        "stop":root/f"{job_id}.stop",
        "pause":root/f"{job_id}.pause",
        "heartbeat":root/f"{job_id}.heartbeat.json",
        "process":root/f"{job_id}.process.json",
        "log":root/f"{job_id}.log",
    }


def _windows_pid_alive(pid: int) -> bool:
    """Non-destructive Windows process liveness probe.

    Never use os.kill(pid, 0) on Windows: CPython maps non-console signals to
    TerminateProcess, so a liveness check can kill the worker it is observing.
    """
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            # Access denied means the process can exist but cannot be queried.
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD(0)
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return ctypes.get_last_error() == 5
            return int(code.value) == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        # Fail conservative: do not declare a worker dead just because the probe failed.
        return True


def _pid_alive(pid: Any) -> bool:
    try:
        pid=int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid,0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _sidecar_pid(factory_root: str|Path, job_id: str) -> int|None:
    data=read_json(job_paths(factory_root,job_id)["process"],{})
    try:
        pid=int(data.get("pid"))
        return pid if pid>0 else None
    except Exception:
        return None


def _heartbeat_pid(factory_root: str|Path, job_id: str) -> int|None:
    data=read_json(job_paths(factory_root,job_id)["heartbeat"],{})
    try:
        pid=int(data.get("pid"))
        return pid if pid>0 else None
    except Exception:
        return None


def _worker_pids(factory_root: str|Path, job: dict) -> list[int]:
    vals=[]
    for raw in (job.get("pid"), _sidecar_pid(factory_root,str(job.get("job_id") or "")), _heartbeat_pid(factory_root,str(job.get("job_id") or ""))):
        try:
            pid=int(raw)
        except Exception:
            continue
        if pid>0 and pid not in vals:
            vals.append(pid)
    return vals


def _alive_worker_pids(factory_root: str|Path, job: dict) -> list[int]:
    return [pid for pid in _worker_pids(factory_root,job) if _pid_alive(pid)]


def _age_seconds(iso_value: Any) -> float:
    try:
        dt=datetime.fromisoformat(str(iso_value).replace("Z","+00:00"))
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=timezone.utc)
        return max(0.0,(datetime.now(timezone.utc)-dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return 1e9


def _reconcile_orphan(factory_root: str|Path, job: dict) -> dict:
    """Convert dead persisted active jobs into resumable INTERRUPTED state.

    This write is legal because it only occurs after the prior worker process is gone.
    A short QUEUED grace avoids racing worker startup.
    """
    if not isinstance(job,dict) or not job:
        return job
    status=str(job.get("status") or "")
    if status not in ACTIVE_STATUSES:
        return job
    alive=_alive_worker_pids(factory_root,job)
    if alive:
        # The launcher sidecar closes the spawn/claim race without letting the UI own
        # the worker JSON. A page rerun therefore cannot turn a live worker INTERRUPTED.
        view=dict(job)
        view["pid"]=int(alive[0])
        if status=="QUEUED":
            action=str(job.get("action") or "").upper()
            payload=dict(job.get("payload") or {})
            needs_dq=action in {"AUTO","MANUAL","DISCOVERY"} and bool(payload.get("run_data_quality_preflight",True))
            view["status"]="DATA_QUALITY_PREFLIGHT" if needs_dq else "RUNNING"
        return view
    if status=="QUEUED" and not job.get("pid") and _age_seconds(job.get("created_utc")) < 30.0:
        return job
    out=dict(job)
    prior=status
    # If STOP was already requested and the worker is gone, that is a stopped job,
    # not an interruption requiring resume.
    if job_paths(factory_root,str(out["job_id"]))["stop"].exists():
        out["status"]="STOPPED"
        out["pid"]=None
        out["stopped_utc"]=utcnow()
        out["error"]="STOPPED_BY_OPERATOR"
    else:
        out["status"]="INTERRUPTED"
        out["pid"]=None
        out["interrupted_utc"]=utcnow()
        out["interruption_reason"]="WORKER_NOT_ALIVE_AFTER_RESTART_OR_CRASH"
        out["error"]=f"Worker tidak hidup; state {prior} direkonsiliasi sebagai INTERRUPTED dan dapat RESUME dari checkpoint."
    out["updated_utc"]=utcnow()
    atomic_write_json(job_paths(factory_root,str(out["job_id"]))["job"],out)
    return out


def load_job(factory_root: str|Path, job_id: str) -> dict:
    paths=job_paths(factory_root,job_id)
    job=read_json(paths["job"],{})
    job=_reconcile_orphan(factory_root,job)
    if isinstance(job,dict) and job:
        status=str(job.get("status") or "")
        # Control signals are out-of-band; UI stays read-only while worker lives.
        if paths["stop"].exists() and status in {"QUEUED","RUNNING","PAUSE_REQUESTED","STOP_REQUESTED"}:
            job=dict(job); job["status"]="STOP_REQUESTED"
        elif paths["pause"].exists() and status in {"QUEUED","RUNNING","PAUSE_REQUESTED"}:
            job=dict(job); job["status"]="PAUSE_REQUESTED"
    return job


def save_job(factory_root: str|Path, job: dict) -> dict:
    job=dict(job)
    job["updated_utc"]=utcnow()
    _atomic_write_json(job_paths(factory_root,str(job["job_id"]))["job"],job)
    return job


def write_heartbeat(factory_root: str|Path, job_id: str, pid: int, state: str="RUNNING") -> None:
    atomic_write_json(job_paths(factory_root,job_id)["heartbeat"],{
        "job_id":job_id,"pid":int(pid),"state":str(state),"utc":utcnow()
    })


def list_jobs(factory_root: str|Path, action: str|None=None) -> list[dict]:
    root=job_root(factory_root)
    rows=[]
    for p in root.glob("*.json"):
        if p.name.endswith(".candidates.json") or p.name.endswith(".heartbeat.json") or p.name.endswith(".process.json"): continue
        j=read_json(p,{})
        if not j.get("job_id"): continue
        j=_reconcile_orphan(factory_root,j)
        if action and str(j.get("action")).upper()!=str(action).upper(): continue
        rows.append(j)
    rows.sort(key=lambda x:str(x.get("created_utc") or ""),reverse=True)
    return rows


def latest_job(factory_root: str|Path, action: str|None=None, active_only: bool=False) -> dict|None:
    for j in list_jobs(factory_root,action):
        if active_only and str(j.get("status")) not in ACTIVE_STATUSES: continue
        return j
    return None


def read_candidates(factory_root: str|Path, job_id: str) -> list[dict]:
    x=read_json(job_paths(factory_root,job_id)["candidates"],[])
    return x if isinstance(x,list) else []


def read_events(factory_root: str|Path, job_id: str, limit: int=30) -> list[dict]:
    p=job_paths(factory_root,job_id)["events"]
    if not p.exists(): return []
    rows=[]
    try:
        for line in p.read_text(encoding="utf-8",errors="replace").splitlines()[-max(1,int(limit)):]:
            try: rows.append(json.loads(line))
            except Exception: pass
    except Exception: pass
    return rows


def _spawn_worker(factory_root: str|Path, app_dir: str|Path, job: dict, resume: bool=False) -> dict:
    job_id=str(job["job_id"]); paths=job_paths(factory_root,job_id)
    worker=Path(app_dir)/"factory_worker.py"
    cmd=[sys.executable,str(worker),"--factory-root",str(Path(factory_root)),"--job-id",job_id]
    if resume: cmd.append("--resume")
    logf=paths["log"].open("ab",buffering=0)
    kwargs={"cwd":str(Path(app_dir)),"stdin":subprocess.DEVNULL,"stdout":logf,"stderr":subprocess.STDOUT,"close_fds":True}
    if os.name=="nt":
        kwargs["creationflags"]=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)|getattr(subprocess,"CREATE_NO_WINDOW",0)
    proc=subprocess.Popen(cmd,**kwargs)
    logf.close()
    # Persist process ownership outside the worker-authoritative job JSON immediately.
    # This closes the short launcher -> worker claim race and gives STOP a PID even if
    # the worker has not yet written its first heartbeat.
    atomic_write_json(paths["process"],{
        "schema":"CP_FACTORY_PROCESS_OWNER_V1","job_id":job_id,"pid":int(proc.pid),
        "spawned_utc":utcnow(),"resume":bool(resume),
    })
    view=dict(job); view["pid"]=int(proc.pid)
    recovery=job.get("recovery_contract") if isinstance(job.get("recovery_contract"),dict) else {}
    needs_dq=(str(job.get("action") or "").upper() in {"AUTO","MANUAL","DISCOVERY"}
              and bool((job.get("payload") or {}).get("run_data_quality_preflight",True))
              and not bool(recovery.get("skip_data_quality_preflight")))
    view["status"]="DATA_QUALITY_PREFLIGHT" if needs_dq else "RUNNING"
    view["resume_spawned"]=bool(resume)
    return view




def _resolve_recovery_factory_dir(factory_root: str|Path, job: dict) -> Path|None:
    root=Path(factory_root); payload=job.get("payload") if isinstance(job.get("payload"),dict) else {}
    direct=str(payload.get("factory_dir") or "").strip()
    if direct:
        p=Path(direct); return p if p.exists() else None
    fid=str(job.get("factory_id") or "").strip()
    if fid and (root/fid).exists(): return root/fid
    oid=str(job.get("job_id") or "").strip()
    state=read_json(root/"_orchestrators"/f"{oid}.json",{}) if oid else {}
    fid=str((state or {}).get("current_factory_id") or "").strip()
    return (root/fid) if fid and (root/fid).exists() else None

def failed_recovery_contract(factory_root: str|Path, job: dict) -> dict:
    root=Path(factory_root)
    rc=classify_recoverable_failure(job,_resolve_recovery_factory_dir(root,job))
    if not bool(rc.get("recoverable")):
        return rc
    action=str((job or {}).get("action") or "").upper()
    if action=="AUTO":
        job_id=str((job or {}).get("job_id") or "").strip()
        state_path=root/"_orchestrators"/f"{job_id}.json"
        state=read_json(state_path,{}) if job_id else {}
        if not isinstance(state,dict) or not state:
            return {**rc,"recoverable":False,"reason":"ORCHESTRATOR_STATE_MISSING"}
        if str(state.get("current_factory_id") or "")!=str(rc.get("factory_id") or ""):
            return {**rc,"recoverable":False,"reason":"ORCHESTRATOR_FACTORY_ID_MISMATCH"}
        if str(state.get("stage") or "").upper()!="CPCV" or str(state.get("manifest_status") or "")!="DISCOVERY_POOL_READY":
            return {**rc,"recoverable":False,"reason":"ORCHESTRATOR_NOT_AT_FAILED_CPCV_STAGE"}
        rc={**rc,"restart_stage":"CPCV","orchestrator_stage":"CPCV","skip_data_quality_preflight":True}
    elif action=="CPCV":
        rc={**rc,"restart_stage":"CPCV","skip_data_quality_preflight":True}
    else:
        return {**rc,"recoverable":False,"reason":"RECOVERY_ACTION_NOT_SUPPORTED"}
    return rc

def job_is_resumable(factory_root: str|Path, job: dict) -> bool:
    status=str((job or {}).get("status") or "")
    if status in RESUMABLE_STATUSES: return True
    return bool(status=="FAILED" and failed_recovery_contract(factory_root,job).get("recoverable"))

def start_job(factory_root: str|Path, app_dir: str|Path, action: str, payload: dict) -> dict:
    action=str(action).upper()
    with _job_registry_lock(factory_root):
        if latest_job(factory_root,active_only=True):
            raise RuntimeError("Masih ada Factory job aktif. PAUSE/STOP atau tunggu selesai sebelum membuat job baru.")
        # A recognized recoverable FAILED Factory is lifecycle authority across actions.
        # Do not allow DISCOVERY ONLY / MANUAL / CPCV to bypass AUTO recovery and
        # accidentally create a second Factory lineage. Existing PAUSED/INTERRUPTED
        # behavior remains action-scoped for compatibility.
        for prior_any in list_jobs(factory_root):
            if str(prior_any.get("status") or "") == "FAILED" and job_is_resumable(factory_root,prior_any):
                raise RuntimeError(
                    f"Ada Factory job {prior_any.get('job_id')} dalam state FAILED · recovery available. "
                    "RESUME atau ABORT dulu; jangan membuat Factory baru lewat action lain."
                )
        prior=latest_job(factory_root,action,active_only=False)
        if prior and job_is_resumable(factory_root,prior):
            state=("FAILED · recovery available" if str(prior.get("status"))=="FAILED" else str(prior.get("status")))
            raise RuntimeError(f"Ada {action} job {prior.get('job_id')} dalam state {state}. RESUME atau ABORT dulu; jangan membuat Factory duplikat.")
        job_id=datetime.now(timezone.utc).strftime("JOB_%Y%m%d_%H%M%S_")+uuid.uuid4().hex[:6].upper()
        paths=job_paths(factory_root,job_id)
        factory_id=payload.get("factory_id")
        if action=="DISCOVERY" and not factory_id:
            factory_id=datetime.now(timezone.utc).strftime("FACTORY_%Y%m%d_%H%M%S_UTC")+"_"+uuid.uuid4().hex[:4].upper()
            payload=dict(payload); payload["factory_id"]=factory_id
        job={
            "schema":"CP_FACTORY_JOB_V3","job_id":job_id,"action":action,"status":"QUEUED",
            "created_utc":utcnow(),"updated_utc":utcnow(),"pid":None,"factory_id":factory_id,
            "payload":payload,"last_event":{},"result":None,"error":None,
            "qualified":0,"target":int(payload.get("target",12) or 12),"generation":0,
            "resume_count":0,"checkpoint_policy":"LAST_COMMITTED_ATOMIC",
        }
        atomic_write_json(paths["job"],job)
        atomic_write_json(paths["candidates"],[])
        for sig in (paths["stop"],paths["pause"]):
            try: sig.unlink()
            except FileNotFoundError: pass
        return _spawn_worker(factory_root,app_dir,job,resume=False)

def request_pause(factory_root: str|Path, job_id: str) -> dict:
    paths=job_paths(factory_root,job_id); job=load_job(factory_root,job_id)
    if not job: raise FileNotFoundError(job_id)
    if str(job.get("status")) not in {"QUEUED","DATA_QUALITY_PREFLIGHT","RUNNING"}: return job
    paths["pause"].write_text(utcnow(),encoding="utf-8")
    view=dict(job); view["status"]="PAUSE_REQUESTED"
    return view


def _terminate_worker_tree(factory_root: str|Path, job: dict, timeout_sec: float=8.0) -> dict:
    """Terminate the owned worker process tree and verify the root PIDs are gone."""
    pids=_alive_worker_pids(factory_root,job)
    if not pids:
        return {"terminated":True,"pids":[],"alive_after":[],"details":[]}
    details=[]
    if os.name=="nt":
        # taskkill /T follows the worker's child process tree; /F avoids native fit
        # threads/libraries keeping research alive after the operator pressed STOP.
        for pid in pids:
            try:
                cp=subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=max(2,int(timeout_sec)),check=False)
                details.append({"pid":pid,"returncode":int(cp.returncode),"output":str(cp.stdout or "")[-1200:]})
            except Exception as exc:
                details.append({"pid":pid,"returncode":-1,"output":f"{type(exc).__name__}: {exc}"})
    else:
        for pid in pids:
            try:
                try: os.killpg(pid,signal.SIGKILL)
                except Exception: os.kill(pid,signal.SIGKILL)
                details.append({"pid":pid,"returncode":0,"output":"SIGKILL"})
            except Exception as exc:
                details.append({"pid":pid,"returncode":-1,"output":f"{type(exc).__name__}: {exc}"})
    deadline=time.monotonic()+max(1.0,float(timeout_sec))
    alive=list(pids)
    while alive and time.monotonic()<deadline:
        time.sleep(0.1)
        alive=[pid for pid in pids if _pid_alive(pid)]
    return {"terminated":not alive,"pids":pids,"alive_after":alive,"details":details}


def request_stop(factory_root: str|Path, job_id: str) -> dict:
    """Operator STOP is a hard stop: no research compute may remain alive.

    Atomic research checkpoints preserve only already-committed work. PAUSE remains the
    graceful safe-boundary action; STOP means terminate the worker tree now.
    """
    paths=job_paths(factory_root,job_id); job=read_json(paths["job"],{})
    if not job: raise FileNotFoundError(job_id)
    paths["stop"].write_text(utcnow(),encoding="utf-8")
    result=_terminate_worker_tree(factory_root,job,timeout_sec=8.0)
    out=dict(job); out["stop_verification"]=result; out["pid"]=None if result["terminated"] else (result["alive_after"][0] if result["alive_after"] else job.get("pid"))
    if result["terminated"]:
        out["status"]="STOPPED"; out["error"]="STOPPED_BY_OPERATOR"; out["stopped_utc"]=utcnow()
    else:
        out["status"]="STOP_FAILED"; out["error"]="STOP_FAILED_WORKER_STILL_ALIVE"; out["stop_failed_utc"]=utcnow()
    save_job(factory_root,out)
    return out


def force_stop(factory_root: str|Path, job_id: str) -> dict:
    """Retry a verified hard stop. Never report STOPPED while an owned PID is alive."""
    paths=job_paths(factory_root,job_id); job=read_json(paths["job"],{})
    if not job: raise FileNotFoundError(job_id)
    paths["stop"].write_text(utcnow(),encoding="utf-8")
    result=_terminate_worker_tree(factory_root,job,timeout_sec=15.0)
    out=dict(job); out["stop_verification"]=result; out["pid"]=None if result["terminated"] else (result["alive_after"][0] if result["alive_after"] else job.get("pid"))
    if result["terminated"]:
        out["status"]="STOPPED"; out["error"]="FORCE_STOPPED_BY_OPERATOR"; out["stopped_utc"]=utcnow()
    else:
        out["status"]="STOP_FAILED"; out["error"]="FORCE_STOP_FAILED_WORKER_STILL_ALIVE"; out["stop_failed_utc"]=utcnow()
    save_job(factory_root,out)
    return out


def abort_job(factory_root: str|Path, job_id: str) -> dict:
    """Permanently abandon a research job after verified worker termination.

    Unlike STOPPED, ABORTED is terminal and intentionally not resumable.
    This is the lifecycle authority behind the UI ABORT action.
    """
    paths=job_paths(factory_root,job_id); job=read_json(paths["job"],{})
    if not job: raise FileNotFoundError(job_id)
    paths["stop"].write_text(utcnow(),encoding="utf-8")
    result=_terminate_worker_tree(factory_root,job,timeout_sec=15.0)
    out=dict(job); out["stop_verification"]=result
    out["pid"]=None if result["terminated"] else (result["alive_after"][0] if result["alive_after"] else job.get("pid"))
    if result["terminated"]:
        out["status"]="ABORTED"
        out["error"]="ABORTED_BY_OPERATOR"
        out["aborted_utc"]=utcnow()
        out["aborted_from_status"]=str(job.get("status") or "")
    else:
        out["status"]="STOP_FAILED"
        out["error"]="ABORT_FAILED_WORKER_STILL_ALIVE"
        out["stop_failed_utc"]=utcnow()
    save_job(factory_root,out)
    return out


def resume_job(factory_root: str|Path, app_dir: str|Path, job_id: str) -> dict:
    with _job_registry_lock(factory_root):
        paths=job_paths(factory_root,job_id); job=load_job(factory_root,job_id)
        if not job: raise FileNotFoundError(job_id)
        status=str(job.get("status") or "")
        recovery=failed_recovery_contract(factory_root,job) if status=="FAILED" else {"recoverable":False}
        if status not in RESUMABLE_STATUSES and not bool(recovery.get("recoverable")):
            reason=str(recovery.get("reason") or "") if status=="FAILED" else ""
            raise RuntimeError(f"Job {job_id} tidak resumable dari state {status}" + (f" · {reason}" if reason else ""))
        other=next((j for j in list_jobs(factory_root) if str(j.get("job_id"))!=str(job_id) and str(j.get("status")) in ACTIVE_STATUSES),None)
        if other:
            raise RuntimeError(f"Tidak dapat RESUME {job_id}; job aktif lain masih berjalan: {other.get('job_id')}")
        alive=_alive_worker_pids(factory_root,job)
        if alive:
            raise RuntimeError(f"Worker lama masih hidup ({alive}); tidak boleh spawn resume kedua")
        for sig in (paths["stop"],paths["pause"]):
            try: sig.unlink()
            except FileNotFoundError: pass
        job=dict(job)
        if status=="FAILED":
            hist=list(job.get("failure_history") or [])
            hist.append({"error":job.get("error"),"traceback":job.get("traceback"),"failed_utc":job.get("updated_utc"),"recovery_contract":recovery})
            job["failure_history"]=hist; job["recovery_contract"]=recovery; job["recovery_state"]="RECOVERY_QUEUED"
        job["status"]="QUEUED"; job["pid"]=None; job["error"]=None; job["traceback"]=None
        job["resume_count"]=int(job.get("resume_count",0) or 0)+1; job["last_resume_utc"]=utcnow()
        save_job(factory_root,job)
        return _spawn_worker(factory_root,app_dir,job,resume=True)
